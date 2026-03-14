const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Learning Path', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('Show Learning Path button visible when prereqs unmet', async ({ page }) => {
    await api.selectNodeByName('Iota Service');
    const btn = await page.$('.show-path-btn');
    expect(btn).not.toBeNull();
  });

  test('Show Learning Path button hidden when prereqs all met', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    const btn = await page.$('.show-path-btn');
    expect(btn).toBeNull();
  });

  test('path from Iota Service shows correct steps', async () => {
    await api.showLearningPath('Iota Service');
    const steps = await api.getPathSteps();
    expect(steps).toContain('Zeta Architecture');
    expect(steps).toContain('Eta Pattern');
    const target = await api.getPathTarget();
    expect(target).toBe('Iota Service');
  });

  test('path from Iota topo order: Zeta before Eta', async () => {
    await api.showLearningPath('Iota Service');
    const steps = await api.getPathSteps();
    const zetaIdx = steps.indexOf('Zeta Architecture');
    const etaIdx = steps.indexOf('Eta Pattern');
    expect(zetaIdx).toBeLessThan(etaIdx);
  });

  test('path panel displays step numbers and names', async ({ page }) => {
    await api.showLearningPath('Iota Service');
    const panel = await page.$('#path-panel');
    expect(panel).not.toBeNull();
    const display = await panel.evaluate(el => el.style.display);
    expect(display).toBe('block');
    const items = await page.$$('.path-step-item');
    expect(items.length).toBeGreaterThan(0);
  });

  test('path step click centers graph without clearing path', async ({ page }) => {
    await api.showLearningPath('Iota Service');
    const stepItem = await page.$('.path-step-item');
    await stepItem.click();
    await page.waitForTimeout(400);
    const active = await api.isPathActive();
    expect(active).toBe(true);
  });

  test('path target node has path-target class', async ({ page }) => {
    await api.showLearningPath('Iota Service');
    const classes = await api.getNodeClasses('Iota Service');
    expect(classes).toContain('path-target');
  });

  test('path unmet ancestors have path-step class', async ({ page }) => {
    await api.showLearningPath('Iota Service');
    const zetaClasses = await api.getNodeClasses('Zeta Architecture');
    expect(zetaClasses).toContain('path-step');
    const etaClasses = await api.getNodeClasses('Eta Pattern');
    expect(etaClasses).toContain('path-step');
  });

  test('path met ancestors have path-met class', async ({ page }) => {
    await api.showLearningPath('Iota Service');
    const alphaClasses = await api.getNodeClasses('Alpha Concept');
    expect(alphaClasses).toContain('path-met');
    const betaClasses = await api.getNodeClasses('Beta Theory');
    expect(betaClasses).toContain('path-met');
  });

  test('non-path nodes are dimmed', async () => {
    await api.showLearningPath('Iota Service');
    const dimmed = await api.getDimmedCount();
    expect(dimmed).toBeGreaterThan(0);
  });

  test('path prerequisite edges have path-edge class', async ({ page }) => {
    await api.showLearningPath('Iota Service');
    const pathEdgeCount = await page.evaluate(() =>
      window.__TEST__.cy.edges('.path-edge').length
    );
    expect(pathEdgeCount).toBeGreaterThan(0);
  });

  test('Escape clears path and closes detail panel', async ({ page }) => {
    await api.selectNodeByName('Iota Service');
    await api.showLearningPath('Iota Service');
    expect(await api.isPathActive()).toBe(true);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(100);
    expect(await api.isPathActive()).toBe(false);
    expect(await api.isDetailPanelOpen()).toBe(false);
  });

  test('Clear Path button clears path visualization', async ({ page }) => {
    await api.showLearningPath('Iota Service');
    expect(await api.isPathActive()).toBe(true);
    const clearBtn = await page.$('.path-clear-btn');
    await clearBtn.click();
    await page.waitForTimeout(100);
    expect(await api.isPathActive()).toBe(false);
  });

  test('background tap clears path', async ({ page }) => {
    await api.selectNodeByName('Iota Service');
    await api.showLearningPath('Iota Service');
    expect(await api.isPathActive()).toBe(true);
    await page.evaluate(() => window.__TEST__.cy.emit('tap'));
    await page.waitForTimeout(100);
    expect(await api.isPathActive()).toBe(false);
  });

  test('detail panel stays open during path mode', async ({ page }) => {
    await api.selectNodeByName('Iota Service');
    expect(await api.isDetailPanelOpen()).toBe(true);
    await api.showLearningPath('Iota Service');
    expect(await api.isDetailPanelOpen()).toBe(true);
    expect(await api.isPathActive()).toBe(true);
  });

  test('Show Suggested clears active path', async ({ page }) => {
    await api.selectNodeByName('Iota Service');
    await api.showLearningPath('Iota Service');
    expect(await api.isPathActive()).toBe(true);
    await api.clickSuggested();
    expect(await api.isPathActive()).toBe(false);
  });

  test('path mode cleared on new node selection', async ({ page }) => {
    await api.selectNodeByName('Iota Service');
    await api.showLearningPath('Iota Service');
    expect(await api.isPathActive()).toBe(true);
    await api.selectNodeByName('Alpha Concept');
    await page.waitForTimeout(100);
    expect(await api.isPathActive()).toBe(false);
  });

  test('path from Omicron Edge includes multiple unmet steps', async () => {
    await api.showLearningPath('Omicron Edge');
    const steps = await api.getPathSteps();
    expect(steps.length).toBeGreaterThanOrEqual(3);
    const target = await api.getPathTarget();
    expect(target).toBe('Omicron Edge');
  });
});
