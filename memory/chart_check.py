import asyncio, re, json
from playwright.async_api import async_playwright

def get_creds():
    txt = open("/app/memory/test_credentials.md").read()
    email = re.search(r"[\w.+-]+@realaicoach\.app", txt).group(0)
    m = re.search(r"(?:password|Password)\s*[:=]?\s*`?([^\s`]+)`?", txt)
    return email, m.group(1)

async def main():
    email, password = get_creds()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        base = "https://full-stack-migrate-1.preview.emergentagent.com"
        await page.goto(f"{base}/auth/login", wait_until="domcontentloaded", timeout=300000)
        await page.wait_for_selector('[data-testid="login-email-input"]', timeout=120000)
        await page.fill('[data-testid="login-email-input"]', email)
        await page.fill('[data-testid="login-password-input"]', password)
        await page.click('[data-testid="login-submit-button"]')
        await page.wait_for_timeout(15000)
        nn = await page.query_selector('text=Not now')
        if nn:
            await nn.click()
            await page.wait_for_timeout(8000)
        me = await page.evaluate("async () => (await fetch('/api/auth/me', {credentials:'include'})).status")
        print("AUTH_ME:", me)
        print("LOGIN_URL:", page.url)

        # Admin console -> SEO dashboard tab (lazy SEODashboardPanel imports recharts directly)
        await page.goto(f"{base}/admin-console?tab=seo-dashboard", wait_until="domcontentloaded", timeout=300000)
        section = None
        for i in range(18):  # up to ~3 min: cold Metro compile of the lazy chunk
            await page.wait_for_timeout(10000)
            svg = await page.evaluate("() => document.querySelectorAll('svg.recharts-surface, .recharts-wrapper').length")
            if svg:
                section = True
                break
        svg_count = await page.evaluate("() => document.querySelectorAll('svg.recharts-surface, .recharts-wrapper').length")
        print("RECHARTS_NODES:", svg_count)
        await page.screenshot(path="/app/memory/admin_chart_check.jpeg", quality=25, type="jpeg")
        print("PAGEERRORS:", errors[:3] if errors else "none")
        await browser.close()

asyncio.run(main())
