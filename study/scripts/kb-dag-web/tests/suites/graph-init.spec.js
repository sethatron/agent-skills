const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Graph Initialization', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('correct node count', async () => {
    expect(await api.getNodeCount()).toBe(15);
  });

  test('correct edge count', async () => {
    expect(await api.getEdgeCount()).toBe(20);
  });

  test('all nodes initially visible', async () => {
    expect(await api.getVisibleNodeCount()).toBe(15);
  });

  test('prereq edges visible between visible endpoints', async ({ page }) => {
    const count = await page.evaluate(() => {
      return window.__TEST__.cy.edges('[type="prerequisite"]').filter(
        e => e.style('display') !== 'none'
      ).length;
    });
    expect(count).toBe(14);
  });

  test('related edges initially hidden', async ({ page }) => {
    const visibleRelated = await page.evaluate(() => {
      return window.__TEST__.cy.edges('[type="related"]').filter(
        e => e.style('display') !== 'none'
      ).length;
    });
    expect(visibleRelated).toBe(0);
  });

  test('DATA.stats.total matches nodes', async () => {
    const data = await api.getData();
    expect(data.stats.total).toBe(15);
  });

  test('DATA.stats.engaged is correct', async () => {
    const data = await api.getData();
    expect(data.stats.engaged).toBe(7);
  });

  test('nameToId mapping complete', async () => {
    const mapping = await api.getNameToId();
    expect(Object.keys(mapping).length).toBe(15);
  });

  test('all 3 categories in config', async () => {
    const data = await api.getData();
    expect(data.config.categoryOrder.length).toBe(3);
  });

  test('config contains all status colors', async () => {
    const data = await api.getData();
    const colors = data.config.statusColors;
    expect(Object.keys(colors).length).toBe(6);
    expect(colors.mastered).toBe('#ffd600');
    expect(colors.not_started).toBe('#616161');
  });

  test('config contains all priority borders', async () => {
    const data = await api.getData();
    const borders = data.config.priorityBorders;
    expect(Object.keys(borders).length).toBe(4);
    expect(borders.critical.width).toBe(4);
    expect(borders.critical.color).toBe('#f44336');
  });
});
