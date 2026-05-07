<template>
  <div class="topology-editor-wrapper" :class="{ 'is-editing': editMode }">
    <aside class="orphan-sidebar">
      <div class="sidebar-header">
        <h3>待核实资产 ({{ orphanList.length }})</h3>
        <p class="subtitle">编辑模式开启后，可拖拽失联摄像头到目标交换机下重新建链。</p>
      </div>

      <div class="lock-status" :class="{ unlocked: editMode }">
        <strong>{{ editMode ? "编辑模式已启用" : "只读锁定中" }}</strong>
        <span>{{ editMode ? "允许拖拽、极坐标吸附、挂载失联点位" : "仅允许缩放、平移、展开和查看节点" }}</span>
      </div>

      <div class="cluster-summary">
        <span class="cluster-pill core">核心 {{ clusterStats.core }}</span>
        <span class="cluster-pill south">南楼 {{ clusterStats.south }}</span>
        <span class="cluster-pill north">北楼 {{ clusterStats.north }}</span>
      </div>

      <div class="orphan-list">
        <div
          v-for="item in orphanList"
          :key="item.id"
          class="orphan-item"
          :class="[`cluster-${item.cluster}`, { disabled: !editMode }]"
          :draggable="editMode"
          @dragstart="handleDragStart($event, item)"
        >
          <div class="item-icon" :title="nodeTypeLabel(item)">{{ assetIcon(item) }}</div>
          <div class="item-info">
            <span class="item-name">{{ item.label || item.id }}</span>
            <span class="item-ip">{{ item.ip || item.nodeKey }}</span>
          </div>
          <span class="cluster-tag">{{ clusterLabel(item.cluster) }}</span>
        </div>
        <p v-if="!orphanList.length" class="empty-text">当前没有失联点位。</p>
      </div>
    </aside>

    <main
      class="canvas-main"
      @drop="handleDrop"
      @dragover.prevent
    >
      <div class="topology-toolbar">
        <div class="mode-title">
          <strong>网络层级折叠树 (椭圆视网膜阵列)</strong>
          <span>{{ toolbarHint }}</span>
        </div>
        <div class="toolbar-actions">
          <span class="selected-hint">{{ selectedNodeLabel }}</span>
          <el-switch
            v-model="editMode"
            inline-prompt
            size="large"
            active-text="编辑"
            inactive-text="锁定"
            active-color="#f59e0b"
            inactive-color="#64748b"
          />
        </div>
      </div>

      <div v-if="editMode" class="edit-warning">
        编辑模式已解锁：节点拖动将自动吸附至对应椭圆轨道，操作会写回数据库。
      </div>

      <div ref="graphContainer" class="g6-container"></div>

      <div
        v-if="hoverTooltip.visible"
        class="semantic-tooltip"
        :class="`tooltip-${hoverTooltip.kind}`"
        :style="{ left: `${hoverTooltip.x}px`, top: `${hoverTooltip.y}px` }"
      >
        <strong class="tooltip-title">{{ hoverTooltip.title }}</strong>
        <div v-for="row in hoverTooltip.rows" :key="row.label" class="tooltip-row">
          <span class="tooltip-key">{{ row.label }}</span>
          <span class="tooltip-value">{{ row.value || "-" }}</span>
        </div>
      </div>

      <div class="legend-overlay" :class="{ collapsed: legendCollapsed }">
        <button class="legend-toggle" type="button" @click="legendCollapsed = !legendCollapsed">
          {{ legendCollapsed ? "展开图例" : "收起图例" }}
        </button>
        <div v-show="!legendCollapsed" class="legend-body">
          <strong>图例说明</strong>
          <div class="legend-row">
            <span class="legend-dot core"></span>
            <span>红色节点：核心机房设备</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot aggregation"></span>
            <span>蓝色节点：汇聚层设备</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot access"></span>
            <span>绿色节点：接入层设备</span>
          </div>
          <div class="legend-row">
            <span class="legend-flow"></span>
            <span>虚线流动：数据连通状态</span>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import G6 from "@antv/g6";
import { ElMessage } from "element-plus";
import {
  clearAssetTopologyBinding,
  createArchitectureEdge,
  deleteArchitectureEdge,
  fetchCentralAvenueArchitecture,
  updateAssetPosition,
} from "../../api/client";

const graphContainer = ref(null);
const editMode = ref(false);
const topologyPayload = ref(null);
const nodes = ref([]);
const edges = ref([]);
const orphanList = ref([]);
const selectedNodeId = ref("");
const legendCollapsed = ref(false);
const expandedAccessIds = ref(new Set());
const hoverTooltip = ref({
  visible: false,
  kind: "node",
  x: 0,
  y: 0,
  title: "",
  rows: [],
});

let graph = null;
let resizeObserver = null;
let draggedItem = null;
let resizeRenderPending = false;
const detachingNodeIds = new Set();
let customElementsRegistered = false;
const COLLAPSE_ANIMATION_DURATION = 500;
const ELLIPSE_INNER_RADIUS_X = 300;
const ELLIPSE_INNER_RADIUS_Y = 150;
const ELLIPSE_OUTER_RADIUS_X = 600;
const ELLIPSE_OUTER_RADIUS_Y = 250;
const NORTH_ARC_START = Math.PI * 0.9;
const NORTH_ARC_END = Math.PI * 0.1;
const SOUTH_ARC_START = Math.PI * 1.1;
const SOUTH_ARC_END = Math.PI * 1.9;
const LOD_LABEL_ZOOM = 0.8;
const STARBURST_CAMERA_RADIUS = 60; // 🔥 缩小环绕半径，配合圆形小图标更紧凑优雅
const LOD_TEXT_SHAPES = new Set([
  "label",
  "meta",
  "port",
  "tier-mark",
  "camera-label",
  "camera-meta",
  "camera-badge-text",
]);
const RELATION_ACTIVE_STATE = "relation-active";
const RELATION_INACTIVE_STATE = "relation-inactive";

const backboneNodes = computed(() => nodes.value.filter((item) => item.kind !== "camera"));
const cameraNodes = computed(() => nodes.value.filter((item) => item.kind === "camera"));

const toolbarHint = computed(() => (
  editMode.value
    ? "编辑锁已打开，允许拖动节点和挂载失联摄像头。"
    : "默认收起接入交换机下属摄像头，点击节点展开或收起。"
));

const selectedNodeLabel = computed(() => {
  const node = nodes.value.find((item) => item.id === selectedNodeId.value);
  return node ? `已选：${node.label}` : "未选择节点";
});

const clusterStats = computed(() => ({
  core: backboneNodes.value.filter((item) => item.cluster === "core").length,
  south: backboneNodes.value.filter((item) => item.cluster === "south").length,
  north: backboneNodes.value.filter((item) => item.cluster === "north").length,
}));

function normalizeText(value) {
  return String(value || "").trim();
}

function stableHash(value) {
  const text = normalizeText(value);
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  }
  return hash;
}

function clusterLabel(cluster) {
  if (cluster === "core") return "核心";
  if (cluster === "south") return "南";
  return "北";
}

function cleanDeviceLabel(value, fallbackValues = []) {
  const text = normalizeText(value).replace(/\s+/g, " ");
  const dirtyTierOnly = /^(acc|access|agg|aggregation|core|cam|camera|switch|unknown|null|undefined)$/i;
  if (text && !dirtyTierOnly.test(text)) return text;
  return fallbackValues.map((item) => normalizeText(item)).find(Boolean) || "未命名设备";
}

function trimDisplayText(value, maxChars = 18) {
  const chars = Array.from(normalizeText(value));
  if (chars.length <= maxChars) return chars.join("");
  return `${chars.slice(0, Math.max(1, maxChars - 1)).join("")}…`;
}

function assetIcon(node) {
  return node?.kind === "camera" ? "📹" : "🖧";
}

function nodeTierCode(node) {
  if (isCoreNode(node)) return "CORE";
  if (isAggregationNode(node)) return "AGG";
  if (isAccessNode(node)) return "ACC";
  return node?.kind === "camera" ? "CAM" : "NET";
}

function nodeTypeLabel(node) {
  if (node.kind === "camera") return "摄像头终端";
  if (node.kind === "junction") return "分线盒";
  if (node.kind === "unmanaged") return "无网管交换机";
  if (node.tier === "core") return "核心机房设备";
  if (node.tier === "aggregation") return "汇聚层设备";
  return "接入层设备";
}

function uniqueText(values) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const text = normalizeText(value);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    result.push(text);
  }
  return result;
}

function relatedEdgesForNode(node) {
  if (!node) return [];
  const aliasMap = buildAliasMap();
  const nodeId = resolveNodeId(node.id, aliasMap) || node.id;
  return edges.value.filter((edge) => (
    (resolveNodeId(edge.source, aliasMap) || normalizeText(edge.source)) === nodeId
    || (resolveNodeId(edge.target, aliasMap) || normalizeText(edge.target)) === nodeId
  ));
}

function nodePortText(node) {
  const raw = node?.raw || {};
  const directPorts = uniqueText([
    raw.port_label,
    raw.port,
    raw.Port,
    raw.Logical_Port,
    raw.uplink_port,
    raw.access_port,
    raw.if_name,
    raw.interface,
    raw.source_port_name,
    raw.src_port_label,
    raw.dst_port_label,
  ]);
  if (directPorts.length) return `PORT ${directPorts.slice(0, 2).join(", ")}`;

  const aliasMap = buildAliasMap();
  const relatedPorts = relatedEdgesForNode(node).flatMap((edge) => {
    const sourceId = edgeEndpointId(edge.source);
    const resolvedSource = resolveNodeId(sourceId, aliasMap) || sourceId;
    const isSource = resolvedSource === node?.id;
    const rawEdge = edge.raw || {};
    return isSource
      ? [rawEdge.src_port_label, rawEdge.source_port_name, rawEdge.Logical_Port, rawEdge.src_port]
      : [rawEdge.dst_port_label, rawEdge.target_port_name, rawEdge.dst_port, rawEdge.Logical_Port];
  });
  const ports = uniqueText(relatedPorts);
  if (ports.length) return `PORT ${ports.slice(0, 2).join(", ")}`;
  if (node?.kind === "camera") return "PORT RTSP/ONVIF";
  return "PORT 待核实";
}

function nodeStatusText(node) {
  const rawStatus = normalizeText(
    node.raw?.status
      || node.raw?.online_status
      || node.raw?.rtsp_status
      || node.raw?.review_status
      || node.raw?.state,
  );
  if (node.conflict) return "冲突待核实";
  if (node.kind === "camera" && !cameraParentId(node)) return "失联待挂载";
  if (node.verified) return "已现场核实";
  return rawStatus || "运行态待同步";
}

function edgeEndpointId(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.id || value.nodeKey || value.getModel?.()?.id || "";
}

function findEdgeByEndpoint(sourceId, targetId) {
  return edges.value.find((edge) => edge.source === sourceId && edge.target === targetId) || null;
}

function edgeRoleText(edge, sourceNode, targetNode) {
  const raw = edge?.raw || {};
  const edgeType = normalizeText(edge?.label || raw.edge_type || raw.Type);
  if (targetNode?.kind === "camera") return "摄像头接入链路";
  if (/fiber|光|sfp/i.test(edgeType) || /光/.test(raw.notes || "")) return "光纤上联";
  if (/uplink|级联|trunk/i.test(edgeType)) return "千兆级联";
  return edgeType || "网络级联";
}

function edgePortText(edge) {
  const raw = edge?.raw || {};
  const srcPort = normalizeText(raw.src_port_label || raw.source_port_name || raw.Logical_Port || raw.src_port || "");
  const dstPort = normalizeText(raw.dst_port_label || raw.target_port_name || raw.dst_port || "");
  if (srcPort || dstPort) return `${srcPort || "-"} -> ${dstPort || "-"}`;
  return normalizeText(raw.notes || raw.manual_note || "") || "端口信息待核实";
}

function nodeTooltipRows(model) {
  return [
    { label: "IP", value: model.ip || model.nodeKey || "-" },
    { label: "层级", value: nodeTierCode(model) },
    { label: "端口", value: nodePortText(model) },
    { label: "设备类型", value: nodeTypeLabel(model) },
    { label: "当前状态", value: nodeStatusText(model) },
    { label: "所属区域", value: clusterLabel(model.cluster) },
  ];
}

function edgeTooltipRows(model) {
  const sourceId = edgeEndpointId(model.source);
  const targetId = edgeEndpointId(model.target);
  const edge = findEdgeByEndpoint(sourceId, targetId);
  const sourceNode = nodes.value.find((node) => node.id === sourceId);
  const targetNode = nodes.value.find((node) => node.id === targetId);
  return {
    title: edgeRoleText(edge, sourceNode, targetNode),
    rows: [
      { label: "上游", value: sourceNode?.label || sourceId },
      { label: "下游", value: targetNode?.label || targetId },
      { label: "端口", value: edgePortText(edge) },
    ],
  };
}

function placeTooltip(event, kind, title, rows) {
  const rect = graphContainer.value?.getBoundingClientRect();
  if (!rect) return;
  const x = Math.min(Math.max(event.clientX - rect.left + 18, 12), Math.max(12, rect.width - 340));
  const y = Math.min(Math.max(event.clientY - rect.top + 18, 72), Math.max(72, rect.height - 190));
  hoverTooltip.value = {
    visible: true,
    kind,
    x,
    y,
    title,
    rows,
  };
}

function hideTooltip() {
  hoverTooltip.value = {
    ...hoverTooltip.value,
    visible: false,
  };
}

function classifyBuilding(node) {
  const text = [
    node.label,
    node.id,
    node.nodeKey,
    node.ip,
    node.layer,
    node.kind,
    node.raw?.asset_label,
    node.raw?.Name,
    node.raw?.weak_current_room,
    node.raw?.room_label,
    node.raw?.floor,
    node.raw?.Physical_Pos?.Area,
    node.raw?.Physical_Pos?.Raw_Address,
    node.raw?.Physical_Pos?.Install_Pos,
  ].filter(Boolean).join(" ").toUpperCase();

  if (node.kind === "core" || /核心|机房|CORE|CENTER|CENTRAL/.test(text)) return "core";
  if (/南楼|南区|南侧|南门|南通道|SOUTH|(^|[\s_\-#])S($|[\s_\-#])|S区/.test(text)) return "south";
  if (/北楼|北区|北侧|北门|北通道|NORTH|(^|[\s_\-#])N($|[\s_\-#])|N区/.test(text)) return "north";

  const ipParts = normalizeText(node.ip).split(".").map((part) => Number(part));
  if (ipParts.length === 4 && ipParts.every(Number.isFinite)) {
    const third = ipParts[2];
    const last = ipParts[3];
    if ([56, 58, 60, 68].includes(third)) return last % 2 === 0 ? "south" : "north";
    return third % 2 === 0 ? "south" : "north";
  }
  return stableHash(node.nodeKey || node.id || node.label) % 2 === 0 ? "south" : "north";
}

function normalizeNode(raw, index) {
  const nodeKey = String(raw.node_key || raw.nodeKey || raw.ID || raw.id || `node-${index}`);
  const typeText = `${raw.node_type || raw.Type || raw.type || ""} ${raw.layer || ""} ${raw.role || ""}`.toLowerCase();
  const physicalPos = raw.Physical_Pos || raw.physical_pos || {};
  const isCamera = typeText.includes("camera") || typeText.includes("terminal") || nodeKey.toLowerCase().startsWith("cam");
  const isCore = typeText.includes("core");
  const isAggregation = typeText.includes("aggregation") || typeText.includes("汇聚");
  const isJunction = typeText.includes("junction") || typeText.includes("分线");
  const isUnmanaged = typeText.includes("unmanaged") || typeText.includes("无网管");
  const conflictCase = raw.Conflict_Case || raw.conflict_case || raw.conflictCases || [];
  const parentId = raw.Parent_ID || raw.parent_node_key || raw.parentId || raw.parent_id || "";
  const x = Number(raw.pos_x ?? raw.x ?? physicalPos.X);
  const y = Number(raw.pos_y ?? raw.y ?? physicalPos.Y);
  const kind = isCore ? "core" : isCamera ? "camera" : isJunction ? "junction" : isUnmanaged ? "unmanaged" : "switch";
  const tier = isCore ? "core" : isAggregation ? "aggregation" : isCamera ? "camera" : "access";
  const rawLabel = raw.label || raw.Name || raw.asset_label || raw.name || "";
  const node = {
    id: nodeKey,
    nodeKey,
    backendId: raw.id && String(raw.id).match(/^\d+$/) ? Number(raw.id) : null,
    deviceId: raw.device_id || raw.deviceId || null,
    parentId,
    ip: raw.ip || raw.IP || "",
    label: cleanDeviceLabel(rawLabel, [raw.ip, raw.IP, nodeKey]),
    kind,
    tier,
    layer: raw.layer || (isCore ? "core" : isCamera ? "terminal" : "access"),
    posX: Number.isFinite(x) ? x : null,
    posY: Number.isFinite(y) ? y : null,
    verified: raw.review_status === "field_verified" || raw.position_source === "manual" || raw.position_source === "field_verified",
    conflict: Array.isArray(conflictCase) ? conflictCase.length > 0 : Boolean(conflictCase),
    raw,
  };
  node.cluster = classifyBuilding(node);
  return node;
}

function normalizeEdge(raw, index) {
  const source = raw.source || raw.Source || raw.src_node_key || raw.source_node_key;
  const target = raw.target || raw.Target || raw.dst_node_key || raw.target_node_key;
  if (!source || !target) return null;
  return {
    id: String(raw.id || raw.ID || `edge-${index}-${source}-${target}`),
    backendId: raw.id && String(raw.id).match(/^\d+$/) ? Number(raw.id) : null,
    source: String(source),
    target: String(target),
    label: raw.label || raw.Logical_Port || raw.src_port_label || raw.edge_type || raw.Type || "",
    verified: raw.review_status === "field_verified" || raw.evidence_type === "field_verified",
    raw,
  };
}

function fallbackTopology() {
  return { nodes: [], edges: [] };
}

function rootNode() {
  return backboneNodes.value.find((node) => node.cluster === "core")
    || backboneNodes.value.find((node) => node.tier === "core")
    || backboneNodes.value.find((node) => node.kind === "switch")
    || backboneNodes.value[0]
    || null;
}

function nodeTierRank(node) {
  if (node?.virtual) return 0;
  if (node?.tier === "core" || node?.kind === "core" || node?.cluster === "core") return 1;
  if (node?.tier === "aggregation" || /aggregation|汇聚/i.test(`${node?.layer || ""} ${node?.role || ""} ${node?.label || ""}`)) return 2;
  if (node?.kind === "camera") return 4;
  return 3;
}

function isCoreNode(node) {
  return nodeTierRank(node) === 1;
}

function isAggregationNode(node) {
  return nodeTierRank(node) === 2;
}

function isAccessNode(node) {
  return nodeTierRank(node) === 3;
}

function wingCluster(node) {
  if (node?.cluster === "north" || node?.cluster === "south") return node.cluster;
  return stableHash(node?.nodeKey || node?.id || node?.label) % 2 === 0 ? "south" : "north";
}

function clusterSortRank(cluster) {
  if (cluster === "north") return 0;
  if (cluster === "core") return 1;
  if (cluster === "south") return 2;
  return 3;
}

function nodeAliasValues(node) {
  const raw = node?.raw || {};
  return [
    node?.id,
    node?.nodeKey,
    node?.ip,
    node?.backendId,
    node?.deviceId ? `device:${node.deviceId}` : "",
    raw.id,
    raw.ID,
    raw.node_key,
    raw.nodeKey,
    raw.ip,
    raw.IP,
    raw.device_id ? `device:${raw.device_id}` : "",
    raw.deviceId ? `device:${raw.deviceId}` : "",
  ].map((value) => normalizeText(value)).filter(Boolean);
}

function buildAliasMap(flatData = nodes.value) {
  const aliasMap = new Map();
  for (const node of flatData) {
    for (const alias of nodeAliasValues(node)) {
      if (!aliasMap.has(alias)) aliasMap.set(alias, node.id);
    }
  }
  return aliasMap;
}

function resolveNodeId(value, aliasMap) {
  const key = normalizeText(value);
  if (!key) return "";
  return aliasMap.get(key) || aliasMap.get(`device:${key}`) || "";
}

function parentCandidates(node) {
  const raw = node?.raw || {};
  return [
    node?.parentId,
    raw.parent_node_key,
    raw.Parent_ID,
    raw.parentId,
    raw.parent_id,
    raw.parent_node_id,
    raw.upstream_id,
    raw.upstream_node_key,
    raw.upstreamNodeKey,
    raw.upstream_device_id ? `device:${raw.upstream_device_id}` : "",
    raw.switch_device_id ? `device:${raw.switch_device_id}` : "",
    raw.switch_node_key,
    raw.switch_ip,
    raw.parent_ip,
  ].map((value) => normalizeText(value)).filter(Boolean);
}

function edgeTargetMatchesNode(edge, node, aliasMap) {
  const targetId = resolveNodeId(edge.target, aliasMap);
  if (targetId) return targetId === node.id;
  const aliases = new Set(nodeAliasValues(node));
  return aliases.has(normalizeText(edge.target));
}

function cameraParentId(camera) {
  if (!camera) return "";
  const aliasMap = buildAliasMap();
  for (const candidate of parentCandidates(camera)) {
    const resolved = resolveNodeId(candidate, aliasMap);
    if (resolved) return resolved;
  }
  const edge = edges.value.find((item) => edgeTargetMatchesNode(item, camera, aliasMap));
  return edge ? resolveNodeId(edge.source, aliasMap) || normalizeText(edge.source) : "";
}

function rebuildOrphans() {
  orphanList.value = cameraNodes.value.filter((item) => !cameraParentId(item));
}

function applyPayload(payload) {
  topologyPayload.value = payload || fallbackTopology();
  nodes.value = (topologyPayload.value.nodes || []).map(normalizeNode);
  edges.value = (topologyPayload.value.edges || []).map(normalizeEdge).filter(Boolean);
  rebuildOrphans();
}

async function loadTopology() {
  try {
    const payload = await fetchCentralAvenueArchitecture();
    applyPayload(payload);
  } catch (error) {
    console.error(error);
    applyPayload(fallbackTopology());
    ElMessage.warning("拓扑接口不可用，已启用本地兜底数据。");
  }
}

function cameraCountUnder(nodeId, childrenBySource, nodeMap) {
  let count = 0;
  const stack = [...(childrenBySource.get(nodeId) || [])];
  const visited = new Set();
  while (stack.length) {
    const id = stack.pop();
    if (visited.has(id)) continue;
    visited.add(id);
    const node = nodeMap.get(id);
    if (!node) continue;
    if (node.kind === "camera") count += 1;
    stack.push(...(childrenBySource.get(id) || []));
  }
  return count;
}

function buildChildrenIndex(nodeMap, aliasMap, flatData = nodes.value) {
  const childrenBySource = new Map();
  const pushChild = (sourceRef, targetRef) => {
    const source = resolveNodeId(sourceRef, aliasMap);
    const target = resolveNodeId(targetRef, aliasMap);
    if (!source || !target || source === target || !nodeMap.has(source) || !nodeMap.has(target)) return;
    if (!childrenBySource.has(source)) childrenBySource.set(source, []);
    const children = childrenBySource.get(source);
    if (!children.includes(target)) children.push(target);
  };

  for (const edge of edges.value) {
    pushChild(edge.source, edge.target);
  }
  for (const node of flatData) {
    for (const candidate of parentCandidates(node)) {
      const parentId = resolveNodeId(candidate, aliasMap);
      if (parentId) {
        pushChild(parentId, node.id);
        break;
      }
    }
  }
  return childrenBySource;
}

function sortTreeChildren(children) {
  return children.sort((a, b) => {
    const clusterDelta = clusterSortRank(a.cluster) - clusterSortRank(b.cluster);
    if (clusterDelta !== 0) return clusterDelta;
    const tierDelta = nodeTierRank(a) - nodeTierRank(b);
    if (tierDelta !== 0) return tierDelta;
    return stableHash(a.id) - stableHash(b.id);
  });
}

function buildTreeData(flatData = nodes.value) {
  const fallbackRoot = rootNode();
  if (!fallbackRoot) return null;
  const nodeMap = new Map(flatData.map((node) => [node.id, node]));
  const aliasMap = buildAliasMap(flatData);
  const childrenBySource = buildChildrenIndex(nodeMap, aliasMap, flatData);
  const rawParentByNode = new Map();
  for (const [source, targets] of childrenBySource.entries()) {
    for (const target of targets) {
      if (!rawParentByNode.has(target)) rawParentByNode.set(target, source);
    }
  }

  const coreNodes = flatData.filter((node) => node.kind !== "camera" && isCoreNode(node));
  const effectiveCores = coreNodes.length ? coreNodes : [fallbackRoot];
  const aggregationNodes = flatData.filter((node) => node.kind !== "camera" && isAggregationNode(node));
  const accessNodes = flatData.filter((node) => node.kind !== "camera" && isAccessNode(node));
  const topologyChildren = new Map();
  const visited = new Set();

  const pushTopologyChild = (parentId, childId) => {
    if (!parentId || !childId || parentId === childId || !nodeMap.has(childId)) return;
    if (!topologyChildren.has(parentId)) topologyChildren.set(parentId, []);
    const children = topologyChildren.get(parentId);
    if (!children.includes(childId)) children.push(childId);
  };

  const findAncestor = (node, matcher) => {
    let current = rawParentByNode.get(node.id);
    const seen = new Set([node.id]);
    while (current && !seen.has(current)) {
      seen.add(current);
      const parent = nodeMap.get(current);
      if (parent && matcher(parent)) return parent;
      current = rawParentByNode.get(current);
    }
    return null;
  };

  const nearestByCluster = (candidates, cluster, fallback = null) => (
    candidates.find((node) => node.cluster === cluster)
    || candidates.find((node) => node.cluster !== "core")
    || candidates[0]
    || fallback
  );

  const ensureAggregationNode = (cluster) => {
    const existing = aggregationNodes.find((node) => node.cluster === cluster);
    if (existing) return existing;
    const id = `virtual:aggregation:${cluster}`;
    if (nodeMap.has(id)) return nodeMap.get(id);
    const node = {
      id,
      nodeKey: id,
      label: cluster === "north" ? "北楼汇聚层" : "南楼汇聚层",
      kind: "switch",
      tier: "aggregation",
      layer: "aggregation",
      cluster,
      virtualGroup: true,
      verified: true,
      raw: {},
    };
    nodeMap.set(id, node);
    aggregationNodes.push(node);
    const parent = nearestByCluster(effectiveCores, cluster, effectiveCores[0]);
    if (parent) pushTopologyChild(parent.id, node.id);
    return node;
  };

  for (const aggregation of aggregationNodes) {
    if (aggregation.cluster !== "north" && aggregation.cluster !== "south") {
      aggregation.cluster = wingCluster(aggregation);
    }
    const parent = findAncestor(aggregation, isCoreNode)
      || nearestByCluster(effectiveCores, aggregation.cluster, effectiveCores[0]);
    if (parent) pushTopologyChild(parent.id, aggregation.id);
  }

  for (const access of accessNodes) {
    if (access.cluster !== "north" && access.cluster !== "south") {
      access.cluster = wingCluster(access);
    }
    const ancestorAggregation = findAncestor(access, isAggregationNode);
    const parent = (ancestorAggregation?.cluster === access.cluster ? ancestorAggregation : null)
      || aggregationNodes.find((node) => node.cluster === access.cluster)
      || ensureAggregationNode(access.cluster)
      || findAncestor(access, isCoreNode)
      || nearestByCluster(effectiveCores, access.cluster, effectiveCores[0]);
    if (parent) pushTopologyChild(parent.id, access.id);
  }

  for (const camera of flatData.filter((node) => node.kind === "camera")) {
    if (camera.cluster !== "north" && camera.cluster !== "south") {
      camera.cluster = wingCluster(camera);
    }
    const rawParent = rawParentByNode.get(camera.id);
    const rawParentNode = rawParent ? nodeMap.get(rawParent) : null;
    const parent = (rawParentNode && isAccessNode(rawParentNode) ? rawParentNode : null)
      || findAncestor(camera, isAccessNode)
      || (rawParentNode && rawParentNode.kind !== "camera" ? rawParentNode : null);
    if (parent) pushTopologyChild(parent.id, camera.id);
  }

  const toTreeNode = (node, depth = 0) => {
    visited.add(node.id);
    const rawChildren = sortTreeChildren(
      (topologyChildren.get(node.id) || [])
        .filter((childId) => !visited.has(childId))
        .map((childId) => nodeMap.get(childId))
        .filter(Boolean),
    );
    const children = rawChildren.map((child) => toTreeNode(child, depth + 1));
    const isAccess = isAccessNode(node);
    const cameraCount = cameraCountUnder(node.id, topologyChildren, nodeMap);
    return {
      ...node,
      type: node.kind === "camera" ? "camera-leaf" : "network-tree-node",
      depth,
      children,
      cameraCount,
      collapsed: isAccess && children.length > 0,
    };
  };

  const forceSideCluster = (node) => {
    if (node && node.cluster !== "north" && node.cluster !== "south") {
      node.cluster = wingCluster(node);
    }
    return node;
  };

  let tree;
  if (effectiveCores.length > 1) {
    const virtualRoot = {
      id: "virtual:topology-root",
      nodeKey: "virtual:topology-root",
      label: "核心层",
      kind: "virtual",
      tier: "virtual",
      layer: "root",
      cluster: "core",
      virtual: true,
      type: "virtual-root-node",
      cameraCount: cameraNodes.value.length,
      children: sortTreeChildren(effectiveCores).map((node) => toTreeNode(node, 1)),
      collapsed: false,
    };
    tree = virtualRoot;
  } else {
    tree = toTreeNode(effectiveCores[0]);
  }

  const detachedRoots = flatData
    .filter((node) => !visited.has(node.id) && node.kind !== "camera")
    .sort((a, b) => a.cluster.localeCompare(b.cluster) || stableHash(a.id) - stableHash(b.id))
    .map((node) => toTreeNode(forceSideCluster(node), tree.virtual ? 1 : 2));
  tree.children = [...(tree.children || []), ...detachedRoots];
  return tree;
}

function buildTopologyTree() {
  return buildTreeData(nodes.value);
}

function tierColor(node) {
  if (node.virtual) return { fill: "rgba(0, 0, 0, 0)", stroke: "rgba(0, 0, 0, 0)", shadow: "rgba(0, 0, 0, 0)" };
  if (node.kind === "camera") return { fill: "rgba(17, 24, 39, 0.96)", stroke: "#94a3b8", shadow: "rgba(148, 163, 184, 0.28)" };
  if (node.tier === "core") return { fill: "rgba(89, 24, 32, 0.96)", stroke: "#f56c6c", shadow: "rgba(245, 108, 108, 0.5)" };
  if (node.tier === "aggregation") return { fill: "rgba(16, 48, 84, 0.96)", stroke: "#409eff", shadow: "rgba(64, 158, 255, 0.42)" };
  return { fill: "rgba(22, 61, 44, 0.96)", stroke: "#67c23a", shadow: "rgba(103, 194, 58, 0.38)" };
}

function graphNodeWidth(node) {
  if (node?.virtual) return 1;
  if (node?.kind === "camera") return 32; // 🔥 宽度暴降，圆形物理边界
  if (isCoreNode(node)) return 216;
  if (isAggregationNode(node)) return 190;
  return 176;
}

function graphNodeHeight(node) {
  if (node?.virtual) return 1;
  if (node?.kind === "camera") return 32; // 🔥 高度暴降，圆形物理边界
  if (isCoreNode(node)) return 84;
  if (isAggregationNode(node)) return 76;
  return 72;
}

function hasCollapsedChildren(model) {
  return Array.isArray(model?.children) && model.children.length > 0;
}

function isCollapsedWithChildren(model) {
  return Boolean(model?.collapsed && hasCollapsedChildren(model));
}

function nodeShellAttrs(model, selected = false) {
  const palette = tierColor(model || {});
  if (selected) {
    return {
      stroke: "#facc15",
      lineWidth: 3,
      shadowColor: "rgba(250, 204, 21, 0.62)",
      shadowBlur: 24,
    };
  }
  if (isCollapsedWithChildren(model)) {
    return {
      stroke: model?.conflict ? "#fb923c" : "#93c5fd",
      lineWidth: 3,
      shadowColor: model?.conflict ? "rgba(251, 146, 60, 0.9)" : "rgba(147, 197, 253, 0.95)",
      shadowBlur: 28,
    };
  }
  return {
    stroke: model?.conflict ? "#f59e0b" : palette.stroke,
    lineWidth: model?.conflict ? 3 : 2,
    shadowColor: model?.conflict ? "rgba(245, 158, 11, 0.75)" : palette.shadow,
    shadowBlur: model?.conflict ? 24 : 16,
  };
}

function collapseMarkerAttrs(model) {
  return {
    fill: model?.collapsed ? "#f59e0b" : "#0ea5e9",
    stroke: isCollapsedWithChildren(model) ? "#bfdbfe" : "#e2e8f0",
    lineWidth: isCollapsedWithChildren(model) ? 1.8 : 1.2,
  };
}

function itemHasState(item, stateName) {
  if (!item || item.destroyed) return false;
  if (typeof item.hasState === "function") return item.hasState(stateName);
  return item.getStates?.().includes(stateName) || false;
}

// 🔥 这里只负责颜色变化，形状去 registerNode 里面改
function cameraShellAttrs(model, selected = false) {
  const palette = tierColor(model || {});
  if (selected) {
    return {
      stroke: "#facc15",
      lineWidth: 2.4,
      shadowColor: "rgba(250, 204, 21, 0.54)",
      shadowBlur: 18,
    };
  }
  return {
    stroke: model?.verified ? "#22c55e" : "#94a3b8",
    lineWidth: 1.8,
    shadowColor: palette.shadow,
    shadowBlur: 8,
  };
}

function applyNodeVisualState(item) {
  if (!item || item.destroyed) return;
  const model = item.getModel?.();
  if (!model) return;
  const group = item.getContainer();
  const shellName = model.kind === "camera" ? "camera-shell" : "shell";
  const shell = group.find((shape) => shape.get("name") === shellName);
  const marker = group.find((shape) => shape.get("name") === "collapse-marker");
  const markerText = group.find((shape) => shape.get("name") === "collapse-marker-text");
  const selected = itemHasState(item, "selected");
  const active = itemHasState(item, RELATION_ACTIVE_STATE);
  const inactive = itemHasState(item, RELATION_INACTIVE_STATE);
  const showText = (graph?.getZoom?.() || 1) >= LOD_LABEL_ZOOM;
  const baseShellAttrs = model.kind === "camera" ? cameraShellAttrs(model, selected) : nodeShellAttrs(model, selected);
  const shellAttrs = {
    ...baseShellAttrs,
    opacity: inactive ? 0.18 : 1,
  };
  if (active) {
    Object.assign(shellAttrs, {
      stroke: "#67e8f9",
      lineWidth: model.kind === "camera" ? 2.4 : 3.2,
      shadowColor: "rgba(103, 232, 249, 0.72)",
      shadowBlur: model.kind === "camera" ? 18 : 28,
      opacity: 1,
    });
  }
  shell?.attr(shellAttrs);
  marker?.attr(collapseMarkerAttrs(model));
  markerText?.attr({ text: model.collapsed ? "+" : "-" });
  const children = group?.get?.("children") || [];
  children.forEach((shape) => {
    const name = shape.get("name");
    if (name === shellName) return;
    const isLodText = LOD_TEXT_SHAPES.has(name);
    const opacity = inactive ? (isLodText ? 0.12 : 0.22) : (isLodText && !showText ? 0 : 1);
    shape.attr({ opacity });
  });
  if (active && typeof item.toFront === "function") item.toFront();
}

function syncCollapsedGlow(item) {
  if (!graph || !item || item.destroyed) return;
  const model = item.getModel?.();
  if (!model || model.kind === "camera") return;
  graph.setItemState(item, "collapsed-glow", isCollapsedWithChildren(model));
  applyNodeVisualState(item);
}

function syncAllCollapsedGlow() {
  if (!graph) return;
  graph.getNodes().forEach(syncCollapsedGlow);
}

function applyLodVisibility() {
  if (!graph) return;
  graph.getNodes().forEach(applyNodeVisualState);
}

let lodFrame = 0;
function scheduleLodVisibility() {
  if (lodFrame) return;
  lodFrame = window.requestAnimationFrame(() => {
    lodFrame = 0;
    applyLodVisibility();
  });
}

// 🔥 彻底废弃视角强制聚焦动画，拒绝反人类“弹回远处”
function focusItemAfterCollapse(item) {
  if (!graph || !item || item.destroyed) return;
  // 直接只做视觉状态同步，不触发任何 graph.focusItem 或视角跳转！
  syncAllCollapsedGlow();
}

function handleCollapseChange(item, collapsed) {
  const data = item?.get("model");
  if (!data) return true;
  data.collapsed = collapsed;
  syncCollapsedGlow(item);
  focusItemAfterCollapse(item);
  return true;
}

function buildGraphPlugins() {
  return [];
}

function edgeBaseAttrs(model = {}) {
  return {
    stroke: model.style?.stroke || "rgba(64, 158, 255, 0.76)",
    lineWidth: model.style?.lineWidth || 1.8,
    lineDash: model.style?.lineDash || [8, 6],
    lineAppendWidth: 15,
    shadowColor: "rgba(64, 158, 255, 0.55)",
    shadowBlur: 10,
    opacity: 1,
  };
}

function applyEdgeVisualState(item) {
  if (!item || item.destroyed) return;
  const shape = item.getKeyShape?.();
  if (!shape) return;
  const active = itemHasState(item, RELATION_ACTIVE_STATE);
  const inactive = itemHasState(item, RELATION_INACTIVE_STATE);
  const attrs = edgeBaseAttrs(item.getModel?.() || {});
  if (inactive) {
    Object.assign(attrs, {
      stroke: "rgba(71, 85, 105, 0.4)",
      lineWidth: 1,
      shadowBlur: 0,
      opacity: 0.12,
    });
  }
  if (active) {
    Object.assign(attrs, {
      stroke: "#67e8f9",
      lineWidth: 3,
      shadowColor: "rgba(103, 232, 249, 0.8)",
      shadowBlur: 18,
      opacity: 1,
    });
    if (typeof item.toFront === "function") item.toFront();
  }
  shape.attr(attrs);
}

function registerCustomElements() {
  if (customElementsRegistered) return;
  customElementsRegistered = true;

  G6.registerEdge("animated-curve", {
    afterDraw(cfg, group) {
      const shape = group.get("children")?.[0];
      if (!shape?.animate) return;
      const stroke = cfg?.style?.stroke || "rgba(64, 158, 255, 0.72)";
      shape.attr({
        stroke,
        lineDash: [8, 6],
        lineDashOffset: 0,
        shadowColor: "rgba(64, 158, 255, 0.55)",
        shadowBlur: 10,
      });
      shape.animate(
        (ratio) => ({
          lineDashOffset: -ratio * 72,
        }),
        {
          repeat: true,
          duration: 1400,
          easing: "easeLinear",
        },
      );
    },
    setState(name, value, item) {
      if ([RELATION_ACTIVE_STATE, RELATION_INACTIVE_STATE].includes(name)) {
        applyEdgeVisualState(item);
      }
    },
  }, "quadratic");

  G6.registerNode("virtual-root-node", {
    draw(cfg, group) {
      return group.addShape("circle", {
        attrs: {
          x: 0,
          y: 0,
          r: 1,
          fill: "rgba(0, 0, 0, 0)",
          stroke: "rgba(0, 0, 0, 0)",
          opacity: 0,
        },
        name: "virtual-root-shell",
      });
    },
  }, "single-node");

  G6.registerNode("network-tree-node", {
    draw(cfg, group) {
      const width = graphNodeWidth(cfg);
      const height = graphNodeHeight(cfg);
      const palette = tierColor(cfg);
      const isCore = isCoreNode(cfg);
      const tierText = nodeTierCode(cfg);
      const titleText = cleanDeviceLabel(cfg.label, [cfg.ip, cfg.nodeKey, cfg.id]);
      const metaText = `${clusterLabel(cfg.cluster)} / IP ${cfg.ip || cfg.nodeKey || "-"}`;
      const portText = nodePortText(cfg);
      const keyShape = group.addShape("rect", {
        attrs: {
          x: -width / 2,
          y: -height / 2,
          width,
          height,
          radius: 12,
          fill: palette.fill,
          ...nodeShellAttrs(cfg),
        },
        name: "shell",
      });
      group.addShape("text", {
        attrs: {
          x: -width / 2 + 14,
          y: isCore ? -20 : -18,
          text: trimDisplayText(titleText, isCore ? 22 : 18),
          fill: "#f8fbff",
          fontSize: isCore ? 14 : 12,
          fontWeight: 800,
          textBaseline: "middle",
        },
        name: "label",
      });
      group.addShape("text", {
        attrs: {
          x: -width / 2 + 14,
          y: isCore ? 3 : 1,
          text: trimDisplayText(metaText, isCore ? 26 : 22),
          fill: "rgba(226, 232, 240, 0.68)",
          fontSize: 10,
          textBaseline: "middle",
        },
        name: "meta",
      });
      group.addShape("text", {
        attrs: {
          x: -width / 2 + 14,
          y: isCore ? 23 : 19,
          text: trimDisplayText(portText, isCore ? 26 : 22),
          fill: "rgba(191, 219, 254, 0.86)",
          fontSize: 9,
          textBaseline: "middle",
        },
        name: "port",
      });
      group.addShape("text", {
        attrs: {
          x: width / 2 - 18,
          y: height / 2 - 15,
          text: tierText,
          fill: isCore ? "#fecaca" : isAggregationNode(cfg) ? "#bfdbfe" : "#bbf7d0",
          fontSize: 10,
          fontWeight: 900,
          textAlign: "right",
          textBaseline: "middle",
        },
        name: "tier-mark",
      });
      if ((cfg.isAccess || isAccessNode(cfg)) && cfg.cameraCount > 0) {
        group.addShape("rect", {
          attrs: {
            x: width / 2 - 54,
            y: -height / 2 - 12,
            width: 64,
            height: 24,
            radius: 12,
            fill: "#f56c6c",
            stroke: "#fecaca",
            lineWidth: 1.6,
            shadowColor: "rgba(245, 108, 108, 0.72)",
            shadowBlur: 14,
          },
          name: "camera-badge",
        });
        group.addShape("text", {
          attrs: {
            x: width / 2 - 22,
            y: -height / 2,
            text: `${cfg.cameraExpanded ? "[-]" : "[+]"} ${cfg.cameraCount}`,
            fill: "#fff",
            fontSize: 10,
            fontWeight: 900,
            textAlign: "center",
            textBaseline: "middle",
          },
          name: "camera-badge-text",
        });
      }
      if (cfg.children?.length) {
        group.addShape("circle", {
          attrs: {
            x: width / 2 + 12,
            y: 0,
            r: 9,
            ...collapseMarkerAttrs(cfg),
          },
          name: "collapse-marker",
        });
        group.addShape("text", {
          attrs: {
            x: width / 2 + 12,
            y: 0,
            text: cfg.collapsed ? "+" : "-",
            fill: "#fff",
            fontSize: 13,
            fontWeight: 900,
            textAlign: "center",
            textBaseline: "middle",
          },
          name: "collapse-marker-text",
        });
      }
      if (cfg.verified) {
        group.addShape("circle", {
          attrs: { x: width / 2 - 12, y: height / 2 - 12, r: 7, fill: "#22c55e", stroke: "#fff", lineWidth: 1 },
          name: "verified-dot",
        });
      }
      return keyShape;
    },
    setState(name, value, item) {
      if (["selected", "collapsed-glow", RELATION_ACTIVE_STATE, RELATION_INACTIVE_STATE].includes(name)) {
        applyNodeVisualState(item);
      }
    },
  }, "single-node");

  // 🔥 终极重构：将摄像头改为极其优雅的高科技小圆点！
  G6.registerNode("camera-leaf", {
    draw(cfg, group) {
      const isVerified = cfg.verified;
      const r = 16;
      
      const keyShape = group.addShape("circle", {
        attrs: {
          x: 0,
          y: 0,
          r: r,
          fill: "rgba(17, 24, 39, 0.96)",
          stroke: isVerified ? "#22c55e" : "#94a3b8",
          lineWidth: 2,
          shadowColor: isVerified ? "rgba(34, 197, 94, 0.3)" : "rgba(148, 163, 184, 0.2)",
          shadowBlur: 10,
        },
        name: "camera-shell",
      });

      // 中心摄像机图标
      group.addShape("text", {
        attrs: {
          x: 0,
          y: 0,
          text: "📹",
          fill: "#e5edf8",
          fontSize: 14,
          textAlign: "center",
          textBaseline: "middle",
        },
        name: "camera-icon",
      });

      // 底部干净利落的名字
      group.addShape("text", {
        attrs: {
          x: 0,
          y: r + 12,
          text: cleanDeviceLabel(cfg.label, [cfg.ip, cfg.nodeKey, cfg.id]),
          fill: "#e5edf8",
          fontSize: 10,
          fontWeight: 700,
          textAlign: "center",
          textBaseline: "middle",
        },
        name: "camera-label",
      });

      // 底部干净利落的 IP
      group.addShape("text", {
        attrs: {
          x: 0,
          y: r + 24,
          text: cfg.ip || cfg.nodeKey || "-",
          fill: "#94a3b8",
          fontSize: 9,
          textAlign: "center",
          textBaseline: "middle",
        },
        name: "camera-meta",
      });
      return keyShape;
    },
    setState(name, value, item) {
      if (["selected", RELATION_ACTIVE_STATE, RELATION_INACTIVE_STATE].includes(name)) {
        applyNodeVisualState(item);
      }
    },
  }, "single-node");
}

function treeLayoutTier(node) {
  if (node?.virtual || isCoreNode(node)) return 0;
  if (isAggregationNode(node)) return 1;
  if (isAccessNode(node)) return 2;
  return 3;
}

function collectTreeLayoutEntries(root) {
  const entries = [];
  const walk = (node, parent = null) => {
    if (!node) return;
    entries.push({ node, parent });
    for (const child of node.children || []) {
      walk(child, node);
    }
  };
  walk(root);
  return entries;
}

function sortedLayoutNodes(entries) {
  return entries
    .map((entry) => entry.node)
    .sort((a, b) => stableHash(a.id || a.nodeKey || a.label) - stableHash(b.id || b.nodeKey || b.label));
}

function ellipseTheta(index, total, startTheta, endTheta) {
  if (total <= 1) return (startTheta + endTheta) / 2;
  return startTheta + ((endTheta - startTheta) * index) / (total - 1);
}

function placeEllipseArc(nodesForArc, centerX, centerY, radiusX, radiusY, startTheta, endTheta) {
  sortedLayoutNodes(nodesForArc).forEach((node, index, ordered) => {
    const theta = ellipseTheta(index, ordered.length, startTheta, endTheta);
    node.x = centerX + radiusX * Math.cos(theta);
    node.y = centerY - radiusY * Math.sin(theta);
  });
}

function ensureSafeCoordinate(node, centerX, centerY) {
  if (!Number.isFinite(Number(node.x)) || !Number.isFinite(Number(node.y))) {
    console.error("节点坐标计算出 NaN:", node);
    node.x = centerX;
    node.y = centerY;
    return;
  }
  node.x = Number(node.x);
  node.y = Number(node.y);
}

function placeCameraStarburst(cameraEntries, centerX, centerY) {
  const cameraGroups = new Map();
  for (const entry of cameraEntries) {
    const anchorX = Number.isFinite(Number(entry.parent?.x)) ? Number(entry.parent.x) : centerX;
    const anchorY = Number.isFinite(Number(entry.parent?.y)) ? Number(entry.parent.y) : centerY;
    entry.node.x = anchorX;
    entry.node.y = anchorY;
    if (!entry.parent || !isAccessNode(entry.parent) || !expandedAccessIds.value.has(entry.parent.id)) continue;
    const parentId = entry.parent?.id || "__orphan-camera";
    if (!cameraGroups.has(parentId)) cameraGroups.set(parentId, []);
    cameraGroups.get(parentId).push(entry);
  }

  for (const groupEntries of cameraGroups.values()) {
    const parent = groupEntries[0]?.parent;
    const ordered = groupEntries.sort((a, b) => stableHash(a.node.id) - stableHash(b.node.id));
    ordered.forEach((entry, index) => {
      const theta = ordered.length <= 1 ? -Math.PI / 2 : (Math.PI * 2 * index) / ordered.length;
      const anchorX = Number.isFinite(Number(parent?.x)) ? Number(parent.x) : centerX;
      const anchorY = Number.isFinite(Number(parent?.y)) ? Number(parent.y) : centerY;
      entry.node.x = anchorX + STARBURST_CAMERA_RADIUS * Math.cos(theta);
      entry.node.y = anchorY + STARBURST_CAMERA_RADIUS * Math.sin(theta);
    });
  }
}

function flattenTreeGraphData(treeRoot) {
  const graphNodes = [];
  const graphEdges = [];
  const seenNodeIds = new Set();
  const seenEdgeIds = new Set();
  const walk = (node, parent = null) => {
    if (!node?.id) return;
    const children = Array.isArray(node.children) ? node.children : [];
    if (node.kind === "camera" && parent && isAccessNode(parent) && !expandedAccessIds.value.has(parent.id)) {
      return;
    }
    const nodeAlreadyAdded = seenNodeIds.has(node.id);
    if (!nodeAlreadyAdded) {
      const { children: _children, ...graphNode } = node;
      graphNode.hasTreeChildren = children.length > 0;
      graphNode.isCore = isCoreNode(graphNode);
      graphNode.isAccess = isAccessNode(graphNode);
      graphNode.isAggregation = isAggregationNode(graphNode);
      graphNode.cameraExpanded = graphNode.isAccess && expandedAccessIds.value.has(graphNode.id);
      graphNodes.push(graphNode);
      seenNodeIds.add(node.id);
    } else {
      console.warn("跳过重复拓扑节点:", node.id);
    }
    if (parent?.id && node.id && seenNodeIds.has(parent.id)) {
      const edgeId = `${parent.id}->${node.id}`;
      if (!seenEdgeIds.has(edgeId)) {
        graphEdges.push({
          id: edgeId,
          source: parent.id,
          target: node.id,
          type: "animated-curve",
        });
        seenEdgeIds.add(edgeId);
      }
    }
    children.forEach((child) => walk(child, node));
  };
  walk(treeRoot);
  return { nodes: graphNodes, edges: graphEdges };
}

function applyEllipticalLayout(treeRoot, graphEdges = []) {
  if (!treeRoot) return { nodes: [], edges: [] };
  const width = graphContainer.value?.clientWidth || graphContainer.value?.offsetWidth || 1000;
  const height = graphContainer.value?.clientHeight || graphContainer.value?.offsetHeight || 600;
  const centerX = width / 2;
  const centerY = height / 2;
  const entries = collectTreeLayoutEntries(treeRoot);
  const arcBuckets = {
    north: { aggregation: [], access: [] },
    south: { aggregation: [], access: [] },
  };
  const cameraEntries = [];

  for (const entry of entries) {
    const { node } = entry;
    const tier = treeLayoutTier(node);
    if (tier === 0) {
      node.x = centerX;
      node.y = centerY;
      continue;
    }

    const cluster = wingCluster(node);
    node.cluster = cluster;
    if (tier === 1) {
      arcBuckets[cluster].aggregation.push(entry);
    } else if (tier === 2) {
      arcBuckets[cluster].access.push(entry);
    } else {
      cameraEntries.push(entry);
    }
  }

  const accessCount = arcBuckets.north.access.length + arcBuckets.south.access.length;
  const currentRadiusX = Math.max(ELLIPSE_OUTER_RADIUS_X, accessCount * 15);
  const currentRadiusY = Math.max(ELLIPSE_OUTER_RADIUS_Y, currentRadiusX * (ELLIPSE_OUTER_RADIUS_Y / ELLIPSE_OUTER_RADIUS_X));

  placeEllipseArc(arcBuckets.north.aggregation, centerX, centerY, ELLIPSE_INNER_RADIUS_X, ELLIPSE_INNER_RADIUS_Y, NORTH_ARC_START, NORTH_ARC_END);
  placeEllipseArc(arcBuckets.north.access, centerX, centerY, currentRadiusX, currentRadiusY, NORTH_ARC_START, NORTH_ARC_END);
  placeEllipseArc(arcBuckets.south.aggregation, centerX, centerY, ELLIPSE_INNER_RADIUS_X, ELLIPSE_INNER_RADIUS_Y, SOUTH_ARC_START, SOUTH_ARC_END);
  placeEllipseArc(arcBuckets.south.access, centerX, centerY, currentRadiusX, currentRadiusY, SOUTH_ARC_START, SOUTH_ARC_END);
  placeCameraStarburst(cameraEntries, centerX, centerY);

  entries.forEach((entry) => ensureSafeCoordinate(entry.node, centerX, centerY));
  return flattenTreeGraphData(treeRoot);
}

function clampThetaToWingArc(theta, cluster) {
  const normalizeAngle = (t) => {
    const full = Math.PI * 2;
    const n = t % full;
    return n < 0 ? n + full : n;
  };
  const angleDistance = (a, b) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));
  const clampAngleToArc = (t, start, end) => {
    const n = normalizeAngle(t);
    if (n >= start && n <= end) return n;
    return angleDistance(n, start) <= angleDistance(n, end) ? start : end;
  };
  
  if (cluster === "north") return clampAngleToArc(theta, Math.PI * 1.1, Math.PI * 1.9);
  if (cluster === "south") return clampAngleToArc(theta, Math.PI * 0.1, Math.PI * 0.9);
  return normalizeAngle(theta);
}

function orbitRadiiForNode(model) {
  if (isAccessNode(model) || model?.isAccess) {
    const accessNodes = nodes.value.filter((node) => node.kind !== "camera" && isAccessNode(node));
    const radiusX = Math.max(ELLIPSE_OUTER_RADIUS_X, accessNodes.length * 15);
    return {
      x: radiusX,
      y: Math.max(ELLIPSE_OUTER_RADIUS_Y, radiusX * (ELLIPSE_OUTER_RADIUS_Y / ELLIPSE_OUTER_RADIUS_X)),
    };
  }
  return { x: ELLIPSE_INNER_RADIUS_X, y: ELLIPSE_INNER_RADIUS_Y };
}

function snapSwitchToPolarOrbit(model, point) {
  const width = graphContainer.value?.clientWidth || graphContainer.value?.offsetWidth || 1000;
  const height = graphContainer.value?.clientHeight || graphContainer.value?.offsetHeight || 600;
  const centerX = width / 2;
  const centerY = height / 2;
  if (model?.isCore || isCoreNode(model)) {
    return { x: centerX, y: centerY };
  }

  const dx = Number(point?.x ?? model?.x ?? centerX) - centerX;
  const dy = Number(point?.y ?? model?.y ?? centerY) - centerY;
  const theta = clampThetaToWingArc(Math.atan2(dy, dx), wingCluster(model));
  const radii = orbitRadiiForNode(model);
  return {
    x: centerX + radii.x * Math.cos(theta),
    y: centerY + radii.y * Math.sin(theta),
  };
}

function relationBehaviorConfig() {
  return {
    type: "activate-relations",
    trigger: "mouseenter",
    activeState: RELATION_ACTIVE_STATE,
    inactiveState: RELATION_INACTIVE_STATE,
    resetSelected: false,
  };
}

function graphConfig() {
  const width = graphContainer.value?.offsetWidth || 800;
  const height = graphContainer.value?.offsetHeight || 600;
  const sharedModes = [
    "drag-canvas",
    { type: "zoom-canvas", enableOptimize: true, optimizeZoom: 0.92 },
    relationBehaviorConfig(),
  ];
  return {
    container: graphContainer.value,
    width,
    height,
    fitView: true,
    fitViewPadding: [64, 120, 64, 80],
    animate: true,
    animateCfg: {
      duration: COLLAPSE_ANIMATION_DURATION,
      easing: "easeCubicInOut",
    },
    plugins: buildGraphPlugins(),
    modes: {
      default: editMode.value
        ? [ ...sharedModes, { type: "drag-node", enableDelegate: true } ]
        : sharedModes,
    },
    defaultNode: {
      type: "network-tree-node",
      anchorPoints: [[0.5, 0], [0.5, 1], [0, 0.5], [1, 0.5]],
    },
    defaultEdge: {
      type: "animated-curve",
      style: {
        stroke: "#40a9ff",
        lineWidth: 1.2,
        lineDash: [8, 6],
        lineAppendWidth: 15,
        endArrow: false,
      },
    },
    layout: null,
    nodeStateStyles: { selected: {}, "collapsed-glow": {}, [RELATION_ACTIVE_STATE]: {}, [RELATION_INACTIVE_STATE]: {} },
    edgeStateStyles: { [RELATION_ACTIVE_STATE]: {}, [RELATION_INACTIVE_STATE]: {} },
  };
}

// 🔥 终极修复：彻底接管视图矩阵，绝对不允许它挂载后把人弹回远处！
async function renderGraph() {
  await nextTick();
  if (!graphContainer.value) return;
  registerCustomElements();

  const graphData = applyEllipticalLayout(buildTopologyTree(), edges.value);

  if (!graph) {
    graph = new G6.Graph(graphConfig());
    graph.data(graphData);
    bindGraphEvents();
    graph.render();
    graph.fitView();
  } else {
    // 🔥 手动截取当前极其珍贵的视角矩阵（包含缩放、拖拽位置）
    let currentMatrix = graph.getGroup().getMatrix();
    if (currentMatrix) currentMatrix = [...currentMatrix]; 

    graph.changeData(graphData);

    // 🔥 渲染完新数据后，直接把刚才的视角矩阵强行按回去！决不退缩半步！
    if (currentMatrix) {
      graph.getGroup().setMatrix(currentMatrix);
      graph.autoPaint();
    }
  }

  syncAllCollapsedGlow();
  applyLodVisibility();
  if (selectedNodeId.value && graph.findById(selectedNodeId.value)) {
    graph.setItemState(graph.findById(selectedNodeId.value), "selected", true);
  }
}

function selectNode(model) {
  selectedNodeId.value = model.id;
  if (!graph) return;
  graph.getNodes().forEach((item) => graph.setItemState(item, "selected", false));
  const item = graph.findById(model.id);
  if (item) graph.setItemState(item, "selected", true);
  syncAllCollapsedGlow();
}

function clearRelationStates() {
  if (!graph) return;
  [...graph.getNodes(), ...graph.getEdges()].forEach((item) => {
    graph.setItemState(item, RELATION_ACTIVE_STATE, false);
    graph.setItemState(item, RELATION_INACTIVE_STATE, false);
  });
}

function activateRelationsForItem(item) {
  if (!graph || !item || item.destroyed) return;
  clearRelationStates();
  const relatedItems = new Set([item]);
  item.getEdges?.().forEach((edge) => {
    relatedItems.add(edge);
    relatedItems.add(edge.getSource?.());
    relatedItems.add(edge.getTarget?.());
  });
  [...graph.getNodes(), ...graph.getEdges()].forEach((graphItem) => {
    if (!graphItem || graphItem.destroyed) return;
    const related = relatedItems.has(graphItem);
    graph.setItemState(graphItem, RELATION_INACTIVE_STATE, !related);
    graph.setItemState(graphItem, RELATION_ACTIVE_STATE, related);
  });
}

function selectedCameraItem() {
  if (!graph || !selectedNodeId.value) return null;
  const item = graph.findById(selectedNodeId.value);
  const model = item?.getModel?.();
  return model?.kind === "camera" ? item : null;
}

function isCameraBadgeTarget(target) {
  const name = target?.get?.("name") || "";
  return name === "camera-badge" || name === "camera-badge-text";
}

async function toggleAccessCameraRing(model) {
  if (!model?.id || !isAccessNode(model) || !model.cameraCount) return false;
  const next = new Set(expandedAccessIds.value);
  if (next.has(model.id)) {
    next.delete(model.id);
  } else {
    next.add(model.id);
  }
  expandedAccessIds.value = next;
  selectedNodeId.value = model.id;
  await renderGraph();
  return true;
}

function inboundEdgeForNode(node) {
  const aliasMap = buildAliasMap();
  return edges.value.find((edge) => edgeTargetMatchesNode(edge, node, aliasMap)) || null;
}

function orphanPoolTargetPoint() {
  const pool = document.querySelector(".orphan-list");
  const sidebar = document.querySelector(".orphan-sidebar");
  const rect = (pool || sidebar)?.getBoundingClientRect();
  if (!rect) return { x: 72, y: 180 };
  return {
    x: rect.left + Math.min(96, rect.width / 2),
    y: rect.top + 52,
  };
}

function createGhostCard(model, startPoint) {
  const ghost = document.createElement("div");
  const icon = document.createElement("span");
  const info = document.createElement("span");
  const name = document.createElement("strong");
  const ip = document.createElement("small");
  icon.className = "topology-ghost-icon";
  icon.textContent = assetIcon(model);
  info.className = "topology-ghost-info";
  name.textContent = model.label || model.id || "摄像头";
  ip.textContent = model.ip || model.nodeKey || "";
  info.append(name, ip);
  ghost.className = "topology-ghost-card";
  ghost.style.left = `${startPoint.x - 78}px`;
  ghost.style.top = `${startPoint.y - 22}px`;
  ghost.append(icon, info);
  document.body.appendChild(ghost);
  return ghost;
}

function animateNodeToOrphanPool(item, model) {
  if (!graph || !item || item.destroyed) return Promise.resolve();
  const containerRect = graphContainer.value?.getBoundingClientRect();
  const clientPoint = graph.getClientByPoint?.(Number(model.x || 0), Number(model.y || 0));
  const canvasPoint = !clientPoint && graph.getCanvasByPoint?.(Number(model.x || 0), Number(model.y || 0));
  let startPoint = {
    x: (containerRect?.left || 0) + (containerRect?.width || 0) / 2,
    y: (containerRect?.top || 0) + (containerRect?.height || 0) / 2,
  };
  if (clientPoint && "x" in clientPoint && "y" in clientPoint) {
    startPoint = { x: clientPoint.x, y: clientPoint.y };
  } else if (canvasPoint && "x" in canvasPoint && "y" in canvasPoint) {
    startPoint = {
      x: (containerRect?.left || 0) + canvasPoint.x,
      y: (containerRect?.top || 0) + canvasPoint.y,
    };
  }
  const target = orphanPoolTargetPoint();
  const ghost = createGhostCard(model, startPoint);
  const dx = target.x - startPoint.x;
  const dy = target.y - startPoint.y;

  return new Promise((resolve) => {
    const cleanup = () => {
      ghost.remove();
      resolve();
    };
    if (ghost.animate) {
      const animation = ghost.animate(
        [
          { transform: "translate3d(0, 0, 0) scale(1)", opacity: 1, filter: "blur(0)" },
          { transform: `translate3d(${dx}px, ${dy}px, 0) scale(0.58)`, opacity: 0.18, filter: "blur(1px)" },
        ],
        {
          duration: 460,
          easing: "cubic-bezier(0.18, 0.9, 0.22, 1)",
          fill: "forwards",
        },
      );
      animation.onfinish = cleanup;
      animation.oncancel = cleanup;
      return;
    }
    ghost.style.transition = "transform 460ms cubic-bezier(0.18, 0.9, 0.22, 1), opacity 460ms ease";
    window.requestAnimationFrame(() => {
      ghost.style.transform = `translate3d(${dx}px, ${dy}px, 0) scale(0.58)`;
      ghost.style.opacity = "0.18";
    });
    window.setTimeout(cleanup, 480);
  });
}

function removeGraphCameraItem(item, model) {
  if (!graph || !item || item.destroyed) return;
  try {
    if (typeof graph.removeChild === "function") {
      graph.removeChild(model.id);
    } else {
      graph.removeItem(item, false);
    }
  } catch (error) {
    console.warn("G6 remove camera node fallback.", error);
    if (!item.destroyed) graph.removeItem(item, false);
  }
}

function unlinkCameraLocally(model) {
  const cameraNode = cameraNodes.value.find((node) => node.id === model.id || node.nodeKey === model.nodeKey);
  if (!cameraNode) return null;
  const edge = inboundEdgeForNode(cameraNode);
  const aliasMap = buildAliasMap();
  cameraNode.parentId = "";
  cameraNode.verified = false;
  cameraNode.posX = null;
  cameraNode.posY = null;
  cameraNode.raw = {
    ...cameraNode.raw,
    parent_node_key: "",
    parent_ip: "",
    pos_x: null,
    pos_y: null,
    position_source: "orphan_pool",
    review_status: "pending_field_review",
  };
  edges.value = edges.value.filter((item) => !edgeTargetMatchesNode(item, cameraNode, aliasMap));
  if (!orphanList.value.some((item) => item.id === cameraNode.id)) {
    orphanList.value = [cameraNode, ...orphanList.value];
  }
  if (selectedNodeId.value === cameraNode.id) selectedNodeId.value = "";
  return { cameraNode, edge };
}

async function clearCameraBindingRemote(cameraNode, edge) {
  try {
    if (edge?.backendId) {
      try {
        await deleteArchitectureEdge(edge.backendId);
      } catch (error) {
        console.warn("Architecture edge delete skipped or already cleared.", error);
      }
    }
    await clearAssetTopologyBinding({
      node_id: cameraNode.backendId,
      node_key: cameraNode.nodeKey || cameraNode.id,
      id: cameraNode.nodeKey || cameraNode.id,
      ip: cameraNode.ip,
      device_id: cameraNode.deviceId,
      edge_id: edge?.backendId || null,
      manual_note: "TopologyEditor 退回待核实资产池",
    });
    ElMessage.success(`${cameraNode.label || cameraNode.ip} 已退回待核实资产池`);
  } catch (error) {
    console.error(error);
    ElMessage.warning("本地已退回待核实池，但后端清空绑定失败，请稍后重试。");
  }
}

async function detachCameraToOrphanPool(item) {
  if (!editMode.value) {
    ElMessage.warning("当前为只读锁定状态，请先启用编辑模式。");
    return;
  }
  const model = item?.getModel?.();
  if (!model || model.kind !== "camera") {
    ElMessage.warning("当前仅支持将摄像头叶子节点退回待核实资产池。");
    return;
  }
  if (detachingNodeIds.has(model.id)) return;
  detachingNodeIds.add(model.id);
  try {
    await animateNodeToOrphanPool(item, model);
    removeGraphCameraItem(item, model);
    const result = unlinkCameraLocally(model);
    if (!result) {
      ElMessage.error("未找到摄像头资产数据，无法退回待核实池。");
      return;
    }
    await renderGraph();
    await clearCameraBindingRemote(result.cameraNode, result.edge);
  } finally {
    detachingNodeIds.delete(model.id);
  }
}

function handleGlobalKeydown(event) {
  if (event.key !== "Delete") return;
  const targetTag = event.target?.tagName?.toLowerCase();
  if (["input", "textarea", "select"].includes(targetTag) || event.target?.isContentEditable) return;
  const item = selectedCameraItem();
  if (!item) return;
  event.preventDefault();
  detachCameraToOrphanPool(item);
}

function bindGraphEvents() {
  if (!graph) return;
  graph.on("afterlayout", () => {
    syncAllCollapsedGlow();
    scheduleLodVisibility();
  });
  graph.on("viewportchange", scheduleLodVisibility);
  graph.on("wheelzoom", scheduleLodVisibility);
  graph.on("node:click", async (event) => {
    const model = event.item?.getModel();
    if (!model) return;
    if (isCameraBadgeTarget(event.target) && await toggleAccessCameraRing(model)) return;
    selectNode(model);
    activateRelationsForItem(event.item);
  });
  graph.on("canvas:click", () => {
    selectedNodeId.value = "";
    clearRelationStates();
    hideTooltip();
  });
  graph.on("node:contextmenu", (event) => {
    event.originalEvent?.preventDefault?.();
    const model = event.item?.getModel();
    if (!model) return;
    selectNode(model);
    detachCameraToOrphanPool(event.item);
  });
  graph.on("node:mouseenter", (event) => {
    const model = event.item?.getModel();
    if (!model) return;
    placeTooltip(event, "node", model.label || model.nodeKey || model.id, nodeTooltipRows(model));
  });
  graph.on("node:mousemove", (event) => {
    const model = event.item?.getModel();
    if (!model || !hoverTooltip.value.visible) return;
    placeTooltip(event, "node", model.label || model.nodeKey || model.id, nodeTooltipRows(model));
  });
  graph.on("node:mouseleave", () => {
    hideTooltip();
  });

  graph.on("node:dragend", async (event) => {
    if (!editMode.value) return;
    const model = event.item?.getModel();
    if (!model || model.kind === "camera") return;
    const snapped = snapSwitchToPolarOrbit(model, { x: event.x, y: event.y });
    graph.updateItem(event.item, snapped);
    if (model.virtual || model.virtualGroup) return;
    await persistPosition({ ...model, ...snapped }, snapped.x, snapped.y);
  });

  graph.on("edge:mouseenter", (event) => {
    if (!event.item) return;
    event.item.getKeyShape()?.attr({
      stroke: "#67e8f9",
      lineWidth: 3,
      shadowBlur: 14,
      shadowColor: "rgba(103, 232, 249, 0.62)",
    });
    const model = event.item.getModel();
    const tooltip = edgeTooltipRows(model);
    placeTooltip(event, "edge", tooltip.title, tooltip.rows);
  });
  graph.on("edge:mousemove", (event) => {
    if (!event.item || !hoverTooltip.value.visible) return;
    const model = event.item.getModel();
    const tooltip = edgeTooltipRows(model);
    placeTooltip(event, "edge", tooltip.title, tooltip.rows);
  });
  graph.on("edge:mouseleave", (event) => {
    applyEdgeVisualState(event.item);
    hideTooltip();
  });
}

function pointInsideNodeBody(point, model) {
  if (!point || !model) return false;
  const x = Number(model.x);
  const y = Number(model.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
  
  // 接入层交换机宽176，高72。我们放宽判定范围，只要误差在半个节点内就算命中
  const width = 176;
  const height = 72;
  return (
    point.x >= x - width
    && point.x <= x + width
    && point.y >= y - height
    && point.y <= y + height
  );
}

function findDropTargetAccessNode(point) {
  if (!graph || !point) return null;
  let nearestModel = null;
  // 🔥 放宽磁吸距离，手残也能稳稳命中！
  let minDistance = 280; 

  graph.getNodes().forEach((item) => {
    const model = item.getModel?.();
    if (!model || !(isAccessNode(model) || model.isAccess)) return;

    const dx = Number(model.x || 0) - point.x;
    const dy = Number(model.y || 0) - point.y;
    const distance = Math.sqrt(dx * dx + dy * dy);

    if (distance < minDistance) {
      minDistance = distance;
      nearestModel = model;
    }
  });

  return nearestModel;
}

async function attachCameraToSwitch(camera, switchModel) {
  const switchNode = backboneNodes.value.find((node) => node.id === switchModel.id);
  const cameraNode = cameraNodes.value.find((node) => node.id === camera.id);
  if (!switchNode || !cameraNode) {
    ElMessage.error("无法识别摄像头或目标交换机。");
    return;
  }
  try {
    const result = await createArchitectureEdge({
      src_node_key: switchNode.nodeKey || switchNode.id,
      dst_node_key: cameraNode.nodeKey || cameraNode.id,
      source_ip: switchNode.ip,
      target_ip: cameraNode.ip,
      edge_type: "camera",
      evidence_type: "field_verified",
      review_status: "field_verified",
      manual_note: `TopologyEditor 编辑锁模式下挂载到 ${switchNode.label}`,
    });
    cameraNode.parentId = switchNode.id;
    cameraNode.verified = true;
    cameraNode.raw = {
      ...cameraNode.raw,
      parent_node_key: switchNode.nodeKey || switchNode.id,
      review_status: "field_verified",
    };
    edges.value = [
      ...edges.value.filter((edge) => edge.target !== cameraNode.id),
      {
        id: String(result?.edge_id || `edge-camera-${switchNode.id}-${cameraNode.id}`),
        backendId: result?.edge_id || null,
        source: switchNode.id,
        target: cameraNode.id,
        label: "摄像头挂载",
        verified: true,
        raw: result || {},
      },
    ];
    rebuildOrphans();
    selectedNodeId.value = switchNode.id;
    
    // 🔥 只要挂载成功，自动替你点开红色的[+]号！
    expandedAccessIds.value.add(switchNode.id);

    await renderGraph();
    ElMessage.success(`${cameraNode.label || cameraNode.ip} 已自动挂载至 ${switchNode.label}`);
  } catch (error) {
    console.error(error);
    ElMessage.error("摄像头挂载写回失败，请检查节点 ID 或登录权限。");
  }
}

async function persistPosition(model, x, y) {
  if (model.kind === "camera") return;
  try {
    await updateAssetPosition({
      node_id: model.backendId,
      node_key: model.nodeKey || model.id,
      id: model.nodeKey || model.id,
      ip: model.ip,
      device_id: model.deviceId,
      x,
      y,
      manual_note: "TopologyEditor 编辑锁模式下拖拽固化坐标",
    });
    const node = nodes.value.find((item) => item.id === model.id);
    if (node) {
      node.posX = x;
      node.posY = y;
      node.verified = true;
    }
    ElMessage.success(`坐标已同步 (${Math.round(x)}, ${Math.round(y)})`);
  } catch (error) {
    console.error(error);
    ElMessage.error("坐标同步失败，请检查登录态或节点 ID。");
  }
}

function handleDragStart(event, item) {
  if (!editMode.value) {
    event.preventDefault();
    return;
  }
  draggedItem = item;
  event.dataTransfer.setData("text/plain", item.id);
  event.dataTransfer.effectAllowed = "copy";
}

async function handleDrop(event) {
  event.preventDefault();
  if (!draggedItem || !graph) return;
  if (!editMode.value) {
    ElMessage.warning("当前为只读锁定状态，请先启用编辑模式。");
    draggedItem = null;
    return;
  }
  if (draggedItem.kind !== "camera") {
    ElMessage.error("当前拖拽入场只允许失联摄像头绑定到接入交换机。");
    draggedItem = null;
    return;
  }
  const point = graph.getPointByClient(event.clientX, event.clientY);
  const targetSwitch = findDropTargetAccessNode(point);
  if (!targetSwitch) {
    ElMessage.error("必须绑定到接入交换机。请把摄像头准确拖放到接入交换机节点上。");
    draggedItem = null;
    return;
  }
  await attachCameraToSwitch(draggedItem, targetSwitch);
  draggedItem = null;
}

watch(editMode, (newMode) => {
  if (graph) {
    if (newMode) {
      graph.addBehaviors([{ type: "drag-node", enableDelegate: true }], "default");
    } else {
      graph.removeBehaviors("drag-node", "default");
    }
  }
  renderGraph();
});

onMounted(async () => {
  document.addEventListener("keydown", handleGlobalKeydown);
  await loadTopology();
  await renderGraph();
  resizeObserver = new ResizeObserver(() => {
    if (!graph || !graphContainer.value) return;
    if (resizeRenderPending) return;
    resizeRenderPending = true;
    window.requestAnimationFrame(async () => {
      resizeRenderPending = false;
      await renderGraph();
    });
  });
  if (graphContainer.value) resizeObserver.observe(graphContainer.value);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", handleGlobalKeydown);
  detachingNodeIds.clear();
  resizeObserver?.disconnect();
  if (graph) graph.destroy();
  graph = null;
});
</script>

<style scoped>
.topology-editor-wrapper {
  display: flex;
  width: 100%;
  height: calc(100vh - 60px);
  min-height: 680px;
  color: #fff;
  background-color: #0b0f19;
  overflow: hidden;
}

.topology-editor-wrapper.is-editing {
  box-shadow: inset 0 0 0 2px rgba(245, 158, 11, 0.72);
}

.orphan-sidebar {
  width: 310px;
  flex: 0 0 310px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(64, 158, 255, 0.22);
  background:
    radial-gradient(circle at 0 0, rgba(64, 158, 255, 0.12), transparent 32%),
    rgba(15, 21, 34, 0.96);
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid rgba(64, 158, 255, 0.18);
}

.sidebar-header h3 {
  margin: 0;
  color: #409eff;
  font-size: 16px;
}

.subtitle {
  margin: 6px 0 0;
  color: #8892a0;
  font-size: 12px;
  line-height: 1.5;
}

.lock-status {
  display: grid;
  gap: 4px;
  margin: 12px 12px 0;
  padding: 10px;
  border: 1px solid rgba(100, 116, 139, 0.34);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.74);
}

.lock-status strong {
  color: #cbd5e1;
  font-size: 13px;
}

.lock-status span {
  color: #8892a0;
  font-size: 12px;
}

.lock-status.unlocked {
  border-color: rgba(245, 158, 11, 0.72);
  background: rgba(120, 53, 15, 0.36);
}

.lock-status.unlocked strong {
  color: #facc15;
}

.cluster-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  padding: 10px 12px 0;
}

.cluster-pill,
.cluster-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
}

.cluster-pill {
  padding: 5px 6px;
  border: 1px solid rgba(148, 163, 184, 0.22);
}

.cluster-pill.core {
  color: #fecaca;
  background: rgba(127, 29, 29, 0.42);
}

.cluster-pill.south {
  color: #99f6e4;
  background: rgba(20, 83, 75, 0.42);
}

.cluster-pill.north {
  color: #bfdbfe;
  background: rgba(30, 64, 175, 0.32);
}

.orphan-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
}

.orphan-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px;
  margin-bottom: 8px;
  border: 1px dashed rgba(64, 158, 255, 0.32);
  border-radius: 8px;
  background-color: rgba(31, 38, 54, 0.9);
  cursor: grab;
  transition: border-color 0.2s, background-color 0.2s, transform 0.2s, opacity 0.2s;
}

.orphan-item.disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.orphan-item.cluster-south {
  border-color: rgba(45, 212, 191, 0.38);
}

.orphan-item.cluster-north {
  border-color: rgba(147, 197, 253, 0.38);
}

.orphan-item:not(.disabled):hover {
  border-color: #409eff;
  background-color: rgba(38, 48, 69, 0.96);
  transform: translateX(2px);
}

.item-icon {
  width: 36px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: #67e8f9;
  font-size: 18px;
  font-weight: 800;
  background: rgba(64, 158, 255, 0.16);
}

.item-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.item-name {
  color: #f8fbff;
  font-size: 13px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-ip,
.empty-text {
  color: #8892a0;
  font-size: 12px;
}

.cluster-tag {
  min-width: 30px;
  padding: 3px 8px;
  color: #e0f2fe;
  background: rgba(64, 158, 255, 0.18);
}

.canvas-main {
  position: relative;
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 40%, rgba(64, 158, 255, 0.1), transparent 42%),
    linear-gradient(rgba(31, 38, 54, 0.72) 1px, transparent 1px),
    linear-gradient(90deg, rgba(31, 38, 54, 0.72) 1px, transparent 1px),
    #08111f;
  background-size: auto, 24px 24px, 24px 24px, auto;
}

.topology-toolbar {
  position: absolute;
  z-index: 5;
  top: 14px;
  right: 16px;
  left: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 12px;
  border: 1px solid rgba(64, 158, 255, 0.2);
  border-radius: 12px;
  background: rgba(8, 15, 26, 0.78);
  backdrop-filter: blur(12px);
}

.mode-title {
  display: grid;
  gap: 3px;
}

.mode-title strong {
  color: #f8fbff;
  font-size: 14px;
}

.mode-title span,
.selected-hint {
  color: rgba(226, 232, 240, 0.68);
  font-size: 12px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.selected-hint {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.edit-warning {
  position: absolute;
  z-index: 5;
  top: 72px;
  right: 16px;
  padding: 8px 12px;
  border: 1px solid rgba(245, 158, 11, 0.72);
  border-radius: 10px;
  color: #fef3c7;
  background: rgba(120, 53, 15, 0.7);
  box-shadow: 0 0 20px rgba(245, 158, 11, 0.18);
  font-size: 12px;
}

.semantic-tooltip {
  position: absolute;
  z-index: 8;
  min-width: 220px;
  max-width: 320px;
  padding: 12px 13px;
  border: 1px solid rgba(64, 158, 255, 0.3);
  border-radius: 12px;
  color: #e5edf8;
  background: rgba(8, 15, 26, 0.9);
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.42), 0 0 18px rgba(64, 158, 255, 0.12);
  backdrop-filter: blur(12px);
  pointer-events: none;
}

.semantic-tooltip.tooltip-edge {
  border-color: rgba(103, 232, 249, 0.34);
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.42), 0 0 18px rgba(103, 232, 249, 0.16);
}

.semantic-tooltip .tooltip-title {
  display: block;
  margin-bottom: 9px;
  color: #f8fbff;
  font-size: 15px;
  line-height: 1.35;
}

.semantic-tooltip .tooltip-row {
  display: grid;
  grid-template-columns: 68px 1fr;
  gap: 10px;
  align-items: start;
  padding: 4px 0;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.semantic-tooltip .tooltip-key {
  color: #93c5fd;
  font-size: 12px;
  font-weight: 800;
}

.semantic-tooltip .tooltip-value {
  color: #dbeafe;
  font-size: 12px;
  line-height: 1.45;
  word-break: break-word;
}

.legend-overlay {
  position: absolute;
  z-index: 6;
  right: 18px;
  bottom: 18px;
  width: 250px;
  border: 1px solid rgba(64, 158, 255, 0.22);
  border-radius: 14px;
  background: rgba(8, 15, 26, 0.78);
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.34);
  backdrop-filter: blur(14px);
  overflow: hidden;
}

.legend-overlay.collapsed {
  width: auto;
}

.legend-toggle {
  width: 100%;
  border: 0;
  padding: 8px 12px;
  color: #dbeafe;
  background: rgba(64, 158, 255, 0.16);
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.legend-toggle:hover {
  color: #fff;
  background: rgba(64, 158, 255, 0.28);
}

.legend-body {
  display: grid;
  gap: 9px;
  padding: 12px;
}

.legend-body strong {
  color: #f8fbff;
  font-size: 13px;
}

.legend-row {
  display: grid;
  grid-template-columns: 24px 1fr;
  align-items: center;
  gap: 8px;
  color: rgba(226, 232, 240, 0.78);
  font-size: 12px;
}

.legend-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  box-shadow: 0 0 14px currentColor;
}

.legend-dot.core {
  color: #f56c6c;
  background: #f56c6c;
}

.legend-dot.aggregation {
  color: #409eff;
  background: #409eff;
}

.legend-dot.access {
  color: #67c23a;
  background: #67c23a;
}

.legend-flow {
  position: relative;
  width: 32px;
  height: 2px;
  overflow: hidden;
  border-radius: 999px;
  background: repeating-linear-gradient(
    90deg,
    #67e8f9 0 8px,
    transparent 8px 14px
  );
  filter: drop-shadow(0 0 7px rgba(103, 232, 249, 0.7));
  animation: legend-flow 1.1s linear infinite;
}

@keyframes legend-flow {
  from {
    background-position: 0 0;
  }
  to {
    background-position: -28px 0;
  }
}

.g6-container {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  outline: none;
}

:deep(.el-switch__label) {
  color: #cbd5e1;
}

:global(.g6-tooltip) {
  border: 0 !important;
  padding: 0 !important;
  color: inherit !important;
  background: transparent !important;
  box-shadow: none !important;
}

:global(.topology-ghost-card) {
  position: fixed;
  z-index: 9999;
  width: 156px;
  height: 44px;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid rgba(103, 232, 249, 0.72);
  border-radius: 11px;
  color: #f8fbff;
  background: rgba(15, 23, 42, 0.94);
  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.42), 0 0 26px rgba(64, 158, 255, 0.42);
  backdrop-filter: blur(10px);
  pointer-events: none;
  will-change: transform, opacity, filter;
}

:global(.topology-ghost-icon) {
  width: 34px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: #67e8f9;
  font-size: 18px;
  font-weight: 900;
  background: rgba(64, 158, 255, 0.22);
}

:global(.topology-ghost-info) {
  min-width: 0;
  display: grid;
  gap: 2px;
}

:global(.topology-ghost-info strong),
:global(.topology-ghost-info small) {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.topology-ghost-info strong) {
  color: #f8fbff;
  font-size: 12px;
  font-weight: 800;
}

:global(.topology-ghost-info small) {
  color: #93c5fd;
  font-size: 10px;
}

:global(.topology-tooltip) {
  min-width: 220px;
  max-width: 320px;
  padding: 12px 13px;
  border: 1px solid rgba(64, 158, 255, 0.3);
  border-radius: 12px;
  color: #e5edf8;
  background: rgba(8, 15, 26, 0.9);
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.42), 0 0 18px rgba(64, 158, 255, 0.12);
  backdrop-filter: blur(12px);
  pointer-events: none;
}

:global(.topology-tooltip.edge-tooltip) {
  border-color: rgba(103, 232, 249, 0.34);
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.42), 0 0 18px rgba(103, 232, 249, 0.16);
}

:global(.topology-tooltip .tooltip-title) {
  display: block;
  margin-bottom: 9px;
  color: #f8fbff;
  font-size: 15px;
  line-height: 1.35;
}

:global(.topology-tooltip .tooltip-row) {
  display: grid;
  grid-template-columns: 68px 1fr;
  gap: 10px;
  align-items: start;
  padding: 4px 0;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

:global(.topology-tooltip .tooltip-key) {
  color: #93c5fd;
  font-size: 12px;
  font-weight: 800;
}

:global(.topology-tooltip .tooltip-value) {
  color: #dbeafe;
  font-size: 12px;
  line-height: 1.45;
  word-break: break-word;
}
</style>