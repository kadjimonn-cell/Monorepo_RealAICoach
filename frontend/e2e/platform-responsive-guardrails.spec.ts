import { test, expect } from '@playwright/test';

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3000';

const ROUTES = [
  '/welcome',
  '/about-us',
  '/contact',
  '/pricing',
  '/admin/mobile-money-dashboard',
];

const VIEWPORTS = [
  { name: 'mobile-320', width: 320, height: 844 },
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'tablet-600', width: 600, height: 960 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'tablet-834', width: 834, height: 1112 },
  { name: 'tablet-912', width: 912, height: 1368 },
  { name: 'desktop-1440', width: 1440, height: 900 },
];

for (const vp of VIEWPORTS) {
  test.describe(`Responsive guardrails @ ${vp.name}`, () => {
    for (const route of ROUTES) {
      test(`no horizontal overflow on ${route}`, async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(1200);

        const overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            inner: window.innerWidth,
            scroll: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > window.innerWidth,
          };
        });

        expect(overflow.hasOverflow, `overflow at ${route} ${vp.name}: ${JSON.stringify(overflow)}`).toBeFalsy();
      });

      if (route === '/welcome') {
        test(`welcome core shell paints immediately in preview-like mobile context on ${vp.name}`, async ({ page }) => {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(2200);

          const shell = page.locator('[data-testid="welcome-hero"]');
          await expect(shell).toBeVisible();

          const state = await page.evaluate(() => ({
            bodyTextLength: (document.body?.innerText || '').trim().length,
            bodyChildren: document.body?.children?.length || 0,
            hasSkeleton: !!document.querySelector('[data-testid="skeleton-welcome"]'),
            hasHero: !!document.querySelector('[data-testid="welcome-hero"]'),
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
          }));

          expect(state.bodyChildren).toBeGreaterThan(0);
          expect(state.bodyTextLength).toBeGreaterThan(80);
          expect(state.hasHero).toBeTruthy();
          expect(state.scrollWidth).toBeLessThanOrEqual(state.innerWidth + 1);
        });

        test(`welcome utility strips stay calm on ${vp.name}`, async ({ page }) => {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(1800);

          const featured = page.locator('[data-testid="welcome-featured-in-marquee"]');
          const media = page.locator('[data-testid="welcome-media-mentions-strip"]');
          await featured.scrollIntoViewIfNeeded();
          await expect(featured).toBeVisible();
          await expect(media).toBeVisible();

          const metrics = await page.evaluate(() => {
            const featuredRoot = document.querySelector('[data-testid="welcome-featured-in-marquee"]') as HTMLElement | null;
            const featuredStatus = document.querySelector('[data-testid="welcome-featured-in-status"]') as HTMLElement | null;
            const staticGrid = document.querySelector('[data-testid="welcome-featured-in-static-grid"]') as HTMLElement | null;
            const marqueeTrack = document.querySelector('[data-testid="welcome-featured-in-marquee-track"]') as HTMLElement | null;
            const mediaMeta = document.querySelector('[data-testid="welcome-media-mention-meta"]') as HTMLElement | null;
            const mobileQuickNav = document.querySelector('[data-testid="welcome-mobile-quick-nav-drawer"]') as HTMLElement | null;
            if (!featuredRoot || !featuredStatus || !mediaMeta) return null;
            return {
              hasOverflow: document.documentElement.scrollWidth > window.innerWidth,
              featuredHeight: Math.round(featuredRoot.getBoundingClientRect().height),
              featuredStatusLines: Math.round((featuredStatus.getBoundingClientRect().height || 0) / 12),
              hasStaticGrid: !!staticGrid,
              hasMarqueeTrack: !!marqueeTrack,
              mediaMetaLines: Math.round((mediaMeta.getBoundingClientRect().height || 0) / 10),
              hasMobileQuickNav: !!mobileQuickNav,
            };
          });

          expect(metrics).not.toBeNull();
          expect(metrics?.hasOverflow).toBeFalsy();
          expect(metrics?.featuredHeight).toBeGreaterThan(60);
          expect(metrics?.mediaMetaLines).toBeLessThanOrEqual(3);

          if (vp.width < 960) {
            expect(metrics?.hasStaticGrid).toBeTruthy();
            expect(metrics?.hasMarqueeTrack).toBeFalsy();
            expect(metrics?.hasMobileQuickNav).toBeFalsy();
          }

          if (vp.width >= 1280) {
            expect(metrics?.hasMarqueeTrack).toBeTruthy();
          }
        });

        test(`welcome hero shell stays balanced on ${vp.name}`, async ({ page }) => {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(1800);

          const metrics = await page.evaluate(() => {
            const shell = document.querySelector('[data-testid="welcome-hero-centered-shell"]') as HTMLElement | null;
            const title = document.querySelector('[data-testid="welcome-hero-title"]') as HTMLElement | null;
            const badge = document.querySelector('[data-testid="welcome-hero-badge"]') as HTMLElement | null;
            if (!shell || !title || !badge) return null;

            const shellRect = shell.getBoundingClientRect();
            return {
              hasOverflow: document.documentElement.scrollWidth > window.innerWidth,
              leftMargin: Math.round(shellRect.left),
              rightMargin: Math.round(window.innerWidth - shellRect.right),
              titleTextAlign: getComputedStyle(title).textAlign,
              badgeAlignSelf: getComputedStyle(badge).alignSelf,
            };
          });

          expect(metrics).not.toBeNull();
          expect(metrics?.hasOverflow).toBeFalsy();

          if (vp.width < 1024) {
            expect(Math.abs((metrics?.leftMargin || 0) - (metrics?.rightMargin || 0)), `${vp.name} welcome shell is not balanced: ${JSON.stringify(metrics)}`).toBeLessThanOrEqual(2);
            expect(metrics?.titleTextAlign).toBe('center');
            expect(metrics?.badgeAlignSelf).toBe('center');
          }
        });

        test(`welcome footer layout adapts correctly on ${vp.name}`, async ({ page }) => {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(1800);

          const footer = page.locator('[data-testid="platform-footer"]');
          await footer.scrollIntoViewIfNeeded();

          const metrics = await page.evaluate(() => {
            const grid = document.querySelector('[data-testid="footer-link-columns-grid"]') as HTMLElement | null;
            const disclaimer = document.querySelector('[data-testid="footer-disclaimer-shell"]') as HTMLElement | null;
            const careers = document.querySelector('[data-testid="footer-section-company-column"]') as HTMLElement | null;
            const careersLink = document.querySelector('[data-testid="footer-careers-link"]') as HTMLElement | null;
            const pressLink = document.querySelector('[data-testid="footer-link-press"]') as HTMLElement | null;
            const newsletterTitle = document.querySelector('[data-testid="footer-newsletter"] h1, [data-testid="footer-newsletter"] h2, [data-testid="footer-newsletter"] [data-testid="footer-newsletter-title"]') as HTMLElement | null;
            if (!grid || !disclaimer || !careers || !careersLink || !pressLink) return null;

            const gridRect = grid.getBoundingClientRect();
            const disclaimerRect = disclaimer.getBoundingClientRect();
            const gridStyle = getComputedStyle(grid);
            const gridChildren = Array.from(grid.children) as HTMLElement[];
            const topRows = Array.from(new Set(gridChildren.map((child) => Math.round(child.getBoundingClientRect().top))));

            return {
              hasOverflow: document.documentElement.scrollWidth > window.innerWidth,
              gridCenter: Math.round(gridRect.left + gridRect.width / 2),
              disclaimerCenter: Math.round(disclaimerRect.left + disclaimerRect.width / 2),
              gridWidth: Math.round(gridRect.width),
              disclaimerWidth: Math.round(disclaimerRect.width),
              childCount: gridChildren.length,
              rowCount: topRows.length,
              justifyContent: gridStyle.justifyContent,
              careersLinkText: (careersLink.textContent || '').trim().length,
              pressLinkText: (pressLink.textContent || '').trim().length,
              hasNewsletterTitle: !!newsletterTitle,
            };
          });

          expect(metrics).not.toBeNull();
          expect(metrics?.hasOverflow).toBeFalsy();
          expect(Math.abs((metrics?.gridCenter || 0) - (metrics?.disclaimerCenter || 0)), `${vp.name} footer/disclaimer centers mismatch: ${JSON.stringify(metrics)}`).toBeLessThanOrEqual(4);
          expect(metrics?.careersLinkText).toBeGreaterThan(2);
          expect(metrics?.pressLinkText).toBeGreaterThan(2);

          if (vp.width < 768) {
            expect(metrics?.rowCount, `${vp.name} should keep a phone-friendly stacked/two-column footer: ${JSON.stringify(metrics)}`).toBeGreaterThanOrEqual(2);
          }

          if (vp.width >= 560 && vp.width < 980) {
            expect(metrics?.rowCount, `${vp.name} should keep the compact-tablet 2x2 footer band: ${JSON.stringify(metrics)}`).toBe(2);
          }

          if (vp.width >= 980) {
            expect(metrics?.rowCount, `${vp.name} should keep the wide tablet/desktop single-row footer band: ${JSON.stringify(metrics)}`).toBe(1);
          }

          if (vp.width >= 768 && vp.width < 1180) {
            expect(metrics?.justifyContent).toBe('space-between');
            expect(metrics?.gridWidth, `${vp.name} tablet footer should use the wider container: ${JSON.stringify(metrics)}`).toBeGreaterThanOrEqual(Math.min(vp.width - 64, 680));
          }

          if (vp.width >= 1180) {
            expect(metrics?.rowCount).toBeLessThanOrEqual(2);
          }
        });

        test(`welcome lower architecture rhythm stays locked on ${vp.name}`, async ({ page }) => {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(2000);

          await page.locator('[data-testid="welcome-footer-wrapper"]').scrollIntoViewIfNeeded();

          const metrics = await page.evaluate(() => {
            const summary = document.querySelector('[data-testid="welcome-enterprise-section-cta"]') as HTMLElement | null;
            const careers = document.querySelector('[data-testid="welcome-careers-banner"]') as HTMLElement | null;
            const footer = document.querySelector('[data-testid="welcome-footer-wrapper"]') as HTMLElement | null;
            const footerGrid = document.querySelector('[data-testid="footer-link-columns-grid"]') as HTMLElement | null;
            const actions = document.querySelector('[data-testid="welcome-careers-actions"]') as HTMLElement | null;
            if (!summary || !careers || !footer || !footerGrid || !actions) return null;

            const rectToDoc = (el: HTMLElement) => {
              const rect = el.getBoundingClientRect();
              return {
                top: Math.round(rect.top + window.scrollY),
                bottom: Math.round(rect.bottom + window.scrollY),
                left: Math.round(rect.left),
                width: Math.round(rect.width),
                center: Math.round(rect.left + rect.width / 2),
              };
            };

            const summaryRect = rectToDoc(summary);
            const careersRect = rectToDoc(careers);
            const footerRect = rectToDoc(footer);
            const footerGridRect = rectToDoc(footerGrid);
            return {
              hasOverflow: document.documentElement.scrollWidth > window.innerWidth,
              summaryToCareersGap: careersRect.top - summaryRect.bottom,
              careersToFooterGap: footerRect.top - careersRect.bottom,
              footerCenter: footerRect.center,
              footerGridCenter: footerGridRect.center,
              footerGridWidth: footerGridRect.width,
              actionsJustify: getComputedStyle(actions).justifyContent,
            };
          });

          expect(metrics).not.toBeNull();
          expect(metrics?.hasOverflow).toBeFalsy();
          expect(metrics?.summaryToCareersGap, `${vp.name} summary-to-careers gap collapsed: ${JSON.stringify(metrics)}`).toBeGreaterThanOrEqual(10);
          expect(metrics?.careersToFooterGap, `${vp.name} careers-to-footer gap collapsed: ${JSON.stringify(metrics)}`).toBeGreaterThanOrEqual(10);
          expect(Math.abs((metrics?.footerCenter || 0) - (metrics?.footerGridCenter || 0)), `${vp.name} footer grid drifted from wrapper center: ${JSON.stringify(metrics)}`).toBeLessThanOrEqual(4);

          if (vp.width < 1180) {
            expect(metrics?.actionsJustify).toBe('center');
          }

          if (vp.width >= 768 && vp.width < 1180) {
            expect(metrics?.footerGridWidth, `${vp.name} lower footer should hold the tablet-width architecture: ${JSON.stringify(metrics)}`).toBeGreaterThanOrEqual(Math.min(vp.width - 64, 680));
          }
        });

        test(`welcome lower neighborhood stays polished in themes and locale on ${vp.name}`, async ({ page }) => {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(1800);

          if (vp.width < 1024) {
            await page.click('[data-testid="welcome-nav-hamburger"]', { force: true });
            await page.waitForTimeout(250);
            await page.click('[data-testid="mobile-lang-fr"]', { force: true });
          } else {
            await page.click('[data-testid="welcome-theme-toggle-dark"]', { force: true });
            await page.waitForTimeout(250);
            await page.click('[data-testid="welcome-language-selector"]', { force: true });
            await page.waitForTimeout(250);
            await page.click('[data-testid="lang-option-fr"]', { force: true });
          }

          await page.waitForTimeout(1200);
          await page.locator('[data-testid="welcome-careers-banner"]').scrollIntoViewIfNeeded();

          const metrics = await page.evaluate(() => {
            const careersTitle = document.querySelector('[data-testid="welcome-careers-title"]') as HTMLElement | null;
            const careersCopy = document.querySelector('[data-testid="welcome-careers-copy"]') as HTMLElement | null;
            const careersActions = document.querySelector('[data-testid="welcome-careers-actions"]') as HTMLElement | null;
            const footer = document.querySelector('[data-testid="platform-footer"]') as HTMLElement | null;
            const pressLink = document.querySelector('[data-testid="footer-link-press"]') as HTMLElement | null;
            const root = document.querySelector('[data-testid="welcome-screen"]') as HTMLElement | null;
            if (!careersTitle || !careersCopy || !careersActions || !footer || !pressLink || !root) return null;
            const rootStyle = getComputedStyle(root);
            return {
              hasOverflow: document.documentElement.scrollWidth > window.innerWidth,
              careersTitleLength: (careersTitle.textContent || '').trim().length,
              careersCopyLength: (careersCopy.textContent || '').trim().length,
              pressLinkLength: (pressLink.textContent || '').trim().length,
              actionsCount: careersActions.querySelectorAll('[data-testid]').length,
              rootBg: rootStyle.backgroundColor,
              footerBg: getComputedStyle(footer).backgroundColor,
            };
          });

          expect(metrics).not.toBeNull();
          expect(metrics?.hasOverflow).toBeFalsy();
          expect(metrics?.careersTitleLength).toBeGreaterThan(10);
          expect(metrics?.careersCopyLength).toBeGreaterThan(20);
          expect(metrics?.pressLinkLength).toBeGreaterThan(2);
          expect(metrics?.actionsCount).toBeGreaterThanOrEqual(3);
          expect(metrics?.rootBg).not.toBe('rgba(0, 0, 0, 0)');
          expect(metrics?.footerBg).not.toBe('rgba(0, 0, 0, 0)');
        });

        test(`welcome growth intelligence module remains responsive on ${vp.name}`, async ({ page }) => {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(1800);

          const module = page.locator('[data-testid="growth-chart-module"]');
          await module.scrollIntoViewIfNeeded();

          const metrics = await page.evaluate(() => {
            const root = document.querySelector('[data-testid="growth-chart-module"]') as HTMLElement | null;
            const proofGrid = document.querySelector('[data-testid="growth-chart-proof-grid"]') as HTMLElement | null;
            const rangeToggle = document.querySelector('[data-testid="growth-chart-range-toggle"]') as HTMLElement | null;
            const premiumTeaser = document.querySelector('[data-testid="growth-chart-premium-teaser"]') as HTMLElement | null;
            const canvas = document.querySelector('[data-testid="growth-chart-canvas"]') as HTMLElement | null;
            const tooltip = document.querySelector('[data-testid="growth-chart-tooltip"]') as HTMLElement | null;
            const yAxisTicks = Array.from(document.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick text'));
            // premiumTeaser is only shown on non-compact layouts (width >= 980)
            if (!root || !proofGrid || !rangeToggle || !canvas) return null;

            const rootRect = root.getBoundingClientRect();
            const toggleRect = rangeToggle.getBoundingClientRect();
            const teaserRect = premiumTeaser?.getBoundingClientRect() || null;
            const canvasRect = canvas.getBoundingClientRect();
            const tooltipRect = tooltip?.getBoundingClientRect() || null;
            const proofChildren = Array.from(proofGrid.children) as HTMLElement[];
            const proofRows = Array.from(new Set(proofChildren.map((child) => Math.round(child.getBoundingClientRect().top))));

            return {
              rootWidth: Math.round(rootRect.width),
              canvasWidth: Math.round(canvasRect.width),
              toggleRight: Math.round(toggleRect.right),
              rootRight: Math.round(rootRect.right),
              teaserRight: teaserRect ? Math.round(teaserRect.right) : null,
              tooltipWidth: tooltipRect ? Math.round(tooltipRect.width) : 0,
              tooltipRight: tooltipRect ? Math.round(tooltipRect.right) : 0,
              proofCardCount: proofChildren.length,
              proofRowCount: proofRows.length,
              yAxisTickCount: yAxisTicks.length,
            };
          });

          expect(metrics).not.toBeNull();
          expect(metrics?.rootWidth).toBeGreaterThan(vp.width < 400 ? 200 : 280);
          expect(metrics?.canvasWidth).toBeGreaterThan(vp.width < 400 ? 150 : 190);
          expect(metrics?.toggleRight).toBeLessThanOrEqual((metrics?.rootRight || 0) + 1);
          // premiumTeaser only shown on non-compact layouts (width >= 980)
          if (metrics?.teaserRight !== null) {
            expect(metrics?.teaserRight).toBeLessThanOrEqual((metrics?.rootRight || 0) + 1);
          }
          if ((metrics?.tooltipWidth || 0) > 0) {
            expect(metrics?.tooltipWidth).toBeLessThanOrEqual(vp.width < 480 ? 190 : 240);
            expect(metrics?.tooltipRight).toBeLessThanOrEqual((metrics?.rootRight || 0) + 1);
          }
          // Compact layout (width < 980) shows 2 primary metrics; full layout shows 4
          expect(metrics?.proofCardCount).toBeGreaterThanOrEqual(vp.width < 980 ? 2 : 4);

          if (vp.width < 560) {
            expect(metrics?.yAxisTickCount).toBe(0);
          }

          // On phone layouts, proof cards stack vertically (2 rows for 2 cards)
          if (vp.width < 560) {
            expect(metrics?.proofRowCount).toBeGreaterThanOrEqual(2);
          }
        });

        test(`welcome capability command center stays responsive on ${vp.name}`, async ({ page }) => {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(2000);

          const section = page.locator('[data-testid="welcome-capability-command-center"]');
          await section.scrollIntoViewIfNeeded();
          await expect(section).toBeVisible();

          const metrics = await page.evaluate(() => {
            const root = document.querySelector('[data-testid="welcome-capability-command-center"]') as HTMLElement | null;
            const spotlight = document.querySelector('[data-testid="welcome-capability-spotlight"]') as HTMLElement | null;
            const board = document.querySelector('[data-testid="welcome-capability-command-board"]') as HTMLElement | null;
            const primaryCta = document.querySelector('[data-testid="welcome-capability-primary-cta"]') as HTMLElement | null;
            const matrix = document.querySelector('[data-testid="welcome-capability-matrix"]') as HTMLElement | null;
            const tabs = document.querySelector('[data-testid="welcome-capability-category-tabs"]') as HTMLElement | null;
            const grid = document.querySelector('[data-testid="welcome-capability-card-grid"]') as HTMLElement | null;
            const shells = Array.from(document.querySelectorAll('[data-testid^="welcome-capability-card-shell-"]')) as HTMLElement[];
            const firstTitle = document.querySelector('[data-testid^="welcome-capability-card-title-"]') as HTMLElement | null;
            const proofStaticGrid = document.querySelector('[data-testid="welcome-capability-proof-static-grid"]') as HTMLElement | null;
            const proofMarquee = document.querySelector('[data-testid="welcome-capability-proof-marquee-track"]') as HTMLElement | null;
            if (!root || !spotlight || !board || !primaryCta || !matrix || !tabs || !grid || shells.length === 0 || !firstTitle) return null;

            const doc = document.documentElement;
            const shellRects = shells.slice(0, 3).map((node) => node.getBoundingClientRect());
            const rowTops = Array.from(new Set(shellRects.map((rect) => Math.round(rect.top))));
            const columnLefts = Array.from(new Set(shellRects.map((rect) => Math.round(rect.left))));
            const rootRect = root.getBoundingClientRect();
            const matrixRect = matrix.getBoundingClientRect();
            const boardRect = board.getBoundingClientRect();
            const primaryCtaRect = primaryCta.getBoundingClientRect();
            const titleRect = firstTitle.getBoundingClientRect();
            return {
              hasOverflow: doc.scrollWidth > window.innerWidth,
              rootWidth: Math.round(rootRect.width),
              matrixRight: Math.round(matrixRect.right),
              rootRight: Math.round(rootRect.right),
              boardTop: Math.round(boardRect.top),
              primaryCtaBottom: Math.round(primaryCtaRect.bottom),
              tabCount: tabs.children.length,
              cardCount: shells.length,
              rowCount: rowTops.length,
              columnCount: columnLefts.length,
              smallestCardWidth: Math.round(Math.min(...shellRects.map((rect) => rect.width))),
              firstTitleWidth: Math.round(titleRect.width),
              hasProofStaticGrid: !!proofStaticGrid,
              hasProofMarquee: !!proofMarquee,
            };
          });

          expect(metrics).not.toBeNull();
          expect(metrics?.hasOverflow).toBeFalsy();
          expect(metrics?.rootWidth).toBeGreaterThan(280);
          expect(metrics?.tabCount).toBeGreaterThanOrEqual(4);
          expect(metrics?.cardCount).toBeGreaterThanOrEqual(3);
          expect(metrics?.matrixRight).toBeLessThanOrEqual((metrics?.rootRight || 0) + 1);
          expect(metrics?.firstTitleWidth).toBeGreaterThan(180);

          if (vp.width < 768) {
            expect(metrics?.columnCount).toBe(1);
            expect(metrics?.rowCount).toBeGreaterThanOrEqual(3);
            expect(metrics?.smallestCardWidth).toBeGreaterThan(240);
          }

          if (vp.width >= 768 && vp.width < 1320) {
            expect(metrics?.columnCount).toBe(2);
          }

          if (vp.width >= 1320) {
            expect(metrics?.columnCount).toBe(3);
          }

          if (vp.width < 1180) {
            expect(metrics?.boardTop).toBeGreaterThanOrEqual((metrics?.primaryCtaBottom || 0) - 4);
            expect(metrics?.hasProofStaticGrid).toBeTruthy();
            expect(metrics?.hasProofMarquee).toBeFalsy();
          }

          if (vp.width >= 1180) {
            expect(metrics?.hasProofMarquee).toBeTruthy();
          }
        });

        test(`welcome pricing and social trust surfaces remain responsive on ${vp.name}`, async ({ page }) => {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(2200);

          const social = page.locator('[data-testid="welcome-social-header-card"]');
          await social.scrollIntoViewIfNeeded();
          await expect(page.locator('[data-testid="welcome-pricing-command-shell"]')).toBeVisible();
          await expect(social).toBeVisible();

          const metrics = await page.evaluate(() => {
            const doc = document.documentElement;
            const progressRail = document.querySelector('[data-testid="welcome-progress-rail"]') as HTMLElement | null;
            const pricing = document.querySelector('[data-testid="welcome-pricing-command-shell"]') as HTMLElement | null;
            const pricingHero = document.querySelector('[data-testid="welcome-pricing-hero-card"]') as HTMLElement | null;
            const pricingControls = document.querySelector('[data-testid="welcome-pricing-control-card"]') as HTMLElement | null;
            const socialHeader = document.querySelector('[data-testid="welcome-social-header-card"]') as HTMLElement | null;
            const socialFeatured = document.querySelector('[data-testid="welcome-social-featured-card"]') as HTMLElement | null;
            const pricingGrid = document.querySelector('[data-testid="welcome-pricing-card-grid"]') as HTMLElement | null;
            const socialGrid = document.querySelector('[data-testid="welcome-testimonials-grid"]') as HTMLElement | null;
            if (!pricing || !pricingHero || !pricingControls || !socialHeader || !socialFeatured || !pricingGrid || !socialGrid) return null;
            return {
              hasOverflow: doc.scrollWidth > window.innerWidth,
              hasProgressRail: !!progressRail,
              pricingWidth: Math.round(pricing.getBoundingClientRect().width),
              pricingHeroBottom: Math.round(pricingHero.getBoundingClientRect().bottom),
              pricingControlsTop: Math.round(pricingControls.getBoundingClientRect().top),
              socialWidth: Math.round(socialHeader.getBoundingClientRect().width),
              socialFeaturedBottom: Math.round(socialFeatured.getBoundingClientRect().bottom),
              socialGridTop: Math.round(socialGrid.getBoundingClientRect().top),
              pricingCards: pricingGrid.querySelectorAll('[data-testid^="welcome-plan-"]').length,
              socialCards: socialGrid.querySelectorAll('[data-testid^="welcome-testimonial-"]').length,
            };
          });

          expect(metrics).not.toBeNull();
          expect(metrics?.hasOverflow).toBeFalsy();
          expect(metrics?.pricingWidth).toBeGreaterThan(280);
          expect(metrics?.socialWidth).toBeGreaterThan(280);
          expect(metrics?.pricingCards).toBeGreaterThanOrEqual(3);
          expect(metrics?.socialCards).toBeGreaterThanOrEqual(1);

          if (vp.width < 1180) {
            expect(metrics?.hasProgressRail).toBeFalsy();
            expect(metrics?.pricingControlsTop).toBeGreaterThanOrEqual((metrics?.pricingHeroBottom || 0) - 4);
            expect(metrics?.socialGridTop).toBeGreaterThanOrEqual((metrics?.socialFeaturedBottom || 0) - 4);
          }

          if (vp.width >= 1180) {
            expect(metrics?.hasProgressRail).toBeTruthy();
          }
        });

        test(`welcome CTA close surface remains responsive on ${vp.name}`, async ({ page }) => {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(2200);

          const summary = page.locator('[data-testid="welcome-summary-header"]');
          await summary.scrollIntoViewIfNeeded();
          await expect(summary).toBeVisible();

          const metrics = await page.evaluate(() => {
            const doc = document.documentElement;
            const summaryHeader = document.querySelector('[data-testid="welcome-summary-header"]') as HTMLElement | null;
            const summaryZone = document.querySelector('[data-testid="welcome-summary-zone"]') as HTMLElement | null;
            const decisionStrip = document.querySelector('[data-testid="welcome-decision-strip"]') as HTMLElement | null;
            const summaryCard = document.querySelector('[data-testid="welcome-summary-card"]') as HTMLElement | null;
            const stripCount = document.querySelectorAll('[data-testid="welcome-decision-strip"]').length;
            if (!summaryHeader || !summaryZone || !decisionStrip || !summaryCard) return null;
            return {
              hasOverflow: doc.scrollWidth > window.innerWidth,
              summaryWidth: Math.round(summaryHeader.getBoundingClientRect().width),
              decisionWidth: Math.round(decisionStrip.getBoundingClientRect().width),
              summaryCardHeight: Math.round(summaryCard.getBoundingClientRect().height),
              summaryZoneBottom: Math.round(summaryZone.getBoundingClientRect().bottom),
              decisionStripTop: Math.round(decisionStrip.getBoundingClientRect().top),
              stripCount,
            };
          });

          expect(metrics).not.toBeNull();
          expect(metrics?.hasOverflow).toBeFalsy();
          expect(metrics?.summaryWidth).toBeGreaterThan(280);
          expect(metrics?.decisionWidth).toBeGreaterThan(260);
          expect(metrics?.summaryCardHeight).toBeGreaterThan(120);
          expect(metrics?.stripCount).toBe(1);

          if (vp.width < 1180) {
            expect(metrics?.decisionStripTop).toBeGreaterThanOrEqual((metrics?.summaryZoneBottom || 0) - 4);
          }
        });
      }
    }
  });
}
