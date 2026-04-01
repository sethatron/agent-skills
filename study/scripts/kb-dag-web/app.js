(function() {

var COLORS = {
    bgPrimary: '#1a1a2e',
    bgSecondary: '#16213e',
    bgTertiary: '#0f3460',
    bgHover: '#1a1a4e',
    textPrimary: '#e0e0e0',
    textSecondary: '#78909c',
    textAccent: '#29b6f6',
    textDanger: '#f44336',
    colorSuccess: '#4caf50',
    colorResource: '#4fc3f7',
    borderPrimary: '#0f3460',
    nodeDefault: '#616161',
    statusNotStarted: '#616161',
    statusExposed: '#4fc3f7',
    statusConceptual: '#2196f3',
    statusApplied: '#4caf50',
    statusProficient: '#9c27b0',
    statusMastered: '#ffd600',
    priorityCritical: '#f44336',
    priorityHigh: '#ff9800',
    priorityMedium: '#78909c',
    priorityLow: '#546e7a',
    edgePrereq: '#455a64',
    edgeRelated: '#37474f',
    highlightWhite: '#ffffff',
    ancestorGold: '#ffd600',
    descendantBlue: '#29b6f6'
};

// --- Utilities ---

function esc(s) {
    if (s == null) return '';
    var d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
}

function safeColor(c, fallback) {
    if (!c || !/^(#[0-9a-fA-F]{3,8}|[a-zA-Z]+|rgba?\([^)]+\)|hsla?\([^)]+\))$/.test(c)) return fallback;
    return c;
}

if (typeof marked !== 'undefined') {
    marked.setOptions({ breaks: true });
    marked.use({
        renderer: {
            html: function(token) { return esc(token.raw); }
        }
    });
}

var nameToId = {};
DATA.nodes.forEach(function(n) {
    nameToId[n.data.name] = n.data.id;
});

var currentTimeOverride = null;
var pathActive = false;
var groupingMode = 'hierarchy';

// --- Shared helpers ---

function computeStaleness(evidence) {
    if (!evidence || evidence.length === 0) return {daysSince: null, tier: null, lastTimestamp: null};
    var now = currentTimeOverride ? new Date(currentTimeOverride) : new Date();
    var latest = null;
    evidence.forEach(function(e) {
        if (e.timestamp) {
            var t = new Date(e.timestamp);
            if (!latest || t > latest) latest = t;
        }
    });
    if (!latest) return {daysSince: null, tier: null, lastTimestamp: null};
    var days = Math.floor((now - latest) / 86400000);
    var tier = days <= 7 ? 'fresh' : days <= 21 ? 'aging' : days <= 45 ? 'stale' : 'overdue';
    return {daysSince: days, tier: tier, lastTimestamp: latest.toISOString()};
}

function checkPrereqsMet(node) {
    var directPrereqs = node.incomers('edge[type="prerequisite"]').sources();
    var metStatuses = {'conceptual':1,'applied':1,'proficient':1,'mastered':1};
    var met = 0;
    var total = 0;
    var unmetList = [];
    var nodeData = node.data();
    var prereqData = nodeData.prerequisites || [];
    prereqData.forEach(function(p) {
        total++;
        if (p.nodeId) {
            var pNode = cy.getElementById(p.nodeId);
            if (pNode.length && metStatuses[pNode.data('status')]) {
                met++;
            } else {
                unmetList.push({name: p.name || p.raw, nodeId: p.nodeId, status: pNode.length ? pNode.data('status') : 'unknown'});
            }
        } else {
            unmetList.push({name: p.raw || p.name || 'Unknown', nodeId: null, status: 'unknown'});
        }
    });
    if (total === 0) {
        directPrereqs.forEach(function(p) {
            total++;
            if (metStatuses[p.data('status')]) {
                met++;
            } else {
                unmetList.push({name: p.data('name'), nodeId: p.id(), status: p.data('status')});
            }
        });
    }
    return {met: met, total: total, unmetList: unmetList};
}

function getRecommendedMode(status, prereqsMet) {
    if (!prereqsMet) return {mode: 'locked', label: 'Unlock prerequisites first', color: '#78909c', cliHint: null};
    switch (status) {
        case 'not_started': return {mode: 'learn', label: 'LEARN', color: '#2196f3', cliHint: 'learn'};
        case 'exposed': return {mode: 'learn', label: 'LEARN / QUIZ', color: '#2196f3', cliHint: 'learn'};
        case 'conceptual': return {mode: 'scenario', label: 'SCENARIO', color: '#4caf50', cliHint: 'scenario'};
        case 'applied': return {mode: 'mastery-challenge', label: 'MASTERY CHALLENGE', color: '#9c27b0', cliHint: 'mastery-challenge'};
        case 'proficient': return {mode: 'mastery-challenge', label: 'MASTERY CHALLENGE', color: '#ffd600', cliHint: 'mastery-challenge'};
        case 'mastered': return {mode: 'complete', label: 'COMPLETE', color: '#ffd600', cliHint: null};
        default: return {mode: 'learn', label: 'LEARN', color: '#2196f3', cliHint: 'learn'};
    }
}

// --- Sidebar rendering ---

function renderSidebar() {
    var el = document.getElementById('sidebar-content');
    var s = DATA.stats;
    var cfg = DATA.config;
    var h = '';

    h += '<div id="search-box"><input id="search-input" type="text" placeholder="Search topics..." aria-label="Search topics">';
    h += '<span class="search-shortcut">\u2318K</span>';
    h += '<button id="search-clear" aria-label="Clear search">&times;</button></div>';
    h += '<span id="search-count"></span>';

    h += '<div class="sidebar-group open" data-group="study">';
    h += '<div class="sidebar-group-header"><span class="group-chevron">&#9656;</span><span>Study</span></div>';
    h += '<div class="sidebar-group-body">';
    h += '<div id="study-queue-container"></div>';
    h += '<div id="review-queue-container"></div>';
    h += '</div></div>';

    h += '<div class="sidebar-group open" data-group="view">';
    h += '<div class="sidebar-group-header"><span class="group-chevron">&#9656;</span><span>View</span></div>';
    h += '<div class="sidebar-group-body">';
    h += '<div class="view-toggle" id="view-toggle">';
    h += '<button class="view-btn active" data-view="hierarchy">Hierarchy</button>';
    h += '<button class="view-btn" data-view="category">Categorical</button>';
    h += '</div>';
    h += '</div></div>';

    h += '<div class="sidebar-group" data-group="stats">';
    h += '<div class="sidebar-group-header"><span class="group-chevron">&#9656;</span><span>Stats</span></div>';
    h += '<div class="sidebar-group-body">';

    var pct = s.total > 0 ? Math.round(s.engaged / s.total * 100) : 0;
    h += '<h3>Progress</h3>';
    h += '<div style="font-size:13px">' + s.engaged + '/' + s.total + ' engaged (' + pct + '%)</div>';
    h += '<div class="progress-bar"><div class="progress-fill" style="width:' + pct + '%"></div></div>';

    h += '<h3>Status Breakdown</h3>';
    var maxS = 0;
    cfg.statusOrder.forEach(function(st) { if (s.by_status[st] > maxS) maxS = s.by_status[st]; });
    cfg.statusOrder.forEach(function(st) {
        var cnt = s.by_status[st] || 0;
        var barPct = maxS > 0 ? (cnt / maxS * 100) : 0;
        var color = safeColor(cfg.statusColors[st], COLORS.nodeDefault);
        h += '<div class="stat-row"><span class="stat-label" style="color:' + color + '">' + st + '</span>';
        h += '<span class="stat-count">' + cnt + '</span>';
        h += '<div class="stat-bar"><div class="stat-bar-fill" style="width:' + barPct + '%;background:' + color + '"></div></div></div>';
    });

    h += '<h3>Categories</h3>';
    cfg.categoryOrder.forEach(function(ck) {
        var cs = s.categories[ck] || {total: 0, engaged: 0};
        var color = safeColor(cfg.categoryColors[ck], COLORS.textSecondary);
        var engPct = cs.total > 0 ? (cs.engaged / cs.total * 100) : 0;
        h += '<div class="stat-row"><span class="cat-dot" style="background:' + color + ';display:inline-block;margin-right:4px"></span>';
        h += '<span class="stat-label">' + ck + '</span>';
        h += '<span class="stat-count">' + cs.engaged + '/' + cs.total + '</span>';
        h += '<div class="stat-bar"><div class="stat-bar-fill" style="width:' + engPct + '%;background:' + color + '"></div></div></div>';
    });

    if (s.priority_gaps.length > 0) {
        h += '<h3>Priority Gaps</h3>';
        s.priority_gaps.slice(0, 8).forEach(function(g) {
            var nid = nameToId[g.name];
            h += '<div class="gap-item" tabindex="0" data-node="' + (nid || '') + '">' + esc(g.name) +
                '<span class="gap-priority">' + g.priority + ' / ' + g.status + '</span></div>';
        });
    }

    if (s.recent_promotions.length > 0) {
        h += '<h3>Recent Promotions</h3>';
        s.recent_promotions.slice(0, 5).forEach(function(p) {
            h += '<div class="evidence-item">' + esc(p.topic) + '<br>' +
                '<span style="opacity:0.6;font-size:11px">' + esc(p.from_level) + ' &rarr; ' + esc(p.to_level) +
                ' &middot; ' + esc(p.timestamp) + '</span></div>';
        });
    }

    h += '</div></div>';

    var subcatStats = {};
    DATA.nodes.forEach(function(n) {
        var cat = n.data.category, sub = n.data.subcategory;
        if (!subcatStats[cat]) subcatStats[cat] = {};
        if (!subcatStats[cat][sub]) subcatStats[cat][sub] = {total: 0, engaged: 0};
        subcatStats[cat][sub].total++;
        if (['exposed','conceptual','applied','proficient','mastered'].indexOf(n.data.status) >= 0)
            subcatStats[cat][sub].engaged++;
    });

    h += '<div class="sidebar-group open" data-group="filters">';
    h += '<div class="sidebar-group-header"><span class="group-chevron">&#9656;</span><span>Filters</span></div>';
    h += '<div class="sidebar-group-body">';

    h += '<h3>Filter Categories</h3>';
    h += '<div class="filter-links"><a id="cat-all">All</a><a id="cat-none">None</a></div>';
    cfg.categoryOrder.forEach(function(ck) {
        var color = safeColor(cfg.categoryColors[ck], COLORS.textSecondary);
        var cs = s.categories[ck] || {total: 0, engaged: 0};
        h += '<div class="cat-row">';
        h += '<input type="checkbox" class="cat-check" value="' + esc(ck) + '" checked>';
        h += '<span class="cat-dot" style="background:' + color + '"></span>';
        h += '<span class="cat-label" tabindex="0" data-cat="' + esc(ck) + '">' + esc(ck) + ' <span style="opacity:0.5">(' + cs.engaged + '/' + cs.total + ')</span></span>';
        h += '</div>';
        if (subcatStats[ck]) {
            Object.keys(subcatStats[ck]).forEach(function(sub) {
                var ss = subcatStats[ck][sub];
                h += '<div class="subcat-row">';
                h += '<input type="checkbox" class="subcat-check" data-category="' + esc(ck) + '" value="' + esc(sub) + '" checked>';
                h += '<span class="subcat-label" data-subcat="' + esc(sub) + '" data-cat="' + esc(ck) + '">' + esc(sub) + ' (' + ss.engaged + '/' + ss.total + ')</span>';
                h += '</div>';
            });
        }
    });

    h += '<h3>Status</h3>';
    h += '<div class="filter-group" id="status-filters">';
    cfg.statusOrder.forEach(function(st) {
        var cnt = s.by_status[st] || 0;
        h += '<button class="filter-btn active" data-status="' + esc(st) + '">' + esc(st) + ' (' + cnt + ')</button>';
    });
    h += '</div>';

    h += '<h3>Priority</h3>';
    h += '<div class="filter-group" id="priority-filters">';
    ['critical', 'high', 'medium', 'low'].forEach(function(p) {
        var cnt = s.by_priority[p] || 0;
        h += '<button class="filter-btn active" data-priority="' + esc(p) + '">' + esc(p) + ' (' + cnt + ')</button>';
    });
    h += '</div>';

    h += '</div></div>';

    h += '<div class="sidebar-group" data-group="tools">';
    h += '<div class="sidebar-group-header"><span class="group-chevron">&#9656;</span><span>Tools</span></div>';
    h += '<div class="sidebar-group-body">';

    h += '<h3>Actions</h3>';
    h += '<button class="action-btn" id="btn-fit">Fit All</button>';
    h += '<button class="action-btn" id="btn-suggested">Show Suggested</button>';
    h += '<button class="action-btn" id="btn-related">Toggle Related Edges</button>';
    h += '<button class="action-btn" id="btn-relayout">Re-layout</button>';
    h += '<button class="action-btn" id="btn-export">Export PNG</button>';

    h += '<h3>Legend</h3>';
    cfg.statusOrder.forEach(function(st) {
        var c = safeColor(cfg.statusColors[st], COLORS.nodeDefault);
        h += '<div class="legend-row"><span class="legend-swatch" style="background:' + c + '"></span>' + esc(st) + '</div>';
    });
    h += '<div style="margin-top:6px">';
    ['critical', 'high', 'medium', 'low'].forEach(function(p) {
        var info = cfg.priorityBorders[p];
        h += '<div class="legend-row"><span class="legend-swatch" style="border:' + info.width + 'px solid ' + info.color + ';background:transparent"></span>' + esc(p) + '</div>';
    });
    h += '</div>';
    h += '<div style="margin-top:6px">';
    [['1-2', '&#9679;'], ['3', '&#9632;'], ['4', '&#9670;'], ['5', '&#9733;']].forEach(function(item) {
        h += '<div class="legend-row"><span class="legend-shape">' + item[1] + '</span>difficulty ' + item[0] + '</div>';
    });
    h += '</div>';
    h += '<div style="margin-top:6px">';
    h += '<div class="legend-row"><span class="legend-swatch" style="border:2px double var(--kb-text-secondary);background:transparent"></span>has guide</div>';
    h += '<div class="legend-row"><span class="legend-swatch" style="border:2px solid #4fc3f7;background:transparent"></span>has sandbox</div>';
    h += '</div>';

    h += '</div></div>';

    el.innerHTML = h;
}

renderSidebar();

document.querySelectorAll('.sidebar-group-header').forEach(function(hdr) {
    hdr.addEventListener('click', function() {
        hdr.parentElement.classList.toggle('open');
    });
});

var headerTitle = document.getElementById('header-title');
var headerStats = document.getElementById('header-stats');
if (headerTitle) {
    headerTitle.textContent = (DATA.config.kbName) || 'Knowledge Base';
}
if (headerStats) {
    var pct = DATA.stats.total > 0 ? Math.round(DATA.stats.engaged / DATA.stats.total * 100) : 0;
    headerStats.textContent = DATA.stats.engaged + '/' + DATA.stats.total + ' engaged (' + pct + '%)';
}

// --- Graph initialization ---

cytoscape.use(cytoscapeDagre);

var selectedNodeId = null;
var showRelated = false;
var dagreLayout = {
    name: 'dagre',
    rankDir: 'TB',
    nodeSep: 50,
    rankSep: 80,
    fit: true,
    padding: 40
};

var styleArr = [
    {selector: 'node', style: {
        'label': 'data(name)', 'text-max-width': 100, 'text-wrap': 'ellipsis',
        'text-valign': 'bottom', 'text-margin-y': 5, 'font-size': 11,
        'color': COLORS.textPrimary, 'width': 'data(size)', 'height': 'data(size)',
        'background-color': COLORS.nodeDefault, 'border-width': 2, 'border-color': COLORS.textSecondary,
        'text-outline-color': COLORS.bgPrimary, 'text-outline-width': 1
    }},
    {selector: 'node[?hasGuide]', style: {
        'border-style': 'double'
    }},
    {selector: 'node[?hasSandbox]', style: {
        'border-color': '#4fc3f7'
    }},
    {selector: ':parent', style: {
        'background-opacity': 0.05,
        'border-width': 1,
        'border-opacity': 0.3,
        'shape': 'roundrectangle',
        'padding': 25,
        'text-valign': 'top',
        'text-halign': 'center',
        'font-size': 13,
        'font-weight': 600,
        'color': COLORS.textSecondary,
        'text-margin-y': -8,
        'text-transform': 'uppercase',
        'label': 'data(name)',
        'background-color': 'data(groupColor)',
        'border-color': 'data(groupColor)'
    }},
    {selector: '.stale-aging', style: {
        'underlay-color': '#ff9800', 'underlay-opacity': 0.12, 'underlay-padding': 4
    }},
    {selector: '.stale-stale', style: {
        'underlay-color': '#ff9800', 'underlay-opacity': 0.2, 'underlay-padding': 6
    }},
    {selector: '.stale-overdue', style: {
        'underlay-color': '#f44336', 'underlay-opacity': 0.2, 'underlay-padding': 6
    }},
    {selector: 'node[status="not_started"]', style: {'background-color': COLORS.statusNotStarted}},
    {selector: 'node[status="exposed"]', style: {'background-color': COLORS.statusExposed}},
    {selector: 'node[status="conceptual"]', style: {'background-color': COLORS.statusConceptual}},
    {selector: 'node[status="applied"]', style: {'background-color': COLORS.statusApplied}},
    {selector: 'node[status="proficient"]', style: {'background-color': COLORS.statusProficient}},
    {selector: 'node[status="mastered"]', style: {'background-color': COLORS.statusMastered}},
    {selector: 'node[priority="critical"]', style: {'border-width': 4, 'border-color': COLORS.priorityCritical}},
    {selector: 'node[priority="high"]', style: {'border-width': 3, 'border-color': COLORS.priorityHigh}},
    {selector: 'node[priority="medium"]', style: {'border-width': 2, 'border-color': COLORS.priorityMedium}},
    {selector: 'node[priority="low"]', style: {'border-width': 1, 'border-color': COLORS.priorityLow}},
    {selector: 'node[difficulty <= 2]', style: {'shape': 'ellipse'}},
    {selector: 'node[difficulty = 3]', style: {'shape': 'roundrectangle'}},
    {selector: 'node[difficulty = 4]', style: {'shape': 'diamond'}},
    {selector: 'node[difficulty >= 5]', style: {'shape': 'star'}},
    {selector: '.has-resources', style: {
        'border-style': 'double'
    }},
    {selector: 'edge[type="prerequisite"]', style: {
        'line-color': COLORS.edgePrereq, 'target-arrow-color': COLORS.edgePrereq,
        'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
        'opacity': 0.15, 'width': 1.5
    }},
    {selector: 'edge[type="related"]', style: {
        'line-color': COLORS.edgeRelated, 'line-style': 'dashed',
        'curve-style': 'bezier', 'opacity': 0.3, 'width': 1,
        'display': 'none'
    }},
    {selector: '.path-target', style: {
        'border-color': '#29b6f6', 'border-width': 4, 'border-style': 'solid',
        'text-outline-color': '#29b6f6', 'text-outline-width': 2, 'z-index': 20
    }},
    {selector: '.path-step', style: {
        'border-color': '#ff9800', 'border-width': 3, 'border-style': 'dashed',
        'text-outline-color': '#ff9800', 'text-outline-width': 1, 'z-index': 15
    }},
    {selector: '.path-met', style: {
        'border-color': '#4caf50', 'border-width': 2, 'border-style': 'solid',
        'overlay-color': '#4caf50', 'overlay-opacity': 0.08, 'z-index': 10
    }},
    {selector: '.highlighted', style: {
        'text-outline-color': COLORS.highlightWhite, 'text-outline-width': 2,
        'border-color': COLORS.highlightWhite, 'border-width': 3,
        'z-index': 20
    }},
    {selector: '.ancestor', style: {
        'border-color': COLORS.ancestorGold, 'border-width': 3,
        'text-outline-color': COLORS.ancestorGold, 'text-outline-width': 1,
        'z-index': 15
    }},
    {selector: '.ancestor-needed', style: {
        'border-color': COLORS.textDanger, 'border-width': 3,
        'text-outline-color': COLORS.textDanger, 'text-outline-width': 1,
        'z-index': 15
    }},
    {selector: '.descendant', style: {
        'border-color': COLORS.descendantBlue, 'border-width': 3,
        'text-outline-color': COLORS.descendantBlue, 'text-outline-width': 1,
        'z-index': 15
    }},
    {selector: '.dimmed', style: {'opacity': 0.15}},
    {selector: '.suggested', style: {
        'border-color': COLORS.colorSuccess, 'border-width': 4,
        'border-style': 'double',
        'z-index': 20
    }},
    {selector: 'edge.path-edge', style: {
        'line-color': COLORS.ancestorGold, 'target-arrow-color': COLORS.ancestorGold,
        'width': 2.5, 'opacity': 1, 'z-index': 15
    }},
    {selector: 'node[?isGroup]', style: {
        'opacity': 1,
        'events': 'no'
    }}
];

var initialLayout = dagreLayout;

var cy = cytoscape({
    container: document.getElementById('cy'),
    elements: { nodes: DATA.nodes, edges: DATA.edges },
    style: styleArr,
    layout: initialLayout,
    minZoom: 0.1,
    maxZoom: 4,
    wheelSensitivity: 0.3
});

cy.nodes().forEach(function(node) {
    var res = node.data('resources');
    if (res && typeof res === 'object' && Object.keys(res).length > 0) {
        node.addClass('has-resources');
    }
});

function applyStalenessClasses() {
    cy.nodes().forEach(function(node) {
        node.removeClass('stale-aging stale-stale stale-overdue');
        var s = computeStaleness(node.data('level_up_evidence'));
        if (s.tier && s.tier !== 'fresh') {
            node.addClass('stale-' + s.tier);
        }
    });
}
applyStalenessClasses();

// --- Loading state ---

var loadingOverlay = document.getElementById('loading-overlay');
if (loadingOverlay) {
    loadingOverlay.classList.add('fade-out');
    setTimeout(function() { loadingOverlay.style.display = 'none'; }, 400);
}

// --- Tooltip ---

var tooltip = document.getElementById('tooltip');
cy.on('mouseover', 'node', function(evt) {
    var d = evt.target.data();
    var stars = '';
    for (var i = 0; i < 5; i++) stars += i < d.difficulty ? '\u2605' : '\u2606';
    var resKeys = (d.resources && typeof d.resources === 'object') ? Object.keys(d.resources) : [];
    var resText = resKeys.length > 0 ? ' \u00b7 \u2692 ' + resKeys.length : '';
    var staleness = computeStaleness(d.level_up_evidence);
    var staleText = staleness.daysSince !== null ? ' \u00b7 ' + staleness.daysSince + 'd ago' : '';
    tooltip.innerHTML = '<div style="font-weight:600;margin-bottom:4px">' + esc(d.name) + '</div>' +
        '<div>' + esc(d.status) + ' \u00b7 ' + esc(d.priority) + ' \u00b7 ' + stars + resText + staleText + '</div>';
    tooltip.style.display = 'block';
    var e = evt.originalEvent;
    var tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
    var x = e.pageX + 12, y = e.pageY + 12;
    if (x + tw > window.innerWidth) x = e.pageX - tw - 12;
    if (y + th > window.innerHeight) y = e.pageY - th - 12;
    x = Math.max(0, x);
    y = Math.max(0, y);
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
});
cy.on('mouseout', 'node', function() { tooltip.style.display = 'none'; });

// --- Graph traversal helpers ---

function prereqPredecessors(node) {
    var visited = cy.collection();
    var queue = [node];
    while (queue.length > 0) {
        var current = queue.shift();
        current.incomers('edge[type="prerequisite"]').sources().forEach(function(n) {
            if (!visited.contains(n)) { visited = visited.union(n); queue.push(n); }
        });
    }
    return visited;
}

function prereqSuccessors(node) {
    var visited = cy.collection();
    var queue = [node];
    while (queue.length > 0) {
        var current = queue.shift();
        current.outgoers('edge[type="prerequisite"]').targets().forEach(function(n) {
            if (!visited.contains(n)) { visited = visited.union(n); queue.push(n); }
        });
    }
    return visited;
}

function prereqEdges(node, ancestors, descendants) {
    var edges = cy.collection();
    ancestors.union(node).forEach(function(n) {
        n.connectedEdges('edge[type="prerequisite"]').forEach(function(e) {
            if (ancestors.union(node).contains(e.source()) && ancestors.union(node).contains(e.target())) {
                edges = edges.union(e);
            }
        });
    });
    descendants.union(node).forEach(function(n) {
        n.connectedEdges('edge[type="prerequisite"]').forEach(function(e) {
            if (descendants.union(node).contains(e.source()) && descendants.union(node).contains(e.target())) {
                edges = edges.union(e);
            }
        });
    });
    return edges;
}

// --- Selection & detail panel ---

function clearSelection() {
    cy.elements().removeClass('highlighted ancestor ancestor-needed descendant dimmed path-edge suggested path-target path-step path-met');
    selectedNodeId = null;
    hideDetailPanel();
    clearPath();
}

function hideDetailPanel() {
    document.getElementById('detail-panel').classList.remove('open');
}

function makeCollapsible(html) {
    var tmp = document.createElement('div');
    tmp.innerHTML = html;
    var out = '';
    var inSection = false;

    for (var i = 0; i < tmp.childNodes.length; i++) {
        var node = tmp.childNodes[i];
        if (node.nodeType === 1 && node.tagName === 'H2') {
            if (inSection) out += '</div></div>';
            out += '<div class="guide-section open">';
            out += '<div class="guide-section-header"><span class="guide-section-chevron">&#9656;</span>' + node.innerHTML + '</div>';
            out += '<div class="guide-section-body">';
            inSection = true;
        } else {
            if (node.nodeType === 1) {
                out += node.outerHTML;
            } else if (node.nodeType === 3 && node.textContent.trim()) {
                out += node.textContent;
            }
        }
    }
    if (inSection) out += '</div></div>';
    return out;
}

function attachCollapsibleListeners(container) {
    container.querySelectorAll('.guide-section-header').forEach(function(hdr) {
        hdr.addEventListener('click', function() {
            hdr.parentElement.classList.toggle('open');
        });
    });
}

function showDetailPanel(d) {
    document.getElementById('detail-panel').classList.add('open');
    var closeBtn = document.getElementById('detail-close');
    if (closeBtn) closeBtn.style.zIndex = '2';
    var c = document.getElementById('detail-content');
    var hasGuide = !!d.guideContent;
    var hasSandbox = !!d.sandboxContent;

    var h = '';

    h += '<div class="detail-tabs">';
    h += '<button class="detail-tab active" data-tab="details">Details</button>';
    h += '<button class="detail-tab ' + (hasGuide ? 'has-content' : 'no-content') + '" data-tab="guide">Guide</button>';
    h += '<button class="detail-tab ' + (hasSandbox ? 'has-content' : 'no-content') + '" data-tab="sandbox">Sandbox</button>';
    h += '</div>';

    h += '<div id="tab-details" class="tab-panel active">';

    h += '<h2 style="font-size:16px;margin-bottom:12px;margin-top:24px">' + esc(d.name) + '</h2>';

    var node = cy.getElementById(d.id);
    var readiness = node.length ? checkPrereqsMet(node) : {met: 0, total: 0, unmetList: []};
    var allMet = readiness.total === 0 || readiness.met >= readiness.total;
    var modeInfo = getRecommendedMode(d.status, allMet);

    h += '<div class="next-steps">';
    if (readiness.total === 0) {
        h += '<div class="prereq-bar met">No prerequisites</div>';
    } else if (allMet) {
        h += '<div class="prereq-bar met">Prerequisites: ' + readiness.met + '/' + readiness.total + ' met</div>';
    } else {
        h += '<div class="prereq-bar partial">Prerequisites: ' + readiness.met + '/' + readiness.total + ' met';
        readiness.unmetList.forEach(function(u) {
            if (u.nodeId) {
                h += ' <span class="prereq-link" data-node="' + esc(u.nodeId) + '">' + esc(u.name) + '</span>';
            } else {
                h += ' <span class="prereq-unresolved">' + esc(u.name) + '</span>';
            }
        });
        h += '</div>';
    }

    if (allMet) {
        h += '<div class="mode-badge" style="background:' + modeInfo.color + '">' + modeInfo.label + '</div>';
        if (modeInfo.cliHint) {
            h += '<div class="cli-hint">study ' + modeInfo.cliHint + ' "' + esc(d.name) + '"</div>';
        }
    } else {
        h += '<div style="font-size:12px;opacity:0.5;margin-top:4px">Unlock prerequisites first</div>';
        h += '<button class="action-btn show-path-btn" data-node="' + esc(d.id) + '" style="margin-top:8px;width:auto;display:inline-block;padding:4px 12px;font-size:11px">Show Learning Path</button>';
    }
    h += '</div>';

    h += '<div class="detail-section"><h4>Description</h4><div class="section-body"><p>' + esc(d.description) + '</p></div></div>';
    h += '<div class="detail-section"><h4>Status</h4><div class="section-body"><p>' + esc(d.status) + '</p></div></div>';
    h += '<div class="detail-section"><h4>Priority</h4><div class="section-body"><p>' + esc(d.priority) + '</p></div></div>';

    var stars = '';
    for (var i = 0; i < 5; i++) stars += i < d.difficulty ? '\u2605' : '\u2606';
    h += '<div class="detail-section"><h4>Difficulty</h4><div class="section-body"><p>' + stars + ' (' + d.difficulty + '/5)</p></div></div>';
    h += '<div class="detail-section"><h4>Category</h4><div class="section-body"><p>' + esc(d.category) + ' / ' + esc(d.subcategory) + '</p></div></div>';

    h += '<div class="detail-section"><h4>Prerequisites</h4><div class="section-body">';
    if (d.prerequisites.length === 0) {
        h += '<span style="opacity:0.5">None</span>';
    } else {
        d.prerequisites.forEach(function(p) {
            if (p.nodeId) {
                h += '<span class="prereq-link" data-node="' + esc(p.nodeId) + '">' + esc(p.name) + '</span><span class="filtered-msg" data-for="' + esc(p.nodeId) + '">Filtered out</span><br>';
            } else {
                h += '<span class="prereq-unresolved">' + esc(p.raw) + '</span><br>';
            }
        });
    }
    h += '</div></div>';

    h += '<div class="detail-section"><h4>Related</h4><div class="section-body">';
    if (d.related.length === 0) {
        h += '<span style="opacity:0.5">None</span>';
    } else {
        d.related.forEach(function(r) {
            if (r.nodeId) {
                h += '<span class="prereq-link" data-node="' + esc(r.nodeId) + '">' + esc(r.name) + '</span><span class="filtered-msg" data-for="' + esc(r.nodeId) + '">Filtered out</span><br>';
            } else {
                h += '<span class="prereq-unresolved">' + esc(r.raw) + '</span><br>';
            }
        });
    }
    h += '</div></div>';

    if (d.tags && d.tags.length) {
        h += '<div class="detail-section"><h4>Tags</h4><div class="section-body">';
        d.tags.forEach(function(t) { h += '<span class="tag-pill">' + esc(t) + '</span>'; });
        h += '</div></div>';
    }

    h += '<div class="detail-section"><h4>Source</h4><div class="section-body"><p>' + (d.source_context ? esc(d.source_context) : 'None') + '</p></div></div>';

    var res = d.resources;
    if (res && typeof res === 'object' && Object.keys(res).length > 0) {
        h += '<div class="detail-section"><h4>Resources</h4><div class="section-body">';
        Object.keys(res).forEach(function(key) {
            var val = res[key];
            var isUrl = /^https?:\/\//.test(val);
            h += '<div class="resource-entry"><span class="resource-type">' + esc(key) + ':</span> ';
            if (isUrl) {
                h += '<a href="' + esc(val) + '" target="_blank" rel="noopener" class="resource-link">' + esc(val) + '</a>';
            } else {
                h += '<span>' + esc(val) + '</span>';
            }
            h += '</div>';
        });
        h += '</div></div>';
    }

    h += '<div class="detail-section"><h4>Evidence</h4><div class="section-body">';
    if (!d.level_up_evidence || d.level_up_evidence.length === 0) {
        h += '<p style="opacity:0.5">No evidence recorded</p>';
    } else {
        d.level_up_evidence.forEach(function(e) {
            h += '<div class="evidence-item">' + esc(e.from_level) + ' &rarr; ' + esc(e.to_level) +
                '<br><span style="opacity:0.6;font-size:11px">' + esc(e.timestamp) + ' &middot; ' + esc(e.method) + '</span>' +
                (e.summary ? '<br><span style="font-size:11px">' + esc(e.summary) + '</span>' : '') + '</div>';
        });
    }
    h += '</div></div>';

    h += '<div class="detail-section"><h4>Connectivity</h4><div class="section-body"><p>' + d.connections + ' connections</p></div></div>';

    h += '</div>';

    h += '<div id="tab-guide" class="tab-panel">';
    if (hasGuide && typeof marked !== 'undefined') {
        h += '<div class="guide-content"><button class="guide-expand-btn" data-target="guide" title="View fullscreen">&#x26F6;</button>'
            + makeCollapsible(marked.parse(d.guideContent)) + '</div>';
    } else if (hasGuide) {
        h += '<div class="guide-content"><pre>' + esc(d.guideContent) + '</pre></div>';
    } else {
        h += '<div class="empty-tab"><p>No guide available for this topic.</p>';
        h += '<p style="font-size:12px;opacity:0.5;margin-top:8px">Guides are generated during study sessions via <code>resume path</code>.</p></div>';
    }
    h += '</div>';

    h += '<div id="tab-sandbox" class="tab-panel">';
    if (hasSandbox && typeof marked !== 'undefined') {
        h += '<div class="guide-content"><button class="guide-expand-btn" data-target="sandbox" title="View fullscreen">&#x26F6;</button>';
        if (d.sandboxSlug) {
            h += '<a class="sandbox-download-btn" href="sandboxes/'
                + encodeURIComponent(d.sandboxSlug) + '.tar.gz" download>'
                + '&#x2B07; Download Challenge</a>';
        }
        h += makeCollapsible(marked.parse(d.sandboxContent)) + '</div>';
    } else if (hasSandbox) {
        h += '<div class="guide-content">';
        if (d.sandboxSlug) {
            h += '<a class="sandbox-download-btn" href="sandboxes/'
                + encodeURIComponent(d.sandboxSlug) + '.tar.gz" download>'
                + '&#x2B07; Download Challenge</a>';
        }
        h += '<pre>' + esc(d.sandboxContent) + '</pre></div>';
    } else {
        h += '<div class="empty-tab"><p>No sandbox project available for this topic.</p>';
        h += '<p style="font-size:12px;opacity:0.5;margin-top:8px">Sandbox challenges are generated during project-mode study sessions.</p></div>';
    }
    h += '</div>';

    c.innerHTML = h;

    var guideEl = c.querySelector('#tab-guide .guide-content');
    if (guideEl) attachCollapsibleListeners(guideEl);
    var sandboxEl = c.querySelector('#tab-sandbox .guide-content');
    if (sandboxEl) attachCollapsibleListeners(sandboxEl);

    c.querySelectorAll('.guide-expand-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var existing = document.querySelector('.guide-fullscreen');
            if (existing) existing.remove();

            var sourceContent = btn.parentElement.cloneNode(true);
            var nestedBtn = sourceContent.querySelector('.guide-expand-btn');
            if (nestedBtn) nestedBtn.remove();

            var overlay = document.createElement('div');
            overlay.className = 'guide-fullscreen';

            var tabLabel = btn.dataset.target.charAt(0).toUpperCase() + btn.dataset.target.slice(1);
            overlay.innerHTML = '<div class="guide-fullscreen-header">'
                + '<span class="guide-fullscreen-title">' + esc(d.name) + ' — ' + tabLabel + '</span>'
                + '<button class="guide-fullscreen-close">&times;</button>'
                + '</div>'
                + '<div class="guide-fullscreen-body guide-content"></div>';

            var body = overlay.querySelector('.guide-fullscreen-body');
            body.innerHTML = sourceContent.innerHTML;
            attachCollapsibleListeners(body);

            document.body.appendChild(overlay);

            overlay.querySelector('.guide-fullscreen-close').addEventListener('click', function() {
                overlay.remove();
            });
            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) overlay.remove();
            });
        });
    });

    c.querySelectorAll('.detail-tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
            c.querySelectorAll('.detail-tab').forEach(function(t) { t.classList.remove('active'); });
            c.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
            tab.classList.add('active');
            document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
        });
    });

    c.querySelectorAll('.prereq-link').forEach(function(el) {
        el.addEventListener('click', function() {
            var nid = el.getAttribute('data-node');
            var node = cy.getElementById(nid);
            if (node.style('display') === 'none') {
                var msg = el.parentNode.querySelector('.filtered-msg[data-for="' + nid + '"]');
                if (msg) {
                    msg.classList.add('show');
                    setTimeout(function() { msg.classList.remove('show'); }, 1500);
                }
                return;
            }
            node.emit('tap');
            cy.animate({ center: { eles: node }, duration: 300 });
        });
    });

    c.querySelectorAll('.detail-section h4').forEach(function(header) {
        header.addEventListener('click', function() {
            header.parentElement.classList.toggle('collapsed');
        });
    });

    c.querySelectorAll('.next-steps .prereq-link').forEach(function(el) {
        el.addEventListener('click', function() {
            var nid = el.getAttribute('data-node');
            var n = cy.getElementById(nid);
            if (n.style('display') === 'none') return;
            n.emit('tap');
            cy.animate({ center: { eles: n }, duration: 300 });
        });
    });

    var pathBtn = c.querySelector('.show-path-btn');
    if (pathBtn) {
        pathBtn.addEventListener('click', function() {
            showLearningPath(pathBtn.getAttribute('data-node'));
        });
    }
}

cy.on('tap', 'node', function(evt) {
    tooltip.style.display = 'none';
    var node = evt.target;
    if (node.data('isGroup')) return;
    clearSelection();
    selectedNodeId = node.id();
    node.addClass('highlighted');

    var ancestors = prereqPredecessors(node);
    var descendants = prereqSuccessors(node);
    var pathEdges = prereqEdges(node, ancestors, descendants);

    var metStatuses = {'conceptual':1,'applied':1,'proficient':1,'mastered':1};
    ancestors.forEach(function(a) {
        if (metStatuses[a.data('status')]) a.addClass('ancestor');
        else a.addClass('ancestor-needed');
    });
    descendants.addClass('descendant');
    pathEdges.addClass('path-edge');

    var involved = node.union(ancestors).union(descendants).union(pathEdges);
    cy.elements().difference(involved).addClass('dimmed');

    showDetailPanel(node.data());
});

cy.on('tap', function(evt) {
    if (evt.target === cy) clearSelection();
});

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        var fs = document.querySelector('.guide-fullscreen');
        if (fs) { fs.remove(); return; }
        clearSelection();
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        var si = document.getElementById('search-input');
        if (si) si.focus();
    }
    if (e.key === 'Enter' && document.activeElement) {
        var el = document.activeElement;
        if (el.classList.contains('cat-label') || el.classList.contains('gap-item')) {
            el.click();
        }
    }
});

document.getElementById('detail-close').addEventListener('click', function() {
    clearSelection();
});

// --- Search ---

var searchInput = document.getElementById('search-input');
var searchClear = document.getElementById('search-clear');
var searchCount = document.getElementById('search-count');
var searchTimer;

function runSearch() {
    var query = searchInput.value.trim().toLowerCase();
    searchClear.style.display = query ? 'block' : 'none';
    var shortcut = document.querySelector('.search-shortcut');
    if (shortcut) shortcut.style.display = query ? 'none' : '';
    if (!query) {
        searchCount.textContent = '';
        return;
    }
    if (selectedNodeId) {
        var visNodes = cy.nodes().filter(function(n) { return n.style('display') !== 'none'; });
        var matches = visNodes.filter(function(n) {
            var d = n.data();
            return d.name.toLowerCase().indexOf(query) >= 0 ||
                (d.tags || []).some(function(t) { return t.toLowerCase().indexOf(query) >= 0; }) ||
                d.description.toLowerCase().indexOf(query) >= 0;
        });
        searchCount.textContent = matches.length + ' matches';
        return;
    }
    cy.elements().removeClass('highlighted dimmed');
    var visNodes = cy.nodes().filter(function(n) { return n.style('display') !== 'none'; });
    var matches = visNodes.filter(function(n) {
        var d = n.data();
        return d.name.toLowerCase().indexOf(query) >= 0 ||
            (d.tags || []).some(function(t) { return t.toLowerCase().indexOf(query) >= 0; }) ||
            d.description.toLowerCase().indexOf(query) >= 0;
    });
    matches.removeClass('dimmed').addClass('highlighted');
    visNodes.not(matches).addClass('dimmed');
    searchCount.textContent = matches.length + ' matches';
    if (matches.length > 0) cy.animate({ fit: { eles: matches, padding: 80 }, duration: 400 });
}

searchInput.addEventListener('input', function() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function() {
        clearSelection();
        runSearch();
    }, 200);
});

searchClear.addEventListener('click', function() {
    searchInput.value = '';
    searchClear.style.display = 'none';
    var shortcut = document.querySelector('.search-shortcut');
    if (shortcut) shortcut.style.display = '';
    searchCount.textContent = '';
    clearSelection();
});

// --- Filters ---

var catChecks = document.querySelectorAll('.cat-check');
var statusBtns = document.querySelectorAll('#status-filters .filter-btn');
var prioBtns = document.querySelectorAll('#priority-filters .filter-btn');

function updateFilterBar() {
    var bar = document.getElementById('filter-bar');
    if (!bar) return;
    var chips = [];

    catChecks.forEach(function(c) {
        if (!c.checked) {
            chips.push('<span class="filter-chip" data-type="cat" data-value="' + esc(c.value) + '">-' + esc(c.value) + ' <span class="chip-x">\u00d7</span></span>');
        }
    });
    statusBtns.forEach(function(b) {
        if (!b.classList.contains('active')) {
            chips.push('<span class="filter-chip" data-type="status" data-value="' + esc(b.dataset.status) + '">-' + esc(b.dataset.status) + ' <span class="chip-x">\u00d7</span></span>');
        }
    });
    prioBtns.forEach(function(b) {
        if (!b.classList.contains('active')) {
            chips.push('<span class="filter-chip" data-type="priority" data-value="' + esc(b.dataset.priority) + '">-' + esc(b.dataset.priority) + ' <span class="chip-x">\u00d7</span></span>');
        }
    });

    bar.innerHTML = chips.join('');

    bar.querySelectorAll('.filter-chip').forEach(function(chip) {
        chip.addEventListener('click', function() {
            var type = chip.dataset.type;
            var val = chip.dataset.value;
            if (type === 'cat') {
                catChecks.forEach(function(c) { if (c.value === val) c.checked = true; });
            } else if (type === 'status') {
                statusBtns.forEach(function(b) { if (b.dataset.status === val) b.classList.add('active'); });
            } else if (type === 'priority') {
                prioBtns.forEach(function(b) { if (b.dataset.priority === val) b.classList.add('active'); });
            }
            applyFilters();
        });
    });
}

function applyFilters() {
    var activeCats = new Set();
    catChecks.forEach(function(c) { if (c.checked) activeCats.add(c.value); });
    var activeSubcats = new Set();
    document.querySelectorAll('.subcat-check').forEach(function(c) {
        if (c.checked) activeSubcats.add(c.dataset.category + '/' + c.value);
    });
    var activeStatuses = new Set();
    statusBtns.forEach(function(b) { if (b.classList.contains('active')) activeStatuses.add(b.dataset.status); });
    var activePrios = new Set();
    prioBtns.forEach(function(b) { if (b.classList.contains('active')) activePrios.add(b.dataset.priority); });

    cy.batch(function() {
        cy.nodes().forEach(function(node) {
            var d = node.data();
            if (d.isGroup) return;
            var vis = activeCats.has(d.category) &&
                      activeSubcats.has(d.category + '/' + d.subcategory) &&
                      activeStatuses.has(d.status) && activePrios.has(d.priority);
            node.style('display', vis ? 'element' : 'none');
        });
        cy.edges().forEach(function(edge) {
            var srcVis = edge.source().style('display') !== 'none';
            var tgtVis = edge.target().style('display') !== 'none';
            if (edge.data('type') === 'related') {
                edge.style('display', (srcVis && tgtVis && showRelated) ? 'element' : 'none');
            } else {
                edge.style('display', (srcVis && tgtVis) ? 'element' : 'none');
            }
        });
        if (groupingMode === 'category') {
            DATA.config.categoryOrder.forEach(function(cat) {
                var group = cy.getElementById('group-' + cat);
                if (group.length) {
                    var anyChildVisible = group.children().some(function(c) {
                        return c.style('display') !== 'none';
                    });
                    group.style('display', anyChildVisible ? 'element' : 'none');
                }
            });
        }
    });

    if (selectedNodeId) {
        var sel = cy.getElementById(selectedNodeId);
        if (sel.style('display') === 'none') clearSelection();
    }

    var visCount = cy.nodes().filter(function(n) { return n.style('display') !== 'none' && !n.data('isGroup'); }).length;
    document.getElementById('empty-state').style.display = visCount === 0 ? 'flex' : 'none';

    if (searchInput && searchInput.value.trim()) runSearch();

    updateFilterBar();
    renderStudyQueue();
}

catChecks.forEach(function(c) {
    c.addEventListener('change', function() {
        document.querySelectorAll('.subcat-check[data-category="' + c.value + '"]').forEach(function(sc) {
            sc.checked = c.checked;
        });
        applyFilters();
    });
});
statusBtns.forEach(function(b) {
    b.addEventListener('click', function() { b.classList.toggle('active'); applyFilters(); });
});
prioBtns.forEach(function(b) {
    b.addEventListener('click', function() { b.classList.toggle('active'); applyFilters(); });
});

document.getElementById('cat-all').addEventListener('click', function() {
    catChecks.forEach(function(c) { c.checked = true; });
    document.querySelectorAll('.subcat-check').forEach(function(c) { c.checked = true; });
    applyFilters();
});
document.getElementById('cat-none').addEventListener('click', function() {
    catChecks.forEach(function(c) { c.checked = false; });
    document.querySelectorAll('.subcat-check').forEach(function(c) { c.checked = false; });
    applyFilters();
});

document.querySelectorAll('.cat-label').forEach(function(lbl) {
    lbl.addEventListener('click', function() {
        var cat = lbl.getAttribute('data-cat');
        var nodes = cy.nodes().filter(function(n) {
            return n.data('category') === cat && n.style('display') !== 'none';
        });
        if (nodes.length > 0) cy.animate({ fit: { eles: nodes, padding: 80 }, duration: 400 });
    });
});

document.querySelectorAll('.subcat-check').forEach(function(sc) {
    sc.addEventListener('change', function() {
        var cat = sc.dataset.category;
        var anyChecked = false;
        document.querySelectorAll('.subcat-check[data-category="' + cat + '"]').forEach(function(s) {
            if (s.checked) anyChecked = true;
        });
        catChecks.forEach(function(c) {
            if (c.value === cat) c.checked = anyChecked;
        });
        applyFilters();
    });
});

document.querySelectorAll('.view-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        setGroupingMode(btn.dataset.view);
    });
});

// --- Reset filters ---

function resetFilters() {
    catChecks.forEach(function(c) { c.checked = true; });
    document.querySelectorAll('.subcat-check').forEach(function(c) { c.checked = true; });
    statusBtns.forEach(function(b) { b.classList.add('active'); });
    prioBtns.forEach(function(b) { b.classList.add('active'); });
    applyFilters();
}

var resetBtn = document.getElementById('reset-filters-btn');
if (resetBtn) resetBtn.addEventListener('click', resetFilters);

// --- Grouping ---

function enableCategoryGrouping() {
    cy.startBatch();
    DATA.config.categoryOrder.forEach(function(cat) {
        if (!cy.getElementById('group-' + cat).length) {
            cy.add({
                group: 'nodes',
                data: {
                    id: 'group-' + cat,
                    name: cat,
                    isGroup: true,
                    groupColor: DATA.config.categoryColors[cat] || COLORS.textSecondary
                }
            });
        }
    });
    cy.nodes().forEach(function(n) {
        if (!n.data('isGroup')) {
            n.move({ parent: 'group-' + n.data('category') });
        }
    });
    cy.endBatch();
    cy.layout(Object.assign({}, dagreLayout, { animate: true, animationDuration: 400 })).run();
}

function disableCategoryGrouping() {
    cy.startBatch();
    cy.nodes().forEach(function(n) {
        if (!n.data('isGroup')) {
            n.move({ parent: null });
        }
    });
    cy.nodes('[?isGroup]').remove();
    cy.endBatch();
    cy.layout(Object.assign({}, dagreLayout, { animate: true, animationDuration: 400 })).run();
}

function setGroupingMode(mode) {
    if (mode === groupingMode) return;
    clearSelection();
    groupingMode = mode;
    if (mode === 'category') enableCategoryGrouping();
    else disableCategoryGrouping();
    document.querySelectorAll('.view-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.view === mode);
    });
}

// --- Actions ---

document.getElementById('btn-fit').addEventListener('click', function() {
    cy.animate({ fit: { padding: 40 }, duration: 400 });
});

document.getElementById('btn-suggested').addEventListener('click', function() {
    clearSelection();
    var visible = cy.nodes().filter(function(n) { return n.style('display') !== 'none'; });
    var suggested = visible.filter(function(node) {
        var d = node.data();
        if (['not_started','exposed'].indexOf(d.status) < 0) return false;
        if (['critical','high'].indexOf(d.priority) < 0) return false;
        var directPrereqs = node.incomers('edge[type="prerequisite"]').sources();
        if (directPrereqs.length === 0) return true;
        return directPrereqs.every(function(p) {
            return ['conceptual','applied','proficient','mastered'].indexOf(p.data('status')) >= 0;
        });
    });
    suggested.addClass('suggested');
    visible.not(suggested).addClass('dimmed');
    if (suggested.length > 0) cy.animate({ fit: { eles: suggested, padding: 80 }, duration: 400 });
});

document.getElementById('btn-related').addEventListener('click', function() {
    showRelated = !showRelated;
    this.classList.toggle('active', showRelated);
    applyFilters();
});

document.getElementById('btn-relayout').addEventListener('click', function() {
    clearSelection();
    cy.layout(dagreLayout).run();
    applyFilters();
});

document.getElementById('btn-export').addEventListener('click', function() {
    var png = cy.png({ full: true, scale: 2, bg: COLORS.bgPrimary });
    var a = document.createElement('a');
    a.href = png; a.download = 'kb-dag.png'; a.click();
});

document.querySelectorAll('.gap-item').forEach(function(item) {
    item.addEventListener('click', function() {
        var nid = item.getAttribute('data-node');
        if (nid) {
            var node = cy.getElementById(nid);
            if (node.style('display') !== 'none') {
                node.emit('tap');
                cy.animate({ center: { eles: node }, duration: 300 });
            }
        }
    });
});

document.getElementById('toolbar').querySelector('[data-action="zoomin"]').addEventListener('click', function() {
    cy.zoom({ level: cy.zoom() * 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
});
document.getElementById('toolbar').querySelector('[data-action="zoomout"]').addEventListener('click', function() {
    cy.zoom({ level: cy.zoom() / 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
});
document.getElementById('toolbar').querySelector('[data-action="fit"]').addEventListener('click', function() {
    cy.animate({ fit: { padding: 40 }, duration: 400 });
});

// --- Sidebar collapse ---

var collapseBtn = document.getElementById('collapse-btn');
var sidebar = document.getElementById('sidebar');
var sidebarOverlay = document.getElementById('sidebar-overlay');

collapseBtn.addEventListener('click', function() {
    var isMobile = window.innerWidth <= 768;
    if (isMobile) {
        sidebar.classList.toggle('mobile-open');
        sidebarOverlay.classList.toggle('active', sidebar.classList.contains('mobile-open'));
    } else {
        sidebar.classList.toggle('collapsed');
        collapseBtn.textContent = sidebar.classList.contains('collapsed') ? '\u203a' : '\u2039';
    }
});

if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', function() {
        sidebar.classList.remove('mobile-open');
        sidebarOverlay.classList.remove('active');
    });
}

sidebar.addEventListener('transitionend', function() { cy.resize(); });

var resizeTimer;
window.addEventListener('resize', function() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function() { cy.resize(); }, 200);
});

// --- Study Queue ---

function computeStudyQueue() {
    var metStatuses = {'conceptual':1,'applied':1,'proficient':1,'mastered':1};
    var visible = cy.nodes().filter(function(n) { return n.style('display') !== 'none'; });
    var scored = [];

    visible.forEach(function(node) {
        var d = node.data();
        var status = d.status;
        var priority = d.priority;
        var score = 0;
        var rationale = '';
        var directPrereqs = node.incomers('edge[type="prerequisite"]').sources();
        var prereqsMet = directPrereqs.length === 0 || directPrereqs.every(function(p) {
            return !!metStatuses[p.data('status')];
        });

        var fanOut = node.outgoers('edge[type="prerequisite"]').targets().length;
        if (!metStatuses[status] && fanOut >= 3) {
            var s = fanOut * 10;
            if (s > score) { score = s; rationale = 'Prerequisite for ' + fanOut + ' topics'; }
        }

        if ((priority === 'critical' || priority === 'high') && (status === 'not_started' || status === 'exposed') && prereqsMet) {
            var s = priority === 'critical' ? 8 : 5;
            if (s > score) { score = s; rationale = 'High priority gap'; }
        }

        if (status === 'conceptual' && prereqsMet) {
            if (4 > score) { score = 4; rationale = 'Ready for SCENARIO'; }
        }
        if (status === 'applied' && prereqsMet) {
            if (4 > score) { score = 4; rationale = 'Ready for MASTERY CHALLENGE'; }
        }
        if (status === 'proficient' && prereqsMet) {
            if (3 > score) { score = 3; rationale = 'Ready for mastered assessment'; }
        }

        var staleness = computeStaleness(d.level_up_evidence);
        if (staleness.daysSince !== null && staleness.daysSince >= 14) {
            var s = Math.min(staleness.daysSince / 7, 6);
            if (s > score) { score = s; rationale = 'Last studied ' + staleness.daysSince + ' days ago'; }
        }

        if (score > 0) {
            var modeInfo = getRecommendedMode(status, prereqsMet);
            scored.push({
                nodeId: node.id(),
                name: d.name,
                status: status,
                score: score,
                rationale: rationale,
                mode: modeInfo
            });
        }
    });

    scored.sort(function(a, b) { return b.score - a.score; });
    return scored.slice(0, 5);
}

function renderStudyQueue() {
    var container = document.getElementById('study-queue-container');
    if (!container) return;
    var queue = computeStudyQueue();
    var h = '<h3>Study Queue</h3>';
    if (queue.length === 0) {
        h += '<div style="font-size:12px;opacity:0.5;padding:4px 0">All caught up!</div>';
    } else {
        queue.forEach(function(item) {
            var statusColor = safeColor(DATA.config.statusColors[item.status], COLORS.nodeDefault);
            h += '<div class="study-queue-item" data-node="' + esc(item.nodeId) + '">';
            h += '<span class="queue-status-dot" style="background:' + statusColor + '"></span>';
            h += '<span class="queue-name">' + esc(item.name) + '</span>';
            h += '<span class="queue-mode-chip" style="background:' + item.mode.color + '">' + esc(item.mode.label) + '</span>';
            h += '<span class="queue-rationale">' + esc(item.rationale) + '</span>';
            h += '</div>';
        });
    }
    container.innerHTML = h;

    container.querySelectorAll('.study-queue-item').forEach(function(el) {
        el.addEventListener('click', function() {
            var nid = el.getAttribute('data-node');
            if (nid) {
                var node = cy.getElementById(nid);
                if (node.style('display') !== 'none') {
                    node.emit('tap');
                    cy.animate({ center: { eles: node }, duration: 300 });
                }
            }
        });
    });
}

// --- Review Queue ---

function renderReviewQueue() {
    var container = document.getElementById('review-queue-container');
    if (!container) return;
    var items = [];
    cy.nodes().forEach(function(node) {
        var d = node.data();
        var s = computeStaleness(d.level_up_evidence);
        if (s.tier && s.tier !== 'fresh') {
            items.push({nodeId: node.id(), name: d.name, daysSince: s.daysSince, tier: s.tier});
        }
    });
    items.sort(function(a, b) { return b.daysSince - a.daysSince; });
    items = items.slice(0, 8);

    if (items.length === 0) {
        container.innerHTML = '';
        return;
    }

    var h = '<h3>Needs Review</h3>';
    items.forEach(function(item) {
        h += '<div class="review-item" data-node="' + esc(item.nodeId) + '">';
        h += '<span class="review-dot ' + esc(item.tier) + '"></span>';
        h += esc(item.name);
        h += '<span class="review-days">' + item.daysSince + ' days ago</span>';
        h += '</div>';
    });
    container.innerHTML = h;

    container.querySelectorAll('.review-item').forEach(function(el) {
        el.addEventListener('click', function() {
            var nid = el.getAttribute('data-node');
            if (nid) {
                var node = cy.getElementById(nid);
                if (node.style('display') !== 'none') {
                    node.emit('tap');
                    cy.animate({ center: { eles: node }, duration: 300 });
                }
            }
        });
    });
}

// --- Learning Path ---

function topoSortUnmet(unmetNodes) {
    var idSet = {};
    unmetNodes.forEach(function(n) { idSet[n.id()] = true; });
    var inDegree = {};
    var adjList = {};
    unmetNodes.forEach(function(n) {
        inDegree[n.id()] = 0;
        adjList[n.id()] = [];
    });
    unmetNodes.forEach(function(n) {
        n.connectedEdges('edge[type="prerequisite"]').forEach(function(e) {
            var src = e.source().id();
            var tgt = e.target().id();
            if (idSet[src] && idSet[tgt]) {
                adjList[src].push(tgt);
                inDegree[tgt] = (inDegree[tgt] || 0) + 1;
            }
        });
    });
    var queue = [];
    unmetNodes.forEach(function(n) {
        if (inDegree[n.id()] === 0) queue.push(n.id());
    });
    var result = [];
    while (queue.length > 0) {
        var cur = queue.shift();
        result.push(cur);
        (adjList[cur] || []).forEach(function(next) {
            inDegree[next]--;
            if (inDegree[next] === 0) queue.push(next);
        });
    }
    return result;
}

function renderPathPanel(sortedIds, targetId) {
    var panel = document.getElementById('path-panel');
    if (!panel) return;
    var h = '<div style="font-size:12px;font-weight:600;margin-bottom:8px;color:' + COLORS.textPrimary + '">Learning Path</div>';

    var someFiltered = false;
    sortedIds.forEach(function(id, idx) {
        var node = cy.getElementById(id);
        var d = node.data();
        var modeInfo = getRecommendedMode(d.status, true);
        var statusColor = safeColor(DATA.config.statusColors[d.status], COLORS.nodeDefault);
        if (node.style('display') === 'none') someFiltered = true;
        h += '<div class="path-step-item" data-node="' + esc(id) + '">';
        h += '<span class="path-step-num">' + (idx + 1) + '.</span>';
        h += '<span class="queue-status-dot" style="background:' + statusColor + '"></span>';
        h += esc(d.name);
        h += ' <span class="queue-mode-chip" style="background:' + modeInfo.color + '">' + esc(modeInfo.label) + '</span>';
        h += '</div>';
    });

    var targetNode = cy.getElementById(targetId);
    var targetData = targetNode.data();
    var targetColor = safeColor(DATA.config.statusColors[targetData.status], COLORS.nodeDefault);
    h += '<div style="margin-top:6px;padding-top:6px;border-top:1px solid ' + COLORS.borderPrimary + ';font-size:12px">';
    h += '<span class="queue-status-dot" style="background:' + targetColor + '"></span>';
    h += '<strong>' + esc(targetData.name) + '</strong> (target)';
    h += '</div>';

    if (someFiltered) {
        h += '<div class="path-note">Some steps may be filtered out of the current view</div>';
    }

    h += '<button class="action-btn path-clear-btn" style="margin-top:8px">Clear Path</button>';
    panel.innerHTML = h;
    panel.style.display = 'block';

    panel.querySelectorAll('.path-step-item').forEach(function(el) {
        el.addEventListener('click', function() {
            var nid = el.getAttribute('data-node');
            if (nid) {
                var node = cy.getElementById(nid);
                cy.animate({ center: { eles: node }, duration: 300 });
            }
        });
    });

    var clearBtn = panel.querySelector('.path-clear-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', function() {
            clearSelection();
        });
    }
}

function showLearningPath(nodeId) {
    var node = cy.getElementById(nodeId);
    cy.elements().removeClass(
        'highlighted ancestor ancestor-needed descendant dimmed path-edge suggested path-target path-step path-met'
    );

    var allAncestors = prereqPredecessors(node);
    var metStatuses = {'conceptual':1,'applied':1,'proficient':1,'mastered':1};
    var unmet = allAncestors.filter(function(a) { return !metStatuses[a.data('status')]; });
    var met = allAncestors.filter(function(a) { return !!metStatuses[a.data('status')]; });

    var sortedIds = topoSortUnmet(unmet);

    node.addClass('path-target');
    unmet.addClass('path-step');
    met.addClass('path-met');

    var pathNodes = node.union(allAncestors);
    pathNodes.forEach(function(n) {
        n.connectedEdges('edge[type="prerequisite"]').forEach(function(e) {
            if (pathNodes.contains(e.source()) && pathNodes.contains(e.target())) {
                e.addClass('path-edge');
            }
        });
    });

    cy.elements().difference(pathNodes.union(cy.edges('.path-edge'))).addClass('dimmed');

    renderPathPanel(sortedIds, nodeId);
    pathActive = true;
}

function clearPath() {
    var panel = document.getElementById('path-panel');
    if (panel) {
        panel.innerHTML = '';
        panel.style.display = 'none';
    }
    pathActive = false;
}

renderStudyQueue();
renderReviewQueue();

window.__TEST__ = {
    getSelectedNodeId: function() { return selectedNodeId; },
    getShowRelated: function() { return showRelated; },
    isDetailPanelOpen: function() { return document.getElementById('detail-panel').classList.contains('open'); },
    isSidebarCollapsed: function() { return sidebar.classList.contains('collapsed'); },
    isEmptyStateVisible: function() { return document.getElementById('empty-state').style.display === 'flex'; },
    getSearchCount: function() { return searchCount.textContent; },
    isLoading: function() {
        var overlay = document.getElementById('loading-overlay');
        return overlay && overlay.style.display !== 'none' && !overlay.classList.contains('fade-out');
    },
    resetFilters: function() { resetFilters(); },
    cy: cy,
    getNodeCount: function() { return cy.nodes().filter(function(n) { return !n.data('isGroup'); }).length; },
    getEdgeCount: function() { return cy.edges().length; },
    getVisibleNodes: function() { return cy.nodes().filter(function(n) { return n.style('display') !== 'none' && !n.data('isGroup'); }); },
    getVisibleEdges: function() { return cy.edges().filter(function(e) { return e.style('display') !== 'none'; }); },
    getNodeById: function(id) { return cy.getElementById(id); },
    getNodeByName: function(name) { return cy.getElementById(nameToId[name]); },
    getNodeData: function(id) { return cy.getElementById(id).data(); },
    getNodeClasses: function(id) { return cy.getElementById(id).classes(); },
    getHighlightedNodes: function() { return cy.nodes('.highlighted'); },
    getDimmedNodes: function() { return cy.nodes('.dimmed'); },
    getSuggestedNodes: function() { return cy.nodes('.suggested'); },
    getAncestorNodes: function() { return cy.nodes('.ancestor'); },
    getAncestorNeededNodes: function() { return cy.nodes('.ancestor-needed'); },
    getDescendantNodes: function() { return cy.nodes('.descendant'); },
    getActiveCategories: function() {
        var active = [];
        catChecks.forEach(function(c) { if (c.checked) active.push(c.value); });
        return active;
    },
    getActiveStatuses: function() {
        var active = [];
        statusBtns.forEach(function(b) { if (b.classList.contains('active')) active.push(b.dataset.status); });
        return active;
    },
    getActivePriorities: function() {
        var active = [];
        prioBtns.forEach(function(b) { if (b.classList.contains('active')) active.push(b.dataset.priority); });
        return active;
    },
    selectNode: function(id) { cy.getElementById(id).emit('tap'); },
    clearSelection: function() { clearSelection(); },
    setSearchQuery: function(q) { searchInput.value = q; searchInput.dispatchEvent(new Event('input')); },
    clearSearch: function() { searchClear.click(); },
    toggleCategory: function(name, checked) {
        catChecks.forEach(function(c) {
            if (c.value === name) c.checked = checked;
        });
        document.querySelectorAll('.subcat-check[data-category="' + name + '"]').forEach(function(sc) {
            sc.checked = checked;
        });
        applyFilters();
    },
    toggleStatus: function(status) {
        statusBtns.forEach(function(b) {
            if (b.dataset.status === status) b.click();
        });
    },
    togglePriority: function(priority) {
        prioBtns.forEach(function(b) {
            if (b.dataset.priority === priority) b.click();
        });
    },
    clickSuggested: function() { document.getElementById('btn-suggested').click(); },
    clickToggleRelated: function() { document.getElementById('btn-related').click(); },
    clickRelayout: function() { document.getElementById('btn-relayout').click(); },
    clickFitAll: function() { document.getElementById('btn-fit').click(); },
    toggleSidebar: function() { collapseBtn.click(); },
    data: DATA,
    nameToId: function() { return Object.assign({}, nameToId); },
    getStudyQueue: function() { return computeStudyQueue(); },
    getRecommendedMode: function(nodeId) {
        var node = cy.getElementById(nodeId);
        var readiness = checkPrereqsMet(node);
        return getRecommendedMode(node.data('status'), readiness.met >= readiness.total);
    },
    getPrereqReadiness: function(nodeId) {
        return checkPrereqsMet(cy.getElementById(nodeId));
    },
    isPathActive: function() { return pathActive; },
    getPathSteps: function() {
        return cy.nodes('.path-step').map(function(n) { return n.data('name'); });
    },
    getPathTarget: function() {
        var t = cy.nodes('.path-target');
        return t.length ? t[0].data('name') : null;
    },
    showLearningPath: function(nodeId) { showLearningPath(nodeId); },
    clearPath: function() { clearPath(); clearSelection(); },
    getStaleTier: function(nodeId) {
        var node = cy.getElementById(nodeId);
        if (node.hasClass('stale-overdue')) return 'overdue';
        if (node.hasClass('stale-stale')) return 'stale';
        if (node.hasClass('stale-aging')) return 'aging';
        return 'fresh';
    },
    setCurrentTime: function(isoString) { currentTimeOverride = isoString; },
    applyStalenessClasses: function() { applyStalenessClasses(); },
    renderReviewQueue: function() { renderReviewQueue(); },
    getGroupingMode: function() { return groupingMode; },
    setGroupingMode: function(mode) { setGroupingMode(mode); },
    getCompoundNodes: function() {
        return cy.nodes('[?isGroup]').map(function(n) { return n.data('name'); });
    },
    toggleSubcategory: function(cat, sub, checked) {
        document.querySelectorAll('.subcat-check').forEach(function(c) {
            if (c.dataset.category === cat && c.value === sub) c.checked = checked;
        });
        var anyChecked = false;
        document.querySelectorAll('.subcat-check[data-category="' + cat + '"]').forEach(function(s) {
            if (s.checked) anyChecked = true;
        });
        catChecks.forEach(function(c) {
            if (c.value === cat) c.checked = anyChecked;
        });
        applyFilters();
    },
    getActiveDetailTab: function() {
        var active = document.querySelector('.detail-tab.active');
        return active ? active.dataset.tab : null;
    },
    setDetailTab: function(tab) {
        var btn = document.querySelector('.detail-tab[data-tab="' + tab + '"]');
        if (btn) btn.click();
    }
};

})();
