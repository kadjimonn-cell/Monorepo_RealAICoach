"""Deep Research Navigator v2 - Comprehensive Backend API Tests

Tests all CRUD operations and critical flows for the research navigator feature:
- Bootstrap workspace
- Project creation/list/get
- Research run orchestration
- Insight board save flow
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)

# Generate unique test user ID for isolation
TEST_USER_ID = f"user_test_rnav_{uuid.uuid4().hex[:12]}"


class TestDeepResearchNavigatorBootstrap:
    """Bootstrap endpoint tests"""

    def test_bootstrap_returns_workspace_state(self):
        """GET /api/research-navigator/bootstrap returns workspace with projects, insights, stats"""
        response = requests.get(
            f"{BASE_URL}/api/research-navigator/bootstrap",
            params={"fallback_user_id": TEST_USER_ID},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "owner_id" in data, "Response should contain owner_id"
        assert "projects" in data, "Response should contain projects array"
        assert "insight_notes" in data, "Response should contain insight_notes array"
        assert "stats" in data, "Response should contain stats object"
        
        # Validate stats structure
        stats = data["stats"]
        assert "project_count" in stats
        assert "insight_count" in stats
        assert "avg_runs_per_project" in stats
        
        # Validate owner_id format
        assert data["owner_id"].startswith("guest:"), f"Guest user should have guest: prefix, got {data['owner_id']}"

    def test_bootstrap_requires_fallback_user_id_for_guest(self):
        """GET /api/research-navigator/bootstrap returns 401 without fallback_user_id"""
        response = requests.get(
            f"{BASE_URL}/api/research-navigator/bootstrap",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error_code"] == "research_nav_auth_required"

    def test_bootstrap_rejects_invalid_guest_id_format(self):
        """GET /api/research-navigator/bootstrap rejects invalid fallback_user_id format"""
        response = requests.get(
            f"{BASE_URL}/api/research-navigator/bootstrap",
            params={"fallback_user_id": "invalid_format"},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error_code"] == "research_nav_invalid_guest_id"


class TestDeepResearchNavigatorProjects:
    """Project CRUD tests"""

    def test_create_project_success(self):
        """POST /api/research-navigator/projects creates a new project"""
        payload = {
            "title": f"TEST_Project_{uuid.uuid4().hex[:8]}",
            "topic": "Enterprise AI strategy research",
            "fallback_user_id": TEST_USER_ID,
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "project" in data, "Response should contain project object"
        
        project = data["project"]
        assert project["title"] == payload["title"]
        assert project["topic"] == payload["topic"]
        assert project["project_id"].startswith("rnav_"), f"Project ID should start with rnav_, got {project['project_id']}"
        assert project["run_count"] == 0
        assert project["last_run_id"] is None
        assert "created_at" in project
        assert "updated_at" in project

    def test_create_project_validates_title_length(self):
        """POST /api/research-navigator/projects validates title min length"""
        payload = {
            "title": "A",  # Too short (min 2)
            "topic": "Test topic",
            "fallback_user_id": TEST_USER_ID,
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 422, f"Expected 422 for validation error, got {response.status_code}"

    def test_list_projects_returns_array(self):
        """GET /api/research-navigator/projects returns projects array"""
        response = requests.get(
            f"{BASE_URL}/api/research-navigator/projects",
            params={"fallback_user_id": TEST_USER_ID},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "projects" in data
        assert isinstance(data["projects"], list)

    def test_get_project_with_runs_and_insights(self):
        """GET /api/research-navigator/projects/{id} returns project with runs and insights"""
        # First create a project
        create_payload = {
            "title": f"TEST_GetProject_{uuid.uuid4().hex[:8]}",
            "topic": "Test topic for get",
            "fallback_user_id": TEST_USER_ID,
        }
        create_response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects",
            json=create_payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert create_response.status_code == 200
        project_id = create_response.json()["project"]["project_id"]
        
        # Get the project
        response = requests.get(
            f"{BASE_URL}/api/research-navigator/projects/{project_id}",
            params={"fallback_user_id": TEST_USER_ID},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "project" in data
        assert "runs" in data
        assert "insight_notes" in data
        assert data["project"]["project_id"] == project_id

    def test_get_project_not_found(self):
        """GET /api/research-navigator/projects/{id} returns 404 for non-existent project"""
        response = requests.get(
            f"{BASE_URL}/api/research-navigator/projects/rnav_nonexistent123",
            params={"fallback_user_id": TEST_USER_ID},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert data["detail"]["error_code"] == "research_nav_project_not_found"


class TestDeepResearchNavigatorRuns:
    """Research run orchestration tests"""

    @pytest.fixture(scope="class")
    def test_project(self):
        """Create a test project for run tests"""
        payload = {
            "title": f"TEST_RunProject_{uuid.uuid4().hex[:8]}",
            "topic": "Research run testing",
            "fallback_user_id": TEST_USER_ID,
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        return response.json()["project"]

    def test_run_research_returns_completed_run(self, test_project):
        """POST /api/research-navigator/projects/{id}/runs executes research and returns completed run"""
        payload = {
            "query": "What are the key trends in enterprise AI adoption in 2026?",
            "fallback_user_id": TEST_USER_ID,
            "idempotency_key": f"test_run_{uuid.uuid4().hex[:8]}",
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/{test_project['project_id']}/runs",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            timeout=60,  # Research runs may take time due to LLM synthesis
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "run" in data, "Response should contain run object"
        
        run = data["run"]
        assert run["run_id"].startswith("run_"), f"Run ID should start with run_, got {run['run_id']}"
        assert run["project_id"] == test_project["project_id"]
        assert run["query"] == payload["query"]
        assert run["status"] == "completed", f"Run status should be completed, got {run['status']}"
        
        # Validate run structure
        assert "steps" in run, "Run should contain steps array"
        assert "sources" in run, "Run should contain sources array"
        assert "answer" in run, "Run should contain answer (synthesis)"
        assert "follow_up_questions" in run, "Run should contain follow_up_questions"
        
        # Validate steps
        steps = run["steps"]
        assert len(steps) == 4, f"Expected 4 steps, got {len(steps)}"
        step_names = [s["step"] for s in steps]
        assert step_names == ["planner", "retriever", "verifier", "synthesizer"]
        
        # Validate sources have required fields
        if run["sources"]:
            source = run["sources"][0]
            assert "source_id" in source
            assert "title" in source
            assert "url" in source
            assert "snippet" in source
            assert "confidence" in source
        
        # Validate follow-ups
        assert len(run["follow_up_questions"]) == 3, "Should have 3 follow-up questions"

    def test_run_research_validates_query_length(self, test_project):
        """POST /api/research-navigator/projects/{id}/runs validates query min length"""
        payload = {
            "query": "Hi",  # Too short (min 3)
            "fallback_user_id": TEST_USER_ID,
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/{test_project['project_id']}/runs",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 422, f"Expected 422 for validation error, got {response.status_code}"

    def test_run_research_project_not_found(self):
        """POST /api/research-navigator/projects/{id}/runs returns 404 for non-existent project"""
        payload = {
            "query": "Test query for non-existent project",
            "fallback_user_id": TEST_USER_ID,
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/rnav_nonexistent123/runs",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    def test_get_run_by_id(self, test_project):
        """GET /api/research-navigator/runs/{id} returns run details"""
        # First create a run
        run_payload = {
            "query": "What is the impact of AI on healthcare?",
            "fallback_user_id": TEST_USER_ID,
            "idempotency_key": f"test_get_run_{uuid.uuid4().hex[:8]}",
        }
        run_response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/{test_project['project_id']}/runs",
            json=run_payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            timeout=60,
        )
        assert run_response.status_code == 200
        run_id = run_response.json()["run"]["run_id"]
        
        # Get the run
        response = requests.get(
            f"{BASE_URL}/api/research-navigator/runs/{run_id}",
            params={"fallback_user_id": TEST_USER_ID},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "run" in data
        assert data["run"]["run_id"] == run_id

    def test_get_run_not_found(self):
        """GET /api/research-navigator/runs/{id} returns 404 for non-existent run"""
        response = requests.get(
            f"{BASE_URL}/api/research-navigator/runs/run_nonexistent123",
            params={"fallback_user_id": TEST_USER_ID},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestDeepResearchNavigatorInsights:
    """Insight board save flow tests"""

    @pytest.fixture(scope="class")
    def insight_project(self):
        """Create a test project for insight tests"""
        payload = {
            "title": f"TEST_InsightProject_{uuid.uuid4().hex[:8]}",
            "topic": "Insight testing",
            "fallback_user_id": TEST_USER_ID,
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        return response.json()["project"]

    def test_add_insight_success(self, insight_project):
        """POST /api/research-navigator/projects/{id}/insights saves insight note"""
        payload = {
            "title": f"TEST_Insight_{uuid.uuid4().hex[:8]}",
            "content": "AI adoption requires strong governance and source transparency. Key finding from research.",
            "fallback_user_id": TEST_USER_ID,
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/{insight_project['project_id']}/insights",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "insight" in data, "Response should contain insight object"
        
        insight = data["insight"]
        assert insight["note_id"].startswith("ins_"), f"Note ID should start with ins_, got {insight['note_id']}"
        assert insight["title"] == payload["title"]
        assert insight["content"] == payload["content"]
        assert insight["project_id"] == insight_project["project_id"]
        assert "created_at" in insight

    def test_add_insight_validates_title_length(self, insight_project):
        """POST /api/research-navigator/projects/{id}/insights validates title min length"""
        payload = {
            "title": "A",  # Too short (min 2)
            "content": "Valid content here",
            "fallback_user_id": TEST_USER_ID,
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/{insight_project['project_id']}/insights",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 422, f"Expected 422 for validation error, got {response.status_code}"

    def test_add_insight_validates_content_length(self, insight_project):
        """POST /api/research-navigator/projects/{id}/insights validates content min length"""
        payload = {
            "title": "Valid Title",
            "content": "AB",  # Too short (min 3)
            "fallback_user_id": TEST_USER_ID,
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/{insight_project['project_id']}/insights",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 422, f"Expected 422 for validation error, got {response.status_code}"

    def test_add_insight_project_not_found(self):
        """POST /api/research-navigator/projects/{id}/insights returns 404 for non-existent project"""
        payload = {
            "title": "Test Insight",
            "content": "Test content for non-existent project",
            "fallback_user_id": TEST_USER_ID,
        }
        response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/rnav_nonexistent123/insights",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    def test_insight_persisted_in_project_get(self, insight_project):
        """Verify insight is persisted and returned in project GET"""
        # Add an insight
        insight_payload = {
            "title": f"TEST_PersistCheck_{uuid.uuid4().hex[:8]}",
            "content": "This insight should be persisted and retrievable.",
            "fallback_user_id": TEST_USER_ID,
        }
        add_response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/{insight_project['project_id']}/insights",
            json=insight_payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert add_response.status_code == 200
        added_note_id = add_response.json()["insight"]["note_id"]
        
        # Get project and verify insight is included
        get_response = requests.get(
            f"{BASE_URL}/api/research-navigator/projects/{insight_project['project_id']}",
            params={"fallback_user_id": TEST_USER_ID},
            headers={"Content-Type": "application/json"},
        )
        assert get_response.status_code == 200
        
        data = get_response.json()
        insight_ids = [n["note_id"] for n in data["insight_notes"]]
        assert added_note_id in insight_ids, f"Added insight {added_note_id} should be in project insights"


class TestDeepResearchNavigatorEndToEnd:
    """End-to-end workflow tests"""

    def test_full_research_workflow(self):
        """Test complete workflow: create project -> run research -> save insight -> verify"""
        unique_id = uuid.uuid4().hex[:8]
        test_user = f"user_test_e2e_{unique_id}"
        
        # Step 1: Create project
        project_payload = {
            "title": f"TEST_E2E_Project_{unique_id}",
            "topic": "End-to-end workflow testing",
            "fallback_user_id": test_user,
        }
        project_response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects",
            json=project_payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert project_response.status_code == 200, f"Project creation failed: {project_response.text}"
        project = project_response.json()["project"]
        project_id = project["project_id"]
        
        # Step 2: Run research
        run_payload = {
            "query": "What are the best practices for AI governance in enterprises?",
            "fallback_user_id": test_user,
            "idempotency_key": f"e2e_run_{unique_id}",
        }
        run_response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/{project_id}/runs",
            json=run_payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            timeout=60,
        )
        assert run_response.status_code == 200, f"Research run failed: {run_response.text}"
        run = run_response.json()["run"]
        assert run["status"] == "completed"
        assert run["answer"], "Run should have synthesized answer"
        
        # Step 3: Save insight based on research
        insight_payload = {
            "title": "Key Finding: AI Governance",
            "content": f"Based on research: {run['answer'][:200]}...",
            "fallback_user_id": test_user,
        }
        insight_response = requests.post(
            f"{BASE_URL}/api/research-navigator/projects/{project_id}/insights",
            json=insight_payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert insight_response.status_code == 200, f"Insight save failed: {insight_response.text}"
        insight = insight_response.json()["insight"]
        assert insight["note_id"].startswith("ins_")
        
        # Step 4: Verify via bootstrap
        bootstrap_response = requests.get(
            f"{BASE_URL}/api/research-navigator/bootstrap",
            params={"fallback_user_id": test_user},
            headers={"Content-Type": "application/json"},
        )
        assert bootstrap_response.status_code == 200
        bootstrap_data = bootstrap_response.json()
        
        # Verify project is in bootstrap
        project_ids = [p["project_id"] for p in bootstrap_data["projects"]]
        assert project_id in project_ids, "Created project should be in bootstrap"
        
        # Verify stats updated
        assert bootstrap_data["stats"]["project_count"] >= 1
        assert bootstrap_data["stats"]["insight_count"] >= 1
