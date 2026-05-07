<template>
  <section class="topology-workspace">
    <WorkbenchShell>
      <template #title>
        <div class="title-block">
          <p>TOPOLOGY WORKBENCH</p>
          <h2>拓扑归属工作台</h2>
          <span>接入摄像头层、交换机层、2F 汇聚层、光汇聚点统一在一张可核实图里处理。</span>
        </div>
      </template>

      <template #actions>
        <button class="tool-btn" :disabled="busy" @click="loadArchitecture">刷新</button>
        <button class="tool-btn primary" :disabled="busy" @click="rebuildArchitecture">
          {{ busy ? "重算中" : "按数据重建" }}
        </button>
      </template>

      <template #summary>
        <div class="summary-stack">
          <section v-if="routeWorkbenchContext.active" class="context-strip">
            <div class="context-copy">
              <span>资产联动上下文</span>
              <strong>{{ routeWorkbenchContext.title }}</strong>
              <small>{{ routeWorkbenchContext.description }}</small>
            </div>
            <div class="context-actions">
              <button class="mini-btn" @click="returnToAssets">返回资产</button>
              <button class="mini-btn" @click="clearRouteContext">清空联动</button>
            </div>
          </section>
          <section class="summary-strip">
            <article v-for="item in summaryCards" :key="item.label" class="summary-item">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </article>
          </section>
        </div>
      </template>

      <template #roadmap>
        <section class="certainty-map">
          <article class="certainty-node core-node" @click="selectNodeByKey(coreAnchor?.node_key)">
            <span>光汇聚核心</span>
            <strong>{{ coreAnchor?.label || "待识别核心" }}</strong>
            <small>{{ coreAnchor?.ip || "-" }} / 下联 {{ coreAnchor?.downstream_switch_count || 0 }} 台</small>
          </article>
          <div class="certainty-flow">
            <span></span>
          </div>
          <article class="certainty-node aggregation-node">
            <span>2F 汇聚层</span>
            <strong>{{ aggregationBackbone.length }} 台汇聚/级联</strong>
            <small>承载 {{ aggregationCameraCount }} 路摄像头，作为各楼层上联骨架</small>
          </article>
          <div class="certainty-flow">
            <span></span>
          </div>
          <div class="floor-pills" aria-label="楼层拓扑入口">
            <button
              v-for="floor in floorCards"
              :key="`map-${floor.floor}`"
              class="floor-pill"
              :class="{ active: selectedFloor === floor.floor && !selectedRoomKey }"
              @click="selectFloor(floor.floor)"
            >
              <strong>{{ floor.floor }}</strong>
              <span>{{ floor.room_count }} 井</span>
              <small>{{ floor.switch_count }} 台 / {{ floor.camera_count }} 路</small>
            </button>
          </div>
          <article class="certainty-node gap-node" @click="focusGaps">
            <span>待现场补齐</span>
            <strong>{{ missingSwitches.length + unlinkedCameras.length }} 项</strong>
            <small>{{ missingSwitches.length }} 台交换机 / {{ unlinkedCameras.length }} 路摄像头</small>
          </article>
        </section>
      </template>

      <template #left>
      <aside class="floor-navigator">
        <div class="side-head">
          <strong>楼层 / 井位</strong>
          <button class="mini-btn" :class="{ active: !selectedFloor && !selectedRoomKey }" @click="clearScope">全图</button>
        </div>

        <div class="floor-list">
          <section v-for="floor in floorCards" :key="floor.floor" class="floor-group">
            <button
              class="floor-row"
              :class="{ active: selectedFloor === floor.floor && !selectedRoomKey }"
              @click="selectFloor(floor.floor)"
            >
              <strong>{{ floor.floor }}</strong>
              <span>{{ floor.room_count }} 井 / {{ floor.switch_count }} 交换机 / {{ floor.camera_count }} 摄像头</span>
            </button>
            <button
              v-for="room in floor.rooms"
              :key="room.room_key"
              class="room-row"
              :class="{ active: selectedRoomKey === room.room_key }"
              @click="selectRoom(floor.floor, room.room_key)"
            >
              <span>{{ room.room_label }}</span>
              <small>{{ room.switch_count }} 台 / {{ room.camera_count }} 路</small>
            </button>
          </section>
        </div>

        <div class="gap-box">
          <div class="side-head compact">
            <strong>待补齐</strong>
            <div class="compact-actions">
              <button class="mini-btn" :disabled="!missingSwitches.length && !unlinkedCameras.length" @click="exportGapChecklist">
                导出核验表
              </button>
              <button class="mini-btn" :disabled="busy" @click="triggerFieldImport">导入结果</button>
              <input ref="importFileRef" class="hidden-input" type="file" accept=".csv,text/csv" @change="importGapChecklist" />
            </div>
          </div>
          <div class="gap-list">
            <button
              v-for="item in missingSwitches.slice(0, 8)"
              :key="`missing-${item.ip}`"
              class="gap-row"
              @click="prefillNode(item)"
            >
              <strong>{{ item.ip }}</strong>
              <span>{{ item.floor }} / {{ item.room_label || "井位待补" }}</span>
            </button>
            <button
              v-for="item in unlinkedCameras.slice(0, 6)"
              :key="`camera-${item.ip}`"
              class="gap-row camera"
              @click="openAssets(item.ip, 'camera')"
            >
              <strong>{{ item.ip }}</strong>
              <span>摄像头未落链路</span>
            </button>
            <p v-if="!missingSwitches.length && !unlinkedCameras.length" class="empty-text">当前没有明显缺口。</p>
          </div>
        </div>
      </aside>
      </template>

      <template #default>
      <section class="canvas-column">
        <CyberTopologyGraph
          :architecture="architecture"
          :access-nodes="visibleAccessNodes"
          :aggregation-nodes="visibleAggregationNodes"
          :core-anchor="coreAnchor"
          :selected-node-key="selectedNodeKey"
          :scope-title="scopeTitle"
          @select-node-key="selectNodeByKey"
          @select-edge-key="selectedEdgeKey = $event"
          @message="message = $event"
        />

        <article class="result-table-panel">
          <div class="list-toolbar compact">
            <div>
              <p class="eyebrow">RESULT TABLE</p>
              <h3>当前范围结果表</h3>
              <span>先把已经确定的接入交换机结果落成清单，再从这里直接选中、联动资产和现场修改。</span>
            </div>
            <div class="result-stats">
              <span>{{ scopeTitle }} / {{ resultFilterLabel }}</span>
              <strong>{{ filteredResultRows.length }} 台</strong>
            </div>
          </div>

          <div class="result-filter-strip">
            <button class="mini-btn" :class="{ active: resultFilter === 'all' }" @click="resultFilter = 'all'">全部</button>
            <button class="mini-btn" :class="{ active: resultFilter === 'pending' }" @click="resultFilter = 'pending'">只看待核实</button>
            <button class="mini-btn" :class="{ active: resultFilter === 'changed' }" @click="resultFilter = 'changed'">只看现场已变更</button>
            <button class="mini-btn" :class="{ active: resultFilter === 'verified' }" @click="resultFilter = 'verified'">只看现场已核实</button>
          </div>

          <div class="result-table-shell">
            <div class="result-table-head">
              <span>接入交换机</span>
              <span>楼层 / 井位</span>
              <span>上联 / 角色</span>
              <span>摄像头 / 核实</span>
              <span>动作</span>
            </div>

            <button
              v-for="row in filteredResultRows"
              :key="`result-${row.node_key}`"
              class="result-table-row"
              :class="[{ active: selectedNodeKey === row.node_key }, `review-${row.review_status || 'system_built'}`]"
              @click="selectNode(row.node)"
            >
              <span>
                <strong>{{ row.label }}</strong>
                <small>{{ row.ip }}</small>
              </span>
              <span>
                <strong>{{ row.floor || "-" }}</strong>
                <small>{{ row.room_label || "井位待补" }}</small>
              </span>
              <span>
                <strong>{{ row.parent_switch_label || row.parent_switch_ip || "待补上联" }}</strong>
                <small>{{ row.role || "接入交换机" }}</small>
              </span>
              <span>
                <strong>{{ row.camera_count }} 路</strong>
                <small>{{ reviewStatusLabel(row.review_status) }}</small>
              </span>
              <span class="row-actions">
                <button class="mini-btn" @click.stop="selectNode(row.node)">选中</button>
                <button class="mini-btn" @click.stop="quickVerifyRow(row)">核实</button>
                <button class="mini-btn" @click.stop="prepareEdgeFromRow(row)">补链</button>
                <button class="mini-btn" @click.stop="openAssets(row.ip, 'switch')">资产</button>
              </span>
            </button>

            <div v-if="!filteredResultRows.length" class="empty-text table-empty">
              当前范围还没有可落地的接入交换机结果。
            </div>
          </div>
        </article>
      </section>
      </template>

      <template #right>
      <aside class="inspector">
        <div class="side-head">
          <strong>现场核实 / 直接修改</strong>
          <span>{{ selectedNode?.ip || "未选择" }}</span>
        </div>

        <template v-if="selectedNode">
          <section class="editor-section">
          <div class="section-headline">
            <strong>节点修改区</strong>
            <span>先改节点，再决定是否补链</span>
          </div>

          <div class="selected-summary">
            <article class="detail-chip">
              <span>当前节点</span>
              <strong>{{ selectedNode.label }}</strong>
              <small>{{ selectedNode.ip }}</small>
            </article>
            <article class="detail-chip">
              <span>当前状态</span>
              <strong>{{ reviewStatusLabel(selectedNode.review_status) }}</strong>
              <small>{{ selectedNode.role || "接入交换机" }} / {{ selectedNode.floor || "楼层待补" }}</small>
            </article>
            <article class="detail-chip">
              <span>当前位置</span>
              <strong>{{ selectedNode.weak_current_room || "井位待补" }}</strong>
              <small>上联 {{ selectedNode.parent_ip || "待补" }}</small>
            </article>
          </div>

          <label>
            <span>名称</span>
            <input v-model.trim="editForm.label" class="field-input" />
          </label>
          <div class="form-row">
            <label>
              <span>楼层</span>
              <input v-model.trim="editForm.floor" class="field-input" />
            </label>
            <label>
              <span>角色</span>
              <select v-model="editForm.role" class="field-input">
                <option value="光汇聚核心">光汇聚核心</option>
                <option value="楼层主汇聚交换机">楼层主汇聚交换机</option>
                <option value="机房汇聚交换机">机房汇聚交换机</option>
                <option value="接入交换机">接入交换机</option>
                <option value="远距离接入交换机">远距离接入交换机</option>
                <option value="待现场核实">待现场核实</option>
              </select>
            </label>
          </div>
          <label>
            <span>井位 / 位置</span>
            <input v-model.trim="editForm.weak_current_room" class="field-input" />
          </label>
          <label>
            <span>上联 IP</span>
            <input v-model.trim="editForm.parent_ip" class="field-input" />
          </label>
          <label>
            <span>核实状态</span>
            <select v-model="editForm.review_status" class="field-input">
              <option value="system_built">系统计算</option>
              <option value="field_verified">现场已核实</option>
              <option value="needs_field_check">待现场核实</option>
              <option value="changed_in_field">现场已变更</option>
            </select>
          </label>
          <label>
            <span>备注</span>
            <textarea v-model.trim="editForm.manual_note" class="field-input" rows="4" />
          </label>

          <div class="button-row">
            <button class="tool-btn primary" :disabled="busy" @click="saveNode">保存修改</button>
            <button class="tool-btn" @click="openAssets(selectedNode.ip, selectedNode.node_type)">资产联动</button>
            <button class="tool-btn danger" :disabled="busy" @click="removeNode">删除节点</button>
          </div>
          </section>

          <section class="editor-section">
            <div class="section-headline">
              <strong>链路工作区</strong>
              <span>从当前节点补链，或把已有链路装入补录表单继续处理</span>
            </div>

            <div class="button-row">
              <button class="mini-btn" @click="primeEdgeFromSelectedNode">以上联为源补链</button>
              <button class="mini-btn" @click="clearEdgeDraft">清空链路草稿</button>
            </div>

          <div class="edge-list">
            <strong>关联链路</strong>
            <article v-for="edge in selectedEdges" :key="edge.id" class="edge-row">
              <span>{{ nodeLabel(edge.source_node_key) }} -> {{ nodeLabel(edge.target_node_key) }}</span>
              <small>{{ edge.src_port_label || edge.edge_type || "链路" }}</small>
              <div class="row-actions edge-actions">
                <button class="mini-btn" @click="prefillEdge(edge)">装入表单</button>
                <button class="mini-btn danger" :disabled="busy" @click="removeEdge(edge.id)">删除</button>
              </div>
            </article>
            <p v-if="!selectedEdges.length" class="empty-text">暂无关联链路。</p>
          </div>
          </section>
        </template>

        <template v-else>
          <p class="empty-text">点击中间画布上的节点，或从左侧缺口清单选择设备。</p>
        </template>

        <div class="add-panel">
          <div class="section-headline">
            <strong>补录设备区</strong>
            <span>处理缺交换机、缺井位、缺名称</span>
          </div>
          <div class="form-row">
            <input v-model.trim="newNode.ip" class="field-input" placeholder="新设备 IP" />
            <input v-model.trim="newNode.floor" class="field-input" placeholder="楼层" />
          </div>
          <input v-model.trim="newNode.label" class="field-input" placeholder="显示名称" />
          <input v-model.trim="newNode.weak_current_room" class="field-input" placeholder="井位/位置" />
          <div class="button-row">
            <button class="tool-btn" :disabled="busy" @click="addNode">新增设备节点</button>
            <button class="mini-btn" @click="clearNodeDraft">清空设备草稿</button>
          </div>

          <div class="section-headline top-gap">
            <strong>补录链路区</strong>
            <span>处理上联交换机、端口和 VLAN 落地</span>
          </div>
          <div class="form-row">
            <input v-model.trim="newEdge.source_ip" class="field-input" placeholder="上级 IP" />
            <input v-model.trim="newEdge.target_ip" class="field-input" placeholder="下级 IP" />
          </div>
          <input v-model.trim="newEdge.source_port_name" class="field-input" placeholder="端口说明，如 2楼3#井24口" />
          <div class="button-row">
            <button class="tool-btn" :disabled="busy" @click="addEdge">新增链路</button>
            <button class="mini-btn" @click="clearEdgeDraft">清空链路草稿</button>
          </div>
        </div>

        <p class="status-line">{{ message }}</p>
      </aside>
      </template>
    </WorkbenchShell>
  </section>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import WorkbenchShell from "../components/workbench/WorkbenchShell.vue";
import {
  createArchitectureEdge,
  createArchitectureNode,
  deleteArchitectureEdge,
  deleteArchitectureNode,
  fetchCentralAvenueArchitecture,
  rebuildCentralAvenueArchitecture,
  updateArchitectureNode,
} from "../api/client";

const route = useRoute();
const router = useRouter();
const CyberTopologyGraph = defineAsyncComponent(() => import("../components/topology/CyberTopologyGraph.vue"));
const architecture = reactive({
  domain: null,
  summary: { node_count: 0, edge_count: 0, layer_counts: [], review_counts: [] },
  simplified: {
    core_anchor: null,
    aggregation_switches: [],
    floor_cards: [],
    missing_runtime_switches: [],
    unlinked_cameras: [],
    stats: {},
  },
  nodes: [],
  edges: [],
});

const busy = ref(false);
const message = ref("拓扑结果已按楼层和井位重新组织。");
const selectedFloor = ref("");
const selectedRoomKey = ref("");
const selectedNodeKey = ref("");
const selectedEdgeKey = ref("");
const resultFilter = ref("all");
const pan = reactive({ x: 0, y: 0, zoom: 1, dragging: false, lastX: 0, lastY: 0 });
const stageRef = ref(null);
const importFileRef = ref(null);

const editForm = reactive({
  label: "",
  floor: "",
  role: "",
  weak_current_room: "",
  parent_ip: "",
  review_status: "system_built",
  manual_note: "",
});

const newNode = reactive({
  layer: "access",
  ip: "",
  label: "",
  floor: "",
  role: "接入交换机",
  weak_current_room: "",
});

const newEdge = reactive({
  source_ip: "",
  target_ip: "",
  edge_type: "uplink",
  evidence_type: "field_verified",
  source_port_name: "",
  vlan_id: "2",
});

const floorCards = computed(() => architecture.simplified?.floor_cards || []);
const missingSwitches = computed(() => architecture.simplified?.missing_runtime_switches || []);
const unlinkedCameras = computed(() => architecture.simplified?.unlinked_cameras || []);
const coreAnchor = computed(() => architecture.simplified?.core_anchor || null);
const aggregationBackbone = computed(() => architecture.simplified?.aggregation_switches || []);
const aggregationCameraCount = computed(() =>
  aggregationBackbone.value.reduce((total, item) => total + Number(item.downstream_camera_count || item.camera_count || 0), 0),
);

const nodeByKey = computed(() => {
  const map = new Map();
  for (const node of architecture.nodes || []) {
    map.set(node.node_key, node);
    if (node.ip) map.set(`ip:${node.ip}`, node);
  }
  return map;
});

const selectedNode = computed(() => nodeByKey.value.get(selectedNodeKey.value) || null);
const routeWorkbenchContext = computed(() => {
  const query = route.query || {};
  const switchIp = typeof query.switch_ip === "string" ? query.switch_ip.trim() : "";
  if (!switchIp) {
    return { active: false };
  }
  const switchLabel = typeof query.switch_label === "string" ? query.switch_label.trim() : switchIp;
  const fromModule = typeof query.from_module === "string" ? query.from_module.trim() : "";
  const returnDeviceType = query.return_device_type === "switch" ? "switch" : "camera";
  const returnQ = typeof query.return_q === "string" ? query.return_q.trim() : "";
  const focusCameraIp = typeof query.focus_camera_ip === "string" ? query.focus_camera_ip.trim() : "";
  const focusCameraLabel = typeof query.focus_camera_label === "string" ? query.focus_camera_label.trim() : "";
  return {
    active: true,
    switchIp,
    switchLabel,
    fromModule,
    returnDeviceType,
    returnQ,
    focusCameraIp,
    focusCameraLabel,
    title: focusCameraIp
      ? `${focusCameraLabel || focusCameraIp} -> ${switchLabel}`
      : `${switchLabel} 拓扑核实`,
    description: focusCameraIp
      ? `当前从资产页带着摄像头 ${focusCameraIp} 跳入，已优先定位它所属交换机 ${switchIp}。`
      : `当前从资产页带着交换机 ${switchIp} 跳入，可直接做楼层、井位和链路核实。`,
  };
});
const selectedEdges = computed(() => {
  if (!selectedNode.value) return [];
  return (architecture.edges || []).filter(
    (edge) => edge.source_node_key === selectedNode.value.node_key || edge.target_node_key === selectedNode.value.node_key,
  );
});

const summaryCards = computed(() => {
  const stats = architecture.simplified?.stats || {};
  return [
    { label: "拓扑节点", value: architecture.summary.node_count || 0 },
    { label: "链路关系", value: architecture.summary.edge_count || 0 },
    { label: "楼层", value: stats.floor_card_count || floorCards.value.length },
    { label: "2F汇聚", value: stats.aggregation_switch_count || aggregationBackbone.value.length },
    { label: "缺交换机", value: stats.runtime_missing_switch_count || missingSwitches.value.length },
    { label: "未落摄像头", value: stats.unlinked_sheet_camera_count || unlinkedCameras.value.length },
  ];
});

const scopeTitle = computed(() => {
  if (selectedRoomKey.value) return selectedRoomKey.value.replace("-", " ");
  if (selectedFloor.value) return `${selectedFloor.value} 楼层视图`;
  return "中央大道全图";
});

const visibleRooms = computed(() => {
  const rooms = [];
  for (const floor of floorCards.value) {
    if (selectedFloor.value && floor.floor !== selectedFloor.value) continue;
    for (const room of floor.rooms || []) {
      if (selectedRoomKey.value && room.room_key !== selectedRoomKey.value) continue;
      rooms.push({ ...room, floor: floor.floor });
    }
  }
  return rooms;
});

const visibleAccessNodes = computed(() => {
  const rows = [];
  for (const room of visibleRooms.value) {
    for (const item of room.switches || []) {
      const node = nodeByKey.value.get(item.node_key);
      if (!node) continue;
      rows.push({
        ...item,
        node,
        floor: room.floor,
        room_label: room.room_label,
        parent_switch_ip: room.parent_switch_ip,
        parent_switch_label: room.parent_switch_label,
      });
    }
  }
  return rows;
});

const visibleCameraCount = computed(() =>
  visibleAccessNodes.value.reduce((total, item) => total + Number(item.camera_count || 0), 0),
);

const visibleResultRows = computed(() =>
  visibleAccessNodes.value.map((item) => ({
    ...item,
    label: item.node?.label || item.label || item.ip,
    ip: item.node?.ip || item.ip,
    role: item.node?.role || item.role,
    floor: item.node?.floor || item.floor,
    weak_current_room: item.node?.weak_current_room || item.room_label || "",
    review_status: item.node?.review_status || item.review_status || "system_built",
    parent_ip: item.node?.parent_ip || item.parent_switch_ip || "",
  })),
);

const filteredResultRows = computed(() => {
  if (resultFilter.value === "pending") {
    return visibleResultRows.value.filter((item) => (item.review_status || "system_built") === "needs_field_check" || (item.review_status || "system_built") === "system_built");
  }
  if (resultFilter.value === "changed") {
    return visibleResultRows.value.filter((item) => item.review_status === "changed_in_field");
  }
  if (resultFilter.value === "verified") {
    return visibleResultRows.value.filter((item) => item.review_status === "field_verified");
  }
  return visibleResultRows.value;
});

const resultFilterLabel = computed(() => {
  const mapping = {
    all: "全部结果",
    pending: "待核实",
    changed: "现场已变更",
    verified: "现场已核实",
  };
  return mapping[resultFilter.value] || "全部结果";
});

const visibleParentIps = computed(() => {
  const set = new Set();
  for (const item of visibleAccessNodes.value) {
    if (item.parent_switch_ip) set.add(item.parent_switch_ip);
  }
  return set;
});

const visibleAggregationNodes = computed(() => {
  const rows = aggregationBackbone.value.filter((item) => visibleParentIps.value.has(item.ip));
  if (rows.length) return rows;
  if (!selectedFloor.value && !selectedRoomKey.value) return aggregationBackbone.value;
  return [];
});

const canvasHeight = computed(() => Math.max(620, visibleAccessNodes.value.length * 72 + 120, visibleAggregationNodes.value.length * 78 + 120));
const canvasWidth = 1320;
const canvasTransform = computed(() => ({
  transform: `translate(${pan.x}px, ${pan.y}px) scale(${pan.zoom})`,
  transformOrigin: "0 0",
}));

const coreCanvasNode = computed(() => {
  const node = coreAnchor.value ? nodeByKey.value.get(coreAnchor.value.node_key) : null;
  if (!coreAnchor.value || !node) return null;
  return {
    ...coreAnchor.value,
    x: 130,
    y: Math.max(160, canvasHeight.value / 2),
    node,
  };
});

const aggregationCanvasNodes = computed(() =>
  visibleAggregationNodes.value.map((item, index) => ({
    ...item,
    x: 420,
    y: distributeY(index, visibleAggregationNodes.value.length, canvasHeight.value),
    node: nodeByKey.value.get(item.node_key),
  })).filter((item) => item.node),
);

const accessCanvasNodes = computed(() =>
  visibleAccessNodes.value.map((item, index) => ({
    ...item,
    x: 800,
    y: distributeY(index, visibleAccessNodes.value.length, canvasHeight.value),
    node_key: item.node_key,
    review_status: item.review_status,
    node: item.node,
  })),
);

const cameraCanvasNodes = computed(() =>
  accessCanvasNodes.value
    .filter((item) => Number(item.camera_count || 0) > 0)
    .map((item) => ({
      key: `camera-${item.node_key}`,
      x: 1120,
      y: item.y,
      label: item.floor || item.room_label || "摄像头",
      camera_count: item.camera_count,
    })),
);

const canvasEdges = computed(() => {
  const edges = [];
  const aggByIp = new Map(aggregationCanvasNodes.value.map((item) => [item.ip, item]));
  if (coreCanvasNode.value) {
    for (const agg of aggregationCanvasNodes.value) {
      const curveMeta = buildCurve(coreCanvasNode.value.x + 88, coreCanvasNode.value.y, agg.x - 104, agg.y);
      edges.push({
        key: `core-${agg.node_key}`,
        path: curveMeta.path,
        labelX: curveMeta.labelX,
        labelY: curveMeta.labelY,
        labelWidth: 108,
        label: "汇聚上联",
        subLabel: agg.ip || "",
        kind: "core",
        sourceNodeKey: coreCanvasNode.value.node_key,
        targetNodeKey: agg.node_key,
        focusNodeKey: agg.node_key,
      });
    }
  }
  for (const access of accessCanvasNodes.value) {
    const parent = aggByIp.get(access.parent_switch_ip);
    if (parent) {
      const curveMeta = buildCurve(parent.x + 104, parent.y, access.x - 116, access.y);
      edges.push({
        key: `agg-${parent.node_key}-${access.node_key}`,
        path: curveMeta.path,
        labelX: curveMeta.labelX,
        labelY: curveMeta.labelY,
        labelWidth: 126,
        label: "接入上联",
        subLabel: parent.ip || "",
        kind: "uplink",
        sourceNodeKey: parent.node_key,
        targetNodeKey: access.node_key,
        focusNodeKey: access.node_key,
      });
    } else if (coreCanvasNode.value) {
      const curveMeta = buildCurve(coreCanvasNode.value.x + 88, coreCanvasNode.value.y, access.x - 116, access.y);
      edges.push({
        key: `missing-parent-${access.node_key}`,
        warning: true,
        path: curveMeta.path,
        labelX: curveMeta.labelX,
        labelY: curveMeta.labelY,
        labelWidth: 134,
        label: "上联待补",
        subLabel: access.ip || "",
        kind: "uplink",
        sourceNodeKey: coreCanvasNode.value.node_key,
        targetNodeKey: access.node_key,
        focusNodeKey: access.node_key,
      });
    }
    if (Number(access.camera_count || 0) > 0) {
      const curveMeta = buildCurve(access.x + 116, access.y, 1098, access.y);
      edges.push({
        key: `camera-${access.node_key}`,
        path: curveMeta.path,
        labelX: curveMeta.labelX,
        labelY: curveMeta.labelY,
        labelWidth: 118,
        label: `${access.camera_count} 路承载`,
        subLabel: access.room_label || access.floor || "",
        kind: "camera",
        sourceNodeKey: access.node_key,
        targetNodeKey: `camera-${access.node_key}`,
        focusNodeKey: access.node_key,
      });
    }
  }
  return edges;
});

const selectedEdge = computed(() => canvasEdges.value.find((item) => item.key === selectedEdgeKey.value) || null);
const activeEdgeKeys = computed(() => {
  const keys = new Set();
  if (selectedEdge.value) {
    keys.add(selectedEdge.value.key);
    return keys;
  }
  if (!selectedNode.value) return keys;
  for (const edge of canvasEdges.value) {
    if (edge.sourceNodeKey === selectedNode.value.node_key || edge.targetNodeKey === selectedNode.value.node_key) {
      keys.add(edge.key);
    }
  }
  return keys;
});

const highlightedCanvasEdges = computed(() => {
  if (selectedEdge.value) return [selectedEdge.value];
  return canvasEdges.value.filter((item) => activeEdgeKeys.value.has(item.key));
});

function distributeY(index, total, height) {
  if (total <= 1) return Math.max(160, height / 2);
  const top = 92;
  const bottom = height - 92;
  return top + ((bottom - top) / (total - 1)) * index;
}

function buildCurve(x1, y1, x2, y2) {
  const mid = Math.max(90, Math.abs(x2 - x1) * 0.48);
  return {
    path: `M ${x1} ${y1} C ${x1 + mid} ${y1}, ${x2 - mid} ${y2}, ${x2} ${y2}`,
    labelX: (x1 + x2) / 2,
    labelY: (y1 + y2) / 2,
  };
}

function nodeLabel(key) {
  return nodeByKey.value.get(key)?.label || key;
}

function reviewStatusLabel(value) {
  const mapping = {
    system_built: "系统计算",
    field_verified: "现场已核实",
    needs_field_check: "待现场核实",
    changed_in_field: "现场已变更",
  };
  return mapping[value] || value || "待确认";
}

async function quickVerifyRow(row) {
  if (!row?.node) return;
  selectNode(row.node);
  editForm.review_status = "field_verified";
  editForm.manual_note = editForm.manual_note || "结果表快捷核实";
  await saveNode();
}

function prepareEdgeFromRow(row) {
  if (!row) return;
  selectNode(row.node);
  newEdge.source_ip = row.parent_switch_ip || row.parent_ip || "";
  newEdge.target_ip = row.ip || "";
  newEdge.edge_type = "uplink";
  newEdge.evidence_type = "field_verified";
  newEdge.vlan_id = "2";
  newEdge.source_port_name = "";
  message.value = row.parent_switch_ip || row.parent_ip
    ? `已预填 ${row.label} 的补链表单，请补端口后直接新增链路。`
    : `已切到 ${row.label}，但它还没有明确上联 IP，请先现场确认上联再补链。`;
}

function clearScope() {
  selectedFloor.value = "";
  selectedRoomKey.value = "";
}

function selectFloor(floor) {
  selectedFloor.value = floor;
  selectedRoomKey.value = "";
  resetViewport();
}

function selectRoom(floor, roomKey) {
  selectedFloor.value = floor;
  selectedRoomKey.value = roomKey;
  resetViewport();
}

function syncEditForm(node) {
  editForm.label = node?.label || "";
  editForm.floor = node?.floor || "";
  editForm.role = node?.role || "";
  editForm.weak_current_room = node?.weak_current_room || "";
  editForm.parent_ip = node?.parent_ip || "";
  editForm.review_status = node?.review_status || "system_built";
  editForm.manual_note = node?.manual_note || "";
}

function selectNode(node) {
  if (!node) return;
  selectedNodeKey.value = node.node_key;
  selectedEdgeKey.value = "";
  syncEditForm(node);
}

function selectEdge(edge) {
  if (!edge) return;
  if (edge.focusNodeKey) {
    const node = nodeByKey.value.get(edge.focusNodeKey);
    if (node) {
      selectedNodeKey.value = node.node_key;
      syncEditForm(node);
    }
  }
  selectedEdgeKey.value = edge.key;
}

function shouldMuteEdge(edgeKey) {
  return activeEdgeKeys.value.size > 0 && !activeEdgeKeys.value.has(edgeKey);
}

function selectNodeByKey(nodeKey) {
  if (!nodeKey) return;
  const node = nodeByKey.value.get(nodeKey);
  if (node) selectNode(node);
}

function applyScopeFromNode(node) {
  if (!node) return;
  for (const floor of floorCards.value) {
    for (const room of floor.rooms || []) {
      const matched = (room.switches || []).some((item) => item.node_key === node.node_key || item.ip === node.ip);
      if (matched) {
        selectedFloor.value = floor.floor;
        selectedRoomKey.value = room.room_key;
        resetViewport();
        return;
      }
    }
  }
  selectedFloor.value = node.floor || "";
  selectedRoomKey.value = "";
  resetViewport();
}

function focusNodeByIp(ip, { silent = false } = {}) {
  if (!ip) return false;
  const node = nodeByKey.value.get(`ip:${ip}`);
  if (node) {
    applyScopeFromNode(node);
    selectNode(node);
    if (!silent) {
      message.value = `已定位交换机 ${ip}，可以直接在当前楼层视图继续核实。`;
    }
    return true;
  }
  const missing = missingSwitches.value.find((item) => String(item.ip || "").trim() === String(ip).trim());
  if (missing) {
    selectedFloor.value = missing.floor || "";
    selectedRoomKey.value = "";
    prefillNode(missing);
    resetViewport();
    if (!silent) {
      message.value = `交换机 ${ip} 还未正式进入拓扑节点，已把它放入右侧补录区。`;
    }
    return true;
  }
  return false;
}

function focusGaps() {
  selectedFloor.value = "";
  selectedRoomKey.value = "";
  if (missingSwitches.value.length) {
    prefillNode(missingSwitches.value[0]);
  } else if (unlinkedCameras.value.length) {
    message.value = `还有 ${unlinkedCameras.value.length} 路摄像头没有物理链路，请从左侧清单进入资产核验。`;
  } else {
    message.value = "当前没有明显缺口。";
  }
}

function csvCell(value) {
  const text = String(value ?? "").replaceAll('"', '""');
  return `"${text}"`;
}

function exportGapChecklist() {
  const rows = [
    ["类型", "IP", "楼层", "井位/区域", "系统判断", "现场核实结果", "正确上联交换机IP", "正确端口", "备注"],
  ];
  for (const item of missingSwitches.value) {
    rows.push([
      "缺失交换机",
      item.ip || "",
      item.floor || "",
      item.room_label || "",
      item.role || "待补录交换机",
      "",
      "",
      "",
      "请现场确认该交换机是否存在、所在井位、上联交换机和端口。",
    ]);
  }
  for (const item of unlinkedCameras.value) {
    rows.push([
      "未落链路摄像头",
      item.ip || "",
      item.floor || "",
      item.area || item.room_label || "",
      "摄像头资产存在，但物理交换机/端口未归属",
      "",
      "",
      "",
      "请现场确认摄像头接入交换机、端口和实际位置。",
    ]);
  }
  const csv = `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10).replaceAll("-", "");
  link.href = url;
  link.download = `中央大道拓扑现场核验_${stamp}.csv`;
  link.click();
  URL.revokeObjectURL(url);
  message.value = `已导出 ${missingSwitches.value.length + unlinkedCameras.value.length} 项现场核验清单。`;
}

function triggerFieldImport() {
  importFileRef.value?.click();
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  const source = text.replace(/^\uFEFF/, "");
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      index += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") index += 1;
      row.push(cell);
      if (row.some((value) => String(value).trim())) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  row.push(cell);
  if (row.some((value) => String(value).trim())) rows.push(row);
  return rows;
}

function rowValue(row, headerMap, name) {
  const index = headerMap.get(name);
  return index === undefined ? "" : String(row[index] || "").trim();
}

async function importGapChecklist(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  busy.value = true;
  try {
    const text = await file.text();
    const rows = parseCsv(text);
    const headers = rows.shift() || [];
    const headerMap = new Map(headers.map((name, index) => [String(name).trim(), index]));
    let nodeCount = 0;
    let edgeCount = 0;
    let skipped = 0;
    for (const row of rows) {
      const type = rowValue(row, headerMap, "类型");
      const ip = rowValue(row, headerMap, "IP");
      const floor = rowValue(row, headerMap, "楼层");
      const room = rowValue(row, headerMap, "井位/区域");
      const reviewResult = rowValue(row, headerMap, "现场核实结果") || "现场已核实";
      const parentIp = rowValue(row, headerMap, "正确上联交换机IP");
      const port = rowValue(row, headerMap, "正确端口");
      const note = rowValue(row, headerMap, "备注");
      if (!ip) {
        skipped += 1;
        continue;
      }
      const isCamera = type.includes("摄像头");
      try {
        await createArchitectureNode({
          ip,
          label: ip,
          layer: isCamera ? "terminal" : "access",
          node_type: isCamera ? "camera" : "switch",
          floor,
          weak_current_room: room,
          parent_ip: parentIp,
          role: isCamera ? "摄像头点位" : "接入交换机",
          review_status: "field_verified",
          manual_note: [reviewResult, note].filter(Boolean).join("；"),
        });
        nodeCount += 1;
        if (parentIp) {
          await createArchitectureEdge({
            source_ip: parentIp,
            target_ip: ip,
            edge_type: isCamera ? "camera_access" : "uplink",
            evidence_type: "field_verified",
            source_port_name: port,
            vlan_id: "2",
            review_status: "field_verified",
            manual_note: [reviewResult, note].filter(Boolean).join("；"),
          });
          edgeCount += 1;
        }
      } catch (rowError) {
        console.warn("field import row skipped", rowError);
        skipped += 1;
      }
    }
    await loadArchitecture();
    message.value = `现场核验结果已导入：更新/新增 ${nodeCount} 个节点，补链 ${edgeCount} 条，跳过 ${skipped} 行。`;
  } catch (error) {
    console.error(error);
    message.value = "现场核验表导入失败，请确认 CSV 表头没有被修改。";
  } finally {
    busy.value = false;
  }
}

function prefillNode(item) {
  newNode.ip = item.ip || "";
  newNode.label = item.label || item.ip || "";
  newNode.floor = item.floor || "";
  newNode.role = item.role || "接入交换机";
  newNode.weak_current_room = item.room_label || "";
  message.value = `已把 ${item.ip} 放到补录表单。`;
}

function clearNodeDraft() {
  newNode.ip = "";
  newNode.label = "";
  newNode.floor = "";
  newNode.role = "接入交换机";
  newNode.weak_current_room = "";
}

function clearEdgeDraft() {
  newEdge.source_ip = "";
  newEdge.target_ip = "";
  newEdge.edge_type = "uplink";
  newEdge.evidence_type = "field_verified";
  newEdge.source_port_name = "";
  newEdge.vlan_id = "2";
}

function prefillEdge(edge) {
  const sourceNode = nodeByKey.value.get(edge.source_node_key);
  const targetNode = nodeByKey.value.get(edge.target_node_key);
  newEdge.source_ip = sourceNode?.ip || "";
  newEdge.target_ip = targetNode?.ip || "";
  newEdge.edge_type = edge.edge_type || "uplink";
  newEdge.evidence_type = edge.evidence_type || "field_verified";
  newEdge.source_port_name = edge.src_port_label || "";
  newEdge.vlan_id = edge.vlan_id || "2";
  message.value = "已把当前链路装入补录表单，可直接修端口或重新补链。";
}

function primeEdgeFromSelectedNode() {
  if (!selectedNode.value) return;
  newEdge.source_ip = selectedNode.value.parent_ip || "";
  newEdge.target_ip = selectedNode.value.ip || "";
  newEdge.edge_type = "uplink";
  newEdge.evidence_type = "field_verified";
  newEdge.vlan_id = "2";
  if (newEdge.source_ip) {
    message.value = `已按 ${selectedNode.value.label} 预填上联补链草稿，请补端口说明后保存。`;
  } else {
    message.value = `当前节点还没有上联 IP，请先现场确认 ${selectedNode.value.label} 的上联交换机。`;
  }
}

function openAssets(ip, type = "switch") {
  if (!ip) return;
  router.push({ path: "/assets", query: { device_type: type === "camera" ? "camera" : "switch", q: ip } });
}

async function syncRouteContext({ silent = false } = {}) {
  if (!routeWorkbenchContext.value.active) return;
  const focused = focusNodeByIp(routeWorkbenchContext.value.switchIp, { silent: true });
  if (!focused && routeWorkbenchContext.value.focusCameraIp) {
    const gapCamera = unlinkedCameras.value.find((item) => String(item.ip || "").trim() === routeWorkbenchContext.value.focusCameraIp);
    if (gapCamera?.floor) {
      selectedFloor.value = gapCamera.floor;
      selectedRoomKey.value = "";
      resetViewport();
    }
  }
  if (!silent) {
    message.value = focused
      ? `已从资产页联动到 ${routeWorkbenchContext.value.switchLabel}，可继续做拓扑核实。`
      : `已带入 ${routeWorkbenchContext.value.switchIp} 的联动上下文，但当前拓扑里还没完全命中，可在右侧补录或左侧缺口区继续处理。`;
  }
}

function clearRouteContext() {
  const nextQuery = { ...route.query };
  delete nextQuery.switch_ip;
  delete nextQuery.switch_label;
  delete nextQuery.from_module;
  delete nextQuery.return_device_type;
  delete nextQuery.return_q;
  delete nextQuery.focus_camera_ip;
  delete nextQuery.focus_camera_label;
  router.replace({ path: route.path, query: nextQuery });
  message.value = "已清空资产联动上下文。";
}

function returnToAssets() {
  const context = routeWorkbenchContext.value;
  if (!context.active) {
    router.push({ path: "/assets" });
    return;
  }
  router.push({
    path: "/assets",
    query: {
      device_type: context.returnDeviceType === "switch" ? "switch" : "camera",
      q: context.returnQ || context.focusCameraIp || context.switchIp,
    },
  });
}

async function loadArchitecture() {
  busy.value = true;
  try {
    const payload = await fetchCentralAvenueArchitecture();
    Object.assign(architecture, payload);
    if (!selectedNodeKey.value && payload.simplified?.core_anchor?.node_key) {
      selectNode(payload.nodes.find((item) => item.node_key === payload.simplified.core_anchor.node_key));
    } else if (selectedNodeKey.value) {
      syncEditForm(payload.nodes.find((item) => item.node_key === selectedNodeKey.value));
    }
    await syncRouteContext({ silent: true });
    message.value = routeWorkbenchContext.value.active
      ? `已联动到 ${routeWorkbenchContext.value.switchLabel} 的拓扑工作台。`
      : "拓扑数据已刷新。";
  } catch (error) {
    console.error(error);
    message.value = "拓扑数据加载失败，请检查后台服务。";
  } finally {
    busy.value = false;
  }
}

async function rebuildArchitecture() {
  busy.value = true;
  message.value = "正在按交换机表、摄像头表和运行库重建拓扑...";
  try {
    await rebuildCentralAvenueArchitecture();
    await loadArchitecture();
    message.value = "重建完成，人工核实项会继续保留。";
  } catch (error) {
    console.error(error);
    message.value = "重建失败，请查看后台日志。";
  } finally {
    busy.value = false;
  }
}

async function saveNode() {
  if (!selectedNode.value) return;
  busy.value = true;
  try {
    const result = await updateArchitectureNode(selectedNode.value.id, { ...editForm });
    if (result.architecture) Object.assign(architecture, result.architecture);
    await loadArchitecture();
    message.value = "现场修订已保存。";
  } catch (error) {
    console.error(error);
    message.value = "保存失败，请检查节点是否存在。";
  } finally {
    busy.value = false;
  }
}

async function removeNode() {
  if (!selectedNode.value) return;
  busy.value = true;
  try {
    const result = await deleteArchitectureNode(selectedNode.value.id);
    if (result.architecture) Object.assign(architecture, result.architecture);
    selectedNodeKey.value = "";
    await loadArchitecture();
    message.value = "节点已删除。源数据仍存在时，后续重建会重新生成。";
  } catch (error) {
    console.error(error);
    message.value = "删除节点失败。";
  } finally {
    busy.value = false;
  }
}

async function addNode() {
  if (!newNode.ip && !newNode.label) {
    message.value = "新增设备至少需要 IP 或名称。";
    return;
  }
  busy.value = true;
  try {
    const result = await createArchitectureNode({ ...newNode });
    if (result.architecture) Object.assign(architecture, result.architecture);
    await loadArchitecture();
    const created = architecture.nodes.find((item) => item.id === result.node_id || item.node_key === result.node_key);
    if (created) selectNode(created);
    clearNodeDraft();
    message.value = "设备节点已补录。";
  } catch (error) {
    console.error(error);
    message.value = "新增设备失败。";
  } finally {
    busy.value = false;
  }
}

async function addEdge() {
  if (!newEdge.source_ip || !newEdge.target_ip) {
    message.value = "新增链路需要上级 IP 和下级 IP。";
    return;
  }
  busy.value = true;
  try {
    const result = await createArchitectureEdge({ ...newEdge });
    if (result.architecture) Object.assign(architecture, result.architecture);
    await loadArchitecture();
    clearEdgeDraft();
    message.value = "链路已补录。";
  } catch (error) {
    console.error(error);
    message.value = "新增链路失败，请确认两个节点已存在。";
  } finally {
    busy.value = false;
  }
}

async function removeEdge(edgeId) {
  busy.value = true;
  try {
    const result = await deleteArchitectureEdge(edgeId);
    if (result.architecture) Object.assign(architecture, result.architecture);
    await loadArchitecture();
    message.value = "链路已删除。";
  } catch (error) {
    console.error(error);
    message.value = "删除链路失败。";
  } finally {
    busy.value = false;
  }
}

function resetViewport() {
  pan.x = 0;
  pan.y = 0;
  pan.zoom = 1;
}

function zoomIn() {
  pan.zoom = Math.min(1.8, Number((pan.zoom + 0.12).toFixed(2)));
}

function zoomOut() {
  pan.zoom = Math.max(0.55, Number((pan.zoom - 0.12).toFixed(2)));
}

function onWheel(event) {
  const delta = event.deltaY > 0 ? -0.08 : 0.08;
  pan.zoom = Math.min(1.8, Math.max(0.55, Number((pan.zoom + delta).toFixed(2))));
}

function startPan(event) {
  pan.dragging = true;
  pan.lastX = event.clientX;
  pan.lastY = event.clientY;
}

function movePan(event) {
  if (!pan.dragging) return;
  pan.x += event.clientX - pan.lastX;
  pan.y += event.clientY - pan.lastY;
  pan.lastX = event.clientX;
  pan.lastY = event.clientY;
}

function stopPan() {
  pan.dragging = false;
}

watch(() => route.fullPath, () => {
  syncRouteContext();
});

onMounted(loadArchitecture);
</script>

<style scoped>
.topology-workspace {
  min-height: 100%;
  padding: 22px;
  color: #e8f3ff;
  background:
    linear-gradient(135deg, rgba(8, 17, 28, 0.96), rgba(9, 34, 41, 0.94)),
    #07131f;
}

.workspace-toolbar,
.summary-strip,
.certainty-map,
.topology-shell {
  max-width: 1880px;
  margin: 0 auto;
}

.workspace-toolbar {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 16px;
  align-items: end;
  margin-bottom: 14px;
}

.title-block {
  display: grid;
  gap: 4px;
}

.title-block p {
  margin: 0;
  color: #70c8e8;
  font-size: 0.72rem;
  font-weight: 700;
}

.title-block h2 {
  margin: 0;
  font-size: 1.52rem;
}

.title-block span,
.scope-text span,
.side-head span,
.edge-row small,
.status-line,
.empty-text {
  color: rgba(221, 236, 249, 0.68);
}

.toolbar-actions,
.button-row,
.canvas-tools,
.form-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.summary-stack {
  display: grid;
  gap: 10px;
}

.context-strip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(117, 202, 244, 0.18);
  border-radius: 10px;
  background:
    radial-gradient(circle at 100% 0%, rgba(99, 197, 255, 0.12), transparent 32%),
    linear-gradient(135deg, rgba(10, 34, 52, 0.82), rgba(7, 24, 38, 0.9));
}

.context-copy {
  display: grid;
  gap: 4px;
}

.context-copy span,
.context-copy small {
  color: rgba(221, 236, 249, 0.68);
}

.context-copy strong {
  color: #f4fbff;
  font-size: 1rem;
}

.context-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}

.summary-item {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid rgba(117, 202, 244, 0.16);
  border-radius: 8px;
  background: rgba(9, 29, 44, 0.72);
}

.summary-item span {
  color: rgba(221, 236, 249, 0.68);
  font-size: 0.78rem;
}

.summary-item strong {
  font-size: 1.18rem;
}

.certainty-map {
  display: grid;
  grid-template-columns: 230px 54px 250px 54px minmax(360px, 1fr) 190px;
  gap: 10px;
  align-items: stretch;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid rgba(108, 230, 189, 0.18);
  border-radius: 12px;
  background:
    radial-gradient(circle at 12% 20%, rgba(108, 230, 189, 0.14), transparent 26%),
    radial-gradient(circle at 80% 10%, rgba(99, 197, 255, 0.12), transparent 32%),
    rgba(5, 20, 31, 0.82);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.02);
}

.certainty-node,
.floor-pill {
  border: 1px solid rgba(117, 202, 244, 0.18);
  background: rgba(10, 34, 52, 0.74);
  color: inherit;
  border-radius: 10px;
}

.certainty-node {
  display: grid;
  gap: 6px;
  align-content: center;
  padding: 12px;
  cursor: pointer;
}

.certainty-node span,
.certainty-node small,
.floor-pill span,
.floor-pill small {
  color: rgba(221, 236, 249, 0.68);
  font-size: 0.76rem;
}

.certainty-node strong {
  font-size: 0.98rem;
  line-height: 1.3;
}

.core-node {
  border-color: rgba(108, 230, 189, 0.32);
  background: linear-gradient(135deg, rgba(14, 78, 70, 0.74), rgba(9, 38, 54, 0.76));
}

.aggregation-node {
  border-color: rgba(99, 197, 255, 0.26);
  background: linear-gradient(135deg, rgba(14, 52, 82, 0.78), rgba(9, 35, 54, 0.72));
}

.gap-node {
  border-color: rgba(247, 185, 85, 0.34);
  background: linear-gradient(135deg, rgba(90, 62, 22, 0.54), rgba(45, 30, 18, 0.64));
}

.certainty-flow {
  position: relative;
  min-height: 76px;
}

.certainty-flow::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, rgba(108, 230, 189, 0.12), rgba(99, 197, 255, 0.72));
}

.certainty-flow span {
  position: absolute;
  top: calc(50% - 5px);
  right: 0;
  width: 10px;
  height: 10px;
  border-top: 2px solid rgba(99, 197, 255, 0.78);
  border-right: 2px solid rgba(99, 197, 255, 0.78);
  transform: rotate(45deg);
}

.floor-pills {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
}

.floor-pill {
  display: grid;
  gap: 4px;
  padding: 10px;
  text-align: left;
  cursor: pointer;
}

.floor-pill strong {
  font-size: 1rem;
}

.floor-pill.active {
  border-color: rgba(108, 230, 189, 0.48);
  background: rgba(31, 90, 92, 0.56);
}

.topology-shell {
  display: grid;
  grid-template-columns: 292px minmax(680px, 1fr) 340px;
  gap: 12px;
  align-items: stretch;
  min-height: calc(100vh - 166px);
}

.floor-navigator,
.canvas-column,
.inspector {
  min-height: 0;
  border: 1px solid rgba(117, 202, 244, 0.14);
  border-radius: 8px;
  background: rgba(7, 23, 36, 0.78);
}

.floor-navigator,
.inspector {
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 12px;
  overflow: auto;
}

.side-head,
.canvas-toolbar,
.floor-stage-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.compact-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.hidden-input {
  display: none;
}

.side-head.compact {
  padding-top: 6px;
  border-top: 1px solid rgba(117, 202, 244, 0.12);
}

.floor-list,
.gap-list,
.edge-list,
.add-panel {
  display: grid;
  gap: 8px;
}

.floor-group {
  display: grid;
  gap: 4px;
}

.floor-row,
.room-row,
.gap-row,
.tool-btn,
.mini-btn {
  border: 1px solid rgba(117, 202, 244, 0.14);
  background: rgba(12, 34, 50, 0.76);
  color: inherit;
  border-radius: 8px;
  cursor: pointer;
}

.floor-row,
.room-row,
.gap-row {
  width: 100%;
  display: grid;
  gap: 3px;
  padding: 9px 10px;
  text-align: left;
}

.room-row {
  margin-left: 10px;
  width: calc(100% - 10px);
  background: rgba(8, 27, 42, 0.62);
}

.floor-row.active,
.room-row.active,
.mini-btn.active {
  border-color: rgba(108, 230, 189, 0.42);
  background: rgba(31, 90, 92, 0.56);
}

.floor-row span,
.room-row small,
.gap-row span {
  color: rgba(221, 236, 249, 0.68);
  font-size: 0.78rem;
}

.tool-btn,
.mini-btn {
  padding: 8px 12px;
  font-size: 0.86rem;
}

.mini-btn {
  padding: 5px 9px;
  font-size: 0.78rem;
}

.tool-btn.primary {
  border-color: rgba(108, 230, 189, 0.4);
  background: linear-gradient(135deg, rgba(46, 146, 156, 0.85), rgba(78, 158, 98, 0.74));
}

.tool-btn.danger,
.mini-btn.danger {
  border-color: rgba(245, 112, 112, 0.34);
  color: #ffb9b9;
}

.canvas-column {
  display: grid;
  grid-template-rows: auto 1fr auto;
  overflow: hidden;
}

.canvas-toolbar {
  padding: 12px;
  border-bottom: 1px solid rgba(117, 202, 244, 0.12);
}

.scope-text {
  display: grid;
  gap: 3px;
}

.result-table-panel {
  border-top: 1px solid rgba(117, 202, 244, 0.12);
  padding: 12px;
  display: grid;
  gap: 10px;
  background: rgba(5, 17, 29, 0.92);
}

.list-toolbar.compact {
  align-items: end;
}

.result-stats {
  display: grid;
  gap: 4px;
  text-align: right;
}

.result-stats span {
  color: rgba(221, 236, 249, 0.62);
  font-size: 0.78rem;
}

.result-stats strong {
  color: #f4fbff;
  font-size: 1.12rem;
}

.result-table-shell {
  display: grid;
  gap: 8px;
}

.result-filter-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.result-table-head,
.result-table-row {
  display: grid;
  grid-template-columns: minmax(170px, 1.25fr) minmax(140px, 1fr) minmax(170px, 1.2fr) minmax(120px, 0.85fr) auto;
  gap: 12px;
  align-items: center;
}

.result-table-head {
  padding: 0 12px;
  color: rgba(221, 236, 249, 0.58);
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.result-table-row {
  width: 100%;
  text-align: left;
  padding: 12px;
  border: 1px solid rgba(117, 202, 244, 0.12);
  border-radius: 10px;
  background: rgba(9, 27, 42, 0.68);
  color: inherit;
  cursor: pointer;
}

.result-table-row.active {
  border-color: rgba(255, 222, 120, 0.58);
  background: linear-gradient(180deg, rgba(40, 80, 100, 0.74), rgba(18, 43, 61, 0.7));
}

.result-table-row.review-field_verified {
  border-color: rgba(108, 230, 189, 0.24);
}

.result-table-row.review-changed_in_field {
  border-color: rgba(247, 185, 85, 0.3);
}

.result-table-row.review-needs_field_check,
.result-table-row.review-system_built {
  border-color: rgba(117, 202, 244, 0.12);
}

.result-table-row span {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.result-table-row strong {
  color: #f4fbff;
}

.result-table-row small {
  color: rgba(221, 236, 249, 0.66);
  overflow-wrap: anywhere;
}

.row-actions {
  display: flex !important;
  align-items: center;
  gap: 6px;
  justify-content: flex-end;
}

.table-empty {
  padding: 8px 12px 2px;
}

.topology-stage {
  position: relative;
  overflow: hidden;
  cursor: grab;
  background:
    linear-gradient(rgba(117, 202, 244, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(117, 202, 244, 0.05) 1px, transparent 1px),
    rgba(3, 13, 24, 0.84);
  background-size: 32px 32px;
}

.topology-stage:active {
  cursor: grabbing;
}

.topology-canvas {
  width: 100%;
  min-height: 100%;
  transition: transform 120ms ease;
}

.lane-labels text {
  fill: rgba(221, 236, 249, 0.52);
  font-size: 14px;
  font-weight: 700;
}

.canvas-edge {
  fill: none;
  stroke: url(#workbenchLink);
  stroke-width: 2;
  opacity: 0.82;
  transition: opacity 140ms ease, stroke-width 140ms ease, filter 140ms ease;
  pointer-events: stroke;
}

.canvas-edge.warning {
  stroke: url(#workbenchWarn);
  stroke-dasharray: 7 7;
}

.canvas-edge.uplink {
  stroke-dasharray: 10 10;
  animation: topologyFlow 11s linear infinite;
}

.canvas-edge.camera {
  stroke-dasharray: 7 9;
  animation: topologyFlow 8.4s linear infinite;
}

.canvas-edge.active {
  opacity: 1;
  stroke-width: 4;
  filter: drop-shadow(0 0 10px rgba(97, 209, 255, 0.48));
}

.canvas-edge.active.warning {
  filter: drop-shadow(0 0 10px rgba(242, 95, 92, 0.4));
}

.canvas-edge.muted {
  opacity: 0.18;
}

.edge-focus-group {
  cursor: pointer;
}

.edge-focus-dot {
  fill: #8de6ff;
  stroke: rgba(255, 255, 255, 0.9);
  stroke-width: 1.2;
  filter: drop-shadow(0 0 10px rgba(107, 224, 255, 0.52));
}

.edge-label rect {
  fill: rgba(4, 15, 24, 0.92);
  stroke: rgba(141, 230, 255, 0.48);
  stroke-width: 1;
}

.edge-label-title {
  fill: #eefbff;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.edge-label-sub {
  fill: rgba(221, 236, 249, 0.74);
  font-size: 10px;
}

.canvas-node rect {
  stroke: rgba(117, 202, 244, 0.24);
  fill: rgba(13, 43, 66, 0.92);
}

.canvas-node.core rect {
  stroke: rgba(108, 230, 189, 0.38);
  fill: rgba(18, 70, 63, 0.94);
}

.canvas-node.aggregation rect {
  fill: rgba(18, 53, 80, 0.94);
}

.canvas-node.access.review rect {
  stroke: rgba(247, 185, 85, 0.5);
}

.canvas-node.active rect {
  stroke: rgba(255, 222, 120, 0.8);
  stroke-width: 2;
}

.node-title {
  fill: #f5fbff;
  font-size: 13px;
  font-weight: 800;
}

.node-sub {
  fill: rgba(221, 236, 249, 0.66);
  font-size: 11px;
}

.camera-rollup circle {
  fill: rgba(108, 230, 189, 0.42);
  stroke: rgba(108, 230, 189, 0.62);
}

.camera-rollup text {
  fill: rgba(237, 250, 255, 0.88);
  font-size: 12px;
  font-weight: 700;
}

@keyframes topologyFlow {
  from {
    stroke-dashoffset: 0;
  }
  to {
    stroke-dashoffset: -64;
  }
}

.stage-empty {
  position: absolute;
  left: 18px;
  bottom: 18px;
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 8px;
  background: rgba(4, 15, 24, 0.78);
}

.selected-summary {
  display: grid;
  gap: 8px;
  margin-bottom: 10px;
}

.editor-section {
  display: grid;
  gap: 10px;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid rgba(117, 202, 244, 0.1);
}

.editor-section:last-of-type {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.section-headline {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.section-headline strong {
  color: #f4fbff;
}

.section-headline span {
  color: rgba(221, 236, 249, 0.62);
  font-size: 0.76rem;
  text-align: right;
}

.edge-actions {
  justify-content: flex-start;
}

.detail-chip {
  display: grid;
  gap: 4px;
  padding: 10px;
  border: 1px solid rgba(117, 202, 244, 0.12);
  border-radius: 8px;
  background: rgba(9, 27, 42, 0.64);
}

.detail-chip span {
  color: rgba(221, 236, 249, 0.62);
  font-size: 0.74rem;
}

.detail-chip strong {
  color: #f4fbff;
}

.detail-chip small {
  color: rgba(221, 236, 249, 0.66);
}

.inspector label,
.add-panel {
  display: grid;
  gap: 6px;
}

.inspector label span {
  color: rgba(221, 236, 249, 0.68);
  font-size: 0.78rem;
}

.field-input {
  width: 100%;
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid rgba(117, 202, 244, 0.14);
  border-radius: 8px;
  background: rgba(2, 12, 22, 0.68);
  color: #eef8ff;
  outline: none;
}

.form-row > * {
  flex: 1;
}

.edge-row {
  display: grid;
  gap: 5px;
  padding: 9px;
  border: 1px solid rgba(117, 202, 244, 0.12);
  border-radius: 8px;
  background: rgba(9, 27, 42, 0.64);
}

.add-panel {
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px solid rgba(117, 202, 244, 0.12);
}

.status-line {
  margin: 0;
  line-height: 1.6;
}

@media (max-width: 1280px) {
  .certainty-map {
    grid-template-columns: 1fr;
  }

  .context-strip {
    align-items: flex-start;
  }

  .certainty-flow {
    display: none;
  }

  .floor-pills {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .topology-shell {
    grid-template-columns: 260px minmax(520px, 1fr);
  }

  .inspector {
    grid-column: 1 / -1;
  }

  .summary-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .result-table-head,
  .result-table-row {
    grid-template-columns: minmax(150px, 1.2fr) minmax(120px, 1fr) minmax(150px, 1.1fr) minmax(110px, 0.8fr) auto;
  }
}

@media (max-width: 820px) {
  .topology-workspace {
    padding: 12px;
  }

  .workspace-toolbar,
  .topology-shell {
    grid-template-columns: 1fr;
  }

  .context-strip {
    flex-direction: column;
    align-items: stretch;
  }

  .summary-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .floor-pills {
    grid-template-columns: 1fr;
  }

  .topology-stage {
    min-height: 520px;
  }

  .result-table-head {
    display: none;
  }

  .result-table-row {
    grid-template-columns: 1fr;
  }

  .row-actions {
    justify-content: flex-start;
  }

  .toolbar-actions,
  .canvas-toolbar,
  .button-row {
    align-items: stretch;
    flex-wrap: wrap;
  }
}
</style>
