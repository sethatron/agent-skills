const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Categorical Grouping', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test.describe('Grouping toggle', () => {
    test('default mode is hierarchy with no compound nodes', async () => {
      expect(await api.getGroupingMode()).toBe('hierarchy');
      expect(await api.getCompoundNodes()).toEqual([]);
    });

    test('toggle to categorical adds compound parent nodes', async () => {
      await api.setGroupingMode('category');
      const groups = await api.getCompoundNodes();
      expect(groups.sort()).toEqual(['fundamentals', 'platforms', 'systems']);
    });

    test('toggle back to hierarchy removes compound nodes', async () => {
      await api.setGroupingMode('category');
      await api.setGroupingMode('hierarchy');
      expect(await api.getCompoundNodes()).toEqual([]);
    });

    test('grouping mode persists across filter changes', async () => {
      await api.setGroupingMode('category');
      await api.toggleStatus('not_started');
      expect(await api.getGroupingMode()).toBe('category');
      expect(await api.getCompoundNodes()).toHaveLength(3);
    });

    test('relayout works in categorical mode', async () => {
      await api.setGroupingMode('category');
      await api.clickRelayout();
      expect(await api.getCompoundNodes()).toHaveLength(3);
      expect(await api.getVisibleNodeCount()).toBe(15);
    });
  });

  test.describe('Compound node behavior', () => {
    test('fundamentals contains correct children', async ({ page }) => {
      await api.setGroupingMode('category');
      const children = await page.evaluate(() => {
        var group = window.__TEST__.cy.getElementById('group-fundamentals');
        return group.children().map(function(c) { return c.data('name'); });
      });
      expect(children.sort()).toEqual([
        'Alpha Concept', 'Beta Theory', 'Delta Advanced',
        'Epsilon Basics', 'Gamma Protocol', 'Network Address Translation (NAT)'
      ]);
    });

    test('systems contains correct children', async ({ page }) => {
      await api.setGroupingMode('category');
      const children = await page.evaluate(() => {
        var group = window.__TEST__.cy.getElementById('group-systems');
        return group.children().map(function(c) { return c.data('name'); });
      });
      expect(children.sort()).toEqual([
        'Eta Pattern', 'Iota Service', 'Kappa Framework',
        'Lambda Tool', 'Theta Principle', 'Zeta Architecture'
      ]);
    });

    test('platforms contains correct children', async ({ page }) => {
      await api.setGroupingMode('category');
      const children = await page.evaluate(() => {
        var group = window.__TEST__.cy.getElementById('group-platforms');
        return group.children().map(function(c) { return c.data('name'); });
      });
      expect(children.sort()).toEqual(['Mu Platform', 'Nu Deployment', 'Omicron Edge']);
    });

    test('compound nodes use category colors', async ({ page }) => {
      await api.setGroupingMode('category');
      const colors = await page.evaluate(() => {
        var config = window.__TEST__.data.config;
        return window.__TEST__.cy.nodes('[?isGroup]').map(function(n) {
          return {
            name: n.data('name'),
            actual: n.data('groupColor'),
            expected: config.categoryColors[n.data('name')]
          };
        });
      });
      colors.forEach(function(c) {
        expect(c.actual).toBe(c.expected);
      });
    });

    test('compound nodes are non-interactive', async ({ page }) => {
      await api.setGroupingMode('category');
      await page.evaluate(() => {
        window.__TEST__.cy.getElementById('group-fundamentals').emit('tap');
      });
      expect(await api.isDetailPanelOpen()).toBe(false);
    });
  });

  test.describe('Subcategory filtering', () => {
    test('unchecking subcategory hides only its nodes', async () => {
      await api.toggleSubcategory('fundamentals', 'advanced', false);
      expect(await api.getVisibleNodeCount()).toBe(13);
      const epsilonVis = await api.getNodeStyle('Epsilon Basics', 'display');
      expect(epsilonVis).toBe('none');
      const deltaVis = await api.getNodeStyle('Delta Advanced', 'display');
      expect(deltaVis).toBe('none');
    });

    test('unchecking category unchecks all subcategories', async ({ page }) => {
      await api.toggleCategory('fundamentals', false);
      const subcatChecks = await page.evaluate(() => {
        var checks = [];
        document.querySelectorAll('.subcat-check[data-category="fundamentals"]').forEach(function(c) {
          checks.push(c.checked);
        });
        return checks;
      });
      expect(subcatChecks.length).toBeGreaterThan(0);
      expect(subcatChecks.every(v => v === false)).toBe(true);
    });

    test('checking category checks all subcategories', async ({ page }) => {
      await api.toggleCategory('fundamentals', false);
      await api.toggleCategory('fundamentals', true);
      const subcatChecks = await page.evaluate(() => {
        var checks = [];
        document.querySelectorAll('.subcat-check[data-category="fundamentals"]').forEach(function(c) {
          checks.push(c.checked);
        });
        return checks;
      });
      expect(subcatChecks.every(v => v === true)).toBe(true);
    });

    test('subcategory filter works in both modes', async () => {
      await api.toggleSubcategory('fundamentals', 'advanced', false);
      expect(await api.getVisibleNodeCount()).toBe(13);
      await api.setGroupingMode('category');
      expect(await api.getVisibleNodeCount()).toBe(13);
    });

    test('compound node hides when all children filtered out', async ({ page }) => {
      await api.setGroupingMode('category');
      await api.toggleCategory('platforms', false);
      const groupDisplay = await page.evaluate(() => {
        return window.__TEST__.cy.getElementById('group-platforms').style('display');
      });
      expect(groupDisplay).toBe('none');
    });

    test('if all subcategories unchecked category becomes unchecked', async ({ page }) => {
      await api.toggleSubcategory('fundamentals', 'basics', false);
      await api.toggleSubcategory('fundamentals', 'advanced', false);
      const catChecked = await page.evaluate(() => {
        var check = document.querySelector('.cat-check[value="fundamentals"]');
        return check ? check.checked : null;
      });
      expect(catChecked).toBe(false);
    });

    test('re-checking subcategory re-checks category', async ({ page }) => {
      await api.toggleSubcategory('fundamentals', 'basics', false);
      await api.toggleSubcategory('fundamentals', 'advanced', false);
      await api.toggleSubcategory('fundamentals', 'basics', true);
      const catChecked = await page.evaluate(() => {
        var check = document.querySelector('.cat-check[value="fundamentals"]');
        return check ? check.checked : null;
      });
      expect(catChecked).toBe(true);
    });
  });

  test.describe('Interaction with existing features', () => {
    test('selection highlighting works in categorical mode', async ({ page }) => {
      await api.setGroupingMode('category');
      await api.selectNodeByName('Alpha Concept');
      expect(await api.isDetailPanelOpen()).toBe(true);
      const groupOpacity = await page.evaluate(() => {
        return window.__TEST__.cy.getElementById('group-fundamentals').style('opacity');
      });
      expect(parseFloat(groupOpacity)).toBe(1);
    });

    test('learning path works in categorical mode', async () => {
      await api.setGroupingMode('category');
      await api.showLearningPath('Eta Pattern');
      expect(await api.isPathActive()).toBe(true);
      expect(await api.getPathTarget()).toBe('Eta Pattern');
    });

    test('show suggested works in categorical mode', async ({ page }) => {
      await api.setGroupingMode('category');
      await api.clickSuggested();
      const suggested = await api.getSuggestedCount();
      expect(suggested).toBeGreaterThan(0);
      const groupOpacity = await page.evaluate(() => {
        return window.__TEST__.cy.getElementById('group-fundamentals').style('opacity');
      });
      expect(parseFloat(groupOpacity)).toBe(1);
    });

    test('study queue updates correctly in categorical mode', async () => {
      const hierarchyQueue = await api.getStudyQueue();
      await api.setGroupingMode('category');
      const categoryQueue = await api.getStudyQueue();
      expect(categoryQueue.length).toBe(hierarchyQueue.length);
    });
  });
});
