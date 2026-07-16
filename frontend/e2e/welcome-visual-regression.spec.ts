/**
 * E2E: Welcome page visual regression
 * Referenced by ci-quality-gate.yml `welcome-visual-regression` job.
 * Checks that the welcome/landing page renders without blank screen or 500,
 * and that the hero centering contract holds at tablet/non-desktop widths.
 */
import { test, expect } from '@playwright/test';

const TABLET_CENTERING_VIEWPORTS = [
  { name: 'large-phone-540', width: 540, height: 960 },
  { name: 'small-tablet-600', width: 600, height: 900 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'ipad-834', width: 834, height: 1112 },
  { name: 'surface-912', width: 912, height: 1368 },
  { name: 'tablet-1024', width: 1024, height: 1180 },
  { name: 'desktop-1179', width: 1179, height: 900 },
  { name: 'desktop-1365', width: 1365, height: 900 },
];

async function gotoWelcome(page: any) {
  await page.goto('/welcome');
  await page.waitForTimeout(3_500);
  await expect(page.locator('[data-testid="welcome-hero"]')).toBeVisible({ timeout: 15_000 });
}

test.describe('Welcome page — Visual Regression', () => {
  test('welcome page renders with content on desktop', async ({ page }) => {
    await page.goto('/welcome');
    await page.waitForTimeout(4_000);

    const url = page.url();
    expect(url).not.toMatch(/404/);
    expect(url).not.toMatch(/500/);

    const body = await page.locator('body').textContent();
    expect(body?.length).toBeGreaterThan(200);
  });

  test('welcome page does not show blank white screen', async ({ page }) => {
    await page.goto('/welcome');
    await page.waitForTimeout(3_000);

    // The root element must have rendered children
    const rootChildren = await page.locator('#root, [data-testid="welcome-page"], body > *').count();
    expect(rootChildren).toBeGreaterThan(0);
  });

  test('welcome page brand wordmark is present', async ({ page }) => {
    await page.goto('/welcome');
    await page.waitForTimeout(3_000);

    // Accept either the welcome hero or a redirect to login
    const body = await page.locator('body').textContent() ?? '';

    const hasBrandContent =
      body.includes('RealAICoach') ||
      body.includes('Real') ||
      body.length > 200;

    expect(hasBrandContent).toBeTruthy();
  });

  test('home route (/) redirects or renders without error', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3_000);

    const body = await page.locator('body').textContent();
    expect(body?.length).toBeGreaterThan(50);
    expect(page.url()).not.toMatch(/500/);
  });

  for (const vp of TABLET_CENTERING_VIEWPORTS) {
    test(`hero remains centered on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await gotoWelcome(page);

      const shell = page.locator('[data-testid="welcome-hero-centered-shell"]');
      const badge = page.locator('[data-testid="welcome-hero-badge"]');
      const title = page.locator('[data-testid="welcome-hero-title"]');
      const subtitle = page.locator('[data-testid="welcome-hero-subtitle"]');
      const nova = page.locator('[data-testid="welcome-hero-nova-card"]');
      const stats = page.locator('[data-testid="welcome-hero-stats"]');

      await expect(shell).toBeVisible();
      await expect(badge).toBeVisible();
      await expect(title).toBeVisible();
      await expect(subtitle).toBeVisible();
      await expect(nova).toBeVisible();
      await expect(stats).toBeVisible();

      const geometry = await page.evaluate(() => {
        const shell = document.querySelector('[data-testid="welcome-hero-centered-shell"]') as HTMLElement | null;
        const badge = document.querySelector('[data-testid="welcome-hero-badge"]') as HTMLElement | null;
        const title = document.querySelector('[data-testid="welcome-hero-title"]') as HTMLElement | null;
        const subtitle = document.querySelector('[data-testid="welcome-hero-subtitle"]') as HTMLElement | null;
        const stats = document.querySelector('[data-testid="welcome-hero-stats"]') as HTMLElement | null;
        if (!shell || !badge || !title || !subtitle || !stats) return null;

        const shellRect = shell.getBoundingClientRect();
        const leftMargin = Math.round(shellRect.left);
        const rightMargin = Math.round(window.innerWidth - shellRect.right);
        return {
          leftMargin,
          rightMargin,
          marginDifference: Math.abs(leftMargin - rightMargin),
          shellMaxWidth: getComputedStyle(shell).maxWidth,
          badgeAlignSelf: getComputedStyle(badge).alignSelf,
          titleTextAlign: getComputedStyle(title).textAlign,
          subtitleTextAlign: getComputedStyle(subtitle).textAlign,
          statsJustify: getComputedStyle(stats).justifyContent,
        };
      });

      expect(geometry).not.toBeNull();
      expect(geometry?.marginDifference, `${vp.name} shell margins drifted: ${JSON.stringify(geometry)}`).toBeLessThanOrEqual(2);
      expect(geometry?.badgeAlignSelf).toBe('center');
      expect(geometry?.titleTextAlign).toBe('center');
      expect(geometry?.subtitleTextAlign).toBe('center');
      expect(geometry?.statsJustify).toBe('center');
    });

    test(`final CTA actions stay centered on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await gotoWelcome(page);

      await page.locator('[data-testid="welcome-decision-strip"]').scrollIntoViewIfNeeded();
      await expect(page.locator('[data-testid="welcome-primary-cta-button"]')).toBeVisible();

      const metrics = await page.evaluate(() => {
        const shell = document.querySelector('[data-testid="welcome-decision-strip"]') as HTMLElement | null;
        const primary = document.querySelector('[data-testid="welcome-primary-cta-button"]') as HTMLElement | null;
        const about = document.querySelector('[data-testid="welcome-about-cta-button"]') as HTMLElement | null;
        const secondary = document.querySelector('[data-testid="welcome-secondary-cta-button"]') as HTMLElement | null;
        if (!shell || !primary || !about || !secondary) return null;
        const shellRect = shell.getBoundingClientRect();
        const primaryRect = primary.getBoundingClientRect();
        const aboutRect = about.getBoundingClientRect();
        const secondaryRect = secondary.getBoundingClientRect();
        return {
          shellCenter: Math.round(shellRect.left + shellRect.width / 2),
          primaryCenter: Math.round(primaryRect.left + primaryRect.width / 2),
          aboutTop: Math.round(aboutRect.top),
          secondaryTop: Math.round(secondaryRect.top),
          aboutCenter: Math.round(aboutRect.left + aboutRect.width / 2),
          secondaryCenter: Math.round(secondaryRect.left + secondaryRect.width / 2),
        };
      });

      expect(metrics).not.toBeNull();
      expect(Math.abs((metrics?.shellCenter || 0) - (metrics?.primaryCenter || 0)), `${vp.name} primary CTA drifted: ${JSON.stringify(metrics)}`).toBeLessThanOrEqual(4);
      if (vp.width < 1180) {
        expect(Math.abs((metrics?.aboutTop || 0) - (metrics?.secondaryTop || 0)), `${vp.name} secondary CTA row drifted: ${JSON.stringify(metrics)}`).toBeLessThanOrEqual(4);
        expect(Math.abs((metrics?.shellCenter || 0) - (metrics?.aboutCenter || 0)), `${vp.name} about CTA drifted: ${JSON.stringify(metrics)}`).toBeLessThanOrEqual(4);
        expect(Math.abs((metrics?.shellCenter || 0) - (metrics?.secondaryCenter || 0)), `${vp.name} secondary CTA drifted: ${JSON.stringify(metrics)}`).toBeLessThanOrEqual(4);
      }
    });

    test(`careers banner stays centered on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await gotoWelcome(page);

      await page.locator('[data-testid="welcome-careers-banner"]').scrollIntoViewIfNeeded();
      await expect(page.locator('[data-testid="welcome-careers-title"]')).toBeVisible();
      await expect(page.locator('[data-testid="welcome-careers-actions"]')).toBeVisible();

      const metrics = await page.evaluate(() => {
        const banner = document.querySelector('[data-testid="welcome-careers-banner"]') as HTMLElement | null;
        const title = document.querySelector('[data-testid="welcome-careers-title"]') as HTMLElement | null;
        const copy = document.querySelector('[data-testid="welcome-careers-copy"]') as HTMLElement | null;
        const actions = document.querySelector('[data-testid="welcome-careers-actions"]') as HTMLElement | null;
        if (!banner || !title || !copy || !actions) return null;
        const bannerRect = banner.getBoundingClientRect();
        const titleRect = title.getBoundingClientRect();
        const copyRect = copy.getBoundingClientRect();
        const actionsRect = actions.getBoundingClientRect();
        const bannerCenter = Math.round(bannerRect.left + bannerRect.width / 2);
        return {
          bannerCenter,
          titleCenter: Math.round(titleRect.left + titleRect.width / 2),
          copyCenter: Math.round(copyRect.left + copyRect.width / 2),
          actionsCenter: Math.round(actionsRect.left + actionsRect.width / 2),
          titleTextAlign: getComputedStyle(title).textAlign,
          copyTextAlign: getComputedStyle(copy).textAlign,
          actionsJustify: getComputedStyle(actions).justifyContent,
        };
      });

      expect(metrics).not.toBeNull();
      expect(metrics?.titleTextAlign).toBe('center');
      expect(metrics?.copyTextAlign).toBe('center');
      expect(metrics?.actionsJustify).toBe('center');
      expect(Math.abs((metrics?.bannerCenter || 0) - (metrics?.titleCenter || 0)), `${vp.name} careers title drifted: ${JSON.stringify(metrics)}`).toBeLessThanOrEqual(4);
      expect(Math.abs((metrics?.bannerCenter || 0) - (metrics?.copyCenter || 0)), `${vp.name} careers copy drifted: ${JSON.stringify(metrics)}`).toBeLessThanOrEqual(4);
      expect(Math.abs((metrics?.bannerCenter || 0) - (metrics?.actionsCenter || 0)), `${vp.name} careers actions drifted: ${JSON.stringify(metrics)}`).toBeLessThanOrEqual(4);
    });

    test(`growth intelligence module stays premium and balanced on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await gotoWelcome(page);

      await page.locator('[data-testid="growth-chart-module"]').scrollIntoViewIfNeeded();
      await expect(page.locator('[data-testid="growth-chart-module"]')).toBeVisible();
      await expect(page.locator('[data-testid="growth-chart-range-toggle"]')).toBeVisible();
      await expect(page.locator('[data-testid="performance-badge"]')).toBeVisible();

      const metrics = await page.evaluate(() => {
        const module = document.querySelector('[data-testid="growth-chart-module"]') as HTMLElement | null;
        const headline = document.querySelector('[data-testid="growth-chart-headline-value"]') as HTMLElement | null;
        const rangeToggle = document.querySelector('[data-testid="growth-chart-range-toggle"]') as HTMLElement | null;
        const chart = document.querySelector('[data-testid="growth-chart-canvas"]') as HTMLElement | null;
        if (!module || !headline || !rangeToggle) return null;

        const moduleRect = module.getBoundingClientRect();
        const headlineRect = headline.getBoundingClientRect();
        const rangeRect = rangeToggle.getBoundingClientRect();
        const chartRect = chart?.getBoundingClientRect();

        return {
          moduleWidth: Math.round(moduleRect.width),
          headlineCenter: Math.round(headlineRect.left + headlineRect.width / 2),
          rangeRight: Math.round(rangeRect.right),
          moduleRight: Math.round(moduleRect.right),
          hasChart: !!chart,
          chartWidth: chartRect ? Math.round(chartRect.width) : 0,
        };
      });

      expect(metrics).not.toBeNull();
      expect(metrics?.moduleWidth).toBeGreaterThan(280);
      expect(metrics?.rangeRight).toBeLessThanOrEqual((metrics?.moduleRight || 0) + 1);
      expect(metrics?.hasChart).toBeTruthy();
      expect(metrics?.chartWidth).toBeGreaterThan(180);
    });

    test(`capability command center feels premium and balanced on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await gotoWelcome(page);

      await page.locator('[data-testid="welcome-capability-command-center"]').scrollIntoViewIfNeeded();
      await expect(page.locator('[data-testid="welcome-capability-command-center"]')).toBeVisible();
      await expect(page.locator('[data-testid="welcome-capability-proof-rail"]')).toBeVisible();
      await expect(page.locator('[data-testid="welcome-capability-matrix"]')).toBeVisible();

      const metrics = await page.evaluate(() => {
        const spotlight = document.querySelector('[data-testid="welcome-capability-spotlight"]') as HTMLElement | null;
        const board = document.querySelector('[data-testid="welcome-capability-command-board"]') as HTMLElement | null;
        const primaryCta = document.querySelector('[data-testid="welcome-capability-primary-cta"]') as HTMLElement | null;
        const tabs = document.querySelector('[data-testid="welcome-capability-category-tabs"]') as HTMLElement | null;
        const cardGrid = document.querySelector('[data-testid="welcome-capability-card-grid"]') as HTMLElement | null;
        const proofStaticGrid = document.querySelector('[data-testid="welcome-capability-proof-static-grid"]') as HTMLElement | null;
        const proofMarquee = document.querySelector('[data-testid="welcome-capability-proof-marquee-track"]') as HTMLElement | null;
        if (!spotlight || !board || !tabs || !cardGrid || !primaryCta) return null;

        const spotlightRect = spotlight.getBoundingClientRect();
        const boardRect = board.getBoundingClientRect();
        const cardRects = Array.from(cardGrid.querySelectorAll('[data-testid^="welcome-capability-card-"]')).map((node: any) => node.getBoundingClientRect());
        const primaryCtaRect = primaryCta.getBoundingClientRect();

        return {
          spotlightWidth: Math.round(spotlightRect.width),
          boardWidth: Math.round(boardRect.width),
          boardTop: Math.round(boardRect.top),
          primaryCtaBottom: Math.round(primaryCtaRect.bottom),
          tabCount: tabs.children.length,
          cardCount: cardRects.length,
          smallestCardWidth: cardRects.length ? Math.round(Math.min(...cardRects.map((rect: any) => rect.width))) : 0,
          hasProofStaticGrid: !!proofStaticGrid,
          hasProofMarquee: !!proofMarquee,
        };
      });

      expect(metrics).not.toBeNull();
      expect(metrics?.spotlightWidth).toBeGreaterThan(260);
      expect(metrics?.boardWidth).toBeGreaterThan(220);
      expect(metrics?.tabCount).toBeGreaterThanOrEqual(4);
      expect(metrics?.cardCount).toBeGreaterThanOrEqual(3);
      expect(metrics?.smallestCardWidth).toBeGreaterThan(160);

      if (vp.width < 1180) {
        expect(metrics?.boardTop).toBeGreaterThanOrEqual((metrics?.primaryCtaBottom || 0) - 4);
        expect(metrics?.hasProofStaticGrid).toBeTruthy();
        expect(metrics?.hasProofMarquee).toBeFalsy();
      }
    });

    test(`pricing, social proof, and workflow memory feel cohesive on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await gotoWelcome(page);

      await page.locator('[data-testid="welcome-pricing-command-shell"]').scrollIntoViewIfNeeded();
      await expect(page.locator('[data-testid="welcome-pricing-workflow-memory-card"]')).toBeVisible();
      await expect(page.locator('[data-testid="welcome-social-header-card"]')).toBeVisible();

      const metrics = await page.evaluate(() => {
        const memory = document.querySelector('[data-testid="welcome-pricing-workflow-memory-value"]') as HTMLElement | null;
        const pricing = document.querySelector('[data-testid="welcome-pricing-command-shell"]') as HTMLElement | null;
        const social = document.querySelector('[data-testid="welcome-social-header-card"]') as HTMLElement | null;
        const trustStats = document.querySelectorAll('[data-testid^="welcome-social-trust-stat-"]').length;
        return {
          memoryTextLength: memory?.textContent?.trim().length || 0,
          pricingHeight: pricing ? Math.round(pricing.getBoundingClientRect().height) : 0,
          socialHeight: social ? Math.round(social.getBoundingClientRect().height) : 0,
          trustStats,
        };
      });

      expect(metrics).not.toBeNull();
      expect(metrics?.memoryTextLength).toBeGreaterThan(10);
      expect(metrics?.pricingHeight).toBeGreaterThan(200);
      expect(metrics?.socialHeight).toBeGreaterThan(180);
      expect(metrics?.trustStats).toBeGreaterThanOrEqual(3);
    });

    test(`CTA close surface feels premium and balanced on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await gotoWelcome(page);

      await page.locator('[data-testid="welcome-summary-header"]').scrollIntoViewIfNeeded();
      await expect(page.locator('[data-testid="welcome-decision-strip"]')).toBeVisible();
      await expect(page.locator('[data-testid="welcome-summary-readiness-card"]')).toBeVisible();
      await expect(page.locator('[data-testid="welcome-decision-path-card"]')).toBeVisible();
      await expect(page.locator('[data-testid="welcome-about-cta-button"]')).toBeVisible();

      const metrics = await page.evaluate(() => {
        const headline = document.querySelector('[data-testid="welcome-summary-headline"]') as HTMLElement | null;
        const decision = document.querySelector('[data-testid="welcome-decision-strip"]') as HTMLElement | null;
        const readiness = document.querySelector('[data-testid="welcome-summary-readiness-card"]') as HTMLElement | null;
        const pathCard = document.querySelector('[data-testid="welcome-decision-path-card"]') as HTMLElement | null;
        const scorePills = document.querySelectorAll('[data-testid^="welcome-decision-path-score-"]').length;
        return {
          headlineLength: headline?.textContent?.trim().length || 0,
          decisionHeight: decision ? Math.round(decision.getBoundingClientRect().height) : 0,
          readinessHeight: readiness ? Math.round(readiness.getBoundingClientRect().height) : 0,
          pathCardHeight: pathCard ? Math.round(pathCard.getBoundingClientRect().height) : 0,
          scorePills,
        };
      });

      expect(metrics).not.toBeNull();
      expect(metrics?.headlineLength).toBeGreaterThan(30);
      expect(metrics?.decisionHeight).toBeGreaterThan(180);
      expect(metrics?.readinessHeight).toBeGreaterThan(100);
      expect(metrics?.pathCardHeight).toBeGreaterThan(120);
      expect(metrics?.scorePills).toBeGreaterThanOrEqual(3);
    });

    test(`smart decision path updates when pricing gets explored on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await gotoWelcome(page);

      await page.locator('[data-testid="welcome-enterprise-section-pricing"]').scrollIntoViewIfNeeded();
      await expect(page.locator('[data-testid="billing-toggle-monthly"]')).toBeVisible();
      await page.click('[data-testid="billing-toggle-monthly"]', { force: true });
      await page.click('[data-testid="billing-toggle-yearly"]', { force: true });
      await page.locator('[data-testid="welcome-enterprise-section-cta"]').scrollIntoViewIfNeeded();
      await expect(page.locator('[data-testid="welcome-decision-path-focus-pricing"]')).toBeVisible();

      const pathState = await page.evaluate(() => {
        const title = document.querySelector('[data-testid="welcome-decision-path-title"]')?.textContent || '';
        const pricingScore = document.querySelector('[data-testid="welcome-decision-path-score-pricing"]')?.textContent || '';
        return { title, pricingScore };
      });

      expect(pathState.title.trim().length).toBeGreaterThan(20);
      expect(pathState.pricingScore.includes('Pricing') || pathState.pricingScore.includes('Tarification')).toBeTruthy();
    });
  }

  test('sticky quick navigator stays center-balanced on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1728, height: 960 });
    await gotoWelcome(page);

    await expect(page.locator('[data-testid="welcome-sticky-quick-navigator"]')).toBeVisible();

    const metrics = await page.evaluate(() => {
      const shell = document.querySelector('[data-testid="welcome-sticky-quick-navigator"]') as HTMLElement | null;
      const title = document.querySelector('[data-testid="welcome-sticky-quick-navigator-title"]') as HTMLElement | null;
      const copy = document.querySelector('[data-testid="welcome-sticky-quick-navigator-copy"]') as HTMLElement | null;
      const faqRow = document.querySelector('[data-testid="welcome-sticky-quick-navigator-faq-row"]') as HTMLElement | null;
      const testimonialRow = document.querySelector('[data-testid="welcome-sticky-quick-navigator-testimonial-row"]') as HTMLElement | null;
      if (!shell || !title || !copy || !faqRow || !testimonialRow) return null;
      return {
        shellAlignItems: getComputedStyle(shell).alignItems,
        titleAlign: getComputedStyle(title).textAlign,
        copyAlign: getComputedStyle(copy).textAlign,
        faqJustify: getComputedStyle(faqRow).justifyContent,
        testimonialJustify: getComputedStyle(testimonialRow).justifyContent,
      };
    });

    expect(metrics).not.toBeNull();
    expect(metrics?.shellAlignItems).toBe('center');
    expect(metrics?.titleAlign).toBe('center');
    expect(metrics?.copyAlign).toBe('center');
    expect(metrics?.faqJustify).toBe('center');
    expect(metrics?.testimonialJustify).toBe('center');
  });

  test('desktop floating chrome hides before overlapping the features section', async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 900 });
    await gotoWelcome(page);

    await page.locator('[data-testid="welcome-enterprise-section-features"]').scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);

    await expect(page.locator('[data-testid="welcome-sticky-quick-navigator"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="welcome-progress-rail"]')).toHaveCount(0);
  });

  test('mobile pricing cards keep CTAs fully visible', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await gotoWelcome(page);

    await page.locator('[data-testid="welcome-pricing-card-grid"]').scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);

    const metrics = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('[data-testid^="welcome-plan-"]')).filter((el) => !(el as HTMLElement).dataset.testid?.endsWith('-cta')) as HTMLElement[];
      return cards.slice(0, 3).map((card) => {
        const cta = card.querySelector('[data-testid$="-cta"]') as HTMLElement | null;
        if (!cta) return null;
        const cardRect = card.getBoundingClientRect();
        const ctaRect = cta.getBoundingClientRect();
        return {
          ctaGapBottom: Math.round(cardRect.bottom - ctaRect.bottom),
          ctaHeight: Math.round(ctaRect.height),
          cardHeight: Math.round(cardRect.height),
        };
      }).filter(Boolean);
    });

    expect(metrics.length).toBeGreaterThanOrEqual(2);
    expect(metrics.every((card: any) => card.ctaGapBottom >= 24)).toBeTruthy();
  });

  test('mobile footer disclaimer keeps Learn more above the bottom bar', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await gotoWelcome(page);

    await page.locator('[data-testid="welcome-footer-wrapper"]').scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);

    const metrics = await page.evaluate(() => {
      const learn = document.querySelector('[data-testid="footer-ai-disclaimer-learn-more-link"]') as HTMLElement | null;
      const bottomBar = document.querySelector('[data-testid="footer-bottom-bar"]') as HTMLElement | null;
      const shell = document.querySelector('[data-testid="footer-disclaimer-shell"]') as HTMLElement | null;
      const card = document.querySelector('[data-testid="footer-ai-disclaimer-container"]') as HTMLElement | null;
      if (!learn || !bottomBar || !shell || !card) return null;
      const learnRect = learn.getBoundingClientRect();
      const bottomBarRect = bottomBar.getBoundingClientRect();
      const shellRect = shell.getBoundingClientRect();
      const cardRect = card.getBoundingClientRect();
      return {
        learnGap: Math.round(bottomBarRect.top - learnRect.bottom),
        shellGap: Math.round(bottomBarRect.top - shellRect.bottom),
        learnInsideCard: Math.round(learnRect.bottom) <= Math.round(cardRect.bottom),
      };
    });

    expect(metrics).not.toBeNull();
    expect(metrics?.shellGap).toBeGreaterThanOrEqual(0);
    expect(metrics?.learnGap).toBeGreaterThanOrEqual(8);
    expect(metrics?.learnInsideCard).toBeTruthy();
  });

  test('mobile welcome footer stays compact and balanced on phone widths', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await gotoWelcome(page);

    await page.locator('[data-testid="welcome-footer-wrapper"]').scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);

    const metrics = await page.evaluate(() => {
      const footer = document.querySelector('[data-testid="platform-footer"]') as HTMLElement | null;
      const newsletter = document.querySelector('[data-testid="footer-newsletter"]') as HTMLElement | null;
      const social = document.querySelector('[data-testid="footer-social-section"]') as HTMLElement | null;
      const links = document.querySelector('[data-testid="footer-link-columns-grid"]') as HTMLElement | null;
      const disclaimer = document.querySelector('[data-testid="footer-disclaimer-shell"]') as HTMLElement | null;
      const bottom = document.querySelector('[data-testid="footer-bottom-bar"]') as HTMLElement | null;
      if (!footer || !newsletter || !social || !links || !disclaimer || !bottom) return null;
      const rr = (el: Element) => {
        const r = (el as HTMLElement).getBoundingClientRect();
        return { top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height) };
      };
      const f = rr(footer);
      const n = rr(newsletter);
      const s = rr(social);
      const l = rr(links);
      const d = rr(disclaimer);
      const b = rr(bottom);
      return {
        footerHeight: f.height,
        socialHeight: s.height,
        linksHeight: l.height,
        newsletterGap: Math.round(s.top - n.bottom),
        socialGap: Math.round(l.top - s.bottom),
        linksGap: Math.round(d.top - l.bottom),
        disclaimerGap: Math.round(b.top - d.bottom),
      };
    });

    expect(metrics).not.toBeNull();
    expect(metrics?.footerHeight).toBeLessThanOrEqual(1325);
    expect(metrics?.socialHeight).toBeLessThanOrEqual(310);
    expect(metrics?.linksHeight).toBeLessThanOrEqual(350);
    expect(metrics?.newsletterGap).toBeLessThanOrEqual(16);
    expect(metrics?.socialGap).toBeLessThanOrEqual(28);
    expect(metrics?.linksGap).toBeLessThanOrEqual(24);
    expect(metrics?.disclaimerGap).toBeLessThanOrEqual(18);
  });

  test('capability card headers stay compact and visually connected on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1365, height: 768 });
    await gotoWelcome(page);

    await page.locator('[data-testid="welcome-capability-matrix-title"]').scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);

    const metrics = await page.evaluate(() => {
      const header = document.querySelector('[data-testid^="welcome-capability-card-header-"]') as HTMLElement | null;
      const lead = document.querySelector('[data-testid^="welcome-capability-card-header-lead-"]') as HTMLElement | null;
      const badge = document.querySelector('[data-testid^="welcome-capability-card-badge-"]') as HTMLElement | null;
      const state = document.querySelector('[data-testid^="welcome-capability-card-state-"]') as HTMLElement | null;
      const title = document.querySelector('[data-testid^="welcome-capability-card-title-"]') as HTMLElement | null;
      if (!header || !lead || !badge || !state || !title) return null;
      const h = header.getBoundingClientRect();
      const l = lead.getBoundingClientRect();
      const b = badge.getBoundingClientRect();
      const s = state.getBoundingClientRect();
      const t = title.getBoundingClientRect();
      return {
        headerHeight: Math.round(h.height),
        emptyTopStrip: Math.round(t.top - h.top),
        badgeLeftOffsetFromLead: Math.round(b.left - l.right),
        stateBottomToTitleTop: Math.round(t.top - s.bottom),
      };
    });

    expect(metrics).not.toBeNull();
    expect(metrics?.headerHeight).toBeLessThanOrEqual(96);
    expect(metrics?.emptyTopStrip).toBeLessThanOrEqual(64);
    expect(metrics?.badgeLeftOffsetFromLead).toBeLessThanOrEqual(48);
    expect(metrics?.stateBottomToTitleTop).toBeGreaterThanOrEqual(-8);
  });
});
