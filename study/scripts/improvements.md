# DAG Visualizer — Future Improvements

## 1. "Ready to Study" Filter Enhancement

The existing "Show Suggested" button finds topics where `status ∈ {not_started, exposed}` and `priority ∈ {critical, high}` with all direct prerequisites `≥ conceptual`. Enhance to also show WHY a topic is suggested — tooltip listing which prerequisites are met and which are blocking.

## 2. Resource-Type Filters

Add filter buttons for "Has Sandbox" and "Has Guide" (`source_context` ends in `.md`). Becomes more useful as resource coverage grows across the 221 topics.

## 3. Heat Map Mode Toggle

Re-color nodes by different dimensions instead of always by status:
- Difficulty (1-5 gradient)
- Priority (critical→low gradient)
- Connection count (hub detection)

Adds analytical value for identifying clusters of hard topics or high-connectivity hubs.

## 4. Mini-Map

Small overview panel in corner showing the full graph with a viewport rectangle. Cytoscape has a `cytoscape-navigator` extension. Helps orientation when zoomed into dense areas of a 221-node graph.

## 5. Subcategory Compound Nodes

Nested compound nodes: category → subcategory → topics. More granular grouping than category-only. Trade-off: adds visual complexity with nested boundaries. May be worth it for categories with many subcategories (e.g., `identity` has 56 topics across multiple subcategories).

## 6. URL State Persistence

Encode active filters, zoom level, and selected node in URL hash. Allows sharing/bookmarking specific views of the DAG (e.g., "show me only critical networking topics").
