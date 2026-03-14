const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Edge Cases', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('isolated node has 0 connections', async () => {
    const data = await api.getNodeData('Theta Principle');
    expect(data.connections).toBe(0);
  });

  test('isolated node dims everything else', async () => {
    await api.selectNodeByName('Theta Principle');
    const ancestors = await api.getAncestorNames();
    const descendants = await api.getDescendantNames();
    expect(ancestors.length).toBe(0);
    expect(descendants.length).toBe(0);
    const dimmed = await api.getDimmedCount();
    expect(dimmed).toBeGreaterThan(0);
  });

  test('alias node exists in nameToId', async () => {
    const mapping = await api.getNameToId();
    expect(mapping['Network Address Translation (NAT)']).toBeDefined();
  });

  test('NAT alias resolves in prereq edges', async ({ page }) => {
    const hasEdge = await page.evaluate(() => {
      const edges = window.__TEST__.cy.edges('[type="prerequisite"]');
      return edges.some(e => {
        const src = e.source().data('name');
        const tgt = e.target().data('name');
        return src === 'Network Address Translation (NAT)' && tgt === 'Zeta Architecture';
      });
    });
    expect(hasEdge).toBe(true);
  });

  test('multi-prereq in detail panel', async ({ page }) => {
    await api.selectNodeByName('Omicron Edge');
    const prereqLinks = await page.$$eval('.prereq-link', els =>
      els.map(e => e.textContent)
    );
    expect(prereqLinks).toContain('Nu Deployment');
    expect(prereqLinks).toContain('Kappa Framework');
  });

  test('deep chain ancestors (4 levels)', async () => {
    await api.selectNodeByName('Kappa Framework');
    const ancestors = await api.getAncestorNames();
    const needed = await api.getAncestorNeededNames();
    const all = [...ancestors, ...needed];
    expect(all).toContain('Alpha Concept');
    expect(all).toContain('Beta Theory');
    expect(all).toContain('Gamma Protocol');
    expect(all).toContain('Delta Advanced');
  });

  test('node sizes differ by connectivity', async () => {
    const zeta = await api.getNodeData('Zeta Architecture');
    const theta = await api.getNodeData('Theta Principle');
    expect(zeta.size).toBe(50);
    expect(theta.size).toBe(30);
  });

  test('rapid filter toggling stays consistent', async () => {
    for (let i = 0; i < 10; i++) {
      await api.toggleStatus('not_started');
    }
    expect(await api.getVisibleNodeCount()).toBe(15);
  });

  test('tooltip shows on hover', async ({ page }) => {
    const nodePos = await page.evaluate(() => {
      const node = window.__TEST__.getNodeByName('Alpha Concept');
      const pos = node.renderedPosition();
      return { x: pos.x, y: pos.y };
    });
    const cyEl = await page.$('#cy');
    const box = await cyEl.boundingBox();
    await page.mouse.move(box.x + nodePos.x, box.y + nodePos.y);
    await page.waitForTimeout(200);
    const display = await page.evaluate(() =>
      document.getElementById('tooltip').style.display
    );
    expect(display).toBe('block');
  });

  test('tooltip hides on mouseout', async ({ page }) => {
    const nodePos = await page.evaluate(() => {
      const node = window.__TEST__.getNodeByName('Alpha Concept');
      const pos = node.renderedPosition();
      return { x: pos.x, y: pos.y };
    });
    const cyEl = await page.$('#cy');
    const box = await cyEl.boundingBox();
    await page.mouse.move(box.x + nodePos.x, box.y + nodePos.y);
    await page.waitForTimeout(200);
    await page.mouse.move(box.x + box.width - 10, box.y + box.height - 10);
    await page.waitForTimeout(300);
    const display = await page.evaluate(() =>
      document.getElementById('tooltip').style.display
    );
    expect(display).toBe('none');
  });

  test('tooltip content is correct', async ({ page }) => {
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
    expect(content).toContain('Alpha Concept');
    expect(content).toContain('mastered');
    expect(content).toContain('critical');
  });

  test('tooltip negative positioning near top-left', async ({ page }) => {
    const nodePos = await page.evaluate(() => {
      const node = window.__TEST__.getNodeByName('Alpha Concept');
      node.renderedPosition({ x: 5, y: 5 });
      const pos = node.renderedPosition();
      return { x: pos.x, y: pos.y };
    });
    const cyEl = await page.$('#cy');
    const box = await cyEl.boundingBox();
    await page.mouse.move(box.x + nodePos.x, box.y + nodePos.y);
    await page.waitForTimeout(200);
    const left = await page.evaluate(() =>
      parseInt(document.getElementById('tooltip').style.left)
    );
    const top = await page.evaluate(() =>
      parseInt(document.getElementById('tooltip').style.top)
    );
    expect(left).toBeGreaterThanOrEqual(0);
    expect(top).toBeGreaterThanOrEqual(0);
  });

  test('has-resources with double border', async () => {
    const borderStyle = await api.getNodeStyle('Alpha Concept', 'border-style');
    expect(borderStyle).toBe('double');
  });
});
