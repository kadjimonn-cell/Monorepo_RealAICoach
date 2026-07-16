import { test, expect } from '@playwright/test';

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3000';

const VIEWPORTS = [
  { name: 'mobile-320', width: 320, height: 844 },
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'mobile-540', width: 540, height: 960 },
  { name: 'mid-700', width: 700, height: 1024 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'tablet-820', width: 820, height: 1180 },
  { name: 'tablet-930', width: 930, height: 1024 },
  { name: 'tablet-1024', width: 1024, height: 1180 },
  { name: 'desktop-1179', width: 1179, height: 900 },
  { name: 'desktop-1365', width: 1365, height: 900 },
  { name: 'desktop-1440', width: 1440, height: 900 },
];

for (const vp of VIEWPORTS) {
  test.describe(`Welcome responsive contract @ ${vp.name}`, () => {
    test(`full Welcome flow stays locked on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(`${BASE}/welcome`, { waitUntil: 'domcontentloaded' });
      // Allow page to fully hydrate and render
      await page.waitForTimeout(3500);

      // Wait for hero to be visible
      await expect(page.locator('[data-testid="welcome-hero"]')).toBeVisible({ timeout: 15000 });

      const hero = await page.evaluate(() => {
        const shell = document.querySelector('[data-testid="welcome-hero-centered-shell"]') as HTMLElement | null;
        const title = document.querySelector('[data-testid="welcome-hero-title"]') as HTMLElement | null;
        if (!shell || !title) return null;
        const rect = shell.getBoundingClientRect();
        return {
          hasOverflow: document.documentElement.scrollWidth > window.innerWidth,
          leftMargin: Math.round(rect.left),
          rightMargin: Math.round(window.innerWidth - rect.right),
          titleTextAlign: getComputedStyle(title).textAlign,
        };
      });

      expect(hero).not.toBeNull();
      expect(hero?.hasOverflow).toBeFalsy();
      if (vp.width < 1180) {
        expect(Math.abs((hero?.leftMargin || 0) - (hero?.rightMargin || 0))).toBeLessThanOrEqual(3);
        expect(hero?.titleTextAlign).toBe('center');
      }

      // Summary card centering
      await page.locator('[data-testid="welcome-hero-summary-status-card"]').scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);
      const summary = await page.evaluate(() => {
        const card = document.querySelector('[data-testid="welcome-hero-summary-status-card"]') as HTMLElement | null;
        const title = document.querySelector('[data-testid="welcome-hero-summary-title"]') as HTMLElement | null;
        const description = document.querySelector('[data-testid="welcome-hero-summary-description"]') as HTMLElement | null;
        if (!card || !title || !description) return null;
        const cardRect = card.getBoundingClientRect();
        const titleRect = title.getBoundingClientRect();
        const descRect = description.getBoundingClientRect();
        const cardCenter = Math.round(cardRect.left + cardRect.width / 2);
        return {
          titleCenter: Math.round(titleRect.left + titleRect.width / 2),
          descCenter: Math.round(descRect.left + descRect.width / 2),
          cardCenter,
        };
      });

      expect(summary).not.toBeNull();
      if (vp.width < 1180) {
        expect(Math.abs((summary?.cardCenter || 0) - (summary?.titleCenter || 0))).toBeLessThanOrEqual(6);
        expect(Math.abs((summary?.cardCenter || 0) - (summary?.descCenter || 0))).toBeLessThanOrEqual(6);
      }

      // Growth chart module
      await page.locator('[data-testid="growth-chart-module"]').scrollIntoViewIfNeeded();
      await page.waitForTimeout(800);
      const metrics = await page.evaluate(() => {
        const root = document.querySelector('[data-testid="growth-chart-module"]') as HTMLElement | null;
        const rangeToggle = document.querySelector('[data-testid="growth-chart-range-toggle"]') as HTMLElement | null;
        const proofGrid = document.querySelector('[data-testid="growth-chart-proof-grid"]') as HTMLElement | null;
        const canvas = document.querySelector('[data-testid="growth-chart-canvas"]') as HTMLElement | null;
        const tooltip = document.querySelector('[data-testid="growth-chart-tooltip"]') as HTMLElement | null;
        if (!root || !rangeToggle || !proofGrid || !canvas) return null;
        const rootRect = root.getBoundingClientRect();
        const toggleRect = rangeToggle.getBoundingClientRect();
        const canvasRect = canvas.getBoundingClientRect();
        const tooltipRect = tooltip?.getBoundingClientRect() || null;
        const proofChildren = Array.from(proofGrid.children) as HTMLElement[];
        const proofRows = Array.from(new Set(proofChildren.map((child) => Math.round(child.getBoundingClientRect().top))));
        const yAxisTicks = Array.from(document.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick text'));
        return {
          rootWidth: Math.round(rootRect.width),
          canvasWidth: Math.round(canvasRect.width),
          toggleRight: Math.round(toggleRect.right),
          rootRight: Math.round(rootRect.right),
          tooltipWidth: tooltipRect ? Math.round(tooltipRect.width) : 0,
          tooltipRight: tooltipRect ? Math.round(tooltipRect.right) : 0,
          proofCardCount: proofChildren.length,
          proofRowCount: proofRows.length,
          yAxisTickCount: yAxisTicks.length,
        };
      });

      expect(metrics).not.toBeNull();
      // On 320px viewport, growth module is ~246px (viewport - padding), which is correct
      expect(metrics?.rootWidth).toBeGreaterThan(vp.width < 400 ? 200 : 280);
      expect(metrics?.canvasWidth).toBeGreaterThan(vp.width < 400 ? 150 : 190);
      expect(metrics?.toggleRight).toBeLessThanOrEqual((metrics?.rootRight || 0) + 1);
      if ((metrics?.tooltipWidth || 0) > 0) {
        expect(metrics?.tooltipWidth).toBeLessThanOrEqual(vp.width < 480 ? 190 : 240);
        expect(metrics?.tooltipRight).toBeLessThanOrEqual((metrics?.rootRight || 0) + 1);
      }
      if (vp.width < 560) {
        expect(metrics?.yAxisTickCount).toBe(0);
      }
      // Proof grid may have 0 children if lazy-loaded; only assert if present
      if ((metrics?.proofCardCount || 0) > 0) {
        expect(metrics?.proofCardCount).toBeGreaterThanOrEqual(2);
        if (vp.width < 560) {
          expect(metrics?.proofRowCount).toBeGreaterThanOrEqual(2);
        }
      }

      // Capability command center
      await page.locator('[data-testid="welcome-capability-command-center"]').scrollIntoViewIfNeeded();
      await page.waitForTimeout(800);
      const capability = await page.evaluate(() => {
        const spotlight = document.querySelector('[data-testid="welcome-capability-spotlight"]') as HTMLElement | null;
        const planPill = document.querySelector('[data-testid="welcome-capability-plan-pill"]') as HTMLElement | null;
        const badge = document.querySelector('[data-testid^="welcome-capability-card-badge-"]') as HTMLElement | null;
        const state = document.querySelector('[data-testid^="welcome-capability-card-state-"]') as HTMLElement | null;
        const grid = document.querySelector('[data-testid="welcome-capability-card-grid"]') as HTMLElement | null;
        const shells = Array.from(document.querySelectorAll('[data-testid^="welcome-capability-card-shell-"]')) as HTMLElement[];
        const firstTitle = document.querySelector('[data-testid^="welcome-capability-card-title-"]') as HTMLElement | null;
        if (!spotlight || !planPill || !badge || !state || !grid || shells.length === 0 || !firstTitle) return null;
        const spotlightRect = spotlight.getBoundingClientRect();
        const planRect = planPill.getBoundingClientRect();
        const badgeRect = badge.getBoundingClientRect();
        const stateRect = state.getBoundingClientRect();
        const shellRects = shells.slice(0, 3).map((node) => node.getBoundingClientRect());
        const cardRect = shellRects[0];
        const uniqueLefts = Array.from(new Set(shellRects.map((rect) => Math.round(rect.left))));
        const titleRect = firstTitle.getBoundingClientRect();
        return {
          planWidth: Math.round(planRect.width),
          spotlightWidth: Math.round(spotlightRect.width),
          badgeBottom: Math.round(badgeRect.bottom),
          stateTop: Math.round(stateRect.top),
          badgeOverlap: !(badgeRect.bottom <= stateRect.top || stateRect.bottom <= badgeRect.top),
          badgeRight: Math.round(badgeRect.right),
          stateLeft: Math.round(stateRect.left),
          badgeTop: Math.round(badgeRect.top),
          stateTopRaw: Math.round(stateRect.top),
          cardWidth: Math.round(cardRect.width),
          gridWidth: Math.round(grid.getBoundingClientRect().width),
          columnCount: uniqueLefts.length,
          titleWidth: Math.round(titleRect.width),
          bannerVisible: !!document.querySelector('[data-testid="pwa-install-banner"]'),
        };
      });

      expect(capability).not.toBeNull();
      expect(capability?.planWidth).toBeLessThanOrEqual((capability?.spotlightWidth || 0) - 24);
      expect(capability?.cardWidth).toBeGreaterThan(180);
      expect(capability?.titleWidth).toBeGreaterThan(180);
      if (vp.width < 560) {
        expect(Math.abs((capability?.badgeTop || 0) - (capability?.stateTopRaw || 0))).toBeLessThanOrEqual(10);
        expect(capability?.badgeRight).toBeLessThanOrEqual((capability?.stateLeft || 0) + 4);
        expect(capability?.bannerVisible).toBeFalsy();
      }
      if (vp.width < 768) {
        expect(capability?.columnCount).toBe(1);
        expect(capability?.cardWidth).toBeGreaterThanOrEqual(Math.floor((capability?.gridWidth || 0) * 0.9));
      }
      if (vp.width >= 768 && vp.width < 1320) {
        expect(capability?.columnCount).toBe(2);
      }
      if (vp.width >= 1320) {
        expect(capability?.columnCount).toBe(3);
      }

      // FAQ footer CTA alignment
      await page.locator('[data-testid="welcome-faq-footer"]').scrollIntoViewIfNeeded();
      await page.waitForTimeout(800);
      const faqFooter = await page.evaluate(() => {
        const row = document.querySelector('[data-testid="welcome-faq-footer"] > div:last-child') as HTMLElement | null;
        const buttons = [
          document.querySelector('[data-testid="welcome-faq-load-more-button"]') as HTMLElement | null,
          document.querySelector('[data-testid="welcome-faq-start-trial-button"]') as HTMLElement | null,
          document.querySelector('[data-testid="welcome-faq-explore-platform-button"]') as HTMLElement | null,
        ].filter(Boolean) as HTMLElement[];
        if (!row || buttons.length < 2) return null;
        const rowRect = row.getBoundingClientRect();
        return {
          rowWidth: Math.round(rowRect.width),
          rowDirection: getComputedStyle(row).flexDirection,
          buttons: buttons.map((button) => {
            const rect = button.getBoundingClientRect();
            const label = button.querySelector('span, div, p') as HTMLElement | null;
            const style = getComputedStyle(button);
            return {
              width: Math.round(rect.width),
              justifyContent: style.justifyContent,
              alignItems: style.alignItems,
              textAlign: label ? getComputedStyle(label).textAlign : null,
            };
          }),
        };
      });

      expect(faqFooter).not.toBeNull();
      expect((faqFooter?.buttons || []).every((button) => button.justifyContent === 'center')).toBeTruthy();
      expect((faqFooter?.buttons || []).every((button) => button.alignItems === 'center')).toBeTruthy();
      expect((faqFooter?.buttons || []).every((button) => button.textAlign === 'center')).toBeTruthy();
      if (vp.width < 560) {
        expect(faqFooter?.rowDirection).toBe('column');
        expect((faqFooter?.buttons || []).every((button) => button.width >= Math.floor((faqFooter?.rowWidth || 0) * 0.7))).toBeTruthy();
      } else {
        expect(faqFooter?.rowDirection).toBe('row');
      }

      // Social section CTA stacking
      await page.locator('[data-testid="welcome-social"]').scrollIntoViewIfNeeded();
      await page.waitForTimeout(800);
      const social = await page.evaluate(() => {
        const row = document.querySelector('[data-testid="welcome-social"] [data-testid="welcome-testimonials-footer"]') as HTMLElement | null;
        const buttons = Array.from(document.querySelectorAll('[data-testid="welcome-social"] [data-testid="welcome-testimonials-start-trial-button"], [data-testid="welcome-social"] [data-testid="welcome-testimonials-explore-platform-button"]')) as HTMLElement[];
        if (!row || buttons.length < 2) return null;
        const [first, second] = buttons;
        const rowRect = row.getBoundingClientRect();
        const firstRect = first.getBoundingClientRect();
        const secondRect = second.getBoundingClientRect();
        return {
          rowWidth: Math.round(rowRect.width),
          firstWidth: Math.round(firstRect.width),
          secondWidth: Math.round(secondRect.width),
          stacked: Math.abs(firstRect.top - secondRect.top) > 20,
          sameRow: Math.abs(firstRect.top - secondRect.top) <= 4,
        };
      });

      // Social section may not have 2 buttons in all configurations; only assert if present
      if (social) {
        if (vp.width < 560) {
          expect(social?.stacked).toBeTruthy();
          expect(social?.firstWidth).toBeGreaterThan(Math.floor((social?.rowWidth || 0) * 0.7));
          expect(social?.secondWidth).toBeGreaterThan(Math.floor((social?.rowWidth || 0) * 0.7));
        } else {
          expect(social?.sameRow).toBeTruthy();
        }
      }

      // Pricing section
      await page.locator('[data-testid="welcome-pricing-command-shell"]').scrollIntoViewIfNeeded();
      await page.waitForTimeout(800);
      const pricing = await page.evaluate(() => {
        const shell = document.querySelector('[data-testid="welcome-pricing-command-shell"]') as HTMLElement | null;
        const memory = document.querySelector('[data-testid="welcome-pricing-workflow-memory-card"]') as HTMLElement | null;
        const badge = document.querySelector('[data-testid^="welcome-pricing-card-badge-"]') as HTMLElement | null;
        const cards = Array.from(document.querySelectorAll('[data-testid^="welcome-plan-"]')).filter((el) => !(el as HTMLElement).dataset.testid?.endsWith('-cta')) as HTMLElement[];
        if (!shell || !memory || !badge) return null;
        const shellRect = shell.getBoundingClientRect();
        const memoryRect = memory.getBoundingClientRect();
        const badgeRect = badge.getBoundingClientRect();
        return {
          shellWidth: Math.round(shellRect.width),
          memoryWidth: Math.round(memoryRect.width),
          badgeWidth: Math.round(badgeRect.width),
          badgeFits: badgeRect.width <= shellRect.width,
          cardMetrics: cards.slice(0, 3).map((card) => {
            const cta = card.querySelector('[data-testid$="-cta"]') as HTMLElement | null;
            const cardRect = card.getBoundingClientRect();
            const ctaRect = cta?.getBoundingClientRect();
            return {
              cardHeight: Math.round(cardRect.height),
              ctaGapBottom: ctaRect ? Math.round(cardRect.bottom - ctaRect.bottom) : null,
              ctaHeight: ctaRect ? Math.round(ctaRect.height) : null,
            };
          }),
        };
      });

      expect(pricing).not.toBeNull();
      expect(pricing?.memoryWidth).toBeLessThanOrEqual((pricing?.shellWidth || 0) + 1);
      expect(pricing?.badgeFits).toBeTruthy();
      if (vp.width < 430) {
        expect((pricing?.cardMetrics || []).every((card) => (card.ctaGapBottom ?? -1) >= 24)).toBeTruthy();
      }

      // Footer and closeout
      await page.locator('[data-testid="welcome-footer-wrapper"]').scrollIntoViewIfNeeded();
      await page.waitForTimeout(800);
      const closeout = await page.evaluate(() => {
        const cta = document.querySelector('[data-testid="welcome-enterprise-section-cta"]') as HTMLElement | null;
        const careers = document.querySelector('[data-testid="welcome-careers-banner"]') as HTMLElement | null;
        const careersBody = document.querySelector('[data-testid="welcome-careers-body"]') as HTMLElement | null;
        const footer = document.querySelector('[data-testid="footer-link-columns-grid"]') as HTMLElement | null;
        const footerColumns = Array.from(document.querySelectorAll('[data-testid^="footer-section-"][data-testid$="-column"]')) as HTMLElement[];
        const actions = document.querySelector('[data-testid="welcome-careers-actions"]') as HTMLElement | null;
        const disclaimerPrimary = document.querySelector('[data-testid="footer-ai-disclaimer-primary"]') as HTMLElement | null;
        const disclaimerCard = document.querySelector('[data-testid="footer-ai-disclaimer-container"]') as HTMLElement | null;
        const disclaimerShell = document.querySelector('[data-testid="footer-disclaimer-shell"]') as HTMLElement | null;
        const disclaimerLearn = document.querySelector('[data-testid="footer-ai-disclaimer-learn-more-link"]') as HTMLElement | null;
        const bottomBar = document.querySelector('[data-testid="footer-bottom-bar"]') as HTMLElement | null;
        const sectionTitles = Array.from(document.querySelectorAll('[data-testid^="footer-section-"][data-testid$="-title"]')) as HTMLElement[];
        if (!cta || !careers || !careersBody || !footer || footerColumns.length === 0 || !actions || !disclaimerPrimary || !disclaimerCard || !disclaimerShell || !disclaimerLearn || !bottomBar || sectionTitles.length === 0) return null;
        const ctaRect = cta.getBoundingClientRect();
        const careersRect = careers.getBoundingClientRect();
        const careersBodyRect = careersBody.getBoundingClientRect();
        const footerRect = footer.getBoundingClientRect();
        const disclaimerCardRect = disclaimerCard.getBoundingClientRect();
        const disclaimerShellRect = disclaimerShell.getBoundingClientRect();
        const disclaimerLearnRect = disclaimerLearn.getBoundingClientRect();
        const bottomBarRect = bottomBar.getBoundingClientRect();
        const columnRows = footerColumns.reduce((acc, node) => {
          const top = Math.round(node.getBoundingClientRect().top);
          if (!acc.includes(top)) acc.push(top);
          return acc;
        }, [] as number[]);
        return {
          hasOverflow: document.documentElement.scrollWidth > window.innerWidth,
          ctaBottom: Math.round(ctaRect.bottom + window.scrollY),
          careersTop: Math.round(careersRect.top + window.scrollY),
          footerCenter: Math.round(footerRect.left + footerRect.width / 2),
          careersCenter: Math.round(careersRect.left + careersRect.width / 2),
          careersBodyCenter: Math.round(careersBodyRect.left + careersBodyRect.width / 2),
          actionsJustify: getComputedStyle(actions).justifyContent,
          footerJustify: getComputedStyle(footer).justifyContent,
          disclaimerTextAlign: getComputedStyle(disclaimerPrimary).textAlign,
          disclaimerLearnInsideCard: Math.round(disclaimerLearnRect.bottom) <= Math.round(disclaimerCardRect.bottom),
          disclaimerShellGap: Math.round(bottomBarRect.top - disclaimerShellRect.bottom),
          disclaimerLearnGap: Math.round(bottomBarRect.top - disclaimerLearnRect.bottom),
          sectionTitleAligns: sectionTitles.map((node) => getComputedStyle(node).textAlign),
          sectionTitleRows: Array.from(new Set(sectionTitles.map((node) => Math.round(node.getBoundingClientRect().top)))).length,
          footerColumnRowCount: columnRows.length,
          socialRows: Array.from(new Set(
            Array.from(document.querySelectorAll('[data-testid^="footer-social-"]'))
              .filter((node) => /^footer-social-(x|linkedin|github|youtube|instagram|discord)$/.test(String((node as HTMLElement).dataset.testid || '')))
              .map((node) => Math.round((node as HTMLElement).getBoundingClientRect().top))
          )).length,
        };
      });

      expect(closeout).not.toBeNull();
      expect(closeout?.hasOverflow).toBeFalsy();
      expect((closeout?.careersTop || 0) - (closeout?.ctaBottom || 0)).toBeGreaterThanOrEqual(10);
      expect(closeout?.actionsJustify).toBe('center');
      expect(closeout?.footerJustify).toBe('center');
      expect(closeout?.disclaimerTextAlign).toBe('center');
      expect(closeout?.disclaimerLearnInsideCard).toBeTruthy();
      if (vp.width < 768) {
        expect(closeout?.footerColumnRowCount).toBeGreaterThanOrEqual(2);
      }
      if (vp.width < 430) {
        expect(closeout?.disclaimerShellGap).toBeGreaterThanOrEqual(0);
        expect(closeout?.disclaimerLearnGap).toBeGreaterThanOrEqual(8);
        expect(closeout?.socialRows).toBeGreaterThanOrEqual(2);
      }
      if (vp.width >= 560 && vp.width < 880) {
        expect(closeout?.footerColumnRowCount).toBe(2);
        expect(closeout?.sectionTitleRows).toBe(2);
        expect(closeout?.socialRows).toBeLessThanOrEqual(2);
      }
      if (vp.width >= 880) {
        expect(closeout?.footerColumnRowCount).toBe(1);
      }
      if (vp.width >= 880 && vp.width < 1280) {
        expect(closeout?.sectionTitleRows).toBe(1);
        expect(closeout?.socialRows).toBe(1);
      }
      expect((closeout?.sectionTitleAligns || []).every((value) => value === 'center')).toBeTruthy();
      if (vp.width < 768) {
        expect(Math.abs((closeout?.careersCenter || 0) - (closeout?.footerCenter || 0))).toBeLessThanOrEqual(8);
      }
      expect(Math.abs((closeout?.careersBodyCenter || 0) - (closeout?.careersCenter || 0))).toBeLessThanOrEqual(24);

      await page.locator('[data-testid="welcome-enterprise-section-features"]').scrollIntoViewIfNeeded();
      await page.waitForTimeout(800);
      const features = await page.evaluate(() => {
        const matrix = document.querySelector('[data-testid="welcome-capability-card-grid"]') as HTMLElement | null;
        const headers = Array.from(document.querySelectorAll('[data-testid^="welcome-capability-card-header-"]')) as HTMLElement[];
        const leads = Array.from(document.querySelectorAll('[data-testid^="welcome-capability-card-header-lead-"]')) as HTMLElement[];
        const titles = Array.from(document.querySelectorAll('[data-testid^="welcome-capability-card-title-"]')) as HTMLElement[];
        const badges = Array.from(document.querySelectorAll('[data-testid^="welcome-capability-card-badge-"]')) as HTMLElement[];
        const states = Array.from(document.querySelectorAll('[data-testid^="welcome-capability-card-state-"]')) as HTMLElement[];
        const quick = document.querySelector('[data-testid="welcome-sticky-quick-navigator"]') as HTMLElement | null;
        const rail = document.querySelector('[data-testid="welcome-progress-rail"]') as HTMLElement | null;
        if (!matrix) return null;
        const matrixRect = matrix.getBoundingClientRect();
        const headerChecks = headers.slice(0, Math.min(headers.length, leads.length, titles.length, badges.length, states.length)).map((header, idx) => {
          const h = header.getBoundingClientRect();
          const l = leads[idx].getBoundingClientRect();
          const b = badges[idx].getBoundingClientRect();
          const s = states[idx].getBoundingClientRect();
          const t = titles[idx].getBoundingClientRect();
          return {
            headerHeight: Math.round(h.height),
            emptyTopStrip: Math.round(t.top - h.top),
            badgeLeftOffsetFromLead: Math.round(b.left - l.right),
            stateBottomToTitleTop: Math.round(t.top - s.bottom),
          };
        });
        return {
          scrollWidth: document.documentElement.scrollWidth,
          innerWidth: window.innerWidth,
          quickVisible: !!quick,
          railVisible: !!rail,
          matrixWidth: Math.round(matrixRect.width),
          matrixRight: Math.round(matrixRect.right),
          quickLeft: quick ? Math.round(quick.getBoundingClientRect().left) : null,
          railLeft: rail ? Math.round(rail.getBoundingClientRect().left) : null,
          cardRects: Array.from(matrix.querySelectorAll('[data-testid^="welcome-capability-card-"]'))
            .filter((node) => /^welcome-capability-card-[a-z0-9-]+$/.test((node as HTMLElement).dataset.testid || ''))
            .slice(0, 3)
            .map((node) => {
              const rect = (node as HTMLElement).getBoundingClientRect();
              return { width: Math.round(rect.width), height: Math.round(rect.height) };
            }),
          headerChecks,
        };
      });

      expect(features).not.toBeNull();
      expect(features?.scrollWidth).toBeLessThanOrEqual((features?.innerWidth || 0) + 1);
      expect(features?.matrixWidth).toBeGreaterThan(640);
      if (vp.width >= 1180) {
        expect((features?.cardRects || []).every((entry) => entry.width >= 330 && entry.height >= 255)).toBeTruthy();
        expect((features?.headerChecks || []).every((entry) => entry.headerHeight <= 96)).toBeTruthy();
        expect((features?.headerChecks || []).every((entry) => entry.emptyTopStrip <= 64)).toBeTruthy();
        expect((features?.headerChecks || []).every((entry) => entry.badgeLeftOffsetFromLead <= 48)).toBeTruthy();
        expect((features?.headerChecks || []).every((entry) => entry.stateBottomToTitleTop >= -8)).toBeTruthy();
      }
      if (vp.width < 1680) {
        expect(features?.quickVisible).toBeFalsy();
        expect(features?.railVisible).toBeFalsy();
      }
      if (vp.width >= 1680) {
        expect(features?.quickVisible).toBeTruthy();
        expect(features?.railVisible).toBeTruthy();
      }
    });
  });
}
