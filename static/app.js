const toast = document.getElementById("toast");
const APP_CONFIG = window.APP_CONFIG || {};
const FANGSHAN_DISTRICT_KEYWORD = "北京市房山区";
let currentRecord = null;
let selectedFangshanRegion = "";
let fangshanMapReadyPromise = null;
let fangshanDistrictSearch = null;
let fangshanGeocoder = null;
let fangshanDistrictBounds = null;
let fangshanDistrictBoundaries = [];
let fangshanMapRenderToken = 0;
const fangshanRegionGeometryCache = new Map();
const tableState = {
    page: 1,
    pageSize: 20,
    pages: 1,
    total: 0,
    filters: new URLSearchParams(),
};

const fangshanMapLayout = [
    { name: "史家营乡", x: 16, y: 18, w: 88, h: 44 },
    { name: "大安山乡", x: 112, y: 18, w: 88, h: 44 },
    { name: "霞云岭乡", x: 208, y: 18, w: 88, h: 44 },
    { name: "蒲洼乡", x: 304, y: 18, w: 88, h: 44 },
    { name: "佛子庄乡", x: 64, y: 72, w: 92, h: 44 },
    { name: "南窖乡", x: 164, y: 72, w: 92, h: 44 },
    { name: "十渡镇", x: 264, y: 72, w: 92, h: 44 },
    { name: "张坊镇", x: 144, y: 126, w: 92, h: 44 },
    { name: "周口店镇", x: 248, y: 126, w: 92, h: 44 },
    { name: "韩村河镇", x: 352, y: 126, w: 96, h: 44 },
    { name: "大石窝镇", x: 64, y: 180, w: 96, h: 44 },
    { name: "河北镇", x: 170, y: 180, w: 88, h: 44 },
    { name: "青龙湖镇", x: 266, y: 180, w: 96, h: 44 },
    { name: "石楼镇", x: 372, y: 180, w: 88, h: 44 },
    { name: "长沟镇", x: 38, y: 234, w: 88, h: 44 },
    { name: "琉璃河镇", x: 136, y: 234, w: 96, h: 44 },
    { name: "窦店镇", x: 242, y: 234, w: 88, h: 44 },
    { name: "阎村镇", x: 338, y: 234, w: 88, h: 44 },
    { name: "长阳镇", x: 92, y: 288, w: 88, h: 44 },
    { name: "良乡镇", x: 188, y: 288, w: 88, h: 44 },
    { name: "拱辰街道", x: 284, y: 288, w: 88, h: 44 },
    { name: "西潞街道", x: 380, y: 288, w: 88, h: 44 },
    { name: "城关街道", x: 152, y: 342, w: 88, h: 40 },
    { name: "向阳街道", x: 246, y: 342, w: 88, h: 40 },
    { name: "东风街道", x: 340, y: 342, w: 88, h: 40 },
    { name: "迎风街道", x: 214, y: 390, w: 88, h: 40 },
    { name: "新镇街道", x: 308, y: 390, w: 88, h: 40 },
];
const fangshanLayoutMap = new Map(fangshanMapLayout.map((item) => [item.name, item]));
const FANGSHAN_DISTRICT_FALLBACK_PATH = "M 134 42 L 212 34 L 294 52 L 364 90 L 420 146 L 470 216 L 496 294 L 482 368 L 446 432 L 388 484 L 320 526 L 242 552 L 172 544 L 112 510 L 76 454 L 54 388 L 42 314 L 58 244 L 92 182 L 82 126 L 104 74 Z";

function showToast(message, isError = false) {
    if (!toast) return;
    toast.textContent = message;
    toast.style.borderColor = isError ? "rgba(255, 111, 111, 0.38)" : "rgba(101, 214, 177, 0.28)";
    toast.classList.add("show");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2800);
}

async function postForm(url, form) {
    const response = await fetch(url, {
        method: "POST",
        body: new FormData(form),
    });
    if (!response.ok) {
        throw new Error(await resolveErrorMessage(response));
    }
    return response.json();
}

async function postFields(url, fields) {
    const data = new FormData();
    Object.entries(fields).forEach(([key, value]) => data.append(key, value));
    const response = await fetch(url, {
        method: "POST",
        body: data,
    });
    if (!response.ok) {
        throw new Error(await resolveErrorMessage(response));
    }
    return response.json();
}

async function getJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(await resolveErrorMessage(response));
    }
    return response.json();
}

async function resolveErrorMessage(response) {
    try {
        const payload = await response.json();
        return payload.detail || payload.message || "request_failed";
    } catch (error) {
        return "request_failed";
    }
}

function createDistributionRows(items) {
    if (!Array.isArray(items) || !items.length) {
        return '<div class="admin-record"><p>暂无数据。</p></div>';
    }
    const safeMax = Math.max(...items.map((item) => item.count), 1);
    return items.map((item) => `
        <div class="distribution-row">
            <span>${item.name}</span>
            <div class="distribution-bar">
                <i style="width:${Math.max((item.count / safeMax) * 100, 10)}%"></i>
            </div>
            <strong>${item.count}</strong>
        </div>
    `).join("");
}

function fillList(container, items, emptyText = "暂无") {
    if (!container) return;
    const normalized = Array.isArray(items) && items.length ? items : [emptyText];
    container.innerHTML = normalized.map((item) => `<li>${item}</li>`).join("");
}

function renderSourceTags(items) {
    const container = document.getElementById("source-tags");
    if (!container) return;
    container.innerHTML = items.map((item) => `<span>${item.name} · ${item.count}</span>`).join("");
}

function renderIntegrationSources(items) {
    const container = document.getElementById("integration-sources");
    if (!container) return;
    container.innerHTML = items.map((item) => `
        <article class="integration-source-item">
            <div class="integration-source-head">
                <strong>${item.source_system}</strong>
                <span>${item.mode}</span>
            </div>
            <p>${item.status}</p>
            <div class="integration-source-meta">
                <span>鉴权：${item.auth_type || "none"}</span>
                <span>拉取：${item.pull_strategy || "manual"}</span>
                <span>地址：${item.endpoint || "未配置"}</span>
            </div>
        </article>
    `).join("");
}

function renderPagination() {
    const pageInfo = document.getElementById("table-page-info");
    const prevBtn = document.getElementById("table-prev-btn");
    const nextBtn = document.getElementById("table-next-btn");
    if (pageInfo) {
        pageInfo.textContent = `第 ${tableState.page} / ${tableState.pages} 页，共 ${tableState.total} 条`;
    }
    if (prevBtn) prevBtn.disabled = tableState.page <= 1;
    if (nextBtn) nextBtn.disabled = tableState.page >= tableState.pages;
}

function renderRecordTable(payload) {
    const items = payload.items || [];
    const container = document.getElementById("screening-table-body");
    const countText = document.getElementById("table-count-text");
    if (!container) return;

    tableState.page = payload.page || 1;
    tableState.pages = payload.pages || 1;
    tableState.total = payload.total || items.length;
    tableState.pageSize = payload.page_size || tableState.pageSize;

    if (countText) {
        countText.textContent = `当前第 ${tableState.page} 页 / 共 ${tableState.total} 条`;
    }
    if (!items.length) {
        container.innerHTML = '<tr><td colspan="8" class="empty-cell">当前条件下暂无工单。</td></tr>';
        renderPagination();
        return;
    }
    container.innerHTML = items.map((item) => {
        const dupLevel = item.duplicate_level && item.duplicate_level !== "无"
            ? `<span class="cell-tag dup">${item.duplicate_level}</span>` : "";
        const anomaly = item.performance_anomaly_level && item.performance_anomaly_level !== "无"
            ? `<span class="cell-tag anomaly">履职${item.performance_anomaly_level}</span>` : "";
        const confidence = item.domain_confidence
            ? `<span class="cell-tag soft">置信${Math.round(item.domain_confidence * 100)}%</span>` : "";
        return `
        <tr>
            <td>${item.ticket_no}</td>
            <td>${item.source}</td>
            <td>${item.category}${confidence}</td>
            <td>${item.public_interest_level || "待复核"}${dupLevel}</td>
            <td>${item.risk_level}</td>
            <td>${item.warning_level || "无"}${anomaly}</td>
            <td>${item.location_text || "未识别"}</td>
            <td><button type="button" class="table-action-btn" data-record-id="${item.id}">查看</button></td>
        </tr>
    `;
    }).join("");
    renderPagination();
}

function renderFocusLocations(items) {
    const container = document.getElementById("focus-location-list");
    if (!container) return;
    if (!items.length) {
        container.innerHTML = '<div class="admin-record"><p>当前暂无重复点位聚合结果。</p></div>';
        return;
    }
    container.innerHTML = items.map((item) => `
        <div class="admin-record">
            <strong>${item.name}</strong>
            <p>关联投诉 ${item.count} 条</p>
        </div>
    `).join("");
}

function renderSearchMeta(meta) {
    const container = document.getElementById("semantic-search-meta");
    if (!container) return;
    if (!meta || !meta.query) {
        container.textContent = "当前支持关键词直达、扩展词召回和本地语义联想检索。";
        return;
    }
    const expanded = (meta.expanded_terms || []).slice(0, 6).join(" / ");
    container.textContent = [
        `当前检索：${meta.query}`,
        `模式：${meta.search_mode || "hybrid"}`,
        `召回 ${meta.matched_count || 0} 条`,
        expanded ? `扩展词：${expanded}` : "",
    ].filter(Boolean).join(" · ");
}

function renderPointClusters(payload) {
    const container = document.getElementById("point-cluster-list");
    const metaNode = document.getElementById("point-cluster-meta");
    if (!container) return;
    const items = (payload || {}).items || [];
    if (metaNode) {
        metaNode.textContent = items.length
            ? `${payload.mode === "aggressive" ? "增强模式" : "默认模式"}已返回 ${payload.total || items.length} 个聚合结果。`
            : "当前没有可展示的监督点位聚合结果。";
    }
    if (!items.length) {
        container.innerHTML = '<div class="admin-record"><p>当前暂无可展示的监督点位聚合结果。</p></div>';
        return;
    }
    container.innerHTML = items.map((item) => `
        <div class="admin-record">
            <strong>${item.label}</strong>
            <p>关联投诉 ${item.count} 条 · 类别：${(item.categories || []).join(" / ") || "待识别"}</p>
            <p>聚类置信度 ${Math.round((item.confidence || 0) * 1000) / 10}%</p>
            <p>${(item.reason_lines || []).join("；") || "暂无解释"}</p>
            <p>${item.risk_hint || ""}</p>
        </div>
    `).join("");
}

function renderExportHistory(items) {
    const container = document.getElementById("export-history");
    if (!container) return;
    if (!items.length) {
        container.innerHTML = '<div class="admin-record"><p>暂无导出记录。</p></div>';
        return;
    }
    container.innerHTML = items.map((item) => `
        <div class="admin-record">
            <strong>${item.file_name}</strong>
            <p>${item.export_scope} · ${item.item_count} 条</p>
        </div>
    `).join("");
}

function renderHotspotList(containerId, items, valueLabel) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!items.length) {
        container.innerHTML = '<div class="admin-record"><p>暂无数据。</p></div>';
        return;
    }
    container.innerHTML = items.map((item) => `
        <div class="admin-record">
            <strong>${item.name}</strong>
            <p>${valueLabel} ${item.count} 条</p>
        </div>
    `).join("");
}

function renderSimpleTrend(containerId, items) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!items.length) {
        container.innerHTML = '<div class="admin-record"><p>暂无趋势数据。</p></div>';
        return;
    }
    const safeMax = Math.max(...items.map((item) => item.count), 1);
    container.innerHTML = items.map((item) => `
        <div class="trend-row">
            <span>${item.label}</span>
            <div class="distribution-bar">
                <i style="width:${Math.max((item.count / safeMax) * 100, 10)}%"></i>
            </div>
            <strong>${item.count}</strong>
        </div>
    `).join("");
}

function renderDomainTrends(items) {
    const container = document.getElementById("domain-trend-list");
    if (!container) return;
    if (!items.length) {
        container.innerHTML = '<div class="admin-record"><p>当前暂无重点领域趋势。</p></div>';
        return;
    }
    container.innerHTML = items.map((item) => `
        <div class="admin-record">
            <strong>${item.domain}</strong>
            <p>${(item.series || []).map((entry) => `${entry.label} ${entry.count}条`).join(" / ")}</p>
        </div>
    `).join("");
}

function renderDifficultRecords(items) {
    const container = document.getElementById("difficult-record-list");
    if (!container) return;
    if (!items.length) {
        container.innerHTML = '<div class="admin-record"><p>当前暂无疑难工单。</p></div>';
        return;
    }
    container.innerHTML = items.map((item) => `
        <div class="admin-record">
            <strong>${item.ticket_no} · ${item.title}</strong>
            <p>${item.district} / ${item.legal_domain} / 预警 ${item.warning_level} / 优先级 ${item.priority_level}</p>
            <p>重复 ${item.duplicate_count} 次，持续 ${item.duration_days} 天</p>
        </div>
    `).join("");
}

function renderSpecialReport(report) {
    const container = document.getElementById("special-report-summary");
    if (!container || !report) return;
    const lines = [
        `统计周期：${report.reporting_period || "待生成"}`,
        ...(report.summary_lines || []),
    ];
    container.textContent = lines.join("\n");
}

function heatColor(value, maxValue) {
    if (!maxValue) return "rgba(90, 140, 255, 0.12)";
    const ratio = Math.max(0, Math.min(1, value / maxValue));
    return `rgba(90, 140, 255, ${0.16 + ratio * 0.54})`;
}

function clampRatio(value) {
    return Math.max(0, Math.min(1, value));
}

function getThermalHue(ratio) {
    const normalized = clampRatio(ratio);
    return 220 - normalized * 214;
}

function getThermalColor(ratio, alpha = 1) {
    const hue = getThermalHue(ratio);
    const saturation = 88;
    const lightness = 58 - clampRatio(ratio) * 10;
    return `hsla(${hue}, ${saturation}%, ${lightness}%, ${alpha})`;
}

function getThermalAccentColor(ratio, alpha = 1) {
    const hue = Math.max(0, getThermalHue(ratio) - 8);
    return `hsla(${hue}, 96%, ${50 - clampRatio(ratio) * 6}%, ${alpha})`;
}

function getFangshanRegionName(item) {
    return item?.region_name || item?.name || "";
}

function getFangshanRegionKeyword(item) {
    return item?.region_search_keyword || `${FANGSHAN_DISTRICT_KEYWORD}${getFangshanRegionName(item)}`;
}

function getFangshanMaxMetric(items, fieldName) {
    return Math.max(...items.map((item) => item?.[fieldName] || 0), 1);
}

function setFangshanMapState(message, tone = "loading") {
    const container = document.getElementById("fangshan-map-panel");
    if (!container) return;
    container.className = `fangshan-map-panel is-${tone}`;
    container.innerHTML = `<div class="fangshan-map-state">${message}</div>`;
}

function clearFangshanMapState() {
    const container = document.getElementById("fangshan-map-panel");
    if (!container) return;
    container.className = "fangshan-map-panel";
}

function hasAmapSupport() {
    return Boolean(APP_CONFIG.amapWebKey && window.AMap);
}

function computeBoundaryBounds(boundaries) {
    let minLng = Infinity;
    let maxLng = -Infinity;
    let minLat = Infinity;
    let maxLat = -Infinity;
    (boundaries || []).forEach((ring) => {
        (ring || []).forEach((point) => {
            const lng = typeof point.getLng === "function" ? point.getLng() : point.lng;
            const lat = typeof point.getLat === "function" ? point.getLat() : point.lat;
            if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
            minLng = Math.min(minLng, lng);
            maxLng = Math.max(maxLng, lng);
            minLat = Math.min(minLat, lat);
            maxLat = Math.max(maxLat, lat);
        });
    });
    if (![minLng, maxLng, minLat, maxLat].every(Number.isFinite)) {
        return null;
    }
    return { minLng, maxLng, minLat, maxLat };
}

function normalizeBoundaryPoint(point) {
    if (!point) return null;
    if (typeof point.getLng === "function" && typeof point.getLat === "function") {
        return { lng: point.getLng(), lat: point.getLat() };
    }
    if (Array.isArray(point) && point.length >= 2) {
        const lng = Number(point[0]);
        const lat = Number(point[1]);
        return Number.isFinite(lng) && Number.isFinite(lat) ? { lng, lat } : null;
    }
    if (typeof point === "string") {
        const parts = point.split(",");
        if (parts.length >= 2) {
            const lng = Number(parts[0]);
            const lat = Number(parts[1]);
            return Number.isFinite(lng) && Number.isFinite(lat) ? { lng, lat } : null;
        }
        return null;
    }
    if (typeof point.lng !== "undefined" && typeof point.lat !== "undefined") {
        const lng = Number(point.lng);
        const lat = Number(point.lat);
        return Number.isFinite(lng) && Number.isFinite(lat) ? { lng, lat } : null;
    }
    return null;
}

function normalizeBoundaryRing(ring) {
    if (!ring) return [];
    if (typeof ring === "string") {
        return ring
            .split(";")
            .map((item) => normalizeBoundaryPoint(item))
            .filter(Boolean);
    }
    if (Array.isArray(ring)) {
        return ring
            .map((item) => normalizeBoundaryPoint(item))
            .filter(Boolean);
    }
    return [];
}

function normalizeDistrictBoundaries(boundaries) {
    return (boundaries || [])
        .map((ring) => normalizeBoundaryRing(ring))
        .filter((ring) => ring.length >= 3);
}

function projectLngLatToSvgPoint(lng, lat, width, height, padding = 28) {
    if (!fangshanDistrictBounds) {
        return { x: width / 2, y: height / 2 };
    }
    const safeWidth = Math.max(width - padding * 2, 1);
    const safeHeight = Math.max(height - padding * 2, 1);
    const xRatio = (lng - fangshanDistrictBounds.minLng) / Math.max(fangshanDistrictBounds.maxLng - fangshanDistrictBounds.minLng, 0.0001);
    const yRatio = (fangshanDistrictBounds.maxLat - lat) / Math.max(fangshanDistrictBounds.maxLat - fangshanDistrictBounds.minLat, 0.0001);
    return {
        x: padding + xRatio * safeWidth,
        y: padding + yRatio * safeHeight,
    };
}

function buildBoundarySvgPath(boundaries, width, height, padding = 28) {
    return (boundaries || []).map((ring) => {
        const commands = (ring || []).map((point, index) => {
            const lng = point.lng;
            const lat = point.lat;
            const projected = projectLngLatToSvgPoint(lng, lat, width, height, padding);
            return `${index === 0 ? "M" : "L"} ${projected.x.toFixed(2)} ${projected.y.toFixed(2)}`;
        });
        return `${commands.join(" ")} Z`;
    }).join(" ");
}

function buildFangshanHeatMetrics(item, geometry, width, height, maxIntensity) {
    const regionName = getFangshanRegionName(item);
    const isSelected = selectedFangshanRegion === regionName;
    const point = geometry?.svgPoint
        ? geometry.svgPoint
        : projectLngLatToSvgPoint(
            ...(geometry.center || getBoundaryCenter(fangshanDistrictBounds)),
            width,
            height,
        );
    const intensity = item.intensity_score || item.count || 0;
    const ratio = Math.max(0.14, Math.min(1, intensity / maxIntensity));
    const complaintRadius = 18 + ratio * 48;
    const riskRatio = clampRatio((item.warning_count + item.difficult_count * 1.4) / Math.max(maxIntensity, 1));
    const riskRadius = 12 + riskRatio * 36;
    const heatOpacity = 0.2 + ratio * 0.42;
    const riskOpacity = item.warning_count || item.difficult_count ? 0.18 + riskRatio * 0.5 : 0;
    const labelY = point.y - complaintRadius - 10;
    const heatColorValue = getThermalColor(ratio, heatOpacity);
    const riskColorValue = getThermalAccentColor(Math.max(ratio, riskRatio), riskOpacity);
    const coreColor = getThermalAccentColor(Math.max(ratio, 0.22), 0.98);
    const glowColor = getThermalColor(ratio, 0.22 + ratio * 0.22);
    return {
        regionName,
        isSelected,
        point,
        complaintRadius,
        riskRadius,
        heatOpacity,
        riskOpacity,
        labelY,
        ratio,
        riskRatio,
        heatColorValue,
        riskColorValue,
        coreColor,
        glowColor,
    };
}

function buildFangshanHeatWaveNode(item, geometry, width, height, maxIntensity) {
    const metrics = buildFangshanHeatMetrics(item, geometry, width, height, maxIntensity);
    return `
        <g class="fangshan-heat-node ${metrics.isSelected ? "selected" : ""}" data-region-name="${metrics.regionName}">
            <circle class="heat-glow" cx="${metrics.point.x.toFixed(2)}" cy="${metrics.point.y.toFixed(2)}" r="${(metrics.complaintRadius * 1.22).toFixed(2)}"
                fill="${metrics.glowColor}"></circle>
            <circle class="heat-wave" cx="${metrics.point.x.toFixed(2)}" cy="${metrics.point.y.toFixed(2)}" r="${metrics.complaintRadius.toFixed(2)}"
                fill="${metrics.heatColorValue}"></circle>
            <circle class="risk-wave" cx="${metrics.point.x.toFixed(2)}" cy="${metrics.point.y.toFixed(2)}" r="${metrics.riskRadius.toFixed(2)}"
                fill="${metrics.riskColorValue}"></circle>
        </g>
    `;
}

function buildFangshanHeatLabelNode(item, geometry, width, height, maxIntensity) {
    const metrics = buildFangshanHeatMetrics(item, geometry, width, height, maxIntensity);
    const trendTag = item.trend_direction === "升温" ? "↑" : item.trend_direction === "回落" ? "↓" : "→";
    return `
        <g class="fangshan-heat-node ${metrics.isSelected ? "selected" : ""}" data-region-name="${metrics.regionName}">
            <circle class="core-point" cx="${metrics.point.x.toFixed(2)}" cy="${metrics.point.y.toFixed(2)}" r="${metrics.isSelected ? 8 : 6}"
                fill="${metrics.isSelected ? "#fff0c7" : metrics.coreColor}"></circle>
            <text class="heat-label" x="${metrics.point.x.toFixed(2)}" y="${metrics.labelY.toFixed(2)}" text-anchor="middle">${metrics.regionName}</text>
            <text class="heat-value" x="${metrics.point.x.toFixed(2)}" y="${(metrics.labelY + 16).toFixed(2)}" text-anchor="middle">${item.count || 0}条 / 风险${item.warning_count || 0} / ${trendTag}</text>
        </g>
    `;
}

function getBoundaryCenter(bounds) {
    if (!bounds) return [116.139, 39.735];
    return [
        (bounds.minLng + bounds.maxLng) / 2,
        (bounds.minLat + bounds.maxLat) / 2,
    ];
}

function projectLayoutPointToBoundary(regionName) {
    const layout = fangshanLayoutMap.get(regionName);
    if (!layout || !fangshanDistrictBounds) {
        const [lng, lat] = getBoundaryCenter(fangshanDistrictBounds);
        return { center: [lng, lat], source: "layout" };
    }
    const xRatio = (layout.x + layout.w / 2) / 490;
    const yRatio = (layout.y + layout.h / 2) / 450;
    const lng = fangshanDistrictBounds.minLng + (fangshanDistrictBounds.maxLng - fangshanDistrictBounds.minLng) * xRatio;
    const lat = fangshanDistrictBounds.maxLat - (fangshanDistrictBounds.maxLat - fangshanDistrictBounds.minLat) * yRatio;
    return { center: [lng, lat], source: "layout" };
}

function projectLayoutPointToSvg(regionName, width, height, padding = 54) {
    const layout = fangshanLayoutMap.get(regionName);
    if (!layout) {
        return { x: width / 2, y: height / 2 };
    }
    const innerWidth = Math.max(width - padding * 2, 1);
    const innerHeight = Math.max(height - padding * 2, 1);
    return {
        x: padding + ((layout.x + layout.w / 2) / 490) * innerWidth,
        y: padding + ((layout.y + layout.h / 2) / 450) * innerHeight,
    };
}

function districtSearchOnce(keyword) {
    return new Promise((resolve, reject) => {
        if (!fangshanDistrictSearch) {
            reject(new Error("district_search_unavailable"));
            return;
        }
        fangshanDistrictSearch.search(keyword, (status, result) => {
            if (status === "complete" && result?.districtList?.length) {
                resolve(result.districtList[0]);
                return;
            }
            reject(new Error("district_search_failed"));
        });
    });
}

function geocodeOnce(keyword) {
    return new Promise((resolve, reject) => {
        if (!fangshanGeocoder) {
            reject(new Error("geocoder_unavailable"));
            return;
        }
        fangshanGeocoder.getLocation(keyword, (status, result) => {
            if (status === "complete" && result?.geocodes?.length) {
                const first = result.geocodes[0];
                const location = first.location;
                const lng = typeof location?.getLng === "function" ? location.getLng() : location?.lng;
                const lat = typeof location?.getLat === "function" ? location.getLat() : location?.lat;
                if (Number.isFinite(lng) && Number.isFinite(lat)) {
                    resolve({ center: [lng, lat], source: "geocoder" });
                    return;
                }
            }
            reject(new Error("geocode_failed"));
        });
    });
}

async function ensureFangshanMapReady() {
    if (fangshanMapReadyPromise) return fangshanMapReadyPromise;
    fangshanMapReadyPromise = (async () => {
        if (!hasAmapSupport()) {
            throw new Error("amap_unavailable");
        }
        const container = document.getElementById("fangshan-map-panel");
        if (!container) {
            throw new Error("map_container_missing");
        }
        setFangshanMapState("正在加载房山区真实地图...", "loading");
        container.innerHTML = "";
        clearFangshanMapState();
        fangshanDistrictSearch = new AMap.DistrictSearch({
            level: "district",
            subdistrict: 0,
            extensions: "all",
        });
        fangshanGeocoder = new AMap.Geocoder({
            city: "北京",
            citylimit: false,
        });
        const district = await districtSearchOnce(FANGSHAN_DISTRICT_KEYWORD);
        fangshanDistrictBoundaries = normalizeDistrictBoundaries(district?.boundaries || []);
        fangshanDistrictBounds = computeBoundaryBounds(fangshanDistrictBoundaries);
        container.classList.add("is-live", "is-thematic");
        return {
            boundaries: fangshanDistrictBoundaries,
            bounds: fangshanDistrictBounds,
        };
    })().catch((error) => {
        fangshanMapReadyPromise = null;
        throw error;
    });
    return fangshanMapReadyPromise;
}

async function resolveFangshanRegionGeometry(item) {
    const regionName = getFangshanRegionName(item);
    if (fangshanRegionGeometryCache.has(regionName)) {
        return fangshanRegionGeometryCache.get(regionName);
    }
    let geometry = null;
    try {
        geometry = await geocodeOnce(getFangshanRegionKeyword(item));
    } catch (error) {
        geometry = null;
    }
    if (!geometry) {
        geometry = {
            ...projectLayoutPointToBoundary(regionName),
            svgPoint: projectLayoutPointToSvg(regionName, 760, 620),
        };
    }
    fangshanRegionGeometryCache.set(regionName, geometry);
    return geometry;
}

function renderFangshanRegionDetails(items, regionName = "") {
    const clusterContainer = document.getElementById("fangshan-map-clusters");
    const recordContainer = document.getElementById("fangshan-map-records");
    const metaNode = document.getElementById("fangshan-map-meta");
    const selectedNode = document.getElementById("fangshan-map-selected");
    if (!clusterContainer || !recordContainer) return;

    if (!regionName) {
        if (selectedNode) selectedNode.textContent = "当前区域：全部街镇";
        if (metaNode) {
            const topHot = [...items]
                .sort((a, b) => (b.intensity_score || 0) - (a.intensity_score || 0))
                .filter((item) => (item.count || 0) > 0)
                .slice(0, 3)
                .map((item) => `${getFangshanRegionName(item)}(${item.count || 0}条/${item.trend_direction || "平稳"})`)
                .join("、");
            metaNode.textContent = topHot
                ? `宏观提示：当前高热区域主要集中在 ${topHot}。点击房山区内部热区，查看对应热点点位和疑难工单。`
                : "点击房山区内部热区，查看对应热点点位和疑难工单。";
        }
        const topRegions = [...items].sort((a, b) => b.count - a.count).filter((item) => item.count > 0).slice(0, 6);
        clusterContainer.innerHTML = topRegions.length ? topRegions.map((item) => `
            <div class="admin-record">
                <strong>${getFangshanRegionName(item)}</strong>
                <p>工单 ${item.count} 条 / 公益 ${item.public_interest_count} 条 / 预警 ${item.warning_count} 条</p>
            </div>
        `).join("") : '<div class="admin-record"><p>当前暂无区域热区数据。</p></div>';
        const difficult = items.flatMap((item) => item.difficult_records || []).slice(0, 6);
        recordContainer.innerHTML = difficult.length ? difficult.map((item) => `
            <div class="admin-record">
                <strong>${item.ticket_no} · ${item.title}</strong>
                <p>${item.area_name} / ${item.legal_domain} / 预警 ${item.warning_level}</p>
            </div>
        `).join("") : '<div class="admin-record"><p>当前暂无疑难工单。</p></div>';
        return;
    }

    const target = items.find((item) => getFangshanRegionName(item) === regionName);
    if (selectedNode) selectedNode.textContent = `当前区域：${regionName}`;
    if (!target) {
        if (metaNode) metaNode.textContent = "当前区域暂无空间聚合数据。";
        clusterContainer.innerHTML = '<div class="admin-record"><p>当前区域暂无热点点位。</p></div>';
        recordContainer.innerHTML = '<div class="admin-record"><p>当前区域暂无疑难工单。</p></div>';
        return;
    }
    if (metaNode) {
        metaNode.textContent = `工单 ${target.count} 条，公益 ${target.public_interest_count} 条，预警 ${target.warning_count} 条，疑难 ${target.difficult_count} 条。${target.trend_summary || ""}`;
    }
    clusterContainer.innerHTML = (target.top_clusters || []).length ? target.top_clusters.map((item) => `
        <div class="admin-record">
            <strong>${item.label}</strong>
            <p>关联 ${item.count} 条</p>
        </div>
    `).join("") : '<div class="admin-record"><p>当前区域暂无热点点位。</p></div>';
    recordContainer.innerHTML = (target.difficult_records || []).length ? target.difficult_records.map((item) => `
        <div class="admin-record">
            <strong>${item.ticket_no} · ${item.title}</strong>
            <p>${item.legal_domain} / 预警 ${item.warning_level} / 重复 ${item.duplicate_count} 次 / ${item.duration_days} 天</p>
        </div>
    `).join("") : '<div class="admin-record"><p>当前区域暂无疑难工单。</p></div>';
}

function renderFangshanFallbackMap(items, reason = "") {
    const container = document.getElementById("fangshan-map-panel");
    if (!container) return;
    container.className = "fangshan-map-panel is-fallback";
    const maxValue = Math.max(...items.map((item) => item.count || 0), 1);
    const itemMap = new Map(items.map((item) => [getFangshanRegionName(item), item]));
    const svg = `
        ${reason ? `<div class="fangshan-map-fallback-tip">${reason}</div>` : ""}
        <svg viewBox="0 0 490 450" class="fangshan-map-svg" role="img" aria-label="房山区街镇热区地图">
            ${fangshanMapLayout.map((region) => {
                const item = itemMap.get(region.name) || { count: 0, warning_count: 0, difficult_count: 0 };
                const selectedClass = selectedFangshanRegion === region.name ? "map-region selected" : "map-region";
                return `
                    <g class="${selectedClass}" data-region-name="${region.name}">
                        <rect x="${region.x}" y="${region.y}" rx="14" ry="14" width="${region.w}" height="${region.h}" fill="${heatColor(item.count, maxValue)}"></rect>
                        <text x="${region.x + region.w / 2}" y="${region.y + 18}" text-anchor="middle" class="map-region-label">${region.name}</text>
                        <text x="${region.x + region.w / 2}" y="${region.y + 34}" text-anchor="middle" class="map-region-value">${item.count || 0}条</text>
                    </g>
                `;
            }).join("")}
        </svg>
    `;
    container.innerHTML = svg;
    container.querySelectorAll("[data-region-name]").forEach((node) => {
        node.addEventListener("click", () => {
            const regionName = node.getAttribute("data-region-name");
            selectedFangshanRegion = selectedFangshanRegion === regionName ? "" : regionName;
            renderFangshanMap(items);
            renderFangshanRegionDetails(items, selectedFangshanRegion);
        });
    });
    renderFangshanRegionDetails(items, selectedFangshanRegion);
}

async function renderFangshanGeoMap(items) {
    const renderToken = ++fangshanMapRenderToken;
    await ensureFangshanMapReady();
    if (renderToken !== fangshanMapRenderToken) return;
    const maxIntensity = getFangshanMaxMetric(items, "intensity_score");
    const geometries = await Promise.all(items.map((item) => resolveFangshanRegionGeometry(item)));
    if (renderToken !== fangshanMapRenderToken) return;
    const container = document.getElementById("fangshan-map-panel");
    if (!container) return;
    container.className = "fangshan-map-panel is-live is-thematic";
    const width = 760;
    const height = 620;
    if (!fangshanDistrictBoundaries.length || !fangshanDistrictBounds) {
        renderFangshanSilhouetteMap(items, "房山区边界数据不可用，已切换为房山区轮廓热力图。");
        return;
    }
    const boundaryPath = buildBoundarySvgPath(fangshanDistrictBoundaries, width, height, 28);
    if (!boundaryPath.trim()) {
        renderFangshanSilhouetteMap(items, "房山区边界路径生成失败，已切换为房山区轮廓热力图。");
        return;
    }
    const heatWaveNodes = items.map((item, index) =>
        buildFangshanHeatWaveNode(
            item,
            geometries[index] || projectLayoutPointToBoundary(getFangshanRegionName(item)),
            width,
            height,
            maxIntensity,
        )
    ).join("");
    const labelNodes = items.map((item, index) =>
        buildFangshanHeatLabelNode(
            item,
            geometries[index] || projectLayoutPointToBoundary(getFangshanRegionName(item)),
            width,
            height,
            maxIntensity,
        )
    ).join("");
    container.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" class="fangshan-thematic-svg" role="img" aria-label="房山区投诉热力专题图">
            <defs>
                <filter id="fangshanGlow">
                    <feGaussianBlur stdDeviation="14" result="blurred"></feGaussianBlur>
                </filter>
                <filter id="fangshanRiskGlow">
                    <feGaussianBlur stdDeviation="10" result="riskBlurred"></feGaussianBlur>
                </filter>
                <clipPath id="fangshanDistrictClip">
                    <path d="${boundaryPath}"></path>
                </clipPath>
            </defs>
            <rect x="0" y="0" width="${width}" height="${height}" class="district-bg"></rect>
            <path d="${boundaryPath}" class="district-shadow"></path>
            <path d="${boundaryPath}" class="district-shape"></path>
            <g clip-path="url(#fangshanDistrictClip)">
                <g class="district-heat-layer" filter="url(#fangshanGlow)">
                    ${heatWaveNodes}
                </g>
            </g>
            <path d="${boundaryPath}" class="district-outline"></path>
            <g class="district-label-layer">
                ${labelNodes}
            </g>
        </svg>
    `;
    container.querySelectorAll("[data-region-name]").forEach((node) => {
        node.addEventListener("click", async () => {
            const regionName = node.getAttribute("data-region-name");
            selectedFangshanRegion = selectedFangshanRegion === regionName ? "" : regionName;
            await renderFangshanMap(items);
        });
    });
    renderFangshanRegionDetails(items, selectedFangshanRegion);
}

function renderFangshanSilhouetteMap(items, reason = "") {
    const container = document.getElementById("fangshan-map-panel");
    if (!container) return;
    container.className = "fangshan-map-panel is-live is-thematic";
    const width = 760;
    const height = 620;
    const maxIntensity = getFangshanMaxMetric(items, "intensity_score");
    const heatWaveNodes = items.map((item) =>
        buildFangshanHeatWaveNode(
            item,
            { svgPoint: projectLayoutPointToSvg(getFangshanRegionName(item), width, height) },
            width,
            height,
            maxIntensity,
        )
    ).join("");
    const labelNodes = items.map((item) =>
        buildFangshanHeatLabelNode(
            item,
            { svgPoint: projectLayoutPointToSvg(getFangshanRegionName(item), width, height) },
            width,
            height,
            maxIntensity,
        )
    ).join("");
    container.innerHTML = `
        ${reason ? `<div class="fangshan-map-fallback-tip">${reason}</div>` : ""}
        <svg viewBox="0 0 ${width} ${height}" class="fangshan-thematic-svg" role="img" aria-label="房山区投诉热力专题图">
            <defs>
                <filter id="fangshanGlow">
                    <feGaussianBlur stdDeviation="14" result="blurred"></feGaussianBlur>
                </filter>
            </defs>
            <rect x="0" y="0" width="${width}" height="${height}" class="district-bg"></rect>
            <path d="${FANGSHAN_DISTRICT_FALLBACK_PATH}" class="district-shadow"></path>
            <path d="${FANGSHAN_DISTRICT_FALLBACK_PATH}" class="district-shape"></path>
            <g class="district-heat-layer" filter="url(#fangshanGlow)">
                ${heatWaveNodes}
            </g>
            <path d="${FANGSHAN_DISTRICT_FALLBACK_PATH}" class="district-outline"></path>
            <g class="district-label-layer">
                ${labelNodes}
            </g>
            <g class="district-legend-layer">
                <text x="528" y="58" class="legend-title">区域风险温度带</text>
                <defs>
                    <linearGradient id="thermalLegend" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stop-color="${getThermalColor(0.02, 0.92)}"></stop>
                        <stop offset="35%" stop-color="${getThermalColor(0.35, 0.92)}"></stop>
                        <stop offset="70%" stop-color="${getThermalColor(0.7, 0.92)}"></stop>
                        <stop offset="100%" stop-color="${getThermalColor(1, 0.98)}"></stop>
                    </linearGradient>
                </defs>
                <rect x="528" y="74" width="170" height="18" rx="9" fill="url(#thermalLegend)"></rect>
                <text x="528" y="108" class="legend-text">低热度</text>
                <text x="664" y="108" class="legend-text">高热度</text>
                <text x="528" y="134" class="legend-text">蓝色偏冷，红色偏热，代表投诉量和风险强度同步走高</text>
                <text x="528" y="156" class="legend-text">趋势：↑升温 / →平稳 / ↓回落</text>
                <text x="528" y="178" class="legend-text">用于发现房山区内部的高发区域、持续预警区域和系统性治理薄弱点</text>
            </g>
        </svg>
    `;
    container.querySelectorAll("[data-region-name]").forEach((node) => {
        node.addEventListener("click", () => {
            const regionName = node.getAttribute("data-region-name");
            selectedFangshanRegion = selectedFangshanRegion === regionName ? "" : regionName;
            renderFangshanSilhouetteMap(items, reason);
            renderFangshanRegionDetails(items, selectedFangshanRegion);
        });
    });
    renderFangshanRegionDetails(items, selectedFangshanRegion);
}

function getDashboardFilterParams() {
    const params = new URLSearchParams(tableState.filters);
    params.delete("query");
    params.delete("search_mode");
    params.delete("page");
    params.delete("page_size");
    return params;
}

async function renderFangshanMap(items) {
    if (!Array.isArray(items) || !items.length) {
        renderFangshanSilhouetteMap([], "当前暂无区域热区数据。");
        return;
    }
    renderFangshanSilhouetteMap(items);
}

function updateMetrics(data) {
    const metricMap = {
        "metric-total-records": data.total_records,
        "metric-screened-records": data.screened_records,
        "metric-procuratorial-records": data.procuratorial_records,
        "metric-high-risk-records": data.high_risk_records,
        "metric-duplicate-records": data.duplicate_records,
        "metric-location-records": data.location_records,
    };
    Object.entries(metricMap).forEach(([id, value]) => {
        const node = document.getElementById(id);
        if (node) node.textContent = value;
    });

    const llmModeNode = document.getElementById("llm-mode-text");
    const llmProviderNode = document.getElementById("llm-provider-text");
    const integrationModeNode = document.getElementById("integration-mode-text");
    const localModelStatusNode = document.getElementById("local-model-status-text");
    const localModelDetailNode = document.getElementById("local-model-detail-text");
    if (llmModeNode) llmModeNode.textContent = data.llm_status.mode;
    if (llmProviderNode) llmProviderNode.textContent = `${data.llm_status.provider} / ${data.llm_status.model_name}`;
    if (integrationModeNode) integrationModeNode.textContent = data.integration_status.status;
    if (localModelStatusNode) localModelStatusNode.textContent = data.model_status.summary;
    if (localModelDetailNode) localModelDetailNode.textContent = data.model_status.detail;
}

function renderDashboard(data) {
    updateMetrics(data);
    renderSourceTags(data.source_distribution || []);
    renderIntegrationSources(data.integration_sources || []);

    const sourceDistribution = document.getElementById("source-distribution");
    const categoryDistribution = document.getElementById("category-distribution");
    const riskDistribution = document.getElementById("risk-distribution");
    const reviewDistribution = document.getElementById("review-distribution");
    const publicInterestDistribution = document.getElementById("public-interest-distribution");
    const legalDomainDistribution = document.getElementById("legal-domain-distribution");
    const warningDistribution = document.getElementById("warning-distribution");
    if (sourceDistribution) sourceDistribution.innerHTML = createDistributionRows(data.source_distribution || []);
    if (categoryDistribution) categoryDistribution.innerHTML = createDistributionRows(data.category_distribution || []);
    if (riskDistribution) riskDistribution.innerHTML = createDistributionRows(data.risk_distribution || []);
    if (reviewDistribution) reviewDistribution.innerHTML = createDistributionRows(data.review_distribution || []);
    if (publicInterestDistribution) publicInterestDistribution.innerHTML = createDistributionRows(data.public_interest_distribution || []);
    if (legalDomainDistribution) legalDomainDistribution.innerHTML = createDistributionRows(data.legal_domain_distribution || []);
    if (warningDistribution) warningDistribution.innerHTML = createDistributionRows(data.warning_distribution || []);

    renderFocusLocations(data.focus_locations || []);
    renderExportHistory(data.recent_exports || []);
    renderHotspotList("district-hotspot-list", data.district_hotspots || [], "重点线索");
    renderSimpleTrend("public-interest-trend", ((data.trend_series || {}).public_interest) || []);
    renderSimpleTrend("warning-trend", ((data.trend_series || {}).warning) || []);
    renderSimpleTrend("duplicate-trend", ((data.trend_series || {}).duplicates) || []);
    renderDomainTrends(data.domain_trends || []);
    renderDifficultRecords(data.difficult_records || []);
    renderSpecialReport(data.special_report || {});
    renderFangshanMap(data.fangshan_map_regions || []);

    const performanceSummary = data.performance_anomaly_summary || {};
    const anomalyDistNode = document.getElementById("performance-anomaly-distribution");
    if (anomalyDistNode) {
        anomalyDistNode.innerHTML = createDistributionRows(performanceSummary.level_distribution || []);
    }
    renderRankingList(
        "performance-anomaly-buckets",
        performanceSummary.ranking || [],
        (item) => `
            <div class="admin-record">
                <strong>${item.district} · ${item.legal_domain}</strong>
                <p>样本 ${item.total} 条 · 解决率 ${formatPercent(item.resolution_rate)} · 不满意率 ${formatPercent(item.dissatisfaction_rate)} · 超时率 ${formatPercent(item.timeout_rate)}</p>
                <p>履职异常工单 ${item.anomaly_count} 条</p>
            </div>
        `
    );
    const dupLayerNode = document.getElementById("duplicate-layer-distribution");
    if (dupLayerNode) {
        dupLayerNode.innerHTML = createDistributionRows(data.duplicate_layer_distribution || []);
    }
    renderRankingList(
        "urgent-record-list",
        data.urgent_records || [],
        (item) => `
            <div class="admin-record">
                <strong>${item.ticket_no} · ${item.title}</strong>
                <p>${item.legal_domain || "待补充"} / 预警 ${item.warning_level || "无"} / 重复 ${item.duplicate_count || 1} 次</p>
                <p>${item.warning_reason_summary || `已持续 ${item.duration_days || 0} 天`}</p>
            </div>
        `
    );
    renderPushTaskSummary(data.push_task_summary);
    renderPushTaskList(data.push_tasks || []);
}

function renderSelectedRecord(record) {
    currentRecord = record;
    const pill = document.getElementById("selected-record-pill");
    const summaryBox = document.getElementById("selected-record-summary");
    const reviewForm = document.getElementById("review-form");
    const structuredFieldsList = document.getElementById("structured-fields-list");
    const matchedRulesList = document.getElementById("matched-rules-list");
    const assistantSummary = document.getElementById("assistant-summary");
    const assistantKeyPoints = document.getElementById("assistant-key-points");
    const pointLabel = ((record.normalized_point || {}).point_label) || record.point_cluster_label || record.location_text || "未识别";
    const searchExplanation = record.search_explanation || {};
    const topCandidates = ((record.ensemble_prediction || {}).top_candidates || [])
        .map((item) => `${item.label} ${Math.round(item.score * 1000) / 10}%`)
        .join(" / ");

    if (pill) {
        pill.textContent = `${record.ticket_no} / ${record.category} / ${record.risk_level} / 预警${record.warning_level || "无"}`;
        pill.className = `status-pill ${riskClass(record.risk_level)}`;
    }
    if (summaryBox) {
        summaryBox.textContent = [
            `标题：${record.title}`,
            `来源：${record.source} / 区域：${record.district || "待核实"}`,
            `投诉时间：${record.event_time || "待补充"}`,
            `筛查摘要：${record.screening_summary || "尚未筛查"}`,
            `公益属性：${record.public_interest_level || "待复核"} / 公益评分：${Math.round((record.public_interest_score || 0) * 1000) / 10}%`,
            `法定领域：${formatLegalDomainDisplay(record)} / 优先级：${record.priority_level || "低"} / 预警等级：${record.warning_level || "无"}`,
            `办理状态：解决=${record.resolved_status || "待核实"} / 满意=${record.satisfaction_status || "待核实"} / 响应=${record.response_status || "待核实"}`,
            record.duration_days ? `持续时长：${record.duration_days} 天` : "",
            `监督点位：${pointLabel}`,
            `默认聚合：${record.point_cluster_label || "未归并"}`,
            `增强聚类：${((record.aggressive_cluster || {}).label) || "未聚类"}`,
            `模型版本：${record.model_version || "rules-v2"} / 特征版本：${record.feature_version || "feature-v2"}`,
            `综合置信度：${Math.round((record.screening_confidence || 0) * 1000) / 10}%`,
            topCandidates ? `候选排序：${topCandidates}` : "",
            (searchExplanation.reasons || []).length ? `检索解释：${searchExplanation.reasons.join("；")}` : "",
            "",
            `投诉内容：${record.complaint_text}`,
        ].filter(Boolean).join("\n");
    }

    if (reviewForm) {
        reviewForm.querySelector('[name="record_id"]').value = record.id;
        reviewForm.querySelector('[name="manual_label"]').value = record.manual_label === "待标注" ? "" : record.manual_label;
        reviewForm.querySelector('[name="review_status"]').value = record.review_status;
        reviewForm.querySelector('[name="handling_status"]').value = record.handling_status;
        reviewForm.querySelector('[name="review_comment"]').value = record.review_comment || "";
    }

    const structuredFields = record.structured_fields || {};
    fillList(
        structuredFieldsList,
        Object.entries(structuredFields)
            .filter(([, value]) => value)
            .map(([key, value]) => `${structuredFieldLabel(key)}：${value}`),
        "暂无结构化提取结果"
    );
    fillList(
        matchedRulesList,
        [
            ...(record.matched_rules || []).map((item) => `${item.keyword}：${item.reason}`),
            ...(record.public_interest_reasons || []).map((item) => `公益判定：${item}`),
            ...(record.warning_flags || []).map((item) => `预警标记：${item}`),
            ...((record.search_explanation || {}).reasons || []),
        ],
        "暂无规则命中结果"
    );
    if (assistantSummary) {
        assistantSummary.textContent = "点击“生成辅助研判说明”后，将结合规则解释、综合模型置信度和人工复核建议生成说明。";
    }
    fillList(assistantKeyPoints, ["等待生成说明"], "等待生成说明");
    renderPublicInterestCard(record);
    renderDomainCard(record);
    renderWarningCard(record);
    renderAnomalyCard(record);
    fillList(document.getElementById("assistant-statutes-list"), [], "暂无");
    fillList(document.getElementById("assistant-cases-list"), [], "暂无");
    fillList(document.getElementById("assistant-regulators-list"), [], "暂无");
    fillList(document.getElementById("assistant-investigation-list"), [], "暂无");
    fillList(document.getElementById("assistant-evidence-list"), [], "暂无");
    const prosecutionNode = document.getElementById("assistant-prosecution");
    if (prosecutionNode) prosecutionNode.textContent = "尚未评估";
    const pushPreviewNode = document.getElementById("assistant-recommended-push");
    if (pushPreviewNode) pushPreviewNode.textContent = "点击\u201c生成辅助研判说明\u201d后会展示推送给业务系统的载荷预览。";
    const pushPill = document.getElementById("assistant-push-pill");
    if (pushPill) {
        pushPill.textContent = "未生成";
        pushPill.className = "status-pill neutral";
    }
}

function formatPercent(value, digits = 1) {
    const ratio = Number(value) || 0;
    return `${(ratio * 100).toFixed(digits)}%`;
}

function joinOrEmpty(values, separator = "、", emptyText = "暂无") {
    if (!Array.isArray(values) || !values.length) return emptyText;
    return values.filter(Boolean).join(separator);
}

function formatLegalDomainDisplay(record) {
    if ((record.public_interest_level || "") === "私益") {
        return "不适用";
    }
    if ((record.public_interest_level || "") === "公益" && !record.legal_domain) {
        return "待细化";
    }
    if ((record.public_interest_level || "") === "待复核" && !record.legal_domain) {
        return "待复核";
    }
    return record.legal_domain || "待补充";
}

function renderPublicInterestCard(record) {
    const node = document.getElementById("record-public-interest-card");
    if (!node) return;
    const evidence = record.public_interest_evidence || {};
    const reasons = record.public_interest_reasons || [];
    const lines = [
        `判别结果：${record.public_interest_level || "待复核"} / 评分 ${formatPercent(record.public_interest_score || 0)}`,
        `投诉主体数量：${evidence.complainant_count ?? "未抽取"}`,
        `波及范围：${joinOrEmpty(evidence.scope_terms, "、", "未抽取")}`,
        `涉及人群：${joinOrEmpty(evidence.group_terms, "、", "未抽取")}`,
        `国家利益线索：${joinOrEmpty(evidence.national_terms, "、", "未识别")}`,
        `监管语义：${joinOrEmpty(evidence.governance_terms, "、", "未识别")}`,
        `公共设施线索：${joinOrEmpty(evidence.public_facility_terms, "、", "未识别")}`,
        `私益纠纷线索：${joinOrEmpty(evidence.private_dispute_terms, "、", "未识别")}`,
        reasons.length ? `命中理由：${reasons.slice(0, 4).join("；")}` : "",
    ].filter(Boolean);
    fillList(node, lines, "暂无公益判别证据");
}

function renderDomainCard(record) {
    const node = document.getElementById("record-domain-card");
    if (!node) return;
    if ((record.public_interest_level || "") === "私益") {
        fillList(node, ["当前判定为私益，11个公益领域分类不适用。"], "暂无领域识别结果");
        return;
    }
    const candidates = (record.domain_candidates || [])
        .map((item) => {
            const score = typeof item.score !== "undefined" ? item.score : item.confidence;
            return `${item.domain || item.name || ""} ${score ? formatPercent(score) : ""}`.trim();
        })
        .filter(Boolean);
    const conflicts = record.domain_conflict_flags || [];
    const tags = record.domain_tags || [];
    const lines = [
        `主领域：${formatLegalDomainDisplay(record)} / 置信度 ${formatPercent(record.domain_confidence || 0)}`,
        candidates.length ? `候选领域：${candidates.slice(0, 4).join(" / ")}` : "候选领域：暂未识别",
        tags.length ? `次要标签：${tags.join("、")}` : "",
        conflicts.length ? `冲突说明：${conflicts.join("；")}` : "冲突说明：无",
    ].filter(Boolean);
    fillList(node, lines, "暂无领域识别结果");
}

function renderWarningCard(record) {
    const node = document.getElementById("record-warning-card");
    if (!node) return;
    const flags = record.warning_flags || [];
    const dupReasons = record.duplicate_reasons || [];
    const lines = [
        `预警等级：${record.warning_level || "无"} / 优先级：${record.priority_level || "低"}`,
        record.warning_reason_summary ? `预警原因：${record.warning_reason_summary}` : "",
        flags.length ? `预警标记：${flags.slice(0, 4).join("、")}` : "",
        `重复等级：${record.duplicate_level || "无"} / 重复次数：${record.duplicate_count || 1}`,
        record.duration_days ? `持续时长：${record.duration_days} 天` : "",
        dupReasons.length ? `重复依据：${dupReasons.slice(0, 4).join("；")}` : "",
    ].filter(Boolean);
    fillList(node, lines, "暂无预警/重复信息");
}

function renderAnomalyCard(record) {
    const node = document.getElementById("record-anomaly-card");
    if (!node) return;
    const reasons = record.performance_anomaly_reasons || [];
    const level = record.performance_anomaly_level || "无";
    const lines = [
        `异常等级：${level}`,
        `办理状态：解决=${record.resolved_status || "待核实"} / 满意=${record.satisfaction_status || "待核实"} / 响应=${record.response_status || "待核实"}`,
        reasons.length ? `异常原因：${reasons.slice(0, 4).join("；")}` : (level === "无" ? "暂未识别异常" : ""),
    ].filter(Boolean);
    fillList(node, lines, "暂无履职异常");
}

function renderRankingList(containerId, items, formatter) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!Array.isArray(items) || !items.length) {
        container.innerHTML = '<div class="admin-record"><p>暂无数据。</p></div>';
        return;
    }
    container.innerHTML = items.map(formatter).join("");
}

function renderPushTaskSummary(summary) {
    const node = document.getElementById("push-task-summary");
    if (!node) return;
    if (!summary) {
        fillList(node, ["暂无推送任务。"]);
        return;
    }
    const lines = [
        `待处理：${summary.pending_count || 0} 条`,
        `已发送：${summary.delivered_count || 0} 条`,
        `失败需重试：${summary.failed_count || 0} 条`,
    ];
    fillList(node, lines);
}

function renderPushTaskList(items) {
    const container = document.getElementById("push-task-list");
    if (!container) return;
    if (!Array.isArray(items) || !items.length) {
        container.innerHTML = '<div class="admin-record"><p>暂无推送任务记录。</p></div>';
        return;
    }
    container.innerHTML = items.map((item) => {
        const statusClass = pushStatusClass(item.status);
        const detail = [
            `类型：${item.push_type || "-"} · 触发：${item.trigger_mode || "-"}`,
            `条数：${item.item_count || 0} · 重试：${item.retry_count || 0}`,
            item.target_endpoint ? `端点：${item.target_endpoint}` : "端点：未配置",
            item.last_error ? `失败原因：${item.last_error}` : "",
        ].filter(Boolean).join("；");
        return `
            <div class="admin-record">
                <strong>#${item.id} <span class="status-pill ${statusClass}">${item.status}</span></strong>
                <p>${detail}</p>
                <p>创建：${item.created_at || "-"} / 投递：${item.delivered_at || "未投递"}</p>
            </div>
        `;
    }).join("");
}

function pushStatusClass(status) {
    if (status === "delivered") return "low";
    if (status === "failed") return "high";
    if (status === "pending" || status === "queued") return "medium";
    return "neutral";
}

async function refreshPushTasks() {
    try {
        const data = await getJson("/api/integrations/push/tasks?limit=10");
        renderPushTaskList(data.items || []);
    } catch (error) {
        // Silent — push panel might not exist on every page render path
    }
}

function structuredFieldLabel(key) {
    const labelMap = {
        project_name: "项目名称",
        point_location: "具体点位",
        start_time: "开工时间",
        worker_count: "涉事人数",
        arrears_subject: "欠薪主体",
        wage_amount: "欠薪金额",
        labor_contract_signed: "是否签订劳动合同",
    };
    return labelMap[key] || key;
}

function riskClass(value) {
    if (value === "高") return "high";
    if (value === "中") return "medium";
    return "low";
}

function updateScreeningMeta(message) {
    const meta = document.getElementById("screening-job-meta");
    if (meta) meta.textContent = message;
}

function jumpToReviewSection() {
    const reviewSection = document.getElementById("review");
    const selectedPill = document.getElementById("selected-record-pill");
    if (!reviewSection) return;

    reviewSection.classList.remove("section-jump-highlight");
    reviewSection.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => {
        reviewSection.classList.add("section-jump-highlight");
        selectedPill?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 220);
    window.setTimeout(() => reviewSection.classList.remove("section-jump-highlight"), 2200);
}

async function refreshDashboard() {
    const query = getDashboardFilterParams().toString();
    const data = await getJson(`/api/dashboard${query ? `?${query}` : ""}`);
    renderDashboard(data);
}

async function loadPointClusters(mode = null) {
    const modeNode = document.getElementById("point-cluster-mode-select");
    const effectiveMode = mode || (modeNode ? modeNode.value : "stable");
    const data = await getJson(`/api/clues/point-clusters?mode=${encodeURIComponent(effectiveMode)}`);
    renderPointClusters(data);
}

function getFilterParams(page = tableState.page) {
    const params = new URLSearchParams(tableState.filters);
    params.set("page", String(page));
    params.set("page_size", String(tableState.pageSize));
    return params;
}

async function loadTableWithFilters(formData = null, page = 1) {
    if (formData instanceof URLSearchParams) {
        tableState.filters = new URLSearchParams(formData);
    } else if (!tableState.filters) {
        tableState.filters = new URLSearchParams();
    }
    const query = getFilterParams(page).toString();
    const data = await getJson(`/api/clues${query ? `?${query}` : ""}`);
    renderRecordTable(data);
    renderSearchMeta(data.search_meta || null);
}

async function loadRecord(recordId) {
    const data = await getJson(`/api/clues/${recordId}`);
    renderSelectedRecord(data.item);
}

function fillImportForm(payload, recordId) {
    const form = document.getElementById("import-form");
    if (!form) return;
    const map = {
        ticket_no: payload.ticket_no || "",
        source: payload.source || "",
        title: payload.title || "",
        complainant_name: payload.complainant_name || "",
        complainant_phone: payload.complainant_phone || "",
        district: payload.district || "",
        location_text: payload.location_text || "",
        event_time: payload.event_time || "",
        complaint_text: payload.complaint_text || "",
        sync_record_id: recordId || "",
    };
    Object.entries(map).forEach(([key, value]) => {
        const field = form.querySelector(`[name="${key}"]`);
        if (field) field.value = value;
    });
}

document.getElementById("import-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
        const result = await postForm("/api/clues", form);
        showToast(result.message);
        form.reset();
        form.querySelector('[name="sync_record_id"]').value = "";
        await refreshDashboard();
        await loadTableWithFilters(tableState.filters, 1);
        if (result.item) renderSelectedRecord(result.item);
    } catch (error) {
        showToast(error.message || "工单导入失败。", true);
    }
});

document.querySelectorAll(".integration-pull-btn").forEach((button) => {
    button.addEventListener("click", async () => {
        const source = button.dataset.source;
        try {
            const result = await postFields("/api/integrations/pull", { source_system: source });
            fillImportForm(result.payload, result.record_id);
            showToast(`${source} 工单已拉取，可直接确认导入。`);
            await refreshDashboard();
        } catch (error) {
            showToast(error.message || "外部工单拉取失败。", true);
        }
    });
});

document.getElementById("demo-import-btn")?.addEventListener("click", async () => {
    try {
        const result = await postFields("/api/clues/import-demo", {});
        showToast(result.message);
        await refreshDashboard();
        await loadTableWithFilters(tableState.filters, 1);
    } catch (error) {
        showToast(error.message || "批量演示工单导入失败。", true);
    }
});

document.getElementById("file-import-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
        const result = await postForm("/api/clues/import-file", form);
        showToast(result.message);
        updateScreeningMeta(
            `文件处理完成：新增 ${result.created_count} 条，更新 ${result.updated_count} 条，` +
            `自动筛查 ${((result.screening_result || {}).screened_count) || 0} 条，工作表：${(result.sheet_names || []).join(" / ")}`
        );
        form.reset();
        await refreshDashboard();
        await loadTableWithFilters(tableState.filters, 1);
        if (result.items && result.items.length) {
            renderSelectedRecord(result.items[0]);
        }
    } catch (error) {
        showToast(error.message || "文件导入失败。", true);
    }
});

document.getElementById("run-screening-btn")?.addEventListener("click", async () => {
    try {
        const result = await postFields("/api/clues/run-screening", {
            only_pending: "true",
            record_ids: "",
            batch_size: String(tableState.pageSize || 20),
        });
        updateScreeningMeta(`最近一次批处理任务 #${result.job_id}，批大小 ${result.batch_size}，模型版本 ${result.model_version || "rules-v2"}。`);
        showToast(result.message);
        await refreshDashboard();
        await loadTableWithFilters(tableState.filters, tableState.page);
    } catch (error) {
        showToast(error.message || "执行筛查失败。", true);
    }
});

document.getElementById("train-ml-btn")?.addEventListener("click", async () => {
    try {
        const result = await postFields("/api/models/train-ml", {});
        updateScreeningMeta(`ML 模型训练完成：${result.model_version}，样本 ${result.sample_count} 条。`);
        showToast(result.message);
        await refreshDashboard();
    } catch (error) {
        showToast(error.message || "本地ML模型训练失败。", true);
    }
});

document.getElementById("warmup-dl-btn")?.addEventListener("click", async () => {
    try {
        const result = await postFields("/api/models/warmup-dl", {});
        updateScreeningMeta(`深度语义模型已预热：${result.model_name}。`);
        showToast(result.message);
        await refreshDashboard();
    } catch (error) {
        showToast(error.message || "深度语义模型预热失败。", true);
    }
});

document.getElementById("refresh-dashboard-btn")?.addEventListener("click", async () => {
    try {
        await refreshDashboard();
        await loadTableWithFilters(tableState.filters, tableState.page);
        await loadPointClusters();
        showToast("平台数据已刷新。");
    } catch (error) {
        showToast("刷新失败。", true);
    }
});

document.getElementById("screening-filter-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
        const params = new URLSearchParams(new FormData(form));
        await loadTableWithFilters(params, 1);
        await refreshDashboard();
        showToast("筛选结果已更新。");
    } catch (error) {
        showToast("筛选失败。", true);
    }
});

document.getElementById("refresh-cluster-btn")?.addEventListener("click", async () => {
    try {
        await loadPointClusters();
        showToast("监督点位聚合结果已刷新。");
    } catch (error) {
        showToast("监督点位聚合加载失败。", true);
    }
});

document.getElementById("point-cluster-mode-select")?.addEventListener("change", async () => {
    try {
        await loadPointClusters();
    } catch (error) {
        showToast("监督点位聚合切换失败。", true);
    }
});

document.getElementById("table-prev-btn")?.addEventListener("click", async () => {
    if (tableState.page <= 1) return;
    try {
        await loadTableWithFilters(tableState.filters, tableState.page - 1);
    } catch (error) {
        showToast("上一页加载失败。", true);
    }
});

document.getElementById("table-next-btn")?.addEventListener("click", async () => {
    if (tableState.page >= tableState.pages) return;
    try {
        await loadTableWithFilters(tableState.filters, tableState.page + 1);
    } catch (error) {
        showToast("下一页加载失败。", true);
    }
});

document.getElementById("screening-table-body")?.addEventListener("click", async (event) => {
    const button = event.target.closest(".table-action-btn");
    if (!button) return;
    try {
        await loadRecord(button.dataset.recordId);
        jumpToReviewSection();
        showToast("已载入工单详情。");
    } catch (error) {
        showToast("工单详情加载失败。", true);
    }
});

document.getElementById("review-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const recordId = form.querySelector('[name="record_id"]').value;
    if (!recordId) {
        showToast("请先选择需要标注的工单。", true);
        return;
    }
    try {
        const result = await postForm(`/api/ledgers/${recordId}/review`, form);
        renderSelectedRecord(result.item);
        showToast(result.message);
        await refreshDashboard();
        await loadTableWithFilters(tableState.filters, tableState.page);
    } catch (error) {
        showToast(error.message || "线索标注失败。", true);
    }
});

document.getElementById("assistant-explain-btn")?.addEventListener("click", async () => {
    if (!currentRecord) {
        showToast("请先选择需要解释的工单。", true);
        return;
    }
    try {
        const result = await getJson(`/api/assistant/explain/${currentRecord.id}`);
        const summaryNode = document.getElementById("assistant-summary");
        const keyPointsNode = document.getElementById("assistant-key-points");
        if (summaryNode) {
            const evidence = result.evidence_analysis || {};
            const prosecution = result.prosecution_potential || {};
            summaryNode.textContent = [
                result.summary,
                prosecution.label ? `\n成案可能性：${prosecution.label}（${formatPercent(prosecution.score || 0)}）` : "",
                evidence.priority_evidence?.length ? `\n优先补强证据：${evidence.priority_evidence.join("、")}` : "",
            ].filter(Boolean).join("\n");
        }
        fillList(
            keyPointsNode,
            [
                ...(result.key_points || []),
                ...(result.matched_rules || []),
                result.recommendation,
            ].filter(Boolean),
            "暂无辅助说明"
        );

        fillList(
            document.getElementById("assistant-statutes-list"),
            (result.legal_references || []).map((item) =>
                `${item.statute_no || ""} ${item.title || ""}${item.summary ? "：" + item.summary : ""}`
            ),
            "未匹配到相关法条"
        );
        fillList(
            document.getElementById("assistant-cases-list"),
            (result.case_references || []).map((item) =>
                `${item.title}（${item.location || "未公开"}）：${item.summary || ""}${item.outcome ? " / 结果：" + item.outcome : ""}`
            ),
            "暂无典型案例"
        );
        fillList(
            document.getElementById("assistant-regulators-list"),
            (result.regulator_references || []).map((item) =>
                `${item.regulator}：${(item.duties || []).join("、") || "职责待补充"}`
            ),
            "暂无监管职责映射"
        );
        fillList(
            document.getElementById("assistant-investigation-list"),
            result.investigation_focus || [],
            "暂无调查重点"
        );
        const evidence = result.evidence_analysis || {};
        const evidenceLines = [
            evidence.priority_evidence?.length ? `优先补强：${evidence.priority_evidence.join("、")}` : "",
            evidence.missing_evidence?.length ? `仍缺：${evidence.missing_evidence.join("、")}` : "",
            evidence.existing_evidence?.length ? `已具备：${evidence.existing_evidence.join("、")}` : "",
        ].filter(Boolean);
        fillList(document.getElementById("assistant-evidence-list"), evidenceLines, "暂无证据建议");

        const prosecutionNode = document.getElementById("assistant-prosecution");
        if (prosecutionNode) {
            const prosecution = result.prosecution_potential || {};
            const reasons = (prosecution.reasons || []).join("；");
            prosecutionNode.textContent = [
                `评估等级：${prosecution.label || "未评估"}`,
                `评分：${formatPercent(prosecution.score || 0)}`,
                reasons ? `判断依据：${reasons}` : "",
            ].filter(Boolean).join("\n");
        }

        const pushNode = document.getElementById("assistant-recommended-push");
        const pushPill = document.getElementById("assistant-push-pill");
        if (pushNode) {
            pushNode.textContent = JSON.stringify(result.recommended_push || {}, null, 2);
        }
        if (pushPill) {
            pushPill.textContent = "已生成";
            pushPill.className = "status-pill low";
        }
        showToast("辅助研判说明已生成。");
    } catch (error) {
        showToast(error.message || "辅助说明生成失败。", true);
    }
});

document.getElementById("export-btn")?.addEventListener("click", async () => {
    const filterForm = document.getElementById("screening-filter-form");
    const params = new URLSearchParams(new FormData(filterForm));
    params.delete("source");
    params.delete("has_location");
    params.delete("is_duplicate");
    params.delete("review_status");
    params.delete("page");
    params.delete("page_size");
    try {
        const result = await getJson(`/api/exports/download?${params.toString()}`);
        const output = document.getElementById("export-output");
        const filePathNode = document.getElementById("export-file-path-text");
        if (output) output.textContent = result.content;
        if (filePathNode) filePathNode.textContent = `导出文件：${result.file_path}`;
        showToast(result.message);
        await refreshDashboard();
    } catch (error) {
        showToast(error.message || "导出失败。", true);
    }
});

async function enqueuePush(pushType, label) {
    try {
        const result = await postFields("/api/integrations/push/enqueue", {
            push_type: pushType,
            trigger_mode: "manual",
        });
        showToast(`${label}任务已入队，编号 #${result.task?.id || ""}`);
        await refreshPushTasks();
        await refreshDashboard();
    } catch (error) {
        showToast(error.message || `${label}任务入队失败。`, true);
    }
}

document.getElementById("push-enqueue-batch-btn")?.addEventListener("click", () => enqueuePush("daily", "T+1 批量推送"));
document.getElementById("push-enqueue-weekly-btn")?.addEventListener("click", () => enqueuePush("weekly", "周报推送"));

document.getElementById("push-enqueue-emergency-btn")?.addEventListener("click", async () => {
    if (!currentRecord) {
        showToast("请先在筛查列表中选择一条工单作为紧急推送对象。", true);
        return;
    }
    try {
        const result = await postFields("/api/integrations/push/emergency", {
            record_ids: String(currentRecord.id),
            trigger_mode: "manual",
        });
        showToast(`紧急推送任务已入队，编号 #${result.task?.id || ""}`);
        await refreshPushTasks();
        await refreshDashboard();
    } catch (error) {
        showToast(error.message || "紧急推送任务入队失败。", true);
    }
});

document.getElementById("push-deliver-btn")?.addEventListener("click", async () => {
    try {
        const result = await postFields("/api/integrations/push/deliver", {
            deliver_pending: "true",
        });
        showToast(`已尝试投递 ${result.delivered_count || 0} 个待处理任务。`);
        await refreshPushTasks();
        await refreshDashboard();
    } catch (error) {
        showToast(error.message || "推送投递失败。", true);
    }
});

function renderSpecialReportPeriod(period, payload) {
    const pill = document.getElementById("special-report-period-pill");
    const summaryNode = document.getElementById("special-report-period-summary");
    const metricsNode = document.getElementById("special-report-period-metrics");
    const highlightsNode = document.getElementById("special-report-period-highlights");
    const actionsNode = document.getElementById("special-report-period-actions");
    if (pill) {
        pill.textContent = period === "quarterly" ? "季度报告" : "月度报告";
        pill.className = "status-pill low";
    }
    const report = payload.period_report || {};
    const summary = payload.report || {};
    const months = (report.months || []).join(" / ") || summary.reporting_period || "-";
    fillList(summaryNode, [
        `统计周期：${months}`,
        ...(report.summary_lines || summary.summary_lines || []),
    ], "暂无报告概要");
    fillList(metricsNode, [
        `公益属性工单：${report.public_interest_count ?? summary.public_interest_count ?? 0} 条`,
        `重复≥3次工单：${report.high_frequency_count ?? summary.high_frequency_count ?? 0} 条`,
        `高等级预警：${report.high_warning_count ?? summary.high_warning_count ?? 0} 条`,
        `履职异常：${report.performance_anomaly_count ?? summary.performance_anomaly_count ?? 0} 条`,
    ], "暂无关键指标");
    const urgent = payload.urgent_records || report.urgent_records || [];
    fillList(highlightsNode, urgent.slice(0, 6).map((item) =>
        `${item.ticket_no} · ${item.title}（${item.district || "-"} / ${item.legal_domain || "-"}）`
    ), "本周期暂无重点工单");
    const anomalyRanking = (payload.performance_anomaly_summary || {}).ranking || [];
    fillList(actionsNode, anomalyRanking.slice(0, 4).map((item) =>
        `重点关注 ${item.district} · ${item.legal_domain}：解决率 ${formatPercent(item.resolution_rate)}，履职异常 ${item.anomaly_count} 条`
    ), "暂无建议处置");
}

async function loadSpecialReport(period) {
    try {
        const data = await getJson(`/api/clues/special-report?period=${encodeURIComponent(period)}`);
        renderSpecialReportPeriod(period, data);
        showToast(`${period === "quarterly" ? "季度" : "月度"}专项报告已生成。`);
    } catch (error) {
        showToast(error.message || "专项报告生成失败。", true);
    }
}

document.getElementById("special-report-monthly-btn")?.addEventListener("click", () => loadSpecialReport("monthly"));
document.getElementById("special-report-quarterly-btn")?.addEventListener("click", () => loadSpecialReport("quarterly"));

window.addEventListener("DOMContentLoaded", async () => {
    try {
        await refreshDashboard();
        await loadTableWithFilters(new URLSearchParams(), 1);
        await loadPointClusters();
        await refreshPushTasks();
    } catch (error) {
        showToast("初始化数据加载失败。", true);
    }
});
