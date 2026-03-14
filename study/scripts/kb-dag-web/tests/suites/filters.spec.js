const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Filters', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('uncheck category hides nodes', async () => {
    await api.toggleCategory('fundamentals', false);
    expect(await api.getVisibleNodeCount()).toBe(9);
  });

  test('cat-none hides all', async ({ page }) => {
    await page.click('#cat-none');
    expect(await api.getVisibleNodeCount()).toBe(0);
  });

  test('cat-all shows all after none', async ({ page }) => {
    await page.click('#cat-none');
    await page.click('#cat-all');
    expect(await api.getVisibleNodeCount()).toBe(15);
  });

  test('status toggle hides matching nodes', async () => {
    await api.toggleStatus('not_started');
    expect(await api.getVisibleNodeCount()).toBe(7);
  });

  test('multiple status filters', async () => {
    await api.toggleStatus('not_started');
    await api.toggleStatus('exposed');
    expect(await api.getVisibleNodeCount()).toBe(4);
  });

  test('priority toggle hides matching nodes', async () => {
    await api.togglePriority('low');
    expect(await api.getVisibleNodeCount()).toBe(13);
  });

  test('AND-combination filters', async () => {
    await api.toggleCategory('systems', false);
    await api.toggleCategory('platforms', false);
    await api.toggleStatus('proficient');
    await api.toggleStatus('applied');
    await api.toggleStatus('conceptual');
    await api.toggleStatus('exposed');
    await api.toggleStatus('not_started');
    expect(await api.getVisibleNodeCount()).toBe(1);
    const data = await api.getNodeData('Alpha Concept');
    expect(data).not.toBeNull();
  });

  test('edge visibility follows nodes', async ({ page }) => {
    await api.toggleCategory('fundamentals', false);
    const alphaEdges = await page.evaluate(() => {
      return window.__TEST__.cy.edges().filter(e => {
        return (e.source().data('name') === 'Alpha Concept' || e.target().data('name') === 'Alpha Concept') &&
          e.style('display') !== 'none';
      }).length;
    });
    expect(alphaEdges).toBe(0);
  });

  test('related edges respect showRelated', async ({ page }) => {
    await api.clickToggleRelated();
    const visibleRelated = await page.evaluate(() => {
      return window.__TEST__.cy.edges('[type="related"]').filter(
        e => e.style('display') !== 'none'
      ).length;
    });
    expect(visibleRelated).toBeGreaterThan(0);
  });

  test('selected node cleared when filtered out', async () => {
    await api.selectNodeByName('Gamma Protocol');
    expect(await api.getSelectedNodeId()).not.toBeNull();
    await api.toggleStatus('applied');
    expect(await api.getSelectedNodeId()).toBeNull();
  });

  test('empty state appears when all filtered', async ({ page }) => {
    await page.click('#cat-none');
    expect(await api.isEmptyStateVisible()).toBe(true);
  });

  test('empty state disappears when filter restored', async ({ page }) => {
    await page.click('#cat-none');
    await page.click('#cat-all');
    expect(await api.isEmptyStateVisible()).toBe(false);
  });

  test('category label click fits to category', async ({ page }) => {
    const zoomBefore = await page.evaluate(() => window.__TEST__.cy.zoom());
    await page.click('.cat-label[data-cat="fundamentals"]');
    await page.waitForTimeout(500);
    const zoomAfter = await page.evaluate(() => window.__TEST__.cy.zoom());
    expect(zoomAfter).not.toBe(zoomBefore);
  });
});
