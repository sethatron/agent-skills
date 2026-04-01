const { test, expect } = require('@playwright/test');
const { TestAPI } = require('../helpers/test-api');

test.describe('Detail Panel Tabs', () => {
  let api;
  test.beforeEach(async ({ page }) => {
    api = new TestAPI(page);
    await page.goto('/');
    await api.waitForGraph();
  });

  test('default tab is Details', async () => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    expect(await api.getActiveDetailTab()).toBe('details');
  });

  test('clicking Guide tab switches to guide panel', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    await api.setDetailTab('guide');
    expect(await api.getActiveDetailTab()).toBe('guide');
    const guidePanel = await page.$('#tab-guide.active');
    expect(guidePanel).not.toBeNull();
  });

  test('clicking Sandbox tab switches to sandbox panel', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    await api.setDetailTab('sandbox');
    expect(await api.getActiveDetailTab()).toBe('sandbox');
    const sandboxPanel = await page.$('#tab-sandbox.active');
    expect(sandboxPanel).not.toBeNull();
  });

  test('clicking Details tab returns to details', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    await api.setDetailTab('guide');
    expect(await api.getActiveDetailTab()).toBe('guide');
    await api.setDetailTab('details');
    expect(await api.getActiveDetailTab()).toBe('details');
    const detailsPanel = await page.$('#tab-details.active');
    expect(detailsPanel).not.toBeNull();
  });

  test('Guide tab shows rendered markdown for topic with guide', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    await api.setDetailTab('guide');
    const guideText = await page.textContent('#tab-guide');
    expect(guideText).toContain('Network Address Translation');
    expect(guideText).toContain('Static NAT');
    expect(guideText).toContain('Dynamic NAT');
    const guideContent = await page.$('#tab-guide .guide-content');
    expect(guideContent).not.toBeNull();
  });

  test('Guide tab shows empty message for topic without guide', async ({ page }) => {
    await api.selectNodeByName('Beta Theory');
    await api.setDetailTab('guide');
    const guideText = await page.textContent('#tab-guide');
    expect(guideText).toContain('No guide available');
  });

  test('Guide tab has-content indicator for topic with guide', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    const guideBtn = await page.$('.detail-tab[data-tab="guide"]');
    const classes = await guideBtn.getAttribute('class');
    expect(classes).toContain('has-content');
  });

  test('Guide tab no-content style for topic without guide', async ({ page }) => {
    await api.selectNodeByName('Beta Theory');
    const guideBtn = await page.$('.detail-tab[data-tab="guide"]');
    const classes = await guideBtn.getAttribute('class');
    expect(classes).toContain('no-content');
  });

  test('Sandbox tab shows rendered markdown for topic with sandbox', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    await api.setDetailTab('sandbox');
    const sandboxText = await page.textContent('#tab-sandbox');
    expect(sandboxText).toContain('NAT Sandbox Project');
    expect(sandboxText).toContain('iptables');
    const sandboxContent = await page.$('#tab-sandbox .guide-content');
    expect(sandboxContent).not.toBeNull();
  });

  test('Sandbox tab shows empty message for topic without sandbox', async ({ page }) => {
    await api.selectNodeByName('Beta Theory');
    await api.setDetailTab('sandbox');
    const sandboxText = await page.textContent('#tab-sandbox');
    expect(sandboxText).toContain('No sandbox project available');
  });

  test('selecting different node updates all tabs', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    await api.setDetailTab('guide');
    const guideText1 = await page.textContent('#tab-guide');
    expect(guideText1).toContain('Static NAT');

    await api.selectNodeByName('Beta Theory');
    await api.setDetailTab('guide');
    const guideText2 = await page.textContent('#tab-guide');
    expect(guideText2).toContain('No guide available');
  });

  test('Sandbox tab shows download button for topic with local sandbox', async ({ page }) => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    await api.setDetailTab('sandbox');
    const btn = await page.$('#tab-sandbox .sandbox-download-btn');
    expect(btn).not.toBeNull();
    const href = await btn.getAttribute('href');
    expect(href).toBe('sandboxes/nat.tar.gz');
    const download = await btn.getAttribute('download');
    expect(download).not.toBeNull();
  });

  test('Sandbox tab does not show download button for topic without sandbox', async ({ page }) => {
    await api.selectNodeByName('Beta Theory');
    await api.setDetailTab('sandbox');
    const btn = await page.$('#tab-sandbox .sandbox-download-btn');
    expect(btn).toBeNull();
  });

  test('tab state resets to Details when selecting new node', async () => {
    await api.selectNodeByName('Network Address Translation (NAT)');
    await api.setDetailTab('guide');
    expect(await api.getActiveDetailTab()).toBe('guide');

    await api.selectNodeByName('Beta Theory');
    expect(await api.getActiveDetailTab()).toBe('details');
  });
});
