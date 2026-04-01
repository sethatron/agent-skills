class TestAPI {
  constructor(page) {
    this.page = page;
  }

  async waitForGraph() {
    await this.page.waitForFunction(
      () => window.__TEST__ && window.__TEST__.getNodeCount() > 0,
      { timeout: 10000 }
    );
  }

  async getNodeCount() {
    return this.page.evaluate(() => window.__TEST__.getNodeCount());
  }

  async getEdgeCount() {
    return this.page.evaluate(() => window.__TEST__.getEdgeCount());
  }

  async getVisibleNodeCount() {
    return this.page.evaluate(() => window.__TEST__.getVisibleNodes().length);
  }

  async getVisibleEdgeCount() {
    return this.page.evaluate(() => window.__TEST__.getVisibleEdges().length);
  }

  async getSelectedNodeId() {
    return this.page.evaluate(() => window.__TEST__.getSelectedNodeId());
  }

  async getShowRelated() {
    return this.page.evaluate(() => window.__TEST__.getShowRelated());
  }

  async isDetailPanelOpen() {
    return this.page.evaluate(() => window.__TEST__.isDetailPanelOpen());
  }

  async isSidebarCollapsed() {
    return this.page.evaluate(() => window.__TEST__.isSidebarCollapsed());
  }

  async isEmptyStateVisible() {
    return this.page.evaluate(() => window.__TEST__.isEmptyStateVisible());
  }

  async getSearchCount() {
    return this.page.evaluate(() => window.__TEST__.getSearchCount());
  }

  async getNodeData(name) {
    return this.page.evaluate((n) => {
      const node = window.__TEST__.getNodeByName(n);
      return node && node.length ? node.data() : null;
    }, name);
  }

  async getNodeStyle(name, prop) {
    return this.page.evaluate(({ n, p }) => {
      const node = window.__TEST__.getNodeByName(n);
      return node && node.length ? node.style(p) : null;
    }, { n: name, p: prop });
  }

  async getNodeClasses(name) {
    return this.page.evaluate((n) => {
      const node = window.__TEST__.getNodeByName(n);
      return node && node.length ? node.classes() : [];
    }, name);
  }

  async getHighlightedCount() {
    return this.page.evaluate(() => window.__TEST__.getHighlightedNodes().length);
  }

  async getDimmedCount() {
    return this.page.evaluate(() => window.__TEST__.getDimmedNodes().length);
  }

  async getSuggestedCount() {
    return this.page.evaluate(() => window.__TEST__.getSuggestedNodes().length);
  }

  async getAncestorNames() {
    return this.page.evaluate(() =>
      window.__TEST__.getAncestorNodes().map(n => n.data('name'))
    );
  }

  async getAncestorNeededNames() {
    return this.page.evaluate(() =>
      window.__TEST__.getAncestorNeededNodes().map(n => n.data('name'))
    );
  }

  async getDescendantNames() {
    return this.page.evaluate(() =>
      window.__TEST__.getDescendantNodes().map(n => n.data('name'))
    );
  }

  async selectNodeByName(name) {
    await this.page.evaluate((n) => {
      const id = window.__TEST__.nameToId()[n];
      if (id) window.__TEST__.selectNode(id);
    }, name);
  }

  async clearSelection() {
    await this.page.evaluate(() => window.__TEST__.clearSelection());
  }

  async search(query) {
    await this.page.evaluate((q) => window.__TEST__.setSearchQuery(q), query);
    await this.page.waitForTimeout(250);
  }

  async clearSearch() {
    await this.page.evaluate(() => window.__TEST__.clearSearch());
  }

  async toggleCategory(name, checked) {
    await this.page.evaluate(({ n, c }) => window.__TEST__.toggleCategory(n, c), { n: name, c: checked });
  }

  async toggleStatus(status) {
    await this.page.evaluate((s) => window.__TEST__.toggleStatus(s), status);
  }

  async togglePriority(priority) {
    await this.page.evaluate((p) => window.__TEST__.togglePriority(p), priority);
  }

  async clickSuggested() {
    await this.page.evaluate(() => window.__TEST__.clickSuggested());
  }

  async clickToggleRelated() {
    await this.page.evaluate(() => window.__TEST__.clickToggleRelated());
  }

  async clickRelayout() {
    await this.page.evaluate(() => window.__TEST__.clickRelayout());
  }

  async clickFitAll() {
    await this.page.evaluate(() => window.__TEST__.clickFitAll());
  }

  async toggleSidebar() {
    await this.page.evaluate(() => window.__TEST__.toggleSidebar());
  }

  async getData() {
    return this.page.evaluate(() => window.__TEST__.data);
  }

  async getNameToId() {
    return this.page.evaluate(() => window.__TEST__.nameToId());
  }

  async getStudyQueue() {
    return this.page.evaluate(() => window.__TEST__.getStudyQueue());
  }

  async getRecommendedMode(name) {
    return this.page.evaluate((n) => {
      const id = window.__TEST__.nameToId()[n];
      return id ? window.__TEST__.getRecommendedMode(id) : null;
    }, name);
  }

  async getPrereqReadiness(name) {
    return this.page.evaluate((n) => {
      const id = window.__TEST__.nameToId()[n];
      return id ? window.__TEST__.getPrereqReadiness(id) : null;
    }, name);
  }

  async isPathActive() {
    return this.page.evaluate(() => window.__TEST__.isPathActive());
  }

  async getPathSteps() {
    return this.page.evaluate(() => window.__TEST__.getPathSteps());
  }

  async getPathTarget() {
    return this.page.evaluate(() => window.__TEST__.getPathTarget());
  }

  async showLearningPath(name) {
    await this.page.evaluate((n) => {
      const id = window.__TEST__.nameToId()[n];
      if (id) window.__TEST__.showLearningPath(id);
    }, name);
  }

  async clearPath() {
    await this.page.evaluate(() => window.__TEST__.clearPath());
  }

  async getStaleTier(name) {
    return this.page.evaluate((n) => {
      const id = window.__TEST__.nameToId()[n];
      return id ? window.__TEST__.getStaleTier(id) : null;
    }, name);
  }

  async setCurrentTime(isoString) {
    await this.page.evaluate((t) => window.__TEST__.setCurrentTime(t), isoString);
  }

  async applyStalenessClasses() {
    await this.page.evaluate(() => window.__TEST__.applyStalenessClasses());
  }

  async renderReviewQueue() {
    await this.page.evaluate(() => window.__TEST__.renderReviewQueue());
  }

  async getGroupingMode() {
    return this.page.evaluate(() => window.__TEST__.getGroupingMode());
  }

  async setGroupingMode(mode) {
    await this.page.evaluate((m) => window.__TEST__.setGroupingMode(m), mode);
  }

  async getCompoundNodes() {
    return this.page.evaluate(() => window.__TEST__.getCompoundNodes());
  }

  async toggleSubcategory(cat, sub, checked) {
    await this.page.evaluate(({c, s, v}) =>
      window.__TEST__.toggleSubcategory(c, s, v), {c: cat, s: sub, v: checked});
  }

  async getActiveDetailTab() {
    return this.page.evaluate(() => window.__TEST__.getActiveDetailTab());
  }

  async setDetailTab(tab) {
    await this.page.evaluate((t) => window.__TEST__.setDetailTab(t), tab);
  }

  async hasGuideContent(name) {
    return this.page.evaluate((n) => {
      var node = window.__TEST__.getNodeByName(n);
      return node && node.length ? !!node.data('guideContent') : false;
    }, name);
  }

  async hasSandboxContent(name) {
    return this.page.evaluate((n) => {
      var node = window.__TEST__.getNodeByName(n);
      return node && node.length ? !!node.data('sandboxContent') : false;
    }, name);
  }
}

module.exports = { TestAPI };
