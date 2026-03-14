const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Review Staleness', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
    await api.setCurrentTime('2026-03-13T00:00:00Z');
    await api.applyStalenessClasses();
    await api.renderReviewQueue();
  });

  test('Alpha Concept (800+ days) has stale-overdue class', async () => {
    const tier = await api.getStaleTier('Alpha Concept');
    expect(tier).toBe('overdue');
  });

  test('Gamma Protocol (26 days) has stale-stale class', async () => {
    const tier = await api.getStaleTier('Gamma Protocol');
    expect(tier).toBe('stale');
  });

  test('NAT (12 days) has stale-aging class', async () => {
    const tier = await api.getStaleTier('Network Address Translation (NAT)');
    expect(tier).toBe('aging');
  });

  test('Beta Theory (3 days) has no staleness class (fresh)', async () => {
    const tier = await api.getStaleTier('Beta Theory');
    expect(tier).toBe('fresh');
  });

  test('Epsilon Basics (no evidence) has no staleness class', async () => {
    const tier = await api.getStaleTier('Epsilon Basics');
    expect(tier).toBe('fresh');
  });

  test('Needs Review section shows stale topics', async ({ page }) => {
    const container = await page.$('#review-queue-container');
    const text = await container.textContent();
    expect(text).toContain('Needs Review');
    expect(text).toContain('Alpha Concept');
  });

  test('Needs Review items ordered by descending staleness', async ({ page }) => {
    const items = await page.$$eval('.review-item', els =>
      els.map(el => el.textContent)
    );
    expect(items.length).toBeGreaterThanOrEqual(2);
    expect(items[0]).toContain('Alpha Concept');
  });

  test('review item click selects node', async ({ page }) => {
    const firstItem = await page.$('.review-item');
    await firstItem.click();
    await page.waitForTimeout(400);
    const isOpen = await api.isDetailPanelOpen();
    expect(isOpen).toBe(true);
  });

  test('tooltip for stale node shows days ago text', async ({ page }) => {
    const nodePos = await page.evaluate(() => {
      const node = window.__TEST__.getNodeByName('Alpha Concept');
      const pos = node.renderedPosition();
      return { x: pos.x, y: pos.y };
    });
    const cyEl = await page.$('#cy');
    const box = await cyEl.boundingBox();
    await page.mouse.move(box.x + nodePos.x, box.y + nodePos.y);
    await page.waitForTimeout(200);
    const content = await page.textContent('#tooltip');
    expect(content).toContain('d ago');
  });

  test('tooltip for node without evidence does not show staleness text', async ({ page }) => {
    const nodePos = await page.evaluate(() => {
      const node = window.__TEST__.getNodeByName('Epsilon Basics');
      const pos = node.renderedPosition();
      return { x: pos.x, y: pos.y };
    });
    const cyEl = await page.$('#cy');
    const box = await cyEl.boundingBox();
    await page.mouse.move(box.x + nodePos.x, box.y + nodePos.y);
    await page.waitForTimeout(200);
    const content = await page.textContent('#tooltip');
    expect(content).not.toContain('d ago');
  });

  test('staleness classes persist after node selection', async () => {
    await api.selectNodeByName('Beta Theory');
    const tier = await api.getStaleTier('Alpha Concept');
    expect(tier).toBe('overdue');
  });

  test('staleness classes persist after filter changes', async () => {
    await api.toggleCategory('systems', false);
    const tier = await api.getStaleTier('Alpha Concept');
    expect(tier).toBe('overdue');
  });

  test('staleness classes NOT removed by clearSelection', async () => {
    await api.selectNodeByName('Alpha Concept');
    await api.clearSelection();
    const tier = await api.getStaleTier('Alpha Concept');
    expect(tier).toBe('overdue');
  });
});
