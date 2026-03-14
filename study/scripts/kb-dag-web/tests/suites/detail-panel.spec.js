const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Detail Panel', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('panel opens on tap', async () => {
    await api.selectNodeByName('Alpha Concept');
    expect(await api.isDetailPanelOpen()).toBe(true);
  });

  test('shows name', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const name = await page.textContent('#detail-content h2');
    expect(name).toContain('Alpha Concept');
  });

  test('shows description', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('root concept with no prerequisites');
  });

  test('shows status', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('mastered');
  });

  test('shows priority', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('critical');
  });

  test('shows difficulty stars', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('\u2605');
    expect(text).toContain('1/5');
  });

  test('shows category and subcategory', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('fundamentals');
    expect(text).toContain('basics');
  });

  test('shows prereqs as clickable links', async ({ page }) => {
    await api.selectNodeByName('Gamma Protocol');
    const prereqLink = await page.$('.prereq-link[data-node="n1"]');
    expect(prereqLink).not.toBeNull();
    const linkText = await prereqLink.textContent();
    expect(linkText).toContain('Beta Theory');
  });

  test('shows None for no prereqs', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('None');
  });

  test('shows related topics', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('Beta Theory');
  });

  test('shows tags', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const tags = await page.$$eval('.tag-pill', els => els.map(e => e.textContent));
    expect(tags).toContain('foundation');
    expect(tags).toContain('core');
  });

  test('shows source_context when set', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('test-source-alpha');
  });

  test('shows None for null source_context', async ({ page }) => {
    await api.selectNodeByName('Gamma Protocol');
    const sections = await page.$$eval('.detail-section', els =>
      els.map(e => ({ title: e.querySelector('h4')?.textContent, text: e.textContent }))
    );
    const sourceSection = sections.find(s => s.title === 'Source');
    expect(sourceSection.text).toContain('None');
  });

  test('shows resources', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('sandbox');
    expect(text).toContain('project');
  });

  test('no resources section when empty', async ({ page }) => {
    await api.selectNodeByName('Beta Theory');
    const resourceEntries = await page.$$('.resource-entry');
    expect(resourceEntries.length).toBe(0);
  });

  test('shows evidence with full fields', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('proficient');
    expect(text).toContain('mastered');
    expect(text).toContain('2024-01-15');
    expect(text).toContain('mastery-challenge');
    expect(text).toContain('Demonstrated complete mastery');
  });

  test('shows no evidence recorded', async ({ page }) => {
    await api.selectNodeByName('Epsilon Basics');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('No evidence recorded');
  });

  test('shows connections count', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const text = await page.textContent('#detail-content');
    expect(text).toContain('3 connections');
  });

  test('prereq link navigates to target', async ({ page }) => {
    await api.selectNodeByName('Gamma Protocol');
    await page.click('.prereq-link[data-node="n1"]');
    await page.waitForTimeout(100);
    const selected = await api.getSelectedNodeId();
    expect(selected).toBe('n1');
  });

  test('filtered prereq shows message', async ({ page }) => {
    await api.toggleStatus('proficient');
    await api.selectNodeByName('Gamma Protocol');
    await page.click('.prereq-link[data-node="n1"]');
    const msg = await page.$('.filtered-msg.show');
    expect(msg).not.toBeNull();
  });

  test('close button works', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    expect(await api.isDetailPanelOpen()).toBe(true);
    await page.click('#detail-close');
    expect(await api.isDetailPanelOpen()).toBe(false);
  });
});
