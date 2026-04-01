const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Sidebar', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('initially visible', async () => {
    expect(await api.isSidebarCollapsed()).toBe(false);
  });

  test('collapse button collapses', async () => {
    await api.toggleSidebar();
    expect(await api.isSidebarCollapsed()).toBe(true);
  });

  test('button text changes on collapse', async ({ page }) => {
    await api.toggleSidebar();
    const text = await page.textContent('#collapse-btn');
    expect(text).toBe('\u203a');
  });

  test('re-expand works', async ({ page }) => {
    await api.toggleSidebar();
    await api.toggleSidebar();
    expect(await api.isSidebarCollapsed()).toBe(false);
    const text = await page.textContent('#collapse-btn');
    expect(text).toBe('\u2039');
  });

  test('progress shows correct engaged/total', async ({ page }) => {
    const text = await page.textContent('#sidebar-content');
    expect(text).toContain('7/15');
    expect(text).toContain('47%');
  });

  test('status breakdown counts are present', async ({ page }) => {
    const text = await page.textContent('#sidebar-content');
    expect(text).toContain('mastered');
    expect(text).toContain('not_started');
  });

  test('category stats correct', async ({ page }) => {
    const text = await page.textContent('#sidebar-content');
    expect(text).toContain('5/6');
    expect(text).toContain('2/6');
    expect(text).toContain('0/3');
  });

  test('priority gaps populated', async ({ page }) => {
    const gapItems = await page.$$('.gap-item');
    expect(gapItems.length).toBeGreaterThan(0);
  });

  test('gap item click selects node', async ({ page }) => {
    await page.click('.sidebar-group[data-group="stats"] .sidebar-group-header');
    const firstGap = await page.$('.gap-item[data-node]');
    if (firstGap) {
      const nodeId = await firstGap.getAttribute('data-node');
      if (nodeId) {
        await firstGap.click();
        await page.waitForTimeout(100);
        expect(await api.getSelectedNodeId()).toBe(nodeId);
      }
    }
  });

  test('legend has 6 status swatches', async ({ page }) => {
    const swatches = await page.$$('.legend-swatch');
    expect(swatches.length).toBeGreaterThanOrEqual(6);
  });

  test('legend has difficulty shapes', async ({ page }) => {
    const shapes = await page.$$('.legend-shape');
    expect(shapes.length).toBe(4);
  });

  test('recent promotions shown', async ({ page }) => {
    const evidenceItems = await page.$$('.evidence-item');
    expect(evidenceItems.length).toBeGreaterThan(0);
    const text = await page.textContent('#sidebar-content');
    expect(text).toContain('Alpha Concept');
  });
});
