const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Mode Recommendations', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('not_started topic shows LEARN mode badge', async () => {
    const mode = await api.getRecommendedMode('Zeta Architecture');
    expect(mode.label).toBe('LEARN');
  });

  test('exposed topic shows LEARN / QUIZ mode badge', async () => {
    const mode = await api.getRecommendedMode('Lambda Tool');
    expect(mode.label).toBe('LEARN / QUIZ');
  });

  test('conceptual topic shows SCENARIO mode badge', async () => {
    const mode = await api.getRecommendedMode('Network Address Translation (NAT)');
    expect(mode.label).toBe('SCENARIO');
  });

  test('applied topic shows MASTERY CHALLENGE mode badge', async () => {
    const mode = await api.getRecommendedMode('Gamma Protocol');
    expect(mode.label).toBe('MASTERY CHALLENGE');
  });

  test('proficient topic shows MASTERY CHALLENGE mode badge', async () => {
    const mode = await api.getRecommendedMode('Beta Theory');
    expect(mode.label).toBe('MASTERY CHALLENGE');
  });

  test('mastered topic shows COMPLETE badge', async () => {
    const mode = await api.getRecommendedMode('Alpha Concept');
    expect(mode.label).toBe('COMPLETE');
  });

  test('prerequisites fully met shows green text', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    const bar = await page.$('.prereq-bar.met');
    expect(bar).not.toBeNull();
    const text = await bar.textContent();
    expect(text).toContain('1/1 met');
  });

  test('prerequisites partially met shows amber text with unmet list', async ({ page }) => {
    await api.selectNodeByName('Omicron Edge');
    const bar = await page.$('.prereq-bar.partial');
    expect(bar).not.toBeNull();
    const text = await bar.textContent();
    expect(text).toContain('met');
  });

  test('no prerequisites shows "No prerequisites" text', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const bar = await page.$('.prereq-bar');
    const text = await bar.textContent();
    expect(text).toContain('No prerequisites');
  });

  test('unmet prereqs replaces mode badge with unlock message', async ({ page }) => {
    await api.selectNodeByName('Iota Service');
    const text = await page.textContent('.next-steps');
    expect(text).toContain('Unlock prerequisites first');
    const badge = await page.$('.next-steps .mode-badge');
    expect(badge).toBeNull();
  });

  test('CLI hint shows correct command format', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    const hint = await page.$('.cli-hint');
    expect(hint).not.toBeNull();
    const text = await hint.textContent();
    expect(text).toContain('study scenario');
    expect(text).toContain('"Network Address Translation (NAT)"');
  });

  test('CLI hint hidden for mastered topics', async ({ page }) => {
    await api.selectNodeByName('Alpha Concept');
    const hint = await page.$('.cli-hint');
    expect(hint).toBeNull();
  });

  test('prereq link click navigates to target node', async ({ page }) => {
    await api.selectNodeByName('Iota Service');
    const link = await page.$('.next-steps .prereq-link');
    expect(link).not.toBeNull();
    await link.click();
    await page.waitForTimeout(500);
    const selected = await api.getSelectedNodeId();
    expect(selected).not.toBeNull();
    const isOpen = await api.isDetailPanelOpen();
    expect(isOpen).toBe(true);
  });

  test('prereq readiness returns correct counts', async () => {
    const readiness = await api.getPrereqReadiness('Zeta Architecture');
    expect(readiness.total).toBe(2);
    expect(readiness.met).toBe(2);
    expect(readiness.unmetList).toHaveLength(0);
  });

  test('prereq readiness identifies unmet prereqs', async () => {
    const readiness = await api.getPrereqReadiness('Omicron Edge');
    expect(readiness.total).toBe(2);
    expect(readiness.met).toBeLessThan(readiness.total);
    expect(readiness.unmetList.length).toBeGreaterThan(0);
  });
});
