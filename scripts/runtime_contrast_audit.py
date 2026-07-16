import asyncio, json
from playwright.async_api import async_playwright

BASE = "http://localhost:3000"
PUBLIC_ROUTES = ["/welcome", "/pricing", "/gdpr", "/security", "/careers", "/blog", "/talent-network"]
USER_ROUTES = [
    "/dashboard", "/ai-learning-hub", "/ai-briefing", "/content-library", "/achievements",
    "/calendar", "/session-history", "/progress", "/leaderboard", "/edit-profile",
    "/subscription", "/book-meeting", "/ai-coaching-team", "/job-search", "/hiring-hub",
    "/messages", "/feedback", "/integrations", "/certificate-gallery", "/features",
    "/ai-problem-solver", "/settings",
]
ADMIN_ROUTES = [
    "/executive-dashboard", "/admin-system", "/performance-observability", "/route-health-report",
    "/email-templates-admin", "/admin-activity-log",
]

AUDIT_JS = """() => {
  const relLum = (r,g,b) => { const f=c=>{c/=255; return c<=0.03928?c/12.92:Math.pow((c+0.055)/1.055,2.4)}; return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b); };
  const parse = (s) => { const m = String(s||'').match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/); return m?{r:+m[1],g:+m[2],b:+m[3],a:m[4]===undefined?1:+m[4]}:null; };
  const effBg = (el) => { let e=el; while(e){ const c=parse(getComputedStyle(e).backgroundColor); if(c&&c.a>0.5) return c; e=e.parentElement; } return parse(getComputedStyle(document.body).backgroundColor)||{r:255,g:255,b:255}; };
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const t = walker.currentNode; const txt = (t.textContent||'').trim();
    if (txt.length < 2) continue;
    const el = t.parentElement; if (!el || seen.has(el)) continue; seen.add(el);
    const r = el.getBoundingClientRect(); if (r.width===0||r.height===0) continue;
    // skip offscreen/sr-only
    if (r.bottom < 0 || r.top > window.innerHeight + 2200 || r.right < 0) continue;
    const st = getComputedStyle(el);
    if (st.visibility==='hidden' || +st.opacity < 0.3 || st.clipPath === 'inset(100%)' || (r.width<=1&&r.height<=1)) continue;
    const isSvg = el.namespaceURI && el.namespaceURI.includes('svg');
    const fg = isSvg ? (parse(st.fill) || parse(st.color)) : parse(st.color);
    if (!fg || fg.a < 0.3) continue;
    const bg = effBg(el);
    const l1 = relLum(fg.r,fg.g,fg.b), l2 = relLum(bg.r,bg.g,bg.b);
    const cr = (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
    if (cr < 2.0) out.push({txt: txt.slice(0,60), cr: +cr.toFixed(2), fg: isSvg?st.fill:st.color, bg: `rgb(${bg.r},${bg.g},${bg.b})`, tid: (el.closest('[data-testid]')||{getAttribute:()=>''}).getAttribute('data-testid')||''});
  }
  return out;
}"""

async def dismiss(page):
    try:
        loc = page.locator('button:has-text("Not now")')
        if await loc.count() > 0:
            await loc.first.click(force=True, timeout=2000)
            await page.wait_for_timeout(300)
    except Exception:
        pass

async def login(page, email, pwd):
    for attempt in range(3):
        await page.goto(BASE + "/auth/login", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        await dismiss(page)
        try:
            await page.locator('input[type="email"], input[placeholder*="mail" i]').first.fill(email)
            await page.locator('input[type="password"]').first.fill(pwd)
            await dismiss(page)
            await page.locator('[data-testid="login-form-submit-button"], button:has-text("SIGN IN")').first.click(force=True)
        except Exception as e:
            print("login form error:", e, flush=True)
            continue
        for _ in range(20):
            await page.wait_for_timeout(1000)
            await dismiss(page)
            if "auth/login" not in page.url:
                return True
        print(f"login attempt {attempt+1} failed, url={page.url}", flush=True)
    return False

async def set_mode(page, mode):
    try:
        await page.wait_for_selector(f'[data-testid="theme-toggle-{mode}"]', timeout=12000)
        await page.locator(f'[data-testid="theme-toggle-{mode}"]').first.click(force=True)
        await page.wait_for_timeout(1200)
        return True
    except Exception:
        return False

async def audit_route(page, route, mode, tag, out):
    try:
        await page.goto(BASE + route, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(7000)
        landed = page.url.replace(BASE, "")
        redirected = (route.rstrip('/') not in landed)
        dedupe = set()
        n = 0
        for scroll in range(5):
            res = await page.evaluate(AUDIT_JS)
            for f in res:
                k = (f["txt"], f["fg"], f["bg"])
                if k in dedupe: continue
                dedupe.add(k)
                f.update({"route": route, "landed": landed, "mode": mode, "who": tag})
                out.append(f); n += 1
            await page.mouse.wheel(0, 1400)
            await page.wait_for_timeout(800)
        print(f"[{tag}] {mode} {route} -> landed={landed} redirected={redirected} issues={n}", flush=True)
    except Exception as e:
        print(f"[{tag}] {mode} {route} ERROR {str(e)[:100]}", flush=True)

async def run(email, pwd, routes, tag, out, public_first=False):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1920, "height": 900})
        page = await ctx.new_page()
        if public_first:
            for mode in ["dark", "light"]:
                await page.goto(BASE + "/welcome", wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3000)
                await set_mode(page, mode)
                for route in PUBLIC_ROUTES:
                    await audit_route(page, route, mode, "public", out)
        if email:
            ok = await login(page, email, pwd)
            print(f"[{tag}] login ok={ok}", flush=True)
            if ok:
                for mode in ["dark", "light"]:
                    await page.goto(BASE + "/dashboard", wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(4000)
                    ms = await set_mode(page, mode)
                    print(f"[{tag}] mode {mode} set={ms}", flush=True)
                    for route in routes:
                        await audit_route(page, route, mode, tag, out)
        await browser.close()

async def main():
    out = []
    await run("p1.free.1779113329@example.com", "P1Free#2026!Aa", USER_ROUTES, "user", out, public_first=True)
    await run("admin@realaicoach.app", "NewAdminPass2026!", ADMIN_ROUTES, "admin", out)
    json.dump(out, open("/app/memory/runtime_contrast_audit.json", "w"), indent=1)
    print(f"TOTAL unique findings: {len(out)}")

asyncio.run(main())
