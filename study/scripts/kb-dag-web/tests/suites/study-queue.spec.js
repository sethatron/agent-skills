const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Study Queue', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('queue renders on page load with items', async ({ page }) => {
    const container = await page.$('#study-queue-container');
    expect(container).not.toBeNull();
    const items = await page.$$('.study-queue-item');
    expect(items.length).toBeGreaterThan(0);
  });

  test('queue contains Zeta Architecture', async () => {
    const queue = await api.getStudyQueue();
    const names = queue.map(i => i.name);
    expect(names).toContain('Zeta Architecture');
  });

  test('queue contains Lambda Tool', async () => {
    const queue = await api.getStudyQueue();
    const names = queue.map(i => i.name);
    expect(names).toContain('Lambda Tool');
  });

  test('queue contains NAT as ready for scenario', async () => {
    const queue = await api.getStudyQueue();
    const nat = queue.find(i => i.name === 'Network Address Translation (NAT)');
    expect(nat).toBeDefined();
    expect(nat.rationale).toContain('SCENARIO');
  });

  test('queue item click selects node and opens detail panel', async ({ page }) => {
    const firstItem = await page.$('.study-queue-item');
    await firstItem.click();
    await page.waitForTimeout(400);
    const isOpen = await api.isDetailPanelOpen();
    expect(isOpen).toBe(true);
    const selectedId = await api.getSelectedNodeId();
    expect(selectedId).not.toBeNull();
  });

  test('queue updates when category filter hides a topic', async () => {
    const queueBefore = await api.getStudyQueue();
    const hadZeta = queueBefore.some(i => i.name === 'Zeta Architecture');
    expect(hadZeta).toBe(true);

    await api.toggleCategory('systems', false);

    const queueAfter = await api.getStudyQueue();
    const hasZeta = queueAfter.some(i => i.name === 'Zeta Architecture');
    expect(hasZeta).toBe(false);
  });

  test('queue shows "All caught up!" when all topics filtered out', async ({ page }) => {
    await page.evaluate(() => {
      document.querySelectorAll('.cat-check').forEach(c => { c.checked = false; });
      document.querySelectorAll('.cat-check')[0].dispatchEvent(new Event('change'));
    });
    await page.waitForTimeout(100);
    const text = await page.textContent('#study-queue-container');
    expect(text).toContain('All caught up!');
  });

  test('queue does not include topics with unmet prerequisites', async () => {
    const queue = await api.getStudyQueue();
    const names = queue.map(i => i.name);
    expect(names).not.toContain('Kappa Framework');
    expect(names).not.toContain('Eta Pattern');
  });

  test('queue returns max 5 items', async () => {
    const queue = await api.getStudyQueue();
    expect(queue.length).toBeLessThanOrEqual(5);
  });
});
