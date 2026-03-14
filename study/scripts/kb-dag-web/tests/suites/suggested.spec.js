const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Suggested Topics', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('identifies correct suggested topics', async ({ page }) => {
    await api.clickSuggested();
    const suggestedNames = await page.evaluate(() =>
      window.__TEST__.getSuggestedNodes().map(n => n.data('name'))
    );
    expect(suggestedNames).toContain('Zeta Architecture');
  });

  test('non-suggested get dimmed', async () => {
    await api.clickSuggested();
    const dimmed = await api.getDimmedCount();
    expect(dimmed).toBeGreaterThan(0);
  });

  test('unmet prereq excludes from suggested', async ({ page }) => {
    await api.clickSuggested();
    const suggestedNames = await page.evaluate(() =>
      window.__TEST__.getSuggestedNodes().map(n => n.data('name'))
    );
    expect(suggestedNames).not.toContain('Kappa Framework');
  });

  test('respects category filters', async ({ page }) => {
    await api.toggleCategory('systems', false);
    await api.clickSuggested();
    const suggestedNames = await page.evaluate(() =>
      window.__TEST__.getSuggestedNodes().map(n => n.data('name'))
    );
    expect(suggestedNames).not.toContain('Zeta Architecture');
  });

  test('Lambda incorrectly excluded due to related-edge traversal bug', async ({ page }) => {
    await api.clickSuggested();
    const suggestedNames = await page.evaluate(() =>
      window.__TEST__.getSuggestedNodes().map(n => n.data('name'))
    );
    expect(suggestedNames).toContain('Lambda Tool');
  });
});
