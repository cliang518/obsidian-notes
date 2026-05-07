<template>
  <div class="topology-editor-wrapper" :class="{ 'is-editing': editMode }">
    <aside class="orphan-sidebar" :class="{ collapsed: leftDrawerCollapsed }">
      <button
        class="orphan-drawer-toggle"
        type="button"
        :aria-label="leftDrawerCollapsed ? '展开待核实资产列表' : '收起待核实资产列表'"
        @click.stop="leftDrawerCollapsed = !leftDrawerCollapsed"
      >
        {{ leftDrawerCollapsed ? "›" : "‹" }}
      </button>
      <div class="sidebar-header">
        <h3>待核实资产 ({{ orphanList.length }})</h3>
        <p class="subtitle">编辑模式开启后，可拖拽失联摄像头到目标交换机下重新建链。</p>
      </div>

      <div class="lock-status" :class="{ unlocked: editMode }">
        <strong>{{ editMode ? "编辑模式已启用" : "只读锁定中" }}</strong>
        <span>{{ editMode ? "允许拖拽、保存坐标、挂载失联点位" : "仅允许缩放、平移、展开和查看节点" }}</span>
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
          @click.stop="jumpToOrphanNode(item)"
          @dragstart="handleDragStart($event, item)"
        >
          <div class="item-icon">CAM</div>
          <div class="item-info">
            <span class="item-name">{{ item.displayText || item.id }}</span>
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
      @dragover="handleDragOver"
      @dragleave="clearDragVisuals"
    >
      <div class="hud-capsule">
        <div class="cyber-hud-bar">
          <div class="hud-section">
            <span class="hud-label">态势模式</span>
            <strong class="hud-value">{{ currentViewMode || "全局大盘视图" }}</strong>
          </div>
          <div class="hud-divider"></div>
          <div class="hud-section ticker-section">
            <span class="ticker-dot"></span>
            <span class="ticker-text">{{ currentMessage.text || "系统运行中..." }}</span>
          </div>
          <div class="hud-divider"></div>

          <div class="hud-search-box">
            <input
              v-model="searchQuery"
              type="text"
              placeholder="输入 IP / 名称雷达直达..."
              @keyup.enter="handleSearch"
            />
            <button class="search-btn" type="button" @click="handleSearch">🎯 锁定</button>
          </div>
          <div class="hud-divider"></div>

          <div class="hud-section stats-section">
            <span class="stat-online">在线: {{ realOnlineCount }}</span>
            <span
              class="stat-offline clickable pulse"
              title="点击开启离线设备自动巡航"
              @click.stop="findNextOffline"
            >
              离线: {{ realOfflineCount }} ⚡
            </span>
          </div>
          <div class="hud-divider"></div>
          <el-switch
            v-model="editMode"
            inline-prompt
            size="small"
            active-text="编辑"
            inactive-text="锁定"
            active-color="#f59e0b"
            inactive-color="#64748b"
          />
        </div>
      </div>

      <div v-if="editMode" class="edit-warning">
        编辑模式已解锁：节点拖动和失联点位挂载会写回数据库，请确认现场核实后操作。
      </div>

      <div ref="graphContainer" class="g6-container"></div>

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

    <aside
      class="detail-sidebar"
      :class="{ open: showDetailPanel && selectedNodeDetail }"
      :aria-hidden="!(showDetailPanel && selectedNodeDetail)"
    >
      <div class="detail-header">
        <div>
          <strong>节点详情</strong>
          <span>{{ selectedNodeDetailLoading ? "正在同步后端详情" : selectedNodeDetail ? "已联动选中节点" : "等待选择节点" }}</span>
        </div>
        <button
          class="detail-close"
          type="button"
          aria-label="关闭节点详情"
          @click.stop="resetSelectedNodeState"
        >
          ×
        </button>
      </div>
      <template v-if="selectedNodeDetail">
        <div class="detail-title">
          <strong>{{ selectedNodeDetail.model.displayText || selectedNodeDetail.model.id }}</strong>
          <span>{{ nodeTypeLabel(selectedNodeDetail.model) }}</span>
        </div>
        <div class="detail-grid">
          <div v-for="row in selectedNodeDetailRows" :key="row.label" class="detail-row">
            <span>{{ row.label }}</span>
            <strong>{{ row.value || "-" }}</strong>
          </div>
        </div>

        <!-- 🔥 新增：编辑状态下的链路/设备情报录入表单 -->
        <div v-if="editMode && selectedNodeDetail" class="detail-action-zone">
          <div v-if="selectedNodeDetail.model.kind === 'link'" class="edit-form-container">
            <div class="edit-form-group">
              <label>本端接口 (Src Port)</label>
              <input v-model="selectedNodeDetail.raw.src_port_label" class="hud-input" placeholder="例: G1/0/24" />
            </div>
            <div class="edit-form-group">
              <label>对端接口 (Dst Port)</label>
              <input v-model="selectedNodeDetail.raw.dst_port_label" class="hud-input" placeholder="例: G1/0/1" />
            </div>
            <div class="edit-form-group">
              <label>透传 VLAN</label>
              <input v-model="selectedNodeDetail.raw.vlan" class="hud-input" placeholder="例: 100" />
            </div>
          </div>
          <div v-else class="edit-form-container">
             <div class="edit-form-group">
              <label>现场位置/变更备注</label>
              <input v-model="selectedNodeDetail.raw.manual_note" class="hud-input" placeholder="例: 师傅已将设备移至A侧桥架" />
            </div>
          </div>
          <button
            class="verify-action-btn"
            :class="{ 'is-update': selectedNodeDetail.model.verified }"
            type="button"
            @click.stop="verifyCurrentSelection"
          >
            {{ selectedNodeDetail.model.verified ? '💾 更新情报并落盘' : ('✅ 现场核实确认' + (selectedNodeDetail.model.kind === 'link' ? '连线' : '设备') + '无误') }}
          </button>
        </div>
        <div v-if="selectedNodeDetail.error" class="detail-warning">
          {{ selectedNodeDetail.error }}
        </div>
      </template>
      <p v-else class="detail-empty">点击拓扑节点后，这里会显示设备厂商、型号、安装时间与链路归属字段。</p>
    </aside>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import G6 from "@antv/g6";
import { ElMessage } from "element-plus";
import { useRoute } from "vue-router";
import {
  clearAssetTopologyBinding,
  createArchitectureEdge,
  deleteArchitectureEdge,
  fetchDeviceDetail,
  fetchCentralAvenueArchitecture,
  updateAssetPosition,
} from "../../api/client";

const route = useRoute();
const graphContainer = ref(null);
const editMode = ref(false);
const topologyPayload = ref(null);
const nodes = ref([]);
const edges = ref([]);
const renderedGraphNodes = ref([]);
const orphanList = ref([]);
const selectedNodeId = ref("");
const selectedNodeDetail = ref(null);
const selectedNodeDetailLoading = ref(false);
const showDetailPanel = ref(false);
const legendCollapsed = ref(false);
const leftDrawerCollapsed = ref(false);
const currentViewMode = ref("全局大盘视图");
const offlineDropdownOpen = ref(false);
const messages = ref([
  { id: 1, type: "alarm", text: "10:02 核心机房A CPU负载突增过80%" },
  { id: 2, type: "workorder", text: "10:05 弱电组张工已接单：排查3F断网问题" },
  { id: 3, type: "asset", text: "10:08 资产嗅探：1F 2#井 发现新MAC接入" },
]);
const currentMsgIndex = ref(0);
const expandedAccessIds = ref(new Set());
const currentGraphics = ref(localStorage.getItem("YJ_GRAPHICS") || "medium");

let graph = null;
let resizeObserver = null;
let draggedItem = null;
let msgTimer = null;
const detachingNodeIds = new Set();
let customElementsRegistered = false;

function handleGraphicsChanged(event) {
  currentGraphics.value = event?.detail || "medium";
  if (!graph) return;
  graph.getNodes?.().forEach((node) => {
    node.clearCache?.();
    graph.updateItem?.(node, node.getModel?.() || {});
  });
  graph.getEdges?.().forEach((edge) => {
    edge.clearCache?.();
    graph.updateItem?.(edge, edge.getModel?.() || {});
  });
  if (typeof graph.paint === "function") {
    graph.paint();
  } else {
    graph.refresh?.();
  }
}

const GRID_SIZE = 24;
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
const STARBURST_CAMERA_RADIUS = 50;

const NORTH_CAMS = new Set(["10.0.59.199", "10.0.56.2", "10.0.56.3", "10.0.56.4", "10.0.56.5", "10.0.56.6", "10.0.56.7", "10.0.56.8", "10.0.56.9", "10.0.56.10", "10.0.56.12", "10.0.56.13", "10.0.56.14", "10.0.56.15", "10.0.56.16", "10.0.56.17", "10.0.56.18", "10.0.56.19", "10.0.56.20", "10.0.56.21", "10.0.56.22", "10.0.56.23", "10.0.56.24", "10.0.56.25", "10.0.56.26", "10.0.56.27", "10.0.56.28", "10.0.56.30", "10.0.56.31", "10.0.56.32", "10.0.56.33", "10.0.56.34", "10.0.56.35", "10.0.56.36", "10.0.56.37", "10.0.56.39", "10.0.56.40", "10.0.56.41", "10.0.56.42", "10.0.56.43", "10.0.56.44", "10.0.56.45", "10.0.56.46", "10.0.56.47", "10.0.56.48", "10.0.56.49", "10.0.56.50", "10.0.56.51", "10.0.56.52", "10.0.56.53", "10.0.56.54", "10.0.56.55", "10.0.56.57", "10.0.56.58", "10.0.56.59", "10.0.56.60", "10.0.59.198", "10.0.56.64", "10.0.56.65", "10.0.56.66", "10.0.56.68", "10.0.56.69", "10.0.56.70", "10.0.56.72", "10.0.56.73", "10.0.56.74", "10.0.56.75", "10.0.56.77", "10.0.56.78", "10.0.56.79", "10.0.56.80", "10.0.56.81", "10.0.56.82", "10.0.56.83", "10.0.56.85", "10.0.56.86", "10.0.56.87", "10.0.56.88", "10.0.56.89", "10.0.56.90", "10.0.56.91", "10.0.56.92", "10.0.56.93", "10.0.56.94", "10.0.56.95", "10.0.56.96", "10.0.56.97", "10.0.56.98", "10.0.56.99", "10.0.56.100", "10.0.56.101", "10.0.56.102", "10.0.56.103", "10.0.56.104", "10.0.56.106", "10.0.56.107", "10.0.56.108", "10.0.56.109", "10.0.56.110", "10.0.56.111", "10.0.56.112", "10.0.56.113", "10.0.56.114", "10.0.56.115", "10.0.56.116", "10.0.56.117", "10.0.56.118", "10.0.56.119", "10.0.56.120", "10.0.56.121", "10.0.56.122", "10.0.56.123", "10.0.56.124", "10.0.56.125", "10.0.56.126", "10.0.56.212", "10.0.56.130", "10.0.56.131", "10.0.56.133", "10.0.56.193", "10.0.56.194", "10.0.56.197", "10.0.56.198", "10.0.56.199", "10.0.56.200", "10.0.56.201", "10.0.56.202", "10.0.56.203", "10.0.56.204", "10.0.56.205", "10.0.56.206", "10.0.56.208", "10.0.56.209", "10.0.56.210", "10.0.56.211", "10.0.56.213", "10.0.56.214", "10.0.56.215", "10.0.56.216", "10.0.56.217", "10.0.56.218", "10.0.56.219", "10.0.56.221", "10.0.56.222", "10.0.56.223", "10.0.56.224", "10.0.56.225", "10.0.56.226", "10.0.56.227", "10.0.56.228", "10.0.56.229", "10.0.56.230", "10.0.56.231", "10.0.56.232", "10.0.56.233", "10.0.56.234", "10.0.56.235", "10.0.56.236", "10.0.56.237", "10.0.56.238", "10.0.56.239", "10.0.56.240", "10.0.56.241", "10.0.56.243", "10.0.56.244", "10.0.56.245", "10.0.56.246", "10.0.56.247", "10.0.56.248", "10.0.56.249", "10.0.56.250", "10.0.56.251", "10.0.56.252", "10.0.56.253", "10.0.56.254", "10.0.57.1", "10.0.57.2", "10.0.57.3", "10.0.57.4", "10.0.57.5", "10.0.57.17", "10.0.57.37", "10.0.57.73", "10.0.57.74", "10.0.57.75", "10.0.57.76", "10.0.57.77", "10.0.57.78", "10.0.57.79", "10.0.57.80", "10.0.57.81", "10.0.57.82", "10.0.57.83", "10.0.57.84", "10.0.57.85", "10.0.57.86", "10.0.57.88", "10.0.57.89", "10.0.57.90", "10.0.57.91", "10.0.57.92", "10.0.57.93", "10.0.57.94", "10.0.57.95", "10.0.57.96", "10.0.57.97", "10.0.57.98", "10.0.57.99", "10.0.57.100", "10.0.57.102", "10.0.57.103", "10.0.57.104", "10.0.57.105", "10.0.57.106", "10.0.57.107", "10.0.57.108", "10.0.57.109", "10.0.57.110", "10.0.57.111", "10.0.57.112", "10.0.57.113", "10.0.57.115", "10.0.57.116", "10.0.57.117", "10.0.57.118", "10.0.57.119", "10.0.57.120", "10.0.57.121", "10.0.57.122", "10.0.57.123", "10.0.57.124", "10.0.57.125", "10.0.57.186", "10.0.57.187", "10.0.57.188", "10.0.57.189", "10.0.57.190", "10.0.57.191", "10.0.57.192", "10.0.57.193", "10.0.57.194", "10.0.57.195", "10.0.57.196", "10.0.57.197", "10.0.57.198", "10.0.57.199", "10.0.57.200", "10.0.57.201", "10.0.57.202", "10.0.57.203", "10.0.57.204", "10.0.57.205", "10.0.57.206", "10.0.57.207", "10.0.57.208", "10.0.57.209", "10.0.57.210", "10.0.57.211", "10.0.57.212", "10.0.57.213", "10.0.57.214", "10.0.56.29", "10.0.57.216", "10.0.56.61", "10.0.57.219", "10.0.57.220", "10.0.57.221", "10.0.57.222", "10.0.57.223", "10.0.57.224", "10.0.57.225", "10.0.57.226", "10.0.57.227", "10.0.57.228", "10.0.57.229", "10.0.57.230", "10.0.58.17", "10.0.58.18", "10.0.58.19", "10.0.58.20", "10.0.58.23", "10.0.58.25", "10.0.58.9", "10.0.58.87", "10.0.58.88", "10.0.58.89", "10.0.58.90", "10.0.58.92", "10.0.58.93", "10.0.58.94", "10.0.58.95", "10.0.58.104", "10.0.58.128", "10.0.59.30", "10.0.59.31", "10.0.59.32", "10.0.59.33", "10.0.59.34", "10.0.59.35", "10.0.59.36", "10.0.59.37", "10.0.59.38", "10.0.59.41", "10.0.59.42", "10.0.59.43", "10.0.59.44", "10.0.59.45", "10.0.59.46", "10.0.59.47", "10.0.59.48", "10.0.59.50", "10.0.58.115", "10.0.58.116", "10.0.58.117", "10.0.58.118", "10.0.58.119", "10.0.58.122", "10.0.58.123", "10.0.56.76", "10.0.56.84"]);

const SOUTH_CAMS = new Set(["10.0.56.127", "10.0.56.134", "10.0.56.135", "10.0.56.136", "10.0.56.137", "10.0.56.140", "10.0.56.141", "10.0.56.142", "10.0.56.143", "10.0.56.144", "10.0.56.145", "10.0.56.146", "10.0.56.147", "10.0.56.148", "10.0.56.149", "10.0.56.150", "10.0.56.151", "10.0.56.152", "10.0.56.153", "10.0.56.154", "10.0.56.155", "10.0.56.156", "10.0.56.157", "10.0.56.158", "10.0.56.159", "10.0.56.160", "10.0.56.161", "10.0.56.162", "10.0.56.163", "10.0.56.164", "10.0.56.165", "10.0.56.166", "10.0.56.167", "10.0.56.168", "10.0.56.169", "10.0.56.170", "10.0.56.171", "10.0.56.172", "10.0.56.173", "10.0.56.174", "10.0.56.175", "10.0.56.176", "10.0.56.177", "10.0.56.178", "10.0.56.179", "10.0.56.180", "10.0.56.181", "10.0.56.182", "10.0.56.183", "10.0.56.184", "10.0.56.185", "10.0.56.186", "10.0.56.188", "10.0.56.189", "10.0.56.190", "10.0.56.191", "10.0.56.196", "10.0.57.6", "10.0.57.7", "10.0.57.9", "10.0.57.12", "10.0.57.13", "10.0.57.14", "10.0.57.16", "10.0.57.18", "10.0.57.19", "10.0.57.20", "10.0.57.21", "10.0.57.22", "10.0.57.23", "10.0.57.24", "10.0.57.25", "10.0.57.26", "10.0.57.27", "10.0.57.28", "10.0.57.29", "10.0.57.30", "10.0.57.31", "10.0.57.32", "10.0.57.33", "10.0.57.34", "10.0.57.35", "10.0.57.36", "10.0.57.38", "10.0.57.39", "10.0.57.40", "10.0.57.41", "10.0.57.42", "10.0.57.43", "10.0.57.44", "10.0.57.45", "10.0.57.46", "10.0.57.47", "10.0.57.48", "10.0.57.49", "10.0.57.50", "10.0.57.51", "10.0.57.52", "10.0.57.53", "10.0.57.54", "10.0.57.55", "10.0.57.56", "10.0.57.57", "10.0.57.58", "10.0.57.59", "10.0.57.60", "10.0.57.61", "10.0.57.62", "10.0.57.64", "10.0.57.65", "10.0.57.66", "10.0.57.67", "10.0.57.68", "10.0.57.72", "10.0.57.126", "10.0.57.127", "10.0.57.128", "10.0.57.129", "10.0.57.130", "10.0.57.131", "10.0.57.132", "10.0.57.134", "10.0.57.135", "10.0.57.136", "10.0.57.137", "10.0.57.138", "10.0.57.139", "10.0.57.140", "10.0.57.141", "10.0.57.142", "10.0.57.143", "10.0.57.144", "10.0.57.145", "10.0.57.146", "10.0.57.147", "10.0.57.148", "10.0.57.149", "10.0.57.150", "10.0.57.151", "10.0.57.152", "10.0.57.153", "10.0.57.154", "10.0.57.155", "10.0.57.156", "10.0.57.157", "10.0.57.158", "10.0.57.159", "10.0.57.160", "10.0.57.161", "10.0.57.162", "10.0.57.163", "10.0.57.164", "10.0.57.165", "10.0.57.166", "10.0.57.167", "10.0.57.168", "10.0.57.169", "10.0.57.170", "10.0.57.171", "10.0.57.172", "10.0.57.173", "10.0.57.174", "10.0.57.175", "10.0.57.176", "10.0.57.177", "10.0.57.178", "10.0.57.179", "10.0.57.180", "10.0.57.181", "10.0.57.182", "10.0.57.183", "10.0.57.184", "10.0.57.185", "10.0.57.233", "10.0.57.234", "10.0.57.235", "10.0.57.236", "10.0.57.237", "10.0.57.238", "10.0.57.239", "10.0.57.240", "10.0.57.241", "10.0.57.242", "10.0.57.243", "10.0.57.244", "10.0.57.245", "10.0.57.246", "10.0.57.247", "10.0.57.249", "10.0.57.252", "10.0.57.253", "10.0.57.254", "10.0.58.1", "10.0.58.80", "10.0.58.82", "10.0.58.84", "10.0.58.85", "10.0.59.39", "10.0.59.49", "10.0.59.51", "10.0.59.52", "10.0.58.105", "10.0.58.109", "10.0.58.110", "10.0.58.112", "10.0.58.120", "10.0.58.121", "10.0.58.124"]);

// 🔥 核心重构：废除 label，防止 G6 底层生成黑影
const LOD_TEXT_SHAPES = new Set([
  "displayText", 
  "meta",
  "tier-mark",
  "camera-label",
  "camera-meta",
  "camera-badge-text",
]);
const LOD_DETAIL_SHAPES = new Set([
  ...LOD_TEXT_SHAPES,
  "camera-icon",
  "camera-icon-bg",
  "camera-badge",
  "collapse-marker",
  "collapse-marker-text",
  "verified-dot",
]);
const LOD_BODY_SHAPES = new Set(["shell", "camera-shell", "camera-dot"]);

const backboneNodes = computed(() => nodes.value.filter((item) => item.kind !== "camera"));
const cameraNodes = computed(() => nodes.value.filter((item) => item.kind === "camera"));

const toolbarHint = computed(() => (
  editMode.value
    ? "编辑锁已打开，允许拖动节点和挂载失联摄像头。"
    : "默认收起接入交换机下属摄像头，点击节点展开或收起。"
));

const selectedNodeLabel = computed(() => {
  const node = nodes.value.find((item) => item.id === selectedNodeId.value);
  return node ? `已选：${node.displayText}` : "未选择节点";
});

const clusterStats = computed(() => ({
  core: backboneNodes.value.filter((item) => item.cluster === "core").length,
  south: backboneNodes.value.filter((item) => item.cluster === "south").length,
  north: backboneNodes.value.filter((item) => item.cluster === "north").length,
}));

const offlineNodes = computed(() => renderedGraphNodes.value.filter((node) => node.status === "offline"));

const nocHudStats = computed(() => {
  const visibleNodes = renderedGraphNodes.value.filter((item) => !item.virtual);
  const offline = offlineNodes.value.length;
  return {
    online: Math.max(visibleNodes.length - offline, 0),
    offline,
  };
});

const hudModeLabel = computed(() => (currentViewMode.value.includes("➔") ? "聚焦模式" : "态势模式"));
const hudModeValue = computed(() => {
  if (!currentViewMode.value.includes("➔")) return currentViewMode.value;
  return currentViewMode.value.split("➔").pop()?.trim() || currentViewMode.value;
});

const currentMessage = computed(() => messages.value[currentMsgIndex.value] || messages.value[0]);

// ==========================================
// 核心雷达狙击系统 & 真实数据绑定
// ==========================================
const realOnlineCount = computed(() => nodes.value.filter((node) => (
  node.status !== "offline" && node.status !== "unknown"
)).length);
const realOfflineCount = computed(() => nodes.value.filter((node) => node.status === "offline").length);
const searchQuery = ref("");

async function executeJump(targetKey) {
  const rawTarget = Array.isArray(targetKey) ? targetKey[0] : targetKey;
  const keyword = normalizeText(rawTarget);
  if (!keyword || !graph) return false;

  const aliasMap = buildAliasMap();
  const targetId = resolveNodeId(keyword, aliasMap) || keyword;
  const targetNode = nodes.value.find((node) => (
    node.id === targetId
    || node.ip === keyword
    || node.nodeKey === keyword
    || (node.displayText && node.displayText.includes(keyword))
  ));

  if (!targetNode) {
    ElMessage.warning(`雷达未扫描到目标：[${keyword}]`);
    return false;
  }

  if (orphanList.value.some((item) => item.id === targetNode.id)) {
    jumpToOrphanNode(targetNode);
    return true;
  }

  if (targetNode.kind === "camera") {
    const parentId = cameraParentId(targetNode);
    if (parentId && !expandedAccessIds.value.has(parentId)) {
      const parentModel = nodes.value.find((node) => node.id === parentId);
      if (parentModel) await toggleAccessCameraRing(parentModel);
    }
  }

  selectNode(targetNode);
  showDetailPanel.value = true;
  currentViewMode.value = `雷达锁定 ➔ ${targetNode.displayText || targetNode.ip || targetNode.id}`;

  const graphItem = graph.findById(targetNode.id);
  if (graphItem) {
    graph.focusItem(graphItem, true, { easing: "easeCubic", duration: 800 });
    window.setTimeout(() => triggerNeonRadar(targetNode.id), 820);
  } else {
    ElMessage.warning(`目标已选中，但当前画布未渲染实体坐标：[${keyword}]`);
  }
  return true;
}

function handleSearch() {
  const keyword = searchQuery.value.trim();
  if (!keyword) return;
  executeJump(keyword);
}

let offlineCruiseIndex = 0;
function findNextOffline() {
  const offlines = nodes.value.filter((node) => node.status === "offline");
  if (offlines.length === 0) {
    ElMessage.success("全网运行良好，无离线设备！");
    return;
  }
  const target = offlines[offlineCruiseIndex % offlines.length];
  offlineCruiseIndex += 1;
  ElMessage.info(`追踪第 ${offlineCruiseIndex} 个离线设备...`);
  executeJump(target.ip || target.id);
}

const selectedNodeDetailRows = computed(() => {
  const detail = selectedNodeDetail.value;
  if (!detail) return [];
  const model = detail.model || {};
  const raw = detail.raw || {};
  const device = detail.device || {};
  return [
    { label: "厂商", value: firstDetailValue(device.vendor, raw.vendor, raw.Vendor, raw.manufacturer, raw.Manufacturer, raw.brand) },
    { label: "型号", value: firstDetailValue(device.model, raw.model, raw.Model, raw.device_model, raw.deviceModel, raw.model_name) },
    { label: "安装时间", value: firstDetailValue(device.installed_at, device.install_time, device.install_date, device.created_at, raw.installed_at, raw.install_time, raw.install_date, raw.installation_time, raw.created_at) },
    { label: "管理 IP", value: firstDetailValue(device.management_ip, device.service_ip, model.ip, raw.ip, raw.IP) },
    { label: "序列号", value: firstDetailValue(device.serial_number, raw.serial_number, raw.sn, raw.SN) },
    { label: "MAC", value: firstDetailValue(device.mac_address, raw.mac_address, raw.mac, raw.MAC) },
    { label: "区域", value: firstDetailValue(device.area_display_name, raw.weak_current_room, raw.room_label, raw.floor, model.cluster ? clusterLabel(model.cluster) : "") },
    { label: "状态", value: firstDetailValue(device.device_status, device.health_state, nodeStatusText(model)) },
    { label: "数据来源", value: firstDetailValue(device.primary_source_type, raw.source_type, raw.position_source) },
  ];
});

function normalizeText(value) {
  return String(value || "").trim();
}

function firstDetailValue(...values) {
  for (const value of values) {
    const text = normalizeText(value);
    if (text) return text;
  }
  return "-";
}

function compactNodeLabel(value) {
  const text = normalizeText(value);
  return text.length > 8 ? `${text.slice(0, 8)}...` : text;
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

function nodeTypeLabel(node) {
  if (node.kind === "camera") return "摄像头终端";
  if (node.kind === "junction") return "分线盒";
  if (node.kind === "unmanaged") return "无网管交换机";
  if (node.tier === "core") return "核心机房设备";
  if (node.tier === "aggregation") return "汇聚层设备";
  return "接入层设备";
}

function messageTypeLabel(type) {
  if (type === "alarm") return "[告警]";
  if (type === "workorder") return "[工单]";
  if (type === "asset") return "[资产]";
  return "[消息]";
}

function nodeStatusText(node) {
  const rawStatus = normalizeText(
    node.status
      || node.raw?.status
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

function isOfflineNode(node) {
  return /离线|失联|故障|offline|down|异常/i.test(nodeStatusText(node));
}

function jumpToOfflineNode(node) {
  offlineDropdownOpen.value = false;
  if (!graph || !node?.id) return;
  if (!graph.findById(node.id)) return;
  currentViewMode.value = `微观聚焦 ➔ ${node.displayText || node.nodeKey || node.id}`;
  graph.focusItem(node.id, true, { easing: "easeCubic", duration: 600 });
}

function jumpToOrphanNode(item) {
  if (!item?.id || !graph) return;
  resetSelectedNodeState();

  // 1. 强制无条件先选中并弹窗，绝不允许被 return 阻断！
  selectNode(item);
  showDetailPanel.value = true;

  // 2. 根据图上是否有真实坐标，决定镜头动作
  const graphItem = graph.findById(item.id);
  if (graphItem) {
    currentViewMode.value = `聚焦模式 ➔ ${item.label || item.nodeKey || item.id}`;
    if (typeof applySmartNoiseFilter === "function") applySmartNoiseFilter();
    enforcePhaseIsolation();
    graph.focusItem(item.id, true, { easing: "easeCubic", duration: 600 });
    window.setTimeout(() => { triggerNeonRadar(item.id); }, 620);
  } else {
    currentViewMode.value = "全局大盘视图";
    enforcePhaseIsolation();
    graph.paint();
    
    // 3. 动态文案提示
    if (editMode.value) {
      ElMessage.success("资产详情已就绪！您现在可以直接【按住该项拖拽】到画布中的交换机上进行挂载。");
    } else {
      ElMessage.warning("已展开详情。此设备暂无物理坐标，如需挂载建链，请先解锁上方【编辑模式】。");
    }
  }
}

function classifyBuilding(node) {
  // 🛡️ 核心战略 1：【物理真理字典裁决】(使用最高优先级)
  // 场景 A：当前节点就是摄像头本体，直接验明正身
  if (node.kind === "camera" && node.ip) {
    if (NORTH_CAMS.has(node.ip)) return "north";
    if (SOUTH_CAMS.has(node.ip)) return "south";
  }
  
  // 场景 B：当前节点是交换机，提取底下的“样本摄像头”进行真理投票
  const sampleIps = node.raw?.camera_sample_ips;
  if (Array.isArray(sampleIps) && sampleIps.length > 0) {
    let northVotes = 0;
    let southVotes = 0;
    for (const ip of sampleIps) {
      if (NORTH_CAMS.has(ip)) northVotes++;
      else if (SOUTH_CAMS.has(ip)) southVotes++;
    }
    // 票数对决：摄像头在哪，爹就在哪！
    if (northVotes > southVotes) return "north";
    if (southVotes > northVotes) return "south";
  }

  // 🛡️ 核心战略 2：【后端大数据统计兜底】(真理字典无票时，相信大数据的区域统计)
  if (node.raw?.camera_area_breakdown && Array.isArray(node.raw.camera_area_breakdown)) {
    let northVotes = 0;
    let southVotes = 0;
    node.raw.camera_area_breakdown.forEach(item => {
      const areaText = String(item.area || "").toUpperCase();
      const count = Number(item.count || 0);
      if (/北楼|北区|北侧|北门|北通道|NORTH|(^|[\s_\-#])N($|[\s_\-#])|N区/.test(areaText)) northVotes += count;
      else if (/南楼|南区|南侧|南门|南通道|SOUTH|(^|[\s_\-#])S($|[\s_\-#])|S区/.test(areaText)) southVotes += count;
    });
    if (northVotes > southVotes) return "north";
    if (southVotes > northVotes) return "south";
  }

  // 🛡️ 核心战略 3：【自身文本特征降维匹配】
  const textTokens = [
    node.displayText, node.id, node.nodeKey, node.layer, node.kind,
    node.raw?.asset_label, node.raw?.Name, node.raw?.weak_current_room,
    node.raw?.room_label, node.raw?.floor, node.raw?.Physical_Pos?.Area,
    node.raw?.Physical_Pos?.Raw_Address, node.raw?.Physical_Pos?.Install_Pos,
  ];
  const text = textTokens.filter(Boolean).join(" ").toUpperCase();
  if (node.kind === "core" || /核心|机房|CORE|CENTER|CENTRAL/.test(text)) return "core";
  if (/南楼|南区|南侧|南门|南通道|SOUTH|(^|[\s_\-#])S($|[\s_\-#])|S区/.test(text)) return "south";
  if (/北楼|北区|北侧|北门|北通道|NORTH|(^|[\s_\-#])N($|[\s_\-#])|N区/.test(text)) return "north";

  // 🛡️ 核心战略 4：【哈希绝对防爆散列】(彻底废除 IP 单双算命，仅作去重防叠)
  return stableHash(node.nodeKey || node.id || node.displayText) % 2 === 0 ? "north" : "south";
}

function normalizeNode(raw, index) {
  const nodeKey = String(raw.node_key || raw.nodeKey || raw.ID || raw.id || `node-${index}`);
  const typeText = `${raw.node_type || raw.Type || raw.type || ""} ${raw.layer || ""} ${raw.role || ""}`.toLowerCase();
  const physicalPos = raw.Physical_Pos || raw.physical_pos || {};
  
  // 🔥 超级基因锁：全面兼容真实环境中的各类摄像头别名！
  const typeAndName = `${typeText} ${raw.label || raw.Name || raw.asset_label || nodeKey}`.toLowerCase();
  const isCamera = /camera|terminal|ipc|sdc|nvr|枪机|球机|半球|摄像|监控|视频|cam/i.test(typeAndName) || /^cam/i.test(nodeKey);
  
  const isCore = !isCamera && typeText.includes("core");
  const isAggregation = !isCamera && (typeText.includes("aggregation") || typeText.includes("汇聚"));
  const isJunction = !isCamera && (typeText.includes("junction") || typeText.includes("分线"));
  const isUnmanaged = !isCamera && (typeText.includes("unmanaged") || typeText.includes("无网管"));
  
  const conflictCase = raw.Conflict_Case || raw.conflict_case || raw.conflictCases || [];
  const parentId = raw.Parent_ID || raw.parent_node_key || raw.parentId || raw.parent_id || "";
  const x = Number(raw.pos_x ?? raw.x ?? physicalPos.X);
  const y = Number(raw.pos_y ?? raw.y ?? physicalPos.Y);
  
  const displayText = raw.label || raw.Name || raw.asset_label || raw.ip || raw.IP || nodeKey;
  
  const node = {
    id: nodeKey,
    nodeKey,
    backendId: raw.id && String(raw.id).match(/^\d+$/) ? Number(raw.id) : null,
    deviceId: raw.device_id || raw.deviceId || null,
    parentId,
    ip: raw.ip || raw.IP || "",
    label: "", 
    displayText, 
    // 🔥 确保 isCamera 拥有绝对第一优先级
    kind: isCamera ? "camera" : isCore ? "core" : isJunction ? "junction" : isUnmanaged ? "unmanaged" : "switch",
    tier: isCamera ? "camera" : isCore ? "core" : isAggregation ? "aggregation" : "access",
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
  return {
    nodes: [],
    edges: [],
  };
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
  
  // 🔥 核心修复：绝对优先级屏障！只要类型是摄像头，直接阻断后续正则判定，强制打入最底层！
  if (node?.kind === "camera") return 4; 
  
  if (node?.tier === "core" || node?.kind === "core" || node?.cluster === "core") return 1;
  if (node?.tier === "aggregation" || /aggregation|汇聚/i.test(`${node?.layer || ""} ${node?.role || ""} ${node?.displayText || ""}`)) return 2;
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
  return stableHash(node?.nodeKey || node?.id || node?.displayText) % 2 === 0 ? "south" : "north";
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

// 🔥 全网最权威的摄像头查户口系统，绝对保证识别到真实的老大
function cameraParentId(camera) {
  if (!camera) return "";
  if (camera.parentId) return camera.parentId; 

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
  
  // 1. 解析后端传来的真实物理节点
  const parsedNodes = (topologyPayload.value.nodes || []).map(normalizeNode);
  const parsedEdges = (topologyPayload.value.edges || []).map(normalizeEdge).filter(Boolean);
  
  const existingIps = new Set();
  parsedNodes.forEach(n => {
    if (n.ip) existingIps.add(n.ip);
  });

  // 2. 🔥 战役核心：实体水合注入（利用花名册，强制唤醒幽灵军团）
  const virtualNodes = [];
  const virtualEdges = [];

  parsedNodes.forEach(switchNode => {
    if (switchNode.kind === "camera" || switchNode.virtual) return;
    
    const raw = switchNode.raw || {};
    const targetCount = Number(raw.camera_count || raw.sheet_camera_count || 0);
    const sampleIps = Array.isArray(raw.camera_sample_ips) ? raw.camera_sample_ips : [];
    
    let generatedCount = 0;

    // A. 优先使用真实的大数据 IP 样本进行实体化
    for (const ip of sampleIps) {
      if (generatedCount >= targetCount) break;
      if (existingIps.has(ip)) continue; 
      
      const camId = `virtual-cam-${switchNode.id}-${ip}`;
      virtualNodes.push({
        id: camId,
        nodeKey: camId,
        backendId: null,
        deviceId: null,
        parentId: switchNode.id,
        ip: ip,
        label: "",
        displayText: `IPC .${ip.split('.').pop()}`, // 截取 IP 末尾显得更极客
        kind: "camera",
        tier: "camera",
        layer: "terminal",
        posX: null,
        posY: null,
        verified: true, 
        conflict: false,
        cluster: switchNode.cluster,
        raw: { node_type: "camera", ip: ip, parent_node_key: switchNode.id }
      });
      
      virtualEdges.push({
        id: `edge-${switchNode.id}-${camId}`,
        backendId: null,
        source: switchNode.id,
        target: camId,
        label: "大数据推演",
        verified: true,
        raw: {}
      });
      existingIps.add(ip);
      generatedCount++;
    }

    // B. 如果大数据的 IP 样本数量给得不够（比如只给了5个抽样，角标却是11），用盲区幽灵补齐
    while (generatedCount < targetCount) {
      const camId = `virtual-cam-${switchNode.id}-ghost-${generatedCount}`;
      virtualNodes.push({
        id: camId,
        nodeKey: camId,
        backendId: null,
        deviceId: null,
        parentId: switchNode.id,
        ip: "未知 IP",
        label: "",
        displayText: `待核实终端 ${generatedCount + 1}`,
        kind: "camera",
        tier: "camera",
        layer: "terminal",
        posX: null,
        posY: null,
        verified: false,
        conflict: false,
        cluster: switchNode.cluster,
        raw: { node_type: "camera", parent_node_key: switchNode.id }
      });
      
      virtualEdges.push({
        id: `edge-${switchNode.id}-${camId}`,
        backendId: null,
        source: switchNode.id,
        target: camId,
        label: "概算分配",
        verified: false,
        raw: {}
      });
      generatedCount++;
    }
  });

  // 3. 将虚拟大军编入正规军
  nodes.value = [...parsedNodes, ...virtualNodes];
  edges.value = [...parsedEdges, ...virtualEdges];

  rebuildOrphans();
}

async function loadTopology() {
  try {
    const payload = await fetchCentralAvenueArchitecture();
    applyPayload(payload);
  } catch (error) {
    console.error(error);
    ElMessage.error("拓扑数据加载失败，请检查网络或登录状态。");
  }
}

function cameraCountUnder(nodeId, childrenBySource, nodeMap) {
  let count = 0;
  const children = childrenBySource.get(nodeId) || [];
  for (const id of children) {
    const node = nodeMap.get(id);
    if (node && node.kind === "camera") count++;
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
    const pId = cameraParentId(node);
    if (pId) pushChild(pId, node.id);
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
      displayText: cluster === "north" ? "北楼汇聚层" : "南楼汇聚层",
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
    
    // 🔥 核心修正：双重保险！取前端计算值和后端权威值的最大值，确保角标绝对不会消失
    const computedCameraCount = cameraCountUnder(node.id, topologyChildren, nodeMap);
    const backendCameraCount = Number(node.raw?.camera_count || node.raw?.sheet_camera_count || 0);
    const cameraCount = Math.max(computedCameraCount, backendCameraCount);
    
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
      displayText: "核心层",
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
  if (node.virtual) return { fill: "rgba(0, 0, 0, 0)", activeFill: "rgba(0, 0, 0, 0)", stroke: "rgba(0, 0, 0, 0)", shadow: "rgba(0, 0, 0, 0)", glow: "#00f2fe" };
  if (isOfflineNode(node)) return { fill: "rgba(92, 20, 28, 0.96)", activeFill: "rgba(69, 10, 10, 0.98)", stroke: "#ef4444", shadow: "rgba(239, 68, 68, 0.62)", glow: "#ef4444" };
  if (node.kind === "camera") return { fill: "rgba(17, 24, 39, 0.96)", activeFill: "rgba(14, 19, 31, 0.98)", stroke: "#94a3b8", shadow: "rgba(148, 163, 184, 0.28)", glow: "#94a3b8" };
  if (node.tier === "core") return { fill: "rgba(89, 24, 32, 0.96)", activeFill: "rgba(71, 19, 26, 0.98)", stroke: "#f56c6c", shadow: "rgba(245, 108, 108, 0.5)", glow: "#f56c6c" };
  if (node.tier === "aggregation") return { fill: "rgba(16, 48, 84, 0.96)", activeFill: "rgba(13, 38, 67, 0.98)", stroke: "#409eff", shadow: "rgba(64, 158, 255, 0.42)", glow: "#00f2fe" };
  return { fill: "rgba(22, 61, 44, 0.96)", activeFill: "rgba(18, 49, 35, 0.98)", stroke: "#67c23a", shadow: "rgba(103, 194, 58, 0.38)", glow: "#67e8f9" };
}

function graphNodeWidth(node) {
  if (node?.virtual) return 1;
  if (node?.kind === "camera") return 124;
  if (isCoreNode(node)) return 184;
  if (isAggregationNode(node)) return 162;
  return 134;
}

function graphNodeHeight(node) {
  if (node?.virtual) return 1;
  if (node?.kind === "camera") return 38;
  if (isCoreNode(node)) return 72;
  if (isAggregationNode(node)) return 62;
  return 58;
}

function hasCollapsedChildren(model) {
  return Array.isArray(model?.children) && model.children.length > 0;
}

function isCollapsedWithChildren(model) {
  return Boolean(model?.collapsed && hasCollapsedChildren(model));
}

function nodeShellAttrs(model, selected = false) {
  const palette = tierColor(model || {});
  const isUltra = currentGraphics.value === "ultra";
  if (selected) {
    return {
      fill: palette.activeFill || palette.fill,
      stroke: "#fff",
      lineWidth: 1,
      shadowColor: model?.color || palette.glow || "#00f2fe",
      shadowBlur: isUltra ? 20 : 10,
      shadowOpacity: 1,
    };
  }
  if (isCollapsedWithChildren(model)) {
    return {
      fill: palette.fill,
      stroke: model?.conflict ? "#fb923c" : "#93c5fd",
      lineWidth: 2,
      shadowColor: model?.conflict ? "rgba(251, 146, 60, 0.9)" : "rgba(147, 197, 253, 0.95)",
      shadowBlur: isUltra ? 24 : 0,
    };
  }
  return {
    fill: palette.fill,
    stroke: model?.conflict ? "#f59e0b" : palette.stroke,
    lineWidth: model?.conflict ? 2 : 1,
    shadowColor: model?.conflict ? "rgba(245, 158, 11, 0.75)" : palette.glow,
    shadowBlur: isUltra && model?.conflict ? 24 : 0,
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

function applyNodeVisualState(item) {
  if (!item || item.destroyed) return;
  const model = item.getModel?.();
  if (!model || model.kind === "camera") return;
  const group = item.getContainer();
  
  if (group.get("capture") === false) return;

  const shell = group.find((shape) => shape.get("name") === "shell");
  const marker = group.find((shape) => shape.get("name") === "collapse-marker");
  const markerText = group.find((shape) => shape.get("name") === "collapse-marker-text");
  shell?.attr(nodeShellAttrs(model, itemHasState(item, "selected")));
  marker?.attr(collapseMarkerAttrs(model));
  markerText?.attr({ text: model.collapsed ? "+" : "-" });
}

function isLodDetailVisible() {
  return (graph?.getZoom?.() || 1) >= LOD_LABEL_ZOOM;
}

function defaultEdgeAttrs() {
  return {
    stroke: "rgba(245, 158, 11, 0.65)",
    lineWidth: 1.2,
    shadowBlur: 8,
    shadowColor: "rgba(245, 158, 11, 0.25)",
  };
}

function activeEdgeAttrs(model = {}) {
  // 🔥 强力拦截：如果已经核实，悬浮/选中时必须保持蓝光并增强亮度！
  if (model.verified) {
    return {
      stroke: "#0ea5e9",
      lineWidth: 3.5,
      shadowBlur: 18,
      shadowColor: "rgba(14, 165, 233, 0.8)",
    };
  }
  return {
    stroke: "#facc15",
    lineWidth: 2.4,
    shadowBlur: 14,
    shadowColor: "rgba(245, 158, 11, 0.72)",
  };
}

function verifiedEdgeAttrs(model = {}) {
  return {
    stroke: "rgba(14, 165, 233, 0.4)",
    lineWidth: 2.5,
    lineDash: null,
    shadowBlur: 0,
  };
}

function applyEdgeVisualState(item, active = false) {
  if (!item || item.destroyed) return;
  const group = item.getContainer();
  if (group && group.get("capture") === false) return; 
  
  const model = item.getModel?.() || {};
  
  if (active) {
    item.getKeyShape?.()?.attr(activeEdgeAttrs(model));
  } else {
    item.getKeyShape?.()?.attr(model.verified ? verifiedEdgeAttrs(model) : defaultEdgeAttrs());
  }
}

function highlightRelatedEdges(item, active = false) {
  const relatedEdges = item?.getEdges?.() || [];
  relatedEdges.forEach((edge) => {
    if (active) edge.toFront?.();
    applyEdgeVisualState(edge, active);
  });
}

function resetSelectedNodeState() {
  selectedNodeId.value = "";
  selectedNodeDetail.value = null;
  selectedNodeDetailLoading.value = false;
  showDetailPanel.value = false;
  if (!graph) return;
  const selectedItems = graph.findAllByState?.("node", "selected") || graph.getNodes();
  selectedItems.forEach((item) => graph.setItemState(item, "selected", false));
  graph.getEdges().forEach((edge) => applyEdgeVisualState(edge, false));
  enforcePhaseIsolation();
  applyLodVisibility();
  graph.paint();
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

// 🛡️ 终极神级力场：全局唯一相位控制器
function enforcePhaseIsolation() {
  if (!graph) return;
  const isDeepWell = expandedAccessIds.value.size > 0;
  const selectedId = selectedNodeId.value;
  const showDrawer = showDetailPanel.value;
  const detailModel = selectedNodeDetail.value?.model;

  let safeNodeIds = new Set();
  let safeEdgeIds = new Set();

  const isLinkSelected = showDrawer && detailModel?.kind === 'link';
  const isNodeSelected = showDrawer && selectedNodeId.value;

  if (isDeepWell) {
    const expandedId = Array.from(expandedAccessIds.value)[0];
    safeNodeIds.add(expandedId);
    graph.getEdges().forEach(e => {
        const srcNode = e.getSource?.();
        const tgtNode = e.getTarget?.();
        if (!srcNode || !tgtNode) return; 
        const src = srcNode.getID();
        const tgt = tgtNode.getID();
        if (src === expandedId) {
            const tgtModel = graph.findById(tgt)?.getModel();
            if (tgtModel && tgtModel.kind === "camera") { safeNodeIds.add(tgt); safeEdgeIds.add(e.getID()); }
        } else if (tgt === expandedId) {
            const srcModel = graph.findById(src)?.getModel();
            if (srcModel && srcModel.kind === "camera") { safeNodeIds.add(src); safeEdgeIds.add(e.getID()); }
        }
    });
  } 
  else if (isLinkSelected) {
    const edgeId = detailModel.id;
    const edgeItem = graph.findById(edgeId);
    if (edgeItem) {
      safeEdgeIds.add(edgeId);
      safeNodeIds.add(edgeItem.getSource().getID());
      safeNodeIds.add(edgeItem.getTarget().getID());
    }
  }
  else if (isNodeSelected) {
    safeNodeIds.add(selectedId);
    const item = graph.findById(selectedId);
    if (item) {
      item.getEdges().forEach(edge => {
        safeEdgeIds.add(edge.getID());
        safeNodeIds.add(edge.getSource().getID());
        safeNodeIds.add(edge.getTarget().getID());
      });
    }
  }

  const hasFocus = isDeepWell || isLinkSelected || isNodeSelected;

  graph.getNodes().forEach(node => {
    const group = node.getContainer();
    if (!group) return;
    const isTarget = hasFocus ? safeNodeIds.has(node.getID()) : true;
    const targetOpacity = isTarget ? 1 : 0.08;
    
    // 🔥 终极防穿透锁：只要产生聚焦暗影，未命中节点无论是否编辑模式，绝对禁止点击！
    const allowCapture = hasFocus ? isTarget : (editMode.value ? true : isTarget); 
    
    group.attr("opacity", targetOpacity);
    group.set("capture", allowCapture); 
    group.get("children")?.forEach(shape => { 
      shape.attr("opacity", targetOpacity); 
      shape.set("capture", allowCapture); 
    });
  });

  graph.getEdges().forEach(edge => {
    const group = edge.getContainer();
    if (!group) return;
    const isTarget = hasFocus ? safeEdgeIds.has(edge.getID()) : true;
    const targetOpacity = isTarget ? 1 : 0.08;
    
    // 🔥 终极防穿透锁
    const allowCapture = hasFocus ? isTarget : (editMode.value ? true : isTarget);
    
    group.attr("opacity", targetOpacity);
    group.set("capture", allowCapture);
    group.get("children")?.forEach(shape => { 
      shape.attr("opacity", targetOpacity); 
      shape.set("capture", allowCapture); 
    });
  });
}

function applyLodVisibility() {
  if (!graph) return;
  const zoom = graph.getZoom?.() || 1;
  const showDetails = zoom >= LOD_LABEL_ZOOM;
  
  graph.getNodes().forEach((item) => {
    const group = item.getContainer?.();
    if (!group?.get) return;
    
    if (group.get("capture") === false) return;

    const children = group.get("children") || [];
    const bodyOpacity = showDetails || itemHasState(item, "selected") ? 1 : 0.6;
    children.forEach((shape) => {
      const name = shape.get("name");
      if (LOD_DETAIL_SHAPES.has(name)) {
        shape.attr({ opacity: showDetails ? 1 : 0 });
      }
      if (LOD_BODY_SHAPES.has(name)) {
        shape.attr({ opacity: bodyOpacity });
      }
    });
  });
}

let lodFrame = 0;
function scheduleLodVisibility() {
  if (lodFrame) return;
  lodFrame = window.requestAnimationFrame(() => {
    lodFrame = 0;
    applyLodVisibility();
  });
}

function focusItemAfterCollapse(item) {
  if (!graph || !item || item.destroyed) return;
  const anchorId = item.getID?.() || item.get?.("id") || item.getModel?.()?.id;
  if (!anchorId) return;
  let focused = false;
  const runFocus = () => {
    if (focused || !graph) return;
    focused = true;
    graph.off?.("afterlayout", runFocus);
    window.setTimeout(() => {
      const anchor = graph?.findById(anchorId);
      if (!anchor || anchor.destroyed) return;
      syncAllCollapsedGlow();
      graph.focusItem(anchor, true, {
        easing: "easeCubic",
        duration: COLLAPSE_ANIMATION_DURATION,
      });
    }, 40);
  };

  graph.on?.("afterlayout", runFocus);
  window.setTimeout(runFocus, COLLAPSE_ANIMATION_DURATION + 120);
}

function handleCollapseChange(item, collapsed) {
  const data = item?.get("model");
  if (!data) return true;
  data.collapsed = collapsed;
  syncCollapsedGlow(item);
  focusItemAfterCollapse(item);
  return true;
}

function snapToGrid(value) {
  return Math.round(Number(value || 0) / GRID_SIZE) * GRID_SIZE;
}

function snapPoint(point) {
  return {
    x: snapToGrid(point.x),
    y: snapToGrid(point.y),
  };
}

function buildGraphPlugins() {
  const plugins = [];
  if (G6.SnapLine) {
    plugins.push(new G6.SnapLine({
      line: {
        stroke: "#facc15",
        lineWidth: 1.2,
      },
      itemAlignType: true,
    }));
  }
  return plugins;
}

function registerCustomElements() {
  if (customElementsRegistered) return;
  customElementsRegistered = true;

  G6.registerEdge("animated-curve", {
    afterDraw(cfg, group) {
      const shape = group.get("children")?.[0];
      if (!shape) return;

      const isVerified = cfg?.verified === true;
      const isActive = cfg?.active === true;
      const isLow = currentGraphics.value === "low";
      const isUltra = currentGraphics.value === "ultra";

      if (isVerified) {
        shape.attr({
          stroke: isActive ? "#0ea5e9" : (isUltra ? "rgba(14, 165, 233, 0.4)" : "#0284c7"),
          lineWidth: isActive ? 3 : 1.5,
          lineDash: null,
          shadowBlur: isActive && !isLow ? 18 : 0,
          shadowColor: isActive && !isLow ? "rgba(14, 165, 233, 0.8)" : "transparent",
        });

        if (!isLow) {
          const particle = group.addShape("circle", {
            attrs: {
              x: 0,
              y: 0,
              r: 2,
              fill: "#38bdf8",
              shadowColor: "#67e8f9",
              shadowBlur: isUltra ? 8 : 0,
            },
            name: "photon-particle",
          });
          particle.animate(
            (ratio) => {
              const tmpPoint = shape.getPoint(ratio);
              return { x: tmpPoint.x, y: tmpPoint.y };
            },
            { repeat: true, duration: isUltra ? 1500 : 2000, easing: "easeCubic" }
          );
        }
      } else {
        shape.attr({
          stroke: isActive ? "#facc15" : "rgba(245, 158, 11, 0.65)",
          lineWidth: isActive ? 2 : 1,
          lineDash: [8, 6],
          lineDashOffset: 0,
          shadowBlur: isActive && !isLow ? 10 : 0,
          shadowColor: isActive && !isLow ? "rgba(245, 158, 11, 0.72)" : "transparent",
        });
        if (!isLow) {
          shape.animate((ratio) => ({ lineDashOffset: -ratio * 60 }), { repeat: true, duration: 1600, easing: "easeLinear" });
        }
      }
    },
    update(cfg, item) {
      const group = item.getContainer();
      if (!group) return;
      
      const shape = group.get("children")?.[0];
      if (shape) {
        shape.stopAnimate();
      }
      
      const oldParticle = group.find(s => s.get("name") === "photon-particle");
      if (oldParticle) oldParticle.remove();
      
      // 🔥 强制清理图元的缓存包络框，强制引擎根据最新属性重新计算视觉
      item.clearCache();
      
      this.afterDraw(cfg, group);
    },
    setState(name, value, item) {
      if (name === "active" || name === "verified") {
        const model = item.getModel();
        model[name] = value;
        this.update(model, item);
      }
    }
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
      const tierText = isCore ? "CORE" : isAggregationNode(cfg) ? "AGG" : "ACC";
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
          y: isCore ? -12 : -8,
          text: compactNodeLabel(cfg.displayText || cfg.id),
          fill: "#f8fbff",
          fontSize: isCore ? 14 : 12,
          fontWeight: 800,
          textBaseline: "middle",
        },
        name: "displayText",
      });
      group.addShape("text", {
        attrs: {
          x: -width / 2 + 14,
          y: isCore ? 14 : 13,
          text: `${clusterLabel(cfg.cluster)} / ${cfg.ip || cfg.nodeKey || "-"}`,
          fill: "rgba(226, 232, 240, 0.68)",
          fontSize: 10,
          textBaseline: "middle",
        },
        name: "meta",
      });
      group.addShape("text", {
        attrs: {
          x: width / 2 - 18,
          y: height / 2 - 14,
          text: tierText,
          fill: isCore ? "#fecaca" : isAggregationNode(cfg) ? "#bfdbfe" : "#bbf7d0",
          fontSize: 10,
          fontWeight: 900,
          textAlign: "right",
          textBaseline: "middle",
        },
        name: "tier-mark",
      });
      // 🛡️ 只要不是摄像头和虚拟壳子，均享有预埋角标的权力
      if (cfg.kind !== "camera" && !cfg.virtual && cfg.cameraCount > 0) {
        const hasCam = cfg.cameraCount > 0;
        const badgeW = 60;
        const badgeH = 20;
        const isExpanded = cfg.cameraExpanded;
        
        const badgeFill = isExpanded ? "rgba(15, 23, 42, 0.95)" : "rgba(30, 41, 59, 0.75)";
        const badgeStroke = isExpanded ? "#0ea5e9" : "rgba(100, 116, 139, 0.4)";
        const textColor = isExpanded ? "#38bdf8" : "#94a3b8";

        group.addShape("rect", {
          attrs: {
            x: width / 2 - badgeW + 6,
            y: -height / 2 - 10,
            width: badgeW,
            height: badgeH,
            radius: 4, 
            fill: badgeFill,
            stroke: badgeStroke,
            lineWidth: 1,
            shadowColor: isExpanded ? "rgba(14, 165, 233, 0.4)" : "transparent",
            shadowBlur: isExpanded ? 8 : 0,
            cursor: hasCam ? "pointer" : "default",
            zIndex: 10, 
          },
          name: "camera-badge",
          visible: hasCam, // 🛡️ G6 原生物理显隐控制
        });

        group.addShape("text", {
          attrs: {
            x: width / 2 - badgeW / 2 + 6,
            y: -height / 2,
            text: isExpanded ? `▼ ${cfg.cameraCount || 0} CAM` : `▶ ${cfg.cameraCount || 0} CAM`,
            fill: textColor,
            fontSize: 9,
            fontWeight: 800,
            textAlign: "center",
            textBaseline: "middle",
            cursor: hasCam ? "pointer" : "default",
            zIndex: 11,
          },
          name: "camera-badge-text",
          visible: hasCam, // 🛡️ G6 原生物理显隐控制
        });
        group.sort(); 
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
    update(cfg, item) {
      const group = item.getContainer();
      const badgeText = group.find((s) => s.get('name') === 'camera-badge-text');
      const badgeRect = group.find((s) => s.get('name') === 'camera-badge');
      const displayShape = group.find((s) => s.get('name') === 'displayText');
      
      if (displayShape) {
         displayShape.attr('text', compactNodeLabel(cfg.displayText || cfg.id));
      }
      
      const isExpanded = cfg.cameraExpanded;
      const hasCam = cfg.cameraCount > 0;
      
      if (badgeText) {
        if (hasCam) {
          badgeText.show(); // 🛡️ 有摄像头时瞬间物理唤醒
          badgeText.attr({
            text: isExpanded ? `▼ ${cfg.cameraCount} CAM` : `▶ ${cfg.cameraCount} CAM`,
            cursor: "pointer"
          });
        } else {
          badgeText.hide(); // 🛡️ 减为 0 时直接物理放逐
        }
      }
      
      if (badgeRect) {
        if (hasCam) {
          badgeRect.show(); // 🛡️ 有摄像头时瞬间物理唤醒
          badgeRect.attr({
            fill: isExpanded ? "rgba(15, 23, 42, 0.95)" : "rgba(30, 41, 59, 0.75)",
            stroke: isExpanded ? "#0ea5e9" : "rgba(100, 116, 139, 0.4)",
            shadowColor: isExpanded ? "rgba(14, 165, 233, 0.4)" : "transparent",
            shadowBlur: isExpanded ? 8 : 0,
            cursor: "pointer"
          });
        } else {
          badgeRect.hide(); // 🛡️ 减为 0 时直接物理放逐
        }
      }
    },
    setState(name, value, item) {
      if (name === "selected" || name === "collapsed-glow") {
        applyNodeVisualState(item);
      }
    },
  }, "single-node");

  G6.registerNode("camera-leaf", {
    draw(cfg, group) {
      const width = 126;
      const height = 28;
      const isVerified = cfg.verified;
      const statusColor = isVerified ? "#10b981" : "#fbbf24";
      const bgColor = "rgba(15, 23, 42, 1)";

      const keyShape = group.addShape("rect", {
        attrs: {
          x: -width / 2,
          y: -height / 2,
          width,
          height,
          radius: 6,
          fill: bgColor,
          stroke: statusColor,
          lineWidth: 1.5,
          shadowColor: "rgba(0, 0, 0, 0.95)",
          shadowBlur: 16,
        },
        name: "camera-shell",
      });

      group.addShape("rect", {
        attrs: {
          x: -width / 2,
          y: -height / 2,
          width: 28,
          height,
          radius: [6, 0, 0, 6],
          fill: isVerified ? "rgba(16, 185, 129, 0.15)" : "rgba(251, 191, 36, 0.15)",
        },
        name: "camera-icon-bg",
      });

      group.addShape("circle", {
        attrs: {
          x: -width / 2 + 14,
          y: 0,
          r: 0,
          fill: statusColor,
        },
        name: "camera-dot",
      });

      group.addShape("text", {
        attrs: {
          x: -width / 2 + 14,
          y: 1,
          text: "📹",
          fill: statusColor,
          fontSize: 12,
          textAlign: "center",
          textBaseline: "middle",
        },
        name: "camera-icon",
      });

      const text = cfg.ip || cfg.nodeKey || "未知设备";
      group.addShape("text", {
        attrs: {
          x: -width / 2 + 46,
          y: 1,
          text: text.length > 14 ? `${text.substring(0, 12)}..` : text,
          fill: "#e2e8f0",
          fontSize: 11,
          fontFamily: "monospace",
          fontWeight: 600,
          textAlign: "left",
          textBaseline: "middle",
        },
        name: "camera-label",
      });

      return keyShape;
    },
    setState(name, value, item) {
      if (["selected", "relation-active", "relation-inactive"].includes(name)) {
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
    .sort((a, b) => stableHash(a.id || a.nodeKey || a.displayText) - stableHash(b.id || b.nodeKey || b.displayText));
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
    // 🛡️ 只要老爹的深井开了，就给它排兵布阵！
    if (!entry.parent || !expandedAccessIds.value.has(entry.parent.id)) continue;
    const parentId = entry.parent?.id || "__orphan-camera";
    if (!cameraGroups.has(parentId)) cameraGroups.set(parentId, []);
    cameraGroups.get(parentId).push(entry);
  }

  for (const groupEntries of cameraGroups.values()) {
    const parent = groupEntries[0]?.parent;
    const ordered = groupEntries.sort((a, b) => stableHash(a.node.id) - stableHash(b.node.id));
    const COLS = 4;
    const SPACING_X = 140;
    const SPACING_Y = 46;
    const parentX = Number.isFinite(Number(parent?.x)) ? Number(parent.x) : centerX;
    const parentY = Number.isFinite(Number(parent?.y)) ? Number(parent.y) : centerY;
    const startY = parentY + graphNodeHeight(parent) / 2 + 40;
    const actualCols = Math.min(ordered.length, COLS);
    const startX = parentX - ((actualCols - 1) * SPACING_X) / 2;

    ordered.forEach((entry, index) => {
      const row = Math.floor(index / COLS);
      const col = index % COLS;
      entry.node.x = startX + col * SPACING_X;
      entry.node.y = startY + row * SPACING_Y;
    });
  }
}

function flattenTreeGraphData(treeRoot, originalEdges = []) {
  const graphNodes = [];
  const graphEdges = [];
  const seenNodeIds = new Set();
  const seenEdgeIds = new Set();
  const walk = (node, parent = null) => {
    if (!node?.id) return;
    const children = Array.isArray(node.children) ? node.children : [];
    // 🛡️ 解除老爹层级限制：只要深井没开，统统隐藏
    if (node.kind === "camera" && parent && !expandedAccessIds.value.has(parent.id)) {
      return;
    }
    const nodeAlreadyAdded = seenNodeIds.has(node.id);
    if (!nodeAlreadyAdded) {
      const { children: _children, label, ...graphNode } = node; 
      graphNode.hasTreeChildren = children.length > 0;
      graphNode.isCore = isCoreNode(graphNode);
      graphNode.isAccess = isAccessNode(graphNode);
      graphNode.isAggregation = isAggregationNode(graphNode);
      // 🛡️ 解除层级限制：任何设备均可展开深井
      graphNode.cameraExpanded = expandedAccessIds.value.has(graphNode.id);
      graphNodes.push(graphNode);
      seenNodeIds.add(node.id);
    }
    if (parent?.id && node.id && seenNodeIds.has(parent.id)) {
      const edgeId = `${parent.id}->${node.id}`;
      if (!seenEdgeIds.has(edgeId)) {
        const oEdge = originalEdges.find((edge) => (
          (edge.source === parent.id && edge.target === node.id)
          || (edge.target === parent.id && edge.source === node.id)
        ));
        // 终极降噪清洗机制：绝不让无意义的垃圾标签上大盘。
        let edgeLabel = "";
        if (oEdge?.verified) {
          if (oEdge?.raw?.vlan) {
            edgeLabel = `VLAN ${oEdge.raw.vlan}`;
          } else {
            const rawStr = String(oEdge?.label || "").trim();
            if (rawStr && !["camera", "switch", "大数据推演", "概算分配", "摄像头挂载"].includes(rawStr)) {
              edgeLabel = rawStr;
            }
          }
        }

        graphEdges.push({
          id: edgeId,
          source: parent.id,
          target: node.id,
          type: "animated-curve",
          label: edgeLabel,
          verified: oEdge?.verified || false,
          backendId: oEdge?.backendId || null,
          raw: oEdge?.raw || {},
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
  const coreNodes = [];

  for (const entry of entries) {
    const { node } = entry;
    const tier = treeLayoutTier(node);
    if (tier === 0) {
      coreNodes.push(node);
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

  const visibleCores = coreNodes.filter((n) => !n.virtual);
  const coreGap = 120;
  const coreStartY = centerY - ((visibleCores.length - 1) * coreGap) / 2;
  visibleCores.forEach((node, idx) => {
    node.x = centerX;
    node.y = coreStartY + idx * coreGap;
  });
  coreNodes.filter((n) => n.virtual).forEach((n) => {
    n.x = centerX;
    n.y = centerY;
  });

  const accessCount = arcBuckets.north.access.length + arcBuckets.south.access.length;
  const currentRadiusX = Math.max(ELLIPSE_OUTER_RADIUS_X, accessCount * 15);
  const currentRadiusY = Math.max(ELLIPSE_OUTER_RADIUS_Y, currentRadiusX * (ELLIPSE_OUTER_RADIUS_Y / ELLIPSE_OUTER_RADIUS_X));

  placeEllipseArc(arcBuckets.north.aggregation, centerX, centerY, ELLIPSE_INNER_RADIUS_X, ELLIPSE_INNER_RADIUS_Y, NORTH_ARC_START, NORTH_ARC_END);
  placeEllipseArc(arcBuckets.north.access, centerX, centerY, currentRadiusX, currentRadiusY, NORTH_ARC_START, NORTH_ARC_END);
  placeEllipseArc(arcBuckets.south.aggregation, centerX, centerY, ELLIPSE_INNER_RADIUS_X, ELLIPSE_INNER_RADIUS_Y, SOUTH_ARC_START, SOUTH_ARC_END);
  placeEllipseArc(arcBuckets.south.access, centerX, centerY, currentRadiusX, currentRadiusY, SOUTH_ARC_START, SOUTH_ARC_END);
  placeCameraStarburst(cameraEntries, centerX, centerY);

  entries.forEach((entry) => ensureSafeCoordinate(entry.node, centerX, centerY));
  return flattenTreeGraphData(treeRoot, graphEdges);
}

function graphConfig() {
  const width = graphContainer.value?.offsetWidth || 800;
  const height = graphContainer.value?.offsetHeight || 600;
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
        ? [
          "drag-canvas",
          { type: "zoom-canvas", sensitivity: 1.2, enableOptimize: true, optimizeZoom: 0.92 },
          { type: "drag-node", enableDelegate: true },
        ]
        : [
          "drag-canvas",
          { type: "zoom-canvas", sensitivity: 1.2, enableOptimize: true, optimizeZoom: 0.92 },
        ],
    },
    defaultNode: {
      type: "network-tree-node",
      anchorPoints: [[0.5, 0], [0.5, 1], [0, 0.5], [1, 0.5]],
    },
    defaultEdge: {
      type: "animated-curve",
      style: {
        stroke: "rgba(245, 158, 11, 0.65)",
        lineWidth: 1.2,
        lineDash: [8, 6],
        lineAppendWidth: 15,
        endArrow: false,
        shadowBlur: 8,
        shadowColor: "rgba(245, 158, 11, 0.25)",
      },
      // 核心修复：注入全局科技感文字涂装，干掉默认黑字。
      labelCfg: {
        autoRotate: true,
        style: {
          fill: "#e2e8f0",
          fontSize: 10,
          fontWeight: 600,
          background: {
            fill: "rgba(15, 23, 42, 0.85)",
            stroke: "rgba(56, 189, 248, 0.4)",
            lineWidth: 1,
            padding: [2, 6, 2, 6],
            radius: 4,
          },
        },
      },
    },
    layout: null,
    nodeStateStyles: {
      selected: {
        zIndex: 999,
        fill: "rgba(15, 23, 42, 0.98)",
        stroke: "#fff",
        lineWidth: 1,
        shadowColor: "#00f2fe",
        shadowBlur: 15,
        shadowOpacity: 1,
      },
      active: {
        opacity: 1,
      },
      inactive: {
        opacity: 0.15,
      },
      "collapsed-glow": {},
    },
    edgeStateStyles: {
      active: {
        opacity: 1,
      },
      inactive: {
        opacity: 0.15,
      },
    },
  };
}

function injectOfflineGraphNodeFixtures(graphData) {
  if (!graphData?.nodes || graphData.nodes.length <= 5) return;
  [2, 5].forEach((index) => {
    graphData.nodes[index].status = "offline";
    graphData.nodes[index].style = { fill: "rgba(239, 68, 68, 0.2)", stroke: "#ef4444" };
    graphData.nodes[index].color = "#ef4444";
    graphData.nodes[index].raw = {
      ...(graphData.nodes[index].raw || {}),
      status: "offline",
    };
  });
}

function triggerNeonRadar(nodeId) {
  setTimeout(() => {
    if(!graph) return;
    const item = graph.findById(nodeId);
    if (!item) return;
    item.toFront(); 
    const group = item.getContainer();
    if(!group) return;
    const shell = group.find(s => s.get("name") === "camera-shell");
    if (shell) {
      shell.animate({
        shadowColor: '#facc15',
        shadowBlur: 35,
        stroke: '#facc15',
        lineWidth: 2
      }, {
        duration: 600,
        repeat: true,
        easing: 'easeCubic'
      });

      setTimeout(() => {
        if (!item.destroyed && shell) {
          shell.stopAnimate();
          shell.attr({
            shadowColor: "rgba(16, 185, 129, 0.25)", 
            shadowBlur: 10,
            stroke: "#10b981",
            lineWidth: 1
          });
        }
      }, 3000);
    }
  }, 150); 
}

async function renderGraph() {
  await nextTick();
  if (!graphContainer.value) return;
  registerCustomElements();

  const graphData = applyEllipticalLayout(buildTopologyTree(), edges.value);
  injectOfflineGraphNodeFixtures(graphData);
  renderedGraphNodes.value = graphData.nodes || [];

  if (!graph) {
    graph = new G6.Graph(graphConfig());
    graph.data(graphData);
    bindGraphEvents(); // 仅在初次创建时绑定！
    graph.render();
    graph.fitView();
  } else {
    // 🔥 无闪烁全盘刷新技术，彻底告别 destroy()
    const currentMatrix = graph.getGroup().getMatrix();
    graph.clear(); 
    graph.data(graphData);
    graph.render();
    if (currentMatrix) {
      graph.getGroup().setMatrix(currentMatrix); 
    }
  }

  syncAllCollapsedGlow();
  if (selectedNodeId.value && graph.findById(selectedNodeId.value)) {
    graph.setItemState(graph.findById(selectedNodeId.value), "selected", true);
  }
  
  enforcePhaseIsolation();
  applyLodVisibility();
}

function setSelectedNodeDetail(model, patch = {}) {
  selectedNodeDetail.value = {
    model,
    raw: model.raw || {},
    device: null,
    ports: [],
    channels: [],
    links: null,
    error: "",
    ...patch,
  };
}

async function loadSelectedNodeDetail(model) {
  if (!model) {
    selectedNodeDetail.value = null;
    selectedNodeDetailLoading.value = false;
    return;
  }
  setSelectedNodeDetail(model);
  selectedNodeDetailLoading.value = false;
  const deviceId = model.deviceId || model.raw?.device_id || model.raw?.deviceId;
  if (!deviceId) return;
  const requestNodeId = model.id;
  selectedNodeDetailLoading.value = true;
  try {
    const detail = await fetchDeviceDetail(deviceId);
    if (selectedNodeId.value !== requestNodeId) return;
    selectedNodeDetail.value = {
      ...(selectedNodeDetail.value || { model, raw: model.raw || {} }),
      device: detail?.device || null,
      ports: detail?.ports || [],
      channels: detail?.channels || [],
      links: detail?.links || null,
      error: detail?.error ? "后端未找到该设备详情，已显示拓扑原始字段。" : "",
    };
  } catch (error) {
    console.error(error);
    if (selectedNodeId.value === requestNodeId) {
      selectedNodeDetail.value = {
        ...(selectedNodeDetail.value || { model, raw: model.raw || {} }),
        error: "设备详情读取失败，已显示拓扑原始字段。",
      };
    }
  } finally {
    if (selectedNodeId.value === requestNodeId) {
      selectedNodeDetailLoading.value = false;
    }
  }
}

function selectNode(model) {
  selectedNodeId.value = model.id;
  loadSelectedNodeDetail(model);
  if (!graph) return;
  
  graph.getNodes().forEach((item) => graph.setItemState(item, "selected", false));
  graph.getEdges().forEach((edge) => applyEdgeVisualState(edge, false)); 

  const item = graph.findById(model.id);
  if (item) {
    graph.setItemState(item, "selected", true);
    highlightRelatedEdges(item, true); 
  }
  syncAllCollapsedGlow();
}

function selectLink(item) {
  const model = item?.getModel?.();
  if (!model) return;
  const sourceId = typeof model.source === "string" ? model.source : model.source?.id;
  const targetId = typeof model.target === "string" ? model.target : model.target?.id;
  selectedNodeId.value = "";
  selectedNodeDetailLoading.value = false;
  selectedNodeDetail.value = {
    model: {
      id: model.id || `${sourceId || ""}-${targetId || ""}`,
      displayText: model.label || `${sourceId || "未知源"} → ${targetId || "未知目标"}`,
      kind: "link",
      source: sourceId,
      target: targetId,
      verified: model.verified,
    },
    raw: model.raw || model,
    device: null,
    ports: [],
    channels: [],
    links: null,
    error: "",
  };
  showDetailPanel.value = true;
  graph?.getEdges?.().forEach((edge) => applyEdgeVisualState(edge, edge === item));
  enforcePhaseIsolation();
}

async function verifyCurrentSelection() {
  const detail = selectedNodeDetail.value;
  if (!detail || !detail.model) return; 

  const targetId = detail.model.id;
  const isLink = detail.model.kind === 'link';

  try {
    if (isLink) {
      await createArchitectureEdge({
        id: detail.model.backendId || detail.raw.id,
        edge_id: detail.model.backendId || detail.raw.id,
        src_node_key: detail.raw.src_node_key || detail.raw.source || detail.model.source,
        dst_node_key: detail.raw.dst_node_key || detail.raw.target || detail.model.target,
        src_port_label: detail.raw.src_port_label,
        dst_port_label: detail.raw.dst_port_label,
        vlan: detail.raw.vlan,
        edge_type: detail.raw.edge_type || "camera",
        evidence_type: 'field_verified',
        review_status: 'field_verified',
        manual_note: detail.raw.manual_note || '现场核实链路固化'
      });
    } else {
      await updateAssetPosition({
        node_id: detail.model.backendId,
        node_key: detail.model.nodeKey || detail.model.id,
        id: detail.model.nodeKey || detail.model.id,
        ip: detail.model.ip,
        device_id: detail.model.deviceId,
        x: detail.model.posX || detail.model.x, 
        y: detail.model.posY || detail.model.y,
        review_status: 'field_verified',
        manual_note: detail.raw.manual_note || '现场核实设备固化'
      });
    }

    if (!graph) return;
    const item = graph.findById(targetId);
    if (!item || item.destroyed) return;

    const rawModel = Object.assign({}, item.getModel());
    rawModel.verified = true;
    if (!rawModel.raw) rawModel.raw = {};
    Object.assign(rawModel.raw, JSON.parse(JSON.stringify(detail.raw)));
    rawModel.raw.review_status = "field_verified";

    if (isLink) {
      rawModel.label = rawModel.raw.vlan
        ? `VLAN ${rawModel.raw.vlan}`
        : (rawModel.raw.label || detail.raw.label || rawModel.label || "");
    }

    graph.updateItem(item, { verified: true, label: rawModel.label, raw: rawModel.raw });

    // 🔥 修复：强制带上 active=true，让刚核实的线瞬间触发更亮的蓝光！
    if (isLink) {
      item.clearCache();
      graph.setItemState(item, "verified", true);
      applyEdgeVisualState(item, true); 
    } else {
      applyNodeVisualState(item); 
    }

    detail.model.verified = true;
    ElMessage.success(`${isLink ? '链路' : '设备'}情报已落盘！`);
    
  } catch (error) {
    console.error(error);
    const errMsg = error?.response?.data?.message || error?.response?.data?.msg || error?.message || '请检查网络或参数';
    ElMessage.error(`后台同步失败: ${errMsg}`);
  }
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
  // 🔥 允许数量归零时正常触发收起动画，允许空设备进入聚焦模式
  if (!model?.id || model.kind === "camera" || model.virtual) return false;

  const isExpanding = !expandedAccessIds.value.has(model.id);
  const next = new Set(expandedAccessIds.value);

  if (isExpanding) {
    next.add(model.id);
    showDetailPanel.value = false;
    currentViewMode.value = `微观聚焦 ➔ ${model.displayText || model.id}`;
  } else {
    next.delete(model.id);
    currentViewMode.value = "全局大盘视图";
  }
  expandedAccessIds.value = next;

  const container = graphContainer.value;

  if (isExpanding) {
    if (container) {
      container.style.transition = "filter 0.4s ease-in, transform 0.4s ease-in";
      container.style.filter = "blur(12px) saturate(150%) brightness(1.3)";
      container.style.transform = "scale(1.08)";
    }
    if (graph) {
      graph.focusItem(model.id, true, { easing: "easeCubicIn", duration: 400 });
      const centerPt = { x: graph.getWidth() / 2, y: graph.getHeight() / 2 };
      graph.zoomTo(1.4, centerPt, true, { easing: "easeCubicIn", duration: 400 });
    }

    await new Promise((r) => setTimeout(r, 400));

    await renderGraph();

    if (graph) {
      const newParentItem = graph.findById(model.id);
      if (newParentItem) {
        graph.focusItem(newParentItem, false);
        const centerPt = { x: graph.getWidth() / 2, y: graph.getHeight() / 2 };
        graph.zoomTo(1.6, centerPt, false);
        graph.translate(0, -60, false);
      }
    }

    await new Promise((r) => setTimeout(r, 50));
    if (container) {
      container.style.transition = "filter 0.6s ease-out, transform 0.6s ease-out";
      container.style.filter = "blur(0px) saturate(100%) brightness(1)";
      container.style.transform = "scale(1)";
    }
  } else {
    if (container) {
      container.style.transition = "filter 0.3s ease-in, transform 0.3s ease-in";
      container.style.filter = "blur(8px) brightness(0.7)";
      container.style.transform = "scale(0.95)";
    }

    await new Promise((r) => setTimeout(r, 300));

    await renderGraph();
    if (graph) {
      graph.fitView(20, false);
    }

    await new Promise((r) => setTimeout(r, 50));
    if (container) {
      container.style.transition = "filter 0.6s ease-out, transform 0.6s ease-out";
      container.style.filter = "blur(0px) brightness(1)";
      container.style.transform = "scale(1)";
    }
  }
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
  icon.textContent = "CAM";
  info.className = "topology-ghost-info";
  name.textContent = model.displayText || model.id || "摄像头";
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
    Parent_ID: "",
    parentId: "",
    parent_id: "",
    parent_node_id: "",
    upstream_id: "",
    upstream_node_key: "",
    upstreamNodeKey: "",
    upstream_device_id: "",
    switch_device_id: "",
    switch_node_key: "",
    switch_ip: "",
    pos_x: null,
    pos_y: null,
    position_source: "orphan_pool",
    review_status: "pending_field_review",
  };
  
  edges.value = edges.value.filter((item) => !edgeTargetMatchesNode(item, cameraNode, aliasMap));
  
  if (!orphanList.value.some((item) => item.id === cameraNode.id)) {
    orphanList.value = [cameraNode, ...orphanList.value];
  }
  if (selectedNodeId.value === cameraNode.id) {
    selectedNodeId.value = "";
    selectedNodeDetail.value = null;
    selectedNodeDetailLoading.value = false;
  }
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
    ElMessage.success(`${cameraNode.displayText || cameraNode.ip} 已退回待核实资产池`);
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
    const parentId = cameraParentId(model);
    await animateNodeToOrphanPool(item, model);
    
    const result = unlinkCameraLocally(model);
    if (!result) {
      ElMessage.error("未找到摄像头资产数据，无法退回待核实池。");
      return;
    }

    // 🛡️ 局部手术拔除：直接更新角标，剔除节点
    if (parentId && graph) {
      const parentItem = graph.findById(parentId);
      if (parentItem) {
        const parentModel = parentItem.getModel();
        parentModel.cameraCount = Math.max(0, (parentModel.cameraCount || 1) - 1);
        graph.updateItem(parentItem, { cameraCount: parentModel.cameraCount });

        if (parentModel.cameraCount === 0 && expandedAccessIds.value.has(parentId)) {
          // 🔥 如果触发了深井收起动画，整个画布会被重建。重建后直接跳过后续的 DOM 操作！
          await toggleAccessCameraRing(parentModel); 
        } else {
          // 只有没有触发重建时，才手动擦除节点
          const camItem = graph.findById(model.id);
          if (camItem) {
            graph.removeItem(camItem);
          }
          nodes.value = [...nodes.value]; 
          enforcePhaseIsolation();
          graph.paint();
        }
      }
    }

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
  graph.on("viewportchange", () => {
    const zoom = graph.getZoom?.() || 1;
    if (Number.isFinite(zoom)) scheduleLodVisibility();
  });
  graph.on("wheelzoom", scheduleLodVisibility);
  graph.on("canvas:click", () => {
    resetSelectedNodeState();
  });
  graph.on("node:dblclick", async (event) => {
    const item = event.item;
    if (!item) return;
    const model = item.getModel?.();
    event.originalEvent?.preventDefault?.();
    event.originalEvent?.stopPropagation?.();
    showDetailPanel.value = false;

    if (model.kind !== "camera" && !model.virtual) {
      await toggleAccessCameraRing(model);
    }
  });
  graph.on("canvas:dblclick", async () => {
    showDetailPanel.value = false;

    if (expandedAccessIds.value.size > 0) {
      const expandedId = Array.from(expandedAccessIds.value)[0];
      const switchItem = graph.findById(expandedId);
      
      if (switchItem) {
        await toggleAccessCameraRing(switchItem.getModel());
        return;
      } else {
        expandedAccessIds.value.clear();
      }
    }

    currentViewMode.value = "全局大盘视图";
    selectedNodeId.value = "";
    graph.fitView(20, { easing: "easeCubic", duration: 600 });
    enforcePhaseIsolation();
    scheduleLodVisibility();
  });
  
  graph.on("node:click", async (event) => {
    const item = event.item;
    const model = item?.getModel();
    if (!model) return;
    
    if (model.id === selectedNodeId.value) {
      resetSelectedNodeState();
      return;
    }
    if (isCameraBadgeTarget(event.target)) {
      await toggleAccessCameraRing(model);
      return;
    }
    selectNode(model);
    showDetailPanel.value = true;
    enforcePhaseIsolation();
  });
  
  graph.on("node:contextmenu", (event) => {
    event.originalEvent?.preventDefault?.();
    const model = event.item?.getModel();
    if (!model) return;
    selectNode(model);
    detachCameraToOrphanPool(event.item);
  });
  
  graph.on("node:mouseenter", (event) => {
    const item = event.item;
    const model = item?.getModel();
    if (!item || !model) return;
    graph.setItemState(item, "selected", true);
    highlightRelatedEdges(item, true);
    applyLodVisibility();
    item.toFront();
    enforcePhaseIsolation();
  });
  
  graph.on("node:mouseleave", (event) => {
    const item = event.item;
    const model = item?.getModel();
    if (!item || !model) return;
    
    if (model.id !== selectedNodeId.value) {
      highlightRelatedEdges(item, false);
      graph.setItemState(item, "selected", false);
      applyNodeVisualState(item);
      applyLodVisibility();
      enforcePhaseIsolation();
    }
  });
  
  graph.on("node:dragstart", (event) => {
    if (!editMode.value) return;
    const item = event.item;
    const model = item?.getModel();

    if (model && model.kind !== "camera" && model.cameraCount > 0 && expandedAccessIds.value.has(model.id)) {
      const nextSet = new Set(expandedAccessIds.value);
      nextSet.delete(model.id);
      expandedAccessIds.value = nextSet;
      model.cameraExpanded = false;

      const linkedEdges = item.getEdges() || [];
      linkedEdges.forEach((edge) => {
        const target = edge.getTarget();
        const targetModel = target?.getModel();
        if (targetModel && targetModel.kind === "camera") {
          target.hide(); 
          edge.hide(); 
        }
      });

      graph.updateItem(item, model);
      enforcePhaseIsolation();
    }
  });
  
  graph.on("node:dragend", async (event) => {
    if (!editMode.value) return;
    const model = event.item?.getModel();
    if (!model) return;
    const snapped = snapPoint(model);
    graph.updateItem(event.item, snapped);
    enforcePhaseIsolation();
    await persistPosition({ ...model, ...snapped }, snapped.x, snapped.y);
  });
  
  graph.on("edge:mouseenter", (event) => {
    if (!event.item) return;
    event.item.toFront?.();
    applyEdgeVisualState(event.item, true);
  });

  graph.on("edge:dblclick", (event) => {
    const item = event.item;
    if (!item) return;
    event.originalEvent?.preventDefault?.();
    event.originalEvent?.stopPropagation?.();
    selectLink(item);
    graph.focusItem(item, true, { easing: "easeCubic", duration: 400 });
    window.setTimeout(() => {
      const centerPt = { x: graph.getWidth() / 2, y: graph.getHeight() / 2 };
      graph.zoomTo(2.0, centerPt, true, { easing: "easeCubic", duration: 500 });
    }, 450);
  });
  
  graph.on("edge:mouseleave", (event) => {
    if (event.item) {
      applyEdgeVisualState(event.item, false);
    }
  });
}

function nearestAttachableNode(point, maxDistance = 160) {
  if (!graph || !point) return null;
  let nearest = null;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const item of graph.getNodes()) {
    const model = item.getModel();
    if (!model || model.kind === "camera") continue;
    const dx = Number(model.x || 0) - point.x;
    const dy = Number(model.y || 0) - point.y;
    const distance = Math.sqrt(dx * dx + dy * dy);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearest = model;
    }
  }
  return nearest && nearestDistance <= maxDistance ? nearest : null;
}

function pointInsideBBox(point, bbox) {
  if (!point || !bbox) return false;
  const minX = Number.isFinite(Number(bbox.minX)) ? Number(bbox.minX) : Number(bbox.x);
  const minY = Number.isFinite(Number(bbox.minY)) ? Number(bbox.minY) : Number(bbox.y);
  const maxX = Number.isFinite(Number(bbox.maxX)) ? Number(bbox.maxX) : minX + Number(bbox.width || 0);
  const maxY = Number.isFinite(Number(bbox.maxY)) ? Number(bbox.maxY) : minY + Number(bbox.height || 0);
  return point.x >= minX && point.x <= maxX && point.y >= minY && point.y <= maxY;
}

function pointInsideNodeBody(point, model) {
  if (!point || !model) return false;
  const x = Number(model.x);
  const y = Number(model.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
  const width = graphNodeWidth(model);
  const height = graphNodeHeight(model);
  return (
    point.x >= x - width / 2
    && point.x <= x + width / 2
    && point.y >= y - height / 2
    && point.y <= y + height / 2
  );
}

let currentMagneticTargetId = null;

function findDropTargetSwitch(point) {
  if (!graph || !point) return null;
  let nearest = null;
  let minDistance = 280;

  graph.getNodes().forEach(item => {
    const group = item.getContainer();
    // 🛡️ 相位过滤：如果该节点当前被放逐在暗影界（无物理碰撞），直接无视，绝对不作为吸附目标！
    if (group && group.get("capture") === false) return; 

    const model = item.getModel();
    if (model.kind === "camera" || model.virtual) return;

    const dx = model.x - point.x;
    const dy = model.y - point.y;
    const distance = Math.sqrt(dx * dx + dy * dy);

    if (distance < minDistance) {
      minDistance = distance;
      nearest = item;
    }
  });
  return nearest;
}

function handleDragStart(event, item) {
  if (!editMode.value) {
    event.preventDefault();
    return;
  }
  draggedItem = item;
  event.dataTransfer.setData("text/plain", item.id);
  event.dataTransfer.effectAllowed = "copy";

  if (graph) {
    graph.getNodes().forEach(node => {
      const group = node.getContainer();
      if (group && group.get("capture") === false) return;
      const model = node.getModel();
      if (model.kind === "camera" || model.virtual) {
        group.attr("opacity", 0.25);
        group.get("children")?.forEach(s => s.attr("opacity", 0.25));
      }
    });
  }
}

function handleDragOver(event) {
  event.preventDefault();
  if (!draggedItem || !graph) return;

  const point = graph.getPointByClient(event.clientX, event.clientY);
  const targetItem = findDropTargetSwitch(point);
  const targetId = targetItem ? targetItem.getID() : null;

  if (currentMagneticTargetId !== targetId) {
    if (currentMagneticTargetId) {
      const oldItem = graph.findById(currentMagneticTargetId);
      if (oldItem) applyNodeVisualState(oldItem);
    }

    if (targetItem) {
      targetItem.toFront();
      const group = targetItem.getContainer();
      group.attr("opacity", 1);
      group.set("capture", true);
      const shell = group.find(s => s.get("name") === "shell");
      if (shell) {
        shell.attr({
          stroke: "#10b981",
          lineWidth: 4, 
          shadowColor: "#10b981",
          shadowBlur: 40,
          fill: "rgba(16, 185, 129, 0.3)",
        });
      }
    }
    currentMagneticTargetId = targetId;
  }
}

function clearDragVisuals() {
  if (!graph) return;
  if (currentMagneticTargetId) {
    const oldItem = graph.findById(currentMagneticTargetId);
    if (oldItem) applyNodeVisualState(oldItem);
    currentMagneticTargetId = null;
  }
  enforcePhaseIsolation();
  applyLodVisibility();
}

async function handleDrop(event) {
  event.preventDefault();
  if (!draggedItem || !graph) return;

  if (!editMode.value) {
    ElMessage.warning("当前为只读锁定状态，请先启用编辑模式。");
    draggedItem = null;
    return;
  }

  const point = graph.getPointByClient(event.clientX, event.clientY);
  const targetItem = findDropTargetSwitch(point);

  clearDragVisuals();

  if (!targetItem) {
    ElMessage.error("挂载失败：周围 280 像素内未检测到任何可用交换机！");
    draggedItem = null;
    return;
  }

  const targetModel = targetItem.getModel();

  if (targetModel.tier !== "access") {
    ElMessage.warning(`提示：您正在将摄像头越级挂载到 [${targetModel.tier.toUpperCase()}] 层设备！`);
  }

  await attachCameraToSwitch(draggedItem, targetModel);
  draggedItem = null;
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

    nodes.value = [...nodes.value]; 
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

    // 🛡️ 局部手术更新：不重启宇宙，直接修改数据并局部注入节点
    if (graph) {
      const parentItem = graph.findById(switchNode.id);
      if (parentItem) {
        const parentModel = parentItem.getModel();
        parentModel.cameraCount = (parentModel.cameraCount || 0) + 1;
        graph.updateItem(parentItem, { cameraCount: parentModel.cameraCount });

        if (!expandedAccessIds.value.has(switchNode.id)) {
          await toggleAccessCameraRing(parentModel);
        } else {
           // 深井已开，计算位置直接追加节点
           const existingCams = graph.getNodes().filter(n => n.getModel().kind === 'camera' && cameraParentId(n.getModel()) === parentModel.id);
           const index = existingCams.length;
           const COLS = 4;
           const SPACING_X = 110;
           const SPACING_Y = 32;
           const startX = parentModel.x - ((Math.min(parentModel.cameraCount, COLS) - 1) * SPACING_X) / 2;
           const startY = parentModel.y + graphNodeHeight(parentModel) / 2 + 40;
           const row = Math.floor(index / COLS);
           const col = index % COLS;
           
           const cameraGraphNode = {
             ...cameraNode,
             x: startX + col * SPACING_X,
             y: startY + row * SPACING_Y,
             type: "camera-leaf",
             label: "" // 屏蔽黑影
           };
           
           graph.addItem('node', cameraGraphNode);
           graph.addItem('edge', {
             id: `edge-${parentModel.id}-${cameraNode.id}`,
             source: parentModel.id,
             target: cameraNode.id,
             type: "animated-curve"
           });
           graph.layout?.();
           graph.refreshPositions?.();
           enforcePhaseIsolation();
           graph.paint();
        }
      }
      triggerNeonRadar(cameraNode.id);
    }

    ElMessage.success(`${cameraNode.displayText || cameraNode.ip} 已成功挂载`);
  } catch (error) {
    console.error(error);
    ElMessage.error("摄像头挂载写回失败，请检查网络或日志。");
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

watch(editMode, (val) => {
  if (!graph) return;
  if (val) {
    graph.addBehavior({ type: "drag-node", enableDelegate: true }, "default");
  } else {
    graph.removeBehavior("drag-node", "default");
  }
});

onMounted(async () => {
  document.addEventListener("keydown", handleGlobalKeydown);
  window.addEventListener("graphics-changed", handleGraphicsChanged);
  msgTimer = window.setInterval(() => {
    currentMsgIndex.value = (currentMsgIndex.value + 1) % messages.value.length;
  }, 8000);
  
  await loadTopology();
  await renderGraph();

  window.setTimeout(() => {
    if (route.query.focusNode) executeJump(route.query.focusNode);
  }, 500);

  resizeObserver = new ResizeObserver(() => {
    if (!graph || !graphContainer.value) return;
    if (resizeRenderPending) return;
    resizeRenderPending = true;
    window.requestAnimationFrame(() => {
      resizeRenderPending = false;
      const width = graphContainer.value.offsetWidth || 800;
      const height = graphContainer.value.offsetHeight || 600;
      graph.changeSize(width, height);
    });
  });
  if (graphContainer.value) resizeObserver.observe(graphContainer.value);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", handleGlobalKeydown);
  window.removeEventListener("graphics-changed", handleGraphicsChanged);
  if (msgTimer) {
    window.clearInterval(msgTimer);
    msgTimer = null;
  }
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  if (graph) {
    graph.destroy();
    graph = null;
  }
});
</script>

<style scoped>
.topology-editor-wrapper {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  min-height: 100%;
  color: #fff;
  background-color: #0b0f19;
  border-radius: 12px;
  overflow: hidden;
}

.topology-editor-wrapper.is-editing {
  box-shadow: inset 0 0 0 2px rgba(245, 158, 11, 0.72);
}

.orphan-sidebar {
  position: absolute;
  z-index: 50;
  top: 0;
  left: 0;
  height: 100%;
  width: 310px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(64, 158, 255, 0.22);
  background:
    radial-gradient(circle at 0 0, rgba(64, 158, 255, 0.12), transparent 32%),
    rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(12px);
  box-shadow: 18px 0 46px rgba(0, 0, 0, 0.26);
  transform: translateX(0);
  transition: transform 0.28s ease, background-color 0.22s ease;
}

.orphan-sidebar.collapsed {
  transform: translateX(calc(-100% + 46px));
}

.orphan-drawer-toggle {
  position: absolute;
  z-index: 2;
  top: 50%;
  right: -24px;
  width: 24px;
  height: 58px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(103, 232, 249, 0.36);
  border-left: 0;
  border-radius: 0 8px 8px 0;
  color: #67e8f9;
  background: rgba(15, 23, 42, 0.82);
  backdrop-filter: blur(12px);
  box-shadow: 8px 0 26px rgba(0, 0, 0, 0.28);
  cursor: pointer;
  font-size: 22px;
  line-height: 1;
  transform: translateY(-50%);
  transition: border-color 0.2s, background-color 0.2s, transform 0.2s;
}

.orphan-drawer-toggle:hover {
  border-color: rgba(103, 232, 249, 0.86);
  background: rgba(14, 116, 144, 0.48);
  transform: translateY(-50%) translateX(1px);
}

.orphan-sidebar.collapsed .sidebar-header,
.orphan-sidebar.collapsed .lock-status,
.orphan-sidebar.collapsed .cluster-summary,
.orphan-sidebar.collapsed .orphan-list {
  opacity: 0;
  pointer-events: none;
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
  font-size: 10px;
  font-weight: 900;
  background: rgba(64, 158, 255, 0.22);
}

.item-info {
  min-width: 0;
  display: grid;
  gap: 2px;
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

.detail-sidebar {
  position: absolute;
  z-index: 50;
  top: 0;
  right: 0;
  width: 286px;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-left: 1px solid rgba(64, 158, 255, 0.22);
  background: rgba(15, 23, 42, 0.9);
  backdrop-filter: blur(12px);
  box-shadow: -18px 0 46px rgba(0, 0, 0, 0.3);
  overflow-y: auto;
  opacity: 0;
  pointer-events: none;
  transform: translateX(100%);
  transition: transform 0.28s ease, opacity 0.22s ease;
}

.detail-sidebar.open {
  opacity: 1;
  pointer-events: auto;
  transform: translateX(0);
}

.detail-header,
.detail-title,
.detail-row {
  display: grid;
  gap: 4px;
}

.detail-header {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(64, 158, 255, 0.18);
}

.detail-header > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.detail-close {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 8px;
  color: #e2e8f0;
  background: rgba(15, 23, 42, 0.48);
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
  transition: border-color 0.2s, color 0.2s, background-color 0.2s;
}

.detail-close:hover {
  border-color: rgba(103, 232, 249, 0.78);
  color: #67e8f9;
  background: rgba(8, 47, 73, 0.62);
}

.detail-header strong,
.detail-title strong {
  color: #f8fbff;
  font-size: 15px;
}

.detail-header span,
.detail-title span,
.detail-empty {
  color: #8892a0;
  font-size: 12px;
  line-height: 1.5;
}

.detail-grid {
  display: grid;
  gap: 8px;
}

.detail-row {
  padding: 9px 10px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.58);
}

.detail-row span {
  color: #93c5fd;
  font-size: 11px;
  font-weight: 800;
}

.detail-row strong {
  color: #e5edf8;
  font-size: 12px;
  line-height: 1.45;
  word-break: break-word;
}

.detail-warning {
  padding: 9px 10px;
  border: 1px solid rgba(245, 158, 11, 0.35);
  border-radius: 8px;
  color: #facc15;
  background: rgba(120, 53, 15, 0.28);
  font-size: 12px;
  line-height: 1.45;
}

.edit-form-container {
  display: grid;
  gap: 12px;
  margin-bottom: 16px;
}

.edit-form-group {
  display: grid;
  gap: 6px;
}

.edit-form-group label {
  color: #93c5fd;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.5px;
}

.hud-input {
  width: 100%;
  padding: 8px 12px;
  background: rgba(15, 23, 42, 0.65);
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 6px;
  color: #f8fbff;
  font-size: 12px;
  font-family: "Consolas", monospace;
  transition: all 0.2s;
}

.hud-input:focus {
  outline: none;
  border-color: #38bdf8;
  box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.25);
  background: rgba(15, 23, 42, 0.9);
}

.detail-action-zone {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed rgba(64, 158, 255, 0.22);
}

.verify-action-btn {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(16, 185, 129, 0.4);
  border-radius: 8px;
  color: #34d399;
  background: rgba(6, 78, 59, 0.4);
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
  transition: all 0.2s;
}

.verify-action-btn:hover {
  border-color: #10b981;
  background: rgba(6, 78, 59, 0.8);
  box-shadow: 0 0 16px rgba(16, 185, 129, 0.25);
  transform: translateY(-1px);
}

.verify-action-btn.is-update {
  border-color: rgba(56, 189, 248, 0.4);
  color: #38bdf8;
  background: rgba(12, 74, 110, 0.4);
}

.verify-action-btn.is-update:hover {
  border-color: #0ea5e9;
  background: rgba(12, 74, 110, 0.8);
  box-shadow: 0 0 16px rgba(14, 165, 233, 0.25);
}

.canvas-main {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background-color: #08111f;
  background-image: 
    linear-gradient(rgba(64, 158, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(64, 158, 255, 0.08) 1px, transparent 1px);
  background-size: 32px 32px;
}

.hud-capsule {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 20px;
  padding: 6px 24px;
  max-width: 45vw;
  background: rgba(15, 23, 42, 0.4);
  backdrop-filter: blur(20px) saturate(150%);
  border: 1px solid rgba(103, 232, 249, 0.4);
  border-radius: 40px;
  box-shadow: 0 0 20px rgba(103, 232, 249, 0.15), inset 0 0 10px rgba(103, 232, 249, 0.05);
  z-index: 40;
}

.hud-breadcrumb {
  flex: 0 0 auto;
  max-width: 190px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hud-mode-label {
  color: #94a3b8;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 1px;
}

.hud-mode-value {
  margin-left: 8px;
  color: #f8fafc;
  font-size: 12px;
  font-weight: 700;
}

.hud-ticker {
  flex: 1 1 300px;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.led-ticker-window {
  flex: 1;
  min-width: 0;
  height: 24px;
  overflow: hidden;
  display: flex;
  align-items: center;
  border-left: 1px solid rgba(255, 255, 255, 0.1);
  border-right: 1px solid rgba(255, 255, 255, 0.1);
  padding: 0 16px;
  position: relative;
}

.status-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
  margin-right: 8px;
}

.status-alarm {
  background: #ef4444;
  box-shadow: 0 0 8px #ef4444;
}

.status-workorder {
  background: #3b82f6;
  box-shadow: 0 0 8px #3b82f6;
}

.status-asset {
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
}

.led-message {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
  color: #67e8f9;
  font-family: "Consolas", monospace;
  font-size: 13px;
  letter-spacing: 1px;
}

.message-type {
  flex: 0 0 auto;
  margin-right: 8px;
  font-weight: 800;
}

.message-text {
  min-width: 0;
  overflow: hidden;
  color: #e0f2fe;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.slide-fade-enter-from {
  transform: translateY(15px);
  opacity: 0;
}

.slide-fade-leave-to {
  transform: translateY(-15px);
  opacity: 0;
}

.hud-control-zone {
  flex: 0 0 auto;
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.hud-stat {
  color: rgba(248, 251, 255, 0.88);
  font-size: 12px;
  font-weight: 800;
}

.hud-stat.online {
  color: #67e8f9;
}

.hud-stat-separator {
  width: 1px;
  height: 14px;
  background: rgba(255, 255, 255, 0.14);
}

.offline-jump-button {
  border: 0;
  padding: 2px 6px;
  border-radius: 4px;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
  cursor: pointer;
  font-size: 12px;
  font-weight: 900;
}

.offline-dropdown {
  position: absolute;
  top: calc(100% + 12px);
  right: 0;
  width: 220px;
  display: grid;
  gap: 6px;
  padding: 10px;
  border: 1px solid rgba(239, 68, 68, 0.28);
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.88);
  backdrop-filter: blur(18px) saturate(140%);
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.36);
}

.offline-dropdown-item {
  display: grid;
  gap: 2px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 8px;
  padding: 8px 10px;
  text-align: left;
  background: rgba(30, 41, 59, 0.48);
  cursor: pointer;
}

.offline-dropdown-item:hover {
  border-color: rgba(239, 68, 68, 0.55);
  background: rgba(127, 29, 29, 0.38);
}

.offline-dropdown-item strong {
  color: #f8fafc;
  font-size: 12px;
}

.offline-dropdown-item span,
.offline-dropdown-empty {
  color: #94a3b8;
  font-size: 11px;
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
  position: absolute;
  inset: 0;
  z-index: 1;
  width: 100%;
  height: 100%;
  outline: none;
  /* 确保不闪屏的关键底色 */
  background-color: transparent; 
}

:deep(.el-switch__label) {
  color: #cbd5e1;
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

/* HUD 搜索与巡航样式 */
.cyber-hud-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  width: 100%;
}

.hud-section {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  white-space: nowrap;
}

.hud-label {
  color: rgba(148, 163, 184, 0.86);
  font-size: 12px;
  font-weight: 700;
}

.hud-value {
  max-width: 220px;
  overflow: hidden;
  color: #f8fafc;
  font-size: 13px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hud-divider {
  width: 1px;
  height: 18px;
  flex: 0 0 auto;
  background: linear-gradient(180deg, transparent, rgba(148, 163, 184, 0.42), transparent);
}

.ticker-section {
  flex: 1;
  min-width: 150px;
}

.ticker-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: #38bdf8;
  box-shadow: 0 0 14px rgba(56, 189, 248, 0.86);
}

.ticker-text {
  min-width: 0;
  overflow: hidden;
  color: rgba(226, 232, 240, 0.88);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hud-search-box {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 16px;
  background: rgba(0, 0, 0, 0.4);
}

.hud-search-box input {
  width: 160px;
  border: none;
  outline: none;
  padding: 4px 12px;
  color: #f8fafc;
  background: transparent;
  font-size: 12px;
}

.hud-search-box input::placeholder {
  color: #475569;
}

.search-btn {
  border: none;
  padding: 4px 12px;
  color: #38bdf8;
  background: rgba(14, 165, 233, 0.2);
  font-weight: 800;
  cursor: pointer;
  transition: all 0.2s;
}

.search-btn:hover {
  background: rgba(14, 165, 233, 0.4);
}

.stats-section {
  gap: 10px;
}

.stat-online {
  color: #34d399;
  font-weight: 800;
}

.stat-offline {
  color: #ef4444;
  font-weight: 800;
  transition: all 0.2s;
}

.stat-offline.clickable {
  border: 1px dashed rgba(239, 68, 68, 0.4);
  border-radius: 12px;
  padding: 2px 8px;
  cursor: pointer;
}

.stat-offline.clickable:hover {
  border-style: solid;
  background: rgba(239, 68, 68, 0.15);
  box-shadow: 0 0 12px rgba(239, 68, 68, 0.3);
}

.pulse {
  animation: offline-pulse 1.8s ease-in-out infinite;
}

@keyframes offline-pulse {
  0%,
  100% {
    filter: drop-shadow(0 0 0 rgba(239, 68, 68, 0));
  }
  50% {
    filter: drop-shadow(0 0 8px rgba(239, 68, 68, 0.5));
  }
}

@media (max-width: 1180px) {
  .hud-value {
    max-width: 150px;
  }

  .hud-search-box input {
    width: 120px;
  }

  .ticker-section {
    display: none;
  }
}

</style>
