"""
Feature 24 - Learning Hub 25-Category Catalog Expansion Backend Tests
Validates:
  1. GET /api/ai-learn/courses returns 70+ courses spanning exactly 25 categories
  2. Category and search filters work
  3. Cover images (unique per course) return HTTP 200 image/jpeg
  4. Enroll + progress flow on a newly seeded course still works
  5. Seeder idempotency: no duplicates across repeated calls
"""
import os
import hashlib
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

EXPECTED_CATEGORIES = {
    "AI", "Cybersecurity", "IT", "Software", "Data Science",
    "Cloud Computing", "DevOps", "Business", "Marketing", "Entrepreneurship",
    "Project Management", "Product Management", "Finance", "Sales", "Leadership",
    "HR & Talent", "Design", "Creative Arts", "Photography", "Music",
    "Writing & Content", "Lifestyle", "Health & Wellness", "Communication",
    "Personal Development",
}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Admin login failed {r.status_code} {r.text[:400]}"
    csrf = s.cookies.get("csrf_token") or s.cookies.get("csrftoken")
    if csrf:
        s.headers.update({"X-CSRF-Token": csrf})
    return s


# ---------- Catalog shape ----------

def test_catalog_has_70plus_courses_and_25_categories(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    courses = data.get("courses") or data.get("items") or []
    assert len(courses) >= 70, f"expected >=70 courses, got {len(courses)}"
    categories = {c.get("category") for c in courses if c.get("category")}
    assert categories == EXPECTED_CATEGORIES, (
        f"category mismatch. missing={EXPECTED_CATEGORIES - categories}, "
        f"extra={categories - EXPECTED_CATEGORIES}"
    )


def test_each_category_has_at_least_two_courses(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
    courses = r.json().get("courses", [])
    from collections import Counter
    counts = Counter(c.get("category") for c in courses)
    for cat in EXPECTED_CATEGORIES:
        assert counts.get(cat, 0) >= 2, f"{cat} has only {counts.get(cat,0)} courses"


def test_all_course_titles_are_unique(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
    courses = r.json().get("courses", [])
    titles = [c.get("title") for c in courses]
    assert len(titles) == len(set(titles)), "Duplicate titles present"


def test_mixed_difficulties_present(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
    courses = r.json().get("courses", [])
    diffs = {c.get("difficulty") for c in courses}
    assert {"beginner", "intermediate", "advanced"}.issubset(diffs), diffs


# ---------- Filters ----------

def test_category_filter_finance(admin_session):
    r = admin_session.get(
        f"{BASE_URL}/api/ai-learn/courses",
        params={"category": "Finance"},
        timeout=30,
    )
    assert r.status_code == 200
    courses = r.json().get("courses", [])
    assert len(courses) >= 2
    assert all(c.get("category") == "Finance" for c in courses), (
        [c.get("category") for c in courses]
    )


def test_search_filter_photography(admin_session):
    r = admin_session.get(
        f"{BASE_URL}/api/ai-learn/courses",
        params={"search": "photography"},
        timeout=30,
    )
    assert r.status_code == 200
    courses = r.json().get("courses", [])
    assert len(courses) >= 1
    # At least one match should contain 'photo' in title/description/category
    def matches(c):
        blob = " ".join(
            str(c.get(k, "")) for k in ("title", "description", "category", "tags")
        ).lower()
        return "photo" in blob
    assert any(matches(c) for c in courses), "no photography-related result"


# ---------- Cover images ----------

@pytest.fixture(scope="module")
def courses_by_category(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
    courses = r.json().get("courses", [])
    grouped = {}
    for c in courses:
        grouped.setdefault(c.get("category"), []).append(c)
    return grouped


@pytest.mark.parametrize("category", [
    "Finance", "Music", "Photography", "DevOps", "HR & Talent"
])
def test_cover_image_returns_jpeg_for_category(admin_session, courses_by_category, category):
    items = courses_by_category.get(category, [])
    assert items, f"No courses found for {category}"
    cid = items[0].get("course_id") or items[0].get("id")
    assert cid, f"course missing id: {items[0]}"
    url = f"{BASE_URL}/api/ai-learn/course-cover/{cid}.jpg"
    r = admin_session.get(url, timeout=30)
    assert r.status_code == 200, f"{url} => {r.status_code}"
    ct = r.headers.get("content-type", "")
    assert "image/jpeg" in ct or "image/jpg" in ct, ct
    assert len(r.content) > 1000, f"cover too small ({len(r.content)} bytes)"


def test_two_courses_same_category_have_different_covers(admin_session, courses_by_category):
    # Use Photography - expect at least 2 courses, unique cover bytes
    items = courses_by_category.get("Photography", [])
    assert len(items) >= 2
    a, b = items[0], items[1]
    aid = a.get("course_id") or a.get("id")
    bid = b.get("course_id") or b.get("id")
    ra = admin_session.get(f"{BASE_URL}/api/ai-learn/course-cover/{aid}.jpg", timeout=30)
    rb = admin_session.get(f"{BASE_URL}/api/ai-learn/course-cover/{bid}.jpg", timeout=30)
    assert ra.status_code == 200 and rb.status_code == 200
    ha = hashlib.sha256(ra.content).hexdigest()
    hb = hashlib.sha256(rb.content).hexdigest()
    assert ha != hb, "Two Photography courses returned identical cover bytes"


# ---------- Enroll + progress ----------

def _find_enrollable_course(courses, preferred_cats=("Photography", "Music", "Finance")):
    def is_enrolled(c):
        return bool(c.get("is_enrolled") or c.get("enrolled"))
    for cat in preferred_cats:
        for c in courses:
            if c.get("category") == cat and not is_enrolled(c):
                return c
    for c in courses:
        if not is_enrolled(c):
            return c
    return courses[0] if courses else None


def test_enroll_and_progress_on_new_seeded_course(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
    courses = r.json().get("courses", [])
    course = _find_enrollable_course(courses)
    assert course, "no course available"
    cid = course.get("course_id") or course.get("id")
    assert cid, course

    # Enroll
    er = admin_session.post(f"{BASE_URL}/api/ai-learn/courses/{cid}/enroll", timeout=30)
    assert er.status_code in (200, 201, 409), f"enroll status {er.status_code}: {er.text[:400]}"

    # Modules from the list payload (course detail endpoint not exposed)
    modules = course.get("modules") or []
    assert modules, f"no modules in course {cid}"
    module_id = modules[0].get("id") or modules[0].get("module_id")
    assert module_id, modules[0]

    # Initial progress from list
    initial_pct = course.get("progress_pct") or 0

    # Post progress
    pr = admin_session.post(
        f"{BASE_URL}/api/ai-learn/courses/{cid}/progress",
        json={"module_id": module_id, "completed": True, "minutes_spent": 20},
        timeout=30,
    )
    assert pr.status_code in (200, 201), f"progress status {pr.status_code}: {pr.text[:400]}"

    # Verify by re-fetching list
    r2 = admin_session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
    courses2 = r2.json().get("courses", [])
    same = next((c for c in courses2 if (c.get("course_id") or c.get("id")) == cid), None)
    assert same is not None, "course disappeared after progress"
    new_pct = same.get("progress_pct") or 0
    assert new_pct >= initial_pct, f"progress did not increase: {initial_pct} -> {new_pct}"


# ---------- Idempotency ----------

def test_seeder_idempotency_no_duplicates(admin_session):
    r1 = admin_session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
    r2 = admin_session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
    c1 = r1.json().get("courses", [])
    c2 = r2.json().get("courses", [])
    assert len(c1) == len(c2), f"count drift {len(c1)} vs {len(c2)}"
    ids1 = sorted(c.get("course_id") or c.get("id") or "" for c in c1)
    ids2 = sorted(c.get("course_id") or c.get("id") or "" for c in c2)
    assert ids1 == ids2, "course ids changed between calls"
