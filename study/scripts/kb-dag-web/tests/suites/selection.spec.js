const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Selection and Highlighting', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('tap sets selectedNodeId', async () => {
    await api.selectNodeByName('Gamma Protocol');
    const mapping = await api.getNameToId();
    expect(await api.getSelectedNodeId()).toBe(mapping['Gamma Protocol']);
  });

  test('selected node gets highlighted class', async () => {
    await api.selectNodeByName('Gamma Protocol');
    const classes = await api.getNodeClasses('Gamma Protocol');
    expect(classes).toContain('highlighted');
  });

  test('met ancestors get ancestor class', async () => {
    await api.selectNodeByName('Gamma Protocol');
    const ancestors = await api.getAncestorNames();
    expect(ancestors).toContain('Alpha Concept');
    expect(ancestors).toContain('Beta Theory');
  });

  test('unmet ancestors get ancestor-needed class', async ({ page }) => {
    await api.selectNodeByName('Iota Service');
    const needed = await api.getAncestorNeededNames();
    expect(needed.length).toBeGreaterThan(0);
  });

  test('descendants get descendant class', async () => {
    await api.selectNodeByName('Alpha Concept');
    const descendants = await api.getDescendantNames();
    expect(descendants).toContain('Beta Theory');
    expect(descendants).toContain('Gamma Protocol');
    expect(descendants.length).toBeGreaterThan(2);
  });

  test('non-involved get dimmed', async () => {
    await api.selectNodeByName('Theta Principle');
    const dimmed = await api.getDimmedCount();
    expect(dimmed).toBeGreaterThan(0);
  });

  test('path edges get path-edge class', async ({ page }) => {
    await api.selectNodeByName('Gamma Protocol');
    const pathEdgeCount = await page.evaluate(() => {
      return window.__TEST__.cy.edges('.path-edge').length;
    });
    expect(pathEdgeCount).toBeGreaterThan(0);
  });

  test('background tap clears selection', async ({ page }) => {
    await api.selectNodeByName('Gamma Protocol');
    expect(await api.getSelectedNodeId()).not.toBeNull();
    await page.evaluate(() => window.__TEST__.cy.emit('tap'));
    expect(await api.getSelectedNodeId()).toBeNull();
  });

  test('Escape clears selection', async ({ page }) => {
    await api.selectNodeByName('Gamma Protocol');
    expect(await api.getSelectedNodeId()).not.toBeNull();
    await page.keyboard.press('Escape');
    expect(await api.getSelectedNodeId()).toBeNull();
  });

  test('detail close clears selection', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    expect(await api.isDetailPanelOpen()).toBe(true);
    await page.click('#detail-close');
    expect(await api.isDetailPanelOpen()).toBe(false);
    expect(await api.getSelectedNodeId()).toBeNull();
  });

  test('re-select clears previous highlighting', async () => {
    await api.selectNodeByName('Gamma Protocol');
    await api.selectNodeByName('Alpha Concept');
    const classes = await api.getNodeClasses('Alpha Concept');
    expect(classes).toContain('highlighted');
    const gammaClasses = await api.getNodeClasses('Gamma Protocol');
    expect(gammaClasses).not.toContain('highlighted');
  });

  test('related edges pollute ancestor traversal', async () => {
    await api.selectNodeByName('Lambda Tool');
    const ancestors = await api.getAncestorNames();
    const ancestorNeeded = await api.getAncestorNeededNames();
    const allAncestors = [...ancestors, ...ancestorNeeded];
    expect(allAncestors).toContain('Alpha Concept');
    expect(allAncestors).not.toContain('Kappa Framework');
    expect(allAncestors).not.toContain('Delta Advanced');
  });
});
