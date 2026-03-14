const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Actions', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('zoom in increases zoom level', async ({ page }) => {
    const before = await page.evaluate(() => window.__TEST__.cy.zoom());
    await page.click('[data-action="zoomin"]');
    const after = await page.evaluate(() => window.__TEST__.cy.zoom());
    expect(after).toBeGreaterThan(before);
  });

  test('zoom out decreases zoom level', async ({ page }) => {
    const before = await page.evaluate(() => window.__TEST__.cy.zoom());
    await page.click('[data-action="zoomout"]');
    const after = await page.evaluate(() => window.__TEST__.cy.zoom());
    expect(after).toBeLessThan(before);
  });

  test('fit resets view', async ({ page }) => {
    await page.click('[data-action="zoomin"]');
    await page.click('[data-action="zoomin"]');
    const zoomed = await page.evaluate(() => window.__TEST__.cy.zoom());
    await page.click('[data-action="fit"]');
    await page.waitForTimeout(500);
    const after = await page.evaluate(() => window.__TEST__.cy.zoom());
    expect(after).not.toBe(zoomed);
  });

  test('related toggle shows edges', async ({ page }) => {
    await api.clickToggleRelated();
    expect(await api.getShowRelated()).toBe(true);
    const visibleRelated = await page.evaluate(() => {
      return window.__TEST__.cy.edges('[type="related"]').filter(
        e => e.style('display') !== 'none'
      ).length;
    });
    expect(visibleRelated).toBeGreaterThan(0);
  });

  test('related toggle hides edges again', async ({ page }) => {
    await api.clickToggleRelated();
    await api.clickToggleRelated();
    expect(await api.getShowRelated()).toBe(false);
    const visibleRelated = await page.evaluate(() => {
      return window.__TEST__.cy.edges('[type="related"]').filter(
        e => e.style('display') !== 'none'
      ).length;
    });
    expect(visibleRelated).toBe(0);
  });

  test('toggle button gets active class', async ({ page }) => {
    await api.clickToggleRelated();
    const hasActive = await page.evaluate(() =>
      document.getElementById('btn-related').classList.contains('active')
    );
    expect(hasActive).toBe(true);
  });

  test('relayout preserves graph', async () => {
    await api.clickRelayout();
    expect(await api.getNodeCount()).toBe(15);
  });

  test('export produces valid data URI', async ({ page }) => {
    const dataUri = await page.evaluate(() => {
      return window.__TEST__.cy.png({ full: true, scale: 1, bg: '#1a1a2e' });
    });
    expect(dataUri).toMatch(/^data:image\/png/);
  });

  test('sidebar fit button works', async ({ page }) => {
    await page.click('[data-action="zoomin"]');
    await page.click('[data-action="zoomin"]');
    const zoomed = await page.evaluate(() => window.__TEST__.cy.zoom());
    await page.click('#btn-fit');
    await page.waitForTimeout(500);
    const after = await page.evaluate(() => window.__TEST__.cy.zoom());
    expect(after).not.toBe(zoomed);
  });
});
