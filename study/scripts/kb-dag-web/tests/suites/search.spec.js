const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Search', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('search by name', async () => {
    await api.search('Epsilon');
    const count = await api.getSearchCount();
    expect(count).toContain('1');
    expect(count).toContain('match');
  });

  test('case-insensitive search', async () => {
    await api.search('alpha');
    const count = await api.getSearchCount();
    expect(count).toContain('match');
    expect(count).not.toContain('0');
  });

  test('search by tag', async () => {
    await api.search('protocol');
    const count = await api.getSearchCount();
    expect(count).toContain('match');
    expect(count).not.toContain('0');
  });

  test('search by description', async () => {
    await api.search('isolated');
    const count = await api.getSearchCount();
    expect(count).toContain('1');
  });

  test('multiple matches', async () => {
    await api.search('concept');
    const count = await api.getSearchCount();
    const num = parseInt(count);
    expect(num).toBeGreaterThanOrEqual(1);
  });

  test('no match', async () => {
    await api.search('zzzzz');
    const count = await api.getSearchCount();
    expect(count).toContain('0');
  });

  test('clear resets search', async () => {
    await api.search('Alpha');
    await api.clearSearch();
    const count = await api.getSearchCount();
    expect(count).toBe('');
    const dimmed = await api.getDimmedCount();
    expect(dimmed).toBe(0);
  });

  test('search respects filters', async () => {
    await api.toggleCategory('fundamentals', false);
    await api.search('root');
    const count = await api.getSearchCount();
    expect(count).toContain('0');
  });

  test('debounce timing', async ({ page }) => {
    await page.evaluate(() => {
      window.__TEST__.setSearchQuery('Alpha');
    });
    const immediateCount = await api.getSearchCount();
    expect(immediateCount).toBe('');
    await page.waitForTimeout(250);
    const delayedCount = await api.getSearchCount();
    expect(delayedCount).toContain('match');
  });

  test('fit-to-matches adjusts viewport', async ({ page }) => {
    const zoomBefore = await page.evaluate(() => window.__TEST__.cy.zoom());
    await api.search('Theta');
    await page.waitForTimeout(500);
    const zoomAfter = await page.evaluate(() => window.__TEST__.cy.zoom());
    expect(zoomAfter).not.toBe(zoomBefore);
  });
});
