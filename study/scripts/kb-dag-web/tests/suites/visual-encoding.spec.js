const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgb(${r},${g},${b})`;
}

test.describe('Visual Encoding', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test.describe('Status colors', () => {
    const cases = [
      ['Alpha Concept', 'mastered', '#ffd600'],
      ['Beta Theory', 'proficient', '#9c27b0'],
      ['Gamma Protocol', 'applied', '#4caf50'],
      ['Network Address Translation (NAT)', 'conceptual', '#2196f3'],
      ['Delta Advanced', 'exposed', '#4fc3f7'],
      ['Epsilon Basics', 'not_started', '#616161'],
    ];
    for (const [name, status, color] of cases) {
      test(`${status} → ${color}`, async () => {
        const bg = await api.getNodeStyle(name, 'background-color');
        expect(bg).toBe(hexToRgb(color));
      });
    }
  });

  test.describe('Priority borders', () => {
    const cases = [
      ['Alpha Concept', 'critical', 4, '#f44336'],
      ['Beta Theory', 'high', 3, '#ff9800'],
      ['Delta Advanced', 'medium', 2, '#78909c'],
      ['Epsilon Basics', 'low', 1, '#546e7a'],
    ];
    for (const [name, priority, width, color] of cases) {
      test(`${priority} → width ${width}, color ${color}`, async () => {
        const bw = await api.getNodeStyle(name, 'border-width');
        const bc = await api.getNodeStyle(name, 'border-color');
        expect(parseFloat(bw)).toBe(width);
        expect(bc).toBe(hexToRgb(color));
      });
    }
  });

  test.describe('Difficulty shapes', () => {
    const cases = [
      ['Alpha Concept', 1, 'ellipse'],
      ['Gamma Protocol', 3, 'roundrectangle'],
      ['Delta Advanced', 4, 'diamond'],
      ['Theta Principle', 5, 'star'],
    ];
    for (const [name, diff, shape] of cases) {
      test(`difficulty ${diff} → ${shape}`, async () => {
        const s = await api.getNodeStyle(name, 'shape');
        expect(s).toBe(shape);
      });
    }
  });

  test('has-resources class on Alpha', async () => {
    const classes = await api.getNodeClasses('Alpha Concept');
    expect(classes).toContain('has-resources');
  });

  test('no has-resources class on Beta', async () => {
    const classes = await api.getNodeClasses('Beta Theory');
    expect(classes).not.toContain('has-resources');
  });

  test('node size scales with connectivity', async () => {
    const zetaData = await api.getNodeData('Zeta Architecture');
    const thetaData = await api.getNodeData('Theta Principle');
    expect(zetaData.size).toBe(50);
    expect(thetaData.size).toBe(30);
    expect(zetaData.size).toBeGreaterThan(thetaData.size);
  });
});
