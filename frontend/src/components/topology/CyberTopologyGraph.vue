<template>
  <section class="blueprint-topology">
    <div class="topology-toolbar">
      <div>
        <p>G6 DAGRE BLUEPRINT</p>
        <strong>{{ scopeTitle }}</strong>
        <span>{{ graphStats }}</span>
      </div>
      <div class="topology-actions">
        <button class="blueprint-btn" @click="fitGraph">居中适配</button>
        <button class="blueprint-btn" @click="resetZoom">重置缩放</button>
        <button class="blueprint-btn" @click="clearSelection">清除高亮</button>
      </div>
    </div>

    <div class="topology-hud">
      <article v-for="item in summaryStats" :key="item.label">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
      <div class="legend-strip">
        <span><i class="physical"></i>主干物理链路</span>
        <span><i class="cross"></i>横向/冗余勾连</span>
        <span><i class="online"></i>在线</span>
        <span><i class="offline"></i>离线</span>
        <span><i class="alarm"></i>告警</span>
      </div>
    </div>

    <section class="visible-blueprint-board">
      <div class="core-rack">
        <div class="core-card">
          <span>核心层</span>
          <strong>{{ coreGraphNode?.label || "总控室核心网" }}</strong>
          <small>{{ coreGraphNode?.ip || "-" }} / 下联 {{ switchGraphNodes.length }} 台交换机</small>
        </div>
        <div class="realtime-indicator">
          <i></i>
          <span>WebSocket Mock 实时状态流 / 500ms 缓冲局部刷新</span>
        </div>
      </div>

      <div class="switch-card-grid" aria-label="交换机智能状态卡片矩阵">
        <button
          v-for="node in switchGraphNodes"
          :key="node.id"
          class="switch-dom-card"
          :class="boardNodeClass(node)"
          @click="selectBoardNode(node)"
        >
          <div class="switch-dom-head">
            <div>
              <strong>{{ node.label }}</strong>
              <span>{{ node.ip || "-" }}</span>
            </div>
            <small>{{ node.floor || "未分层" }}</small>
          </div>

          <div class="switch-dom-stats">
            <span class="online">在线 {{ countByStatus(node, "online") }}</span>
            <span class="offline">离线 {{ countByStatus(node, "offline") }}</span>
            <span class="alarm">告警 {{ countByStatus(node, "alarm") }}</span>
          </div>

          <div class="dom-matrix" aria-label="摄像头状态点阵">
            <i
              v-for="camera in node.cameras.slice(0, 96)"
              :key="camera.id"
              :class="camera.status"
              :title="`${camera.ip || camera.id} / ${camera.status}`"
            ></i>
          </div>

          <div class="switch-dom-foot">
            <span>{{ node.roomLabel || "井位待补" }}</span>
            <small>{{ node.cameras.length }} 路</small>
          </div>
        </button>
      </div>
    </section>

    <div ref="containerRef" class="blueprint-stage"></div>
  </section>
</template>

<script setup>
import G6 from "@antv/g6";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps({
  architecture: {
    type: Object,
    required: true,
  },
  accessNodes: {
    type: Array,
    default: () => [],
  },
  aggregationNodes: {
    type: Array,
    default: () => [],
  },
  coreAnchor: {
    type: Object,
    default: null,
  },
  selectedNodeKey: {
    type: String,
    default: "",
  },
  scopeTitle: {
    type: String,
    default: "中央大道全图",
  },
});

const emit = defineEmits(["select-node-key", "select-edge-key", "message"]);

const containerRef = ref(null);
const graphRef = ref(null);
const graphData = ref({ nodes: [], edges: [] });
const resizeObserver = ref(null);
const selectedGraphId = ref("");
const messageBuffer = [];
const alertNodeIds = new Set();
let bufferFlushTimer = null;
let mockStatusTimer = null;

const CARD_WIDTH = 230;
const CARD_HEIGHT = 154;
const CORE_WIDTH = 260;
const CORE_HEIGHT = 108;

let customElementsRegistered = false;

const graphStats = computed(() => {
  const switchCount = graphData.value.nodes.filter((node) => node.nodeRole === "switch").length;
  const cameraCount = graphData.value.nodes.reduce((sum, node) => sum + (node.cameras?.length || 0), 0);
  const crossCount = graphData.value.edges.filter((edge) => edge.edgeRole === "cross").length;
  return `${switchCount} 台交换机 / ${cameraCount} 路摄像头聚合 / ${crossCount} 条勾连`;
});

const coreGraphNode = computed(() => graphData.value.nodes.find((node) => node.nodeRole === "core") || null);

const switchGraphNodes = computed(() => graphData.value.nodes.filter((node) => node.nodeRole === "switch"));

const summaryStats = computed(() => {
  const nodes = graphData.value.nodes;
  const switchCount = nodes.filter((node) => node.nodeRole === "switch").length;
  const cameras = nodes.flatMap((node) => node.cameras || []);
  return [
    { label: "核心节点", value: nodes.some((node) => node.nodeRole === "core") ? 1 : 0 },
    { label: "交换机卡片", value: switchCount },
    { label: "摄像头矩阵", value: cameras.length },
    { label: "在线", value: cameras.filter((camera) => camera.status === "online").length },
    { label: "离线", value: cameras.filter((camera) => camera.status === "offline").length },
    { label: "告警", value: cameras.filter((camera) => camera.status === "alarm").length },
  ];
});

const architectureNodeLookup = computed(() => {
  const map = new Map();
  for (const node of props.architecture.nodes || []) {
    if (node.node_key) map.set(node.node_key, node);
    if (node.ip) map.set(`ip:${node.ip}`, node);
  }
  return map;
});

function registerBlueprintElements() {
  if (customElementsRegistered) return;
  customElementsRegistered = true;

  G6.registerNode(
    "core-blueprint-card",
    {
      draw(cfg, group) {
        const width = cfg.size?.[0] || CORE_WIDTH;
        const height = cfg.size?.[1] || CORE_HEIGHT;
        const keyShape = group.addShape("rect", {
          attrs: {
            x: -width / 2,
            y: -height / 2,
            width,
            height,
            radius: 14,
            fill: "rgba(12, 40, 64, 0.92)",
            stroke: "#67e8f9",
            lineWidth: 2,
            shadowColor: "rgba(103, 232, 249, 0.42)",
            shadowBlur: 24,
          },
          name: "core-shell",
        });

        group.addShape("circle", {
          attrs: {
            x: -width / 2 + 34,
            y: -height / 2 + 34,
            r: 17,
            fill: "rgba(34, 211, 238, 0.28)",
            stroke: "#67e8f9",
            lineWidth: 2,
          },
          name: "core-icon",
        });
        group.addShape("text", {
          attrs: {
            x: -width / 2 + 64,
            y: -height / 2 + 29,
            text: cfg.label || "总控室核心网",
            fill: "#f8fbff",
            fontSize: 16,
            fontWeight: 800,
            textBaseline: "middle",
          },
          name: "core-label",
        });
        group.addShape("text", {
          attrs: {
            x: -width / 2 + 64,
            y: -height / 2 + 55,
            text: cfg.ip || "核心地址待确认",
            fill: "rgba(203, 233, 255, 0.72)",
            fontSize: 12,
            textBaseline: "middle",
          },
          name: "core-ip",
        });
        group.addShape("text", {
          attrs: {
            x: -width / 2 + 20,
            y: height / 2 - 24,
            text: `下联 ${cfg.switchCount || 0} 台交换机 / 承载 ${cfg.cameraCount || 0} 路摄像头`,
            fill: "rgba(148, 220, 255, 0.86)",
            fontSize: 12,
            textBaseline: "middle",
          },
          name: "core-meta",
        });
        return keyShape;
      },
      setState(name, value, item) {
        const shell = item.getContainer().find((shape) => shape.get("name") === "core-shell");
        if (!shell) return;
        if ((name === "selected" || name === "focus") && value) {
          shell.attr({ stroke: "#fbbf24", shadowColor: "rgba(251, 191, 36, 0.55)", shadowBlur: 34 });
        } else if (name === "inactive") {
          shell.attr({ opacity: value ? 0.18 : 1 });
        } else if (!value) {
          shell.attr({ stroke: "#67e8f9", shadowColor: "rgba(103, 232, 249, 0.42)", shadowBlur: 24, opacity: 1 });
        }
      },
    },
    "single-node",
  );

  G6.registerNode(
    "switch-smart-card",
    {
      draw(cfg, group) {
        const width = cfg.size?.[0] || CARD_WIDTH;
        const height = cfg.size?.[1] || CARD_HEIGHT;
        const cameras = cfg.cameras || [];
        const online = cameras.filter((camera) => camera.status === "online").length;
        const offline = cameras.filter((camera) => camera.status === "offline").length;
        const alarm = cameras.filter((camera) => camera.status === "alarm").length;
        const portCapacity = Number(cfg.portCapacity || 24);
        const usedPorts = Math.min(portCapacity, Math.max(cameras.length, Number(cfg.usedPorts || 0)));
        const loadRate = portCapacity ? usedPorts / portCapacity : 0;

        const keyShape = group.addShape("rect", {
          attrs: {
            x: -width / 2,
            y: -height / 2,
            width,
            height,
            radius: 12,
            fill: "rgba(15, 23, 42, 0.86)",
            stroke: cfg.hasRisk ? "#fbbf24" : "#38bdf8",
            lineWidth: 1.5,
            shadowColor: cfg.hasRisk ? "rgba(251, 191, 36, 0.28)" : "rgba(56, 189, 248, 0.28)",
            shadowBlur: 18,
          },
          name: "card-shell",
        });

        group.addShape("rect", {
          attrs: {
            x: -width / 2,
            y: -height / 2,
            width,
            height: 42,
            radius: [12, 12, 0, 0],
            fill: "rgba(14, 116, 144, 0.24)",
          },
          name: "card-header",
        });
        group.addShape("rect", {
          attrs: {
            x: -width / 2 + 13,
            y: -height / 2 + 12,
            width: 20,
            height: 18,
            radius: 4,
            fill: "rgba(59, 130, 246, 0.34)",
            stroke: "#60a5fa",
            lineWidth: 1,
          },
          name: "switch-icon",
        });
        group.addShape("text", {
          attrs: {
            x: -width / 2 + 42,
            y: -height / 2 + 15,
            text: ellipsis(cfg.label || "接入交换机", 18),
            fill: "#f8fbff",
            fontSize: 13,
            fontWeight: 800,
            textBaseline: "middle",
          },
          name: "card-title",
        });
        group.addShape("text", {
          attrs: {
            x: -width / 2 + 42,
            y: -height / 2 + 31,
            text: cfg.ip || "-",
            fill: "rgba(203, 233, 255, 0.68)",
            fontSize: 10,
            textBaseline: "middle",
          },
          name: "card-ip",
        });

        const progressX = width / 2 - 70;
        const progressY = -height / 2 + 13;
        group.addShape("rect", {
          attrs: {
            x: progressX,
            y: progressY,
            width: 52,
            height: 7,
            radius: 4,
            fill: "rgba(30, 41, 59, 0.92)",
          },
          name: "port-progress-bg",
        });
        group.addShape("rect", {
          attrs: {
            x: progressX,
            y: progressY,
            width: Math.max(4, Math.round(52 * loadRate)),
            height: 7,
            radius: 4,
            fill: loadRate > 0.85 ? "#f59e0b" : "#22d3ee",
          },
          name: "port-progress",
        });
        group.addShape("text", {
          attrs: {
            x: width / 2 - 18,
            y: -height / 2 + 29,
            text: `${Math.round(loadRate * 100)}%`,
            fill: "rgba(226, 246, 255, 0.82)",
            fontSize: 9,
            textAlign: "right",
            textBaseline: "middle",
          },
          name: "port-rate",
        });

        drawMetric(group, -width / 2 + 16, -height / 2 + 60, "#22c55e", online, "在线", "online");
        drawMetric(group, -width / 2 + 84, -height / 2 + 60, "#ef4444", offline, "离线", "offline");
        drawMetric(group, -width / 2 + 152, -height / 2 + 60, "#fbbf24", alarm, "告警", "alarm");

        // 摄像头不作为全局 Node 渲染，而是在交换机卡片内以 4x4 状态点阵表达。
        // 这样 616 路摄像头只增加卡片内部 Canvas Shape，不参与图布局和边路由计算。
        const matrixStartX = -width / 2 + 16;
        const matrixStartY = -height / 2 + 98;
        const dotSize = 4;
        const gap = 4;
        const columns = 24;
        const maxDots = 96;
        cameras.slice(0, maxDots).forEach((camera, index) => {
          const col = index % columns;
          const row = Math.floor(index / columns);
          group.addShape("rect", {
            attrs: {
              x: matrixStartX + col * (dotSize + gap),
              y: matrixStartY + row * (dotSize + gap),
              width: dotSize,
              height: dotSize,
              radius: 1,
              fill: cameraStatusColor(camera.status),
              opacity: camera.status === "unconfigured" ? 0.42 : 0.95,
            },
            name: `camera-dot-${index}`,
          });
        });

        if (cameras.length > maxDots) {
          group.addShape("text", {
            attrs: {
              x: width / 2 - 18,
              y: height / 2 - 14,
              text: `+${cameras.length - maxDots}`,
              fill: "#93c5fd",
              fontSize: 10,
              textAlign: "right",
              textBaseline: "middle",
            },
            name: "camera-more",
          });
        }
        return keyShape;
      },
      setState(name, value, item) {
        const group = item.getContainer();
        const shell = group.find((shape) => shape.get("name") === "card-shell");
        const header = group.find((shape) => shape.get("name") === "card-header");
        if (!shell) return;

        if (name === "alert") {
          if (value) {
            shell.stopAnimate?.();
            shell.animate(
              (ratio) => {
                const pulse = Math.sin(ratio * Math.PI * 2);
                return {
                  stroke: "#ef4444",
                  shadowColor: "rgba(239, 68, 68, 0.68)",
                  shadowBlur: 26 + pulse * 9,
                  lineWidth: 2.4,
                };
              },
              {
                duration: 1050,
                repeat: true,
              },
            );
            header?.attr({ fill: "rgba(239, 68, 68, 0.18)" });
          } else {
            shell.stopAnimate?.();
            const model = item.getModel();
            shell.attr({
              stroke: model.hasRisk ? "#fbbf24" : "#38bdf8",
              lineWidth: 1.5,
              shadowColor: model.hasRisk ? "rgba(251, 191, 36, 0.28)" : "rgba(56, 189, 248, 0.28)",
              shadowBlur: 18,
            });
            header?.attr({ fill: "rgba(14, 116, 144, 0.24)" });
          }
          return;
        }

        if ((name === "selected" || name === "focus") && value) {
          shell.attr({ stroke: "#fbbf24", lineWidth: 2.4, shadowColor: "rgba(251, 191, 36, 0.5)", shadowBlur: 30, opacity: 1 });
          header?.attr({ fill: "rgba(251, 191, 36, 0.16)" });
        } else if (name === "active" && value) {
          shell.attr({ stroke: "#67e8f9", lineWidth: 2.2, shadowColor: "rgba(103, 232, 249, 0.48)", shadowBlur: 26, opacity: 1 });
        } else if (name === "inactive") {
          group.get("children").forEach((shape) => shape.attr({ opacity: value ? 0.18 : 1 }));
        } else if (!value) {
          const model = item.getModel();
          group.get("children").forEach((shape) => shape.attr({ opacity: 1 }));
          shell.attr({
            stroke: model.hasRisk ? "#fbbf24" : "#38bdf8",
            lineWidth: 1.5,
            shadowColor: model.hasRisk ? "rgba(251, 191, 36, 0.28)" : "rgba(56, 189, 248, 0.28)",
            shadowBlur: 18,
          });
          header?.attr({ fill: "rgba(14, 116, 144, 0.24)" });
        }
      },
      update(cfg, item) {
        // 高频状态更新只改文字和点阵，不清空整个节点，避免 updateItem 触发多余绘制。
        const group = item.getContainer();
        const cameras = cfg.cameras || [];
        const counts = cameraCounts(cameras);
        const onlineText = group.find((shape) => shape.get("name") === "metric-text-online");
        const offlineText = group.find((shape) => shape.get("name") === "metric-text-offline");
        const alarmText = group.find((shape) => shape.get("name") === "metric-text-alarm");
        onlineText?.attr({ text: `在线 ${counts.online}` });
        offlineText?.attr({ text: `离线 ${counts.offline}` });
        alarmText?.attr({ text: `告警 ${counts.alarm}` });

        cameras.slice(0, 96).forEach((camera, index) => {
          const dot = group.find((shape) => shape.get("name") === `camera-dot-${index}`);
          dot?.attr({
            fill: cameraStatusColor(camera.status),
            opacity: camera.status === "unconfigured" ? 0.42 : 0.95,
          });
        });

        const model = item.getModel();
        model.cameras = cameras;
        model.hasRisk = cfg.hasRisk;
        model.usedPorts = cfg.usedPorts;
      },
    },
    "single-node",
  );
}

function drawMetric(group, x, y, color, value, label, key) {
  group.addShape("rect", {
    attrs: {
      x,
      y,
      width: 56,
      height: 22,
      radius: 8,
      fill: "rgba(2, 8, 23, 0.58)",
      stroke: color,
      lineWidth: 1,
      opacity: 0.9,
    },
    name: `metric-${key}`,
  });
  group.addShape("circle", {
    attrs: {
      x: x + 10,
      y: y + 11,
      r: 3,
      fill: color,
    },
    name: `metric-dot-${key}`,
  });
  group.addShape("text", {
    attrs: {
      x: x + 18,
      y: y + 11,
      text: `${label} ${value}`,
      fill: "#e5f4ff",
      fontSize: 10,
      fontWeight: 700,
      textBaseline: "middle",
    },
    name: `metric-text-${key}`,
  });
}

function cameraCounts(cameras) {
  return {
    online: cameras.filter((camera) => camera.status === "online").length,
    offline: cameras.filter((camera) => camera.status === "offline").length,
    alarm: cameras.filter((camera) => camera.status === "alarm").length,
  };
}

function countByStatus(node, status) {
  return (node.cameras || []).filter((camera) => camera.status === status).length;
}

function boardNodeClass(node) {
  const hasAlarm = countByStatus(node, "alarm") > 0;
  const hasOffline = countByStatus(node, "offline") > 0;
  return {
    selected: selectedGraphId.value === node.id || props.selectedNodeKey === node.nodeKey,
    alarm: hasAlarm,
    offline: !hasAlarm && hasOffline,
  };
}

function selectBoardNode(node) {
  selectedGraphId.value = node.id;
  if (node.nodeKey) emit("select-node-key", node.nodeKey);
  emit("message", `${node.label || node.ip} 已在拓扑卡片矩阵中选中。`);
  console.table(node.cameras || []);
  const graphNode = graphRef.value?.findById(node.id);
  if (graphNode) focusNode(graphNode, true);
}

function cameraStatusColor(status) {
  if (status === "offline") return "#ef4444";
  if (status === "alarm") return "#fbbf24";
  if (status === "unconfigured") return "#64748b";
  return "#22c55e";
}

function ellipsis(text, maxLength) {
  const value = String(text || "");
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}...` : value;
}

function stableHash(value) {
  const text = String(value || "");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function nodeByKey(nodeKey) {
  return architectureNodeLookup.value.get(nodeKey) || null;
}

function makeCameraArray(switchSource, count) {
  const baseIp = switchSource.ip || switchSource.node?.ip || "10.0.0.0";
  const seed = stableHash(`${baseIp}-${switchSource.node_key || switchSource.label || ""}`);
  const total = Math.max(0, Number(count || 0));

  return Array.from({ length: total }, (_, index) => {
    const score = (seed + index * 17) % 100;
    let status = "online";
    if (score > 93) status = "offline";
    else if (score > 84) status = "alarm";
    else if (score < 3) status = "unconfigured";

    return {
      id: `${switchSource.node_key || baseIp}-cam-${index + 1}`,
      ip: switchSource.camera_ips?.[index] || deriveCameraIp(baseIp, index),
      mac: `02:16:${((seed + index) % 255).toString(16).padStart(2, "0")}:9a:${(index % 255).toString(16).padStart(2, "0")}:cc`,
      status,
      channel: index + 1,
    };
  });
}

function deriveCameraIp(baseIp, index) {
  const parts = String(baseIp).split(".");
  if (parts.length !== 4) return `camera-${index + 1}`;
  const last = Math.max(1, Math.min(254, Number(parts[3] || 1) + index + 1));
  return `${parts[0]}.${parts[1]}.${parts[2]}.${last}`;
}

function normalizeNodeId(value) {
  return String(value || "").replaceAll(":", "_").replaceAll("/", "_").replaceAll(" ", "_");
}

function buildCoreNode(cameraCount, switchCount) {
  const coreRaw = props.coreAnchor?.node_key ? nodeByKey(props.coreAnchor.node_key) || props.coreAnchor : props.coreAnchor;
  return {
    id: "core-node",
    type: "core-blueprint-card",
    nodeRole: "core",
    nodeKey: coreRaw?.node_key || props.coreAnchor?.node_key || "core-node",
    label: coreRaw?.label || props.coreAnchor?.label || "总控室核心网",
    ip: coreRaw?.ip || props.coreAnchor?.ip || "10.0.68.254",
    switchCount,
    cameraCount,
    size: [CORE_WIDTH, CORE_HEIGHT],
    x: 640,
    y: 90,
  };
}

function buildSwitchNodes() {
  const accessList = collectSwitchSources();
  return accessList.map((source, index) => {
    const raw = source.node || nodeByKey(source.node_key) || source;
    const nodeKey = raw.node_key || source.node_key || `switch-${index + 1}`;
    const cameraCount = Number(source.camera_count || source.downstream_camera_count || raw.camera_count || 0);
    const cameras = makeCameraArray({ ...source, ...raw, node_key: nodeKey }, cameraCount || 8);
    const hasRisk = cameras.some((camera) => camera.status === "offline" || camera.status === "alarm") || raw.review_status === "needs_field_check";

    return {
      id: `switch-${normalizeNodeId(nodeKey)}`,
      type: "switch-smart-card",
      nodeRole: "switch",
      nodeKey,
      label: raw.label || source.label || raw.ip || source.ip || `接入交换机 ${index + 1}`,
      ip: raw.ip || source.ip || "",
      floor: raw.floor || source.floor || "",
      roomLabel: raw.room_label || source.room_label || "",
      parentSwitchIp: source.parent_switch_ip || raw.parent_switch_ip || "",
      portCapacity: Number(raw.port_capacity || source.port_capacity || 24),
      usedPorts: Number(raw.used_ports || source.used_ports || cameras.length),
      cameras,
      hasRisk,
      size: [CARD_WIDTH, CARD_HEIGHT],
    };
  });
}

function collectSwitchSources() {
  const mergeUniqueSources = (items) => {
    const seen = new Set();
    const rows = [];
    for (const item of items) {
      const key = item?.node_key || item?.node?.node_key || item?.ip || item?.node?.ip;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      rows.push(item);
    }
    return rows;
  };

  const visibleSources = mergeUniqueSources([...(props.aggregationNodes || []), ...(props.accessNodes || [])]);
  if (visibleSources.length) return visibleSources;

  const fromFloorCards = [];
  for (const item of props.architecture.simplified?.aggregation_switches || []) {
    fromFloorCards.push({
      ...item,
      node: nodeByKey(item.node_key) || item.node,
      role: item.role || "汇聚/级联交换机",
    });
  }
  for (const floor of props.architecture.simplified?.floor_cards || []) {
    for (const room of floor.rooms || []) {
      for (const item of room.switches || []) {
        fromFloorCards.push({
          ...item,
          floor: floor.floor,
          room_label: room.room_label,
          parent_switch_ip: room.parent_switch_ip,
          parent_switch_label: room.parent_switch_label,
          node: nodeByKey(item.node_key) || item.node,
        });
      }
    }
  }
  if (fromFloorCards.length) return mergeUniqueSources(fromFloorCards);

  const fromArchitectureNodes = (props.architecture.nodes || [])
    .filter((node) => {
      const text = `${node.node_type || ""} ${node.layer || ""} ${node.role || ""} ${node.label || ""}`;
      return /switch|交换机|access|aggregation|汇聚|接入/i.test(text) && node.node_key !== props.coreAnchor?.node_key;
    })
    .map((node) => ({
      node_key: node.node_key,
      label: node.label,
      ip: node.ip,
      floor: node.floor,
      room_label: node.weak_current_room || node.room_label,
      camera_count: Number(node.camera_count || node.downstream_camera_count || 0),
      node,
    }));
  if (fromArchitectureNodes.length) return mergeUniqueSources(fromArchitectureNodes);

  return createMockSwitchSources();
}

function createMockSwitchSources() {
  return Array.from({ length: 10 }, (_, index) => ({
    node_key: `mock-switch-${index + 1}`,
    label: `示例接入交换机 ${index + 1}`,
    ip: `10.0.68.${index + 10}`,
    camera_count: 20,
    floor: `${(index % 5) + 1}F`,
  }));
}

function buildBlueprintData() {
  const switchNodes = buildSwitchNodes();
  const cameraCount = switchNodes.reduce((sum, node) => sum + node.cameras.length, 0);
  const coreNode = buildCoreNode(cameraCount, switchNodes.length);
  const positionedSwitchNodes = assignBlueprintPositions(switchNodes);
  const nodes = [coreNode, ...positionedSwitchNodes];
  const nodeIdByKey = new Map(positionedSwitchNodes.map((node) => [node.nodeKey, node.id]));
  const nodeIdByIp = new Map(positionedSwitchNodes.filter((node) => node.ip).map((node) => [node.ip, node.id]));
  const coreKey = props.coreAnchor?.node_key || coreNode.nodeKey;
  const coreIp = props.coreAnchor?.ip || coreNode.ip;
  const edges = [];
  const hasIncoming = new Set();

  for (const edge of props.architecture.edges || []) {
    const sourceRaw = nodeByKey(edge.source_node_key);
    const targetRaw = nodeByKey(edge.target_node_key);
    const sourceIsCore = edge.source_node_key === coreKey || sourceRaw?.ip === coreIp;
    const targetIsCore = edge.target_node_key === coreKey || targetRaw?.ip === coreIp;
    const sourceId = sourceIsCore ? coreNode.id : nodeIdByKey.get(edge.source_node_key) || nodeIdByIp.get(sourceRaw?.ip);
    const targetId = targetIsCore ? coreNode.id : nodeIdByKey.get(edge.target_node_key) || nodeIdByIp.get(targetRaw?.ip);
    if (!sourceId || !targetId || sourceId === targetId) continue;
    const edgeRole = isCrossEdge(edge) ? "cross" : "physical";
    hasIncoming.add(targetId);
    edges.push({
      id: `${edgeRole}-${edge.id || sourceId}-${targetId}`,
      source: sourceId,
      target: targetId,
      edgeRole,
      label: edge.src_port_label || edge.edge_type || (edgeRole === "cross" ? "横向勾连" : "物理链路"),
      style: edgeRole === "cross" ? crossEdgeStyle() : physicalEdgeStyle(),
    });
  }

  positionedSwitchNodes.forEach((node) => {
    if (hasIncoming.has(node.id)) return;
    edges.push({
      id: `fallback-core-${node.id}`,
      source: coreNode.id,
      target: node.id,
      edgeRole: "physical",
      label: node.parentSwitchIp ? `上联 ${node.parentSwitchIp}` : "待核实上联",
      style: physicalEdgeStyle(),
    });
  });

  if (!edges.some((edge) => edge.edgeRole === "cross") && positionedSwitchNodes.length > 2) {
    createMockCrossEdges(positionedSwitchNodes).forEach((edge) => edges.push(edge));
  }

  return { nodes, edges: dedupeEdges(edges) };
}

function assignBlueprintPositions(nodes) {
  // 68 台交换机用固定秩网格，而不是 dagre/force 自动布局。
  // 这样每次刷新坐标都稳定，现场核实时不会“设备突然换位置”，也不会因为大卡片导致自动布局跑飞。
  const floorOrder = ["1F", "2F", "3F", "4F", "5F"];
  const sorted = [...nodes].sort((a, b) => {
    const floorA = floorOrder.indexOf(a.floor || "");
    const floorB = floorOrder.indexOf(b.floor || "");
    if (floorA !== floorB) return (floorA === -1 ? 99 : floorA) - (floorB === -1 ? 99 : floorB);
    return `${a.roomLabel || ""}${a.ip || ""}`.localeCompare(`${b.roomLabel || ""}${b.ip || ""}`, "zh-CN");
  });

  const columns = 4;
  const xStart = 170;
  const yStart = 250;
  const xGap = 300;
  const yGap = 205;
  return sorted.map((node, index) => {
    const col = index % columns;
    const row = Math.floor(index / columns);
    return {
      ...node,
      x: xStart + col * xGap,
      y: yStart + row * yGap,
    };
  });
}

function isCrossEdge(edge) {
  const text = `${edge.edge_type || ""} ${edge.evidence_type || ""} ${edge.src_port_label || ""}`.toLowerCase();
  return /cross|lateral|redundant|backup|peer|横向|冗余|勾连|级联/.test(text);
}

function createMockCrossEdges(switchNodes) {
  const count = Math.min(5, Math.floor(switchNodes.length / 2));
  return Array.from({ length: count }, (_, index) => {
    const source = switchNodes[index * 2];
    const target = switchNodes[switchNodes.length - 1 - index];
    return {
      id: `mock-cross-${source.id}-${target.id}`,
      source: source.id,
      target: target.id,
      edgeRole: "cross",
      label: "冗余/勾连",
      style: crossEdgeStyle(),
    };
  });
}

function dedupeEdges(edges) {
  const seen = new Set();
  return edges.filter((edge) => {
    const key = `${edge.source}->${edge.target}->${edge.edgeRole}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function physicalEdgeStyle() {
  return {
    stroke: "#3b82f6",
    lineWidth: 2,
    radius: 5,
    endArrow: {
      path: G6.Arrow.triangle(8, 10, 0),
      fill: "#3b82f6",
    },
  };
}

function crossEdgeStyle() {
  return {
    stroke: "#fbbf24",
    lineWidth: 1.8,
    radius: 5,
    lineDash: [4, 4],
    opacity: 0.86,
    endArrow: {
      path: G6.Arrow.triangle(7, 9, 0),
      fill: "#fbbf24",
    },
  };
}

function graphConfig(data) {
  const rows = Math.max(1, Math.ceil((data.nodes.length - 1) / 4));
  const width = Math.max(containerRef.value?.clientWidth || 1200, 1360);
  const height = Math.max(containerRef.value?.clientHeight || 680, rows * 205 + 360);
  return {
    container: containerRef.value,
    width,
    height,
    data,
    fitView: false,
    fitCenter: true,
    modes: {
      default: ["drag-canvas", "zoom-canvas", "drag-node"],
    },
    // 固定坐标蓝图布局：节点坐标在 buildBlueprintData 阶段生成。
    // 这里不配置 dagre/force，避免 G6 自动布局把 68 张大卡片排到画布外。
    defaultNode: {
      type: "switch-smart-card",
      anchorPoints: [
        [0.5, 0],
        [0.5, 1],
        [0, 0.5],
        [1, 0.5],
      ],
    },
    defaultEdge: {
      type: "polyline",
      routeCfg: {
        gridSize: 16,
        offset: 20,
      },
      labelCfg: {
        autoRotate: true,
        style: {
          fill: "rgba(203, 233, 255, 0.78)",
          fontSize: 10,
          background: {
            fill: "rgba(2, 8, 23, 0.72)",
            padding: [2, 5, 2, 5],
            radius: 4,
          },
        },
      },
    },
    nodeStateStyles: {
      active: {},
      inactive: {},
      selected: {},
    },
    edgeStateStyles: {
      active: {
        lineWidth: 4,
        shadowColor: "#67e8f9",
        shadowBlur: 18,
        opacity: 1,
      },
      inactive: {
        opacity: 0.12,
      },
      selected: {
        lineWidth: 4,
        shadowColor: "#fbbf24",
        shadowBlur: 22,
        opacity: 1,
      },
      alert: {
        stroke: "#ef4444",
        lineWidth: 4,
        shadowColor: "#ef4444",
        shadowBlur: 20,
        opacity: 1,
      },
    },
  };
}

async function renderGraph() {
  await nextTick();
  if (!containerRef.value) return;
  registerBlueprintElements();
  const data = buildBlueprintData();
  graphData.value = data;

  if (!graphRef.value || graphRef.value.destroyed) {
    graphRef.value = new G6.Graph(graphConfig(data));
    bindGraphEvents(graphRef.value);
    graphRef.value.data(data);
    graphRef.value.render();
  } else {
    graphRef.value.changeData(data);
  }

  animateCrossEdges();
  restoreAlertStates();
  applyExternalSelection();
  startRealtimeStatusMock();
}

function bindGraphEvents(graph) {
  graph.on("node:mouseenter", (event) => {
    if (!selectedGraphId.value) focusNode(event.item, false);
  });
  graph.on("edge:mouseenter", (event) => {
    if (!selectedGraphId.value) focusEdge(event.item, false);
  });
  graph.on("node:mouseleave", () => {
    if (!selectedGraphId.value) clearGraphStates();
  });
  graph.on("edge:mouseleave", () => {
    if (!selectedGraphId.value) clearGraphStates();
  });
  graph.on("node:click", (event) => {
    const node = event.item;
    const model = node.getModel();
    selectedGraphId.value = model.id;
    focusNode(node, true);
    // 生产接口预留：右侧抽屉可直接使用 model.cameras，不需要再次从画布节点里查摄像头。
    console.table(model.cameras || []);
    if (model.nodeKey) emit("select-node-key", model.nodeKey);
    emit("message", `${model.label || model.ip} 已选中，已输出下辖摄像头明细。`);
  });
  graph.on("edge:click", (event) => {
    const edge = event.item;
    const model = edge.getModel();
    selectedGraphId.value = model.id;
    focusEdge(edge, true);
    emit("select-edge-key", model.id);
    emit("message", `${model.label || "链路"} 已高亮。`);
  });
  graph.on("canvas:click", () => clearSelection());
}

function clearGraphStates() {
  const graph = graphRef.value;
  if (!graph || graph.destroyed) return;
  graph.getNodes().forEach((node) => {
    graph.clearItemStates(node);
  });
  graph.getEdges().forEach((edge) => {
    graph.clearItemStates(edge);
  });
}

function focusNode(node, lockSelection) {
  const graph = graphRef.value;
  if (!graph || !node) return;
  clearGraphStates();
  const relatedEdges = node.getEdges();
  const relatedNodes = new Set([node]);
  relatedEdges.forEach((edge) => {
    relatedNodes.add(edge.getSource());
    relatedNodes.add(edge.getTarget());
  });
  graph.getNodes().forEach((item) => {
    graph.setItemState(item, relatedNodes.has(item) ? "active" : "inactive", true);
  });
  graph.getEdges().forEach((edge) => {
    graph.setItemState(edge, relatedEdges.includes(edge) ? "active" : "inactive", true);
  });
  graph.setItemState(node, lockSelection ? "selected" : "focus", true);
}

function focusEdge(edge, lockSelection) {
  const graph = graphRef.value;
  if (!graph || !edge) return;
  clearGraphStates();
  const source = edge.getSource();
  const target = edge.getTarget();
  graph.getNodes().forEach((node) => {
    graph.setItemState(node, node === source || node === target ? "active" : "inactive", true);
  });
  graph.getEdges().forEach((item) => {
    graph.setItemState(item, item === edge ? (lockSelection ? "selected" : "active") : "inactive", true);
  });
}

function animateCrossEdges() {
  const graph = graphRef.value;
  if (!graph || graph.destroyed) return;
  graph.getEdges().forEach((edge) => {
    const model = edge.getModel();
    if (model.edgeRole !== "cross") return;
    const shape = edge.getKeyShape();
    if (!shape || shape.get("blueprintAnimated")) return;
    shape.set("blueprintAnimated", true);
    // 虚线偏移动画只改变线条样式，不触发布局重算，适合高频运维页面长期运行。
    shape.animate(
      (ratio) => ({
        lineDashOffset: -ratio * 32,
        opacity: 0.62 + Math.sin(ratio * Math.PI) * 0.28,
      }),
      {
        repeat: true,
        duration: 1500,
      },
    );
  });
}

function startRealtimeStatusMock() {
  if (bufferFlushTimer) return;
  bufferFlushTimer = window.setInterval(flushStatusBuffer, 500);
  scheduleMockStatusMessage();
}

function scheduleMockStatusMessage() {
  window.clearTimeout(mockStatusTimer);
  mockStatusTimer = window.setTimeout(() => {
    enqueueStatusMessage(createMockStatusChangeMessage());
    scheduleMockStatusMessage();
  }, 1000 + Math.floor(Math.random() * 2000));
}

function createMockStatusChangeMessage() {
  const switchNodes = graphData.value.nodes.filter((node) => node.nodeRole === "switch" && node.cameras?.length);
  if (!switchNodes.length) return null;
  const switchModel = switchNodes[Math.floor(Math.random() * switchNodes.length)];
  const camera = switchModel.cameras[Math.floor(Math.random() * switchModel.cameras.length)];
  const statuses = ["online", "offline", "alarm"];
  const newStatus = statuses[(statuses.indexOf(camera.status) + 1 + Math.floor(Math.random() * 2)) % statuses.length];
  return {
    type: "status_change",
    switchId: switchModel.id,
    cameraId: camera.id,
    newStatus,
    ts: Date.now(),
  };
}

function enqueueStatusMessage(message) {
  if (!message || message.type !== "status_change") return;
  messageBuffer.push(message);
}

function flushStatusBuffer() {
  if (!messageBuffer.length || !graphRef.value || graphRef.value.destroyed) return;
  const graph = graphRef.value;
  const latestBySwitch = new Map();

  while (messageBuffer.length) {
    const message = messageBuffer.shift();
    if (!latestBySwitch.has(message.switchId)) latestBySwitch.set(message.switchId, new Map());
    latestBySwitch.get(message.switchId).set(message.cameraId, message);
  }

  const changedNodeModels = new Map();
  for (const [switchId, cameraMessages] of latestBySwitch.entries()) {
    const node = graph.findById(switchId);
    if (!node || node.destroyed) continue;

    const model = node.getModel();
    const cameras = (model.cameras || []).map((camera) => {
      const message = cameraMessages.get(camera.id);
      return message ? { ...camera, status: message.newStatus, lastUpdateAt: message.ts } : camera;
    });
    const hasRisk = cameras.some((camera) => camera.status === "offline" || camera.status === "alarm");
    const hasAlert = cameras.some((camera) => camera.status === "alarm");
    const newModel = {
      ...model,
      cameras,
      hasRisk,
      statusUpdatedAt: Date.now(),
    };

    // 核心性能要求：严禁 graph.render/read/changeData，全程只 updateItem 单个交换机节点。
    graph.updateItem(node, newModel);
    updateAlertVisualState(node, hasAlert);
    changedNodeModels.set(switchId, newModel);
  }

  if (changedNodeModels.size) {
    graphData.value = {
      nodes: graphData.value.nodes.map((node) => changedNodeModels.get(node.id) || node),
      edges: graphData.value.edges,
    };
  }
}

function updateAlertVisualState(node, hasAlert) {
  const graph = graphRef.value;
  if (!graph || graph.destroyed || !node) return;
  const nodeId = node.getModel().id;
  graph.setItemState(node, "alert", hasAlert);
  if (hasAlert) alertNodeIds.add(nodeId);
  else alertNodeIds.delete(nodeId);

  node.getEdges().forEach((edge) => {
    const model = edge.getModel();
    const shouldBoost = hasAlert && model.edgeRole === "cross";
    graph.setItemState(edge, "alert", shouldBoost);
    if (shouldBoost) boostCrossEdgeAnimation(edge);
    else if (model.edgeRole === "cross") resetCrossEdgeAnimation(edge);
  });
}

function boostCrossEdgeAnimation(edge) {
  const shape = edge.getKeyShape();
  if (!shape || shape.get("blueprintBoosted")) return;
  shape.stopAnimate?.();
  shape.set("blueprintBoosted", true);
  shape.attr({ stroke: "#ef4444", lineDash: [5, 3] });
  shape.animate(
    (ratio) => ({
      lineDashOffset: -ratio * 48,
      opacity: 0.75 + Math.sin(ratio * Math.PI) * 0.24,
    }),
    {
      repeat: true,
      duration: 620,
    },
  );
}

function resetCrossEdgeAnimation(edge) {
  const shape = edge.getKeyShape();
  if (!shape || !shape.get("blueprintBoosted")) return;
  shape.stopAnimate?.();
  shape.set("blueprintBoosted", false);
  shape.attr({ stroke: "#fbbf24", lineDash: [4, 4], opacity: 0.86 });
  shape.animate(
    (ratio) => ({
      lineDashOffset: -ratio * 32,
      opacity: 0.62 + Math.sin(ratio * Math.PI) * 0.28,
    }),
    {
      repeat: true,
      duration: 1500,
    },
  );
}

function restoreAlertStates() {
  if (!graphRef.value || graphRef.value.destroyed) return;
  for (const nodeId of alertNodeIds) {
    const node = graphRef.value.findById(nodeId);
    if (node) updateAlertVisualState(node, true);
  }
}

function applyExternalSelection() {
  if (!props.selectedNodeKey || !graphRef.value || graphRef.value.destroyed) return;
  const node = graphRef.value.findById(`switch-${normalizeNodeId(props.selectedNodeKey)}`);
  if (node) {
    selectedGraphId.value = node.getModel().id;
    focusNode(node, true);
  }
}

function fitGraph() {
  if (!graphRef.value || graphRef.value.destroyed) return;
  graphRef.value.fitView([40, 40, 40, 40]);
}

function resetZoom() {
  if (!graphRef.value || graphRef.value.destroyed) return;
  graphRef.value.zoomTo(1);
  graphRef.value.fitCenter();
}

function clearSelection() {
  selectedGraphId.value = "";
  clearGraphStates();
}

watch(
  () => [props.architecture.nodes, props.architecture.edges, props.accessNodes, props.coreAnchor, props.selectedNodeKey],
  () => renderGraph(),
  { deep: true },
);

onMounted(() => {
  renderGraph();
  resizeObserver.value = new ResizeObserver(() => {
    const graph = graphRef.value;
    if (!graph || graph.destroyed || !containerRef.value) return;
    const rows = Math.max(1, Math.ceil((graphData.value.nodes.length - 1) / 4));
    graph.changeSize(Math.max(containerRef.value.clientWidth || 1200, 1360), Math.max(containerRef.value.clientHeight || 680, rows * 205 + 360));
  });
  resizeObserver.value.observe(containerRef.value);
});

onBeforeUnmount(() => {
  window.clearInterval(bufferFlushTimer);
  window.clearTimeout(mockStatusTimer);
  bufferFlushTimer = null;
  mockStatusTimer = null;
  resizeObserver.value?.disconnect();
  graphRef.value?.destroy();
});
</script>

<style scoped>
.blueprint-topology {
  position: relative;
  min-height: 760px;
  overflow: hidden;
  border: 1px solid rgba(56, 189, 248, 0.2);
  border-radius: 10px;
  background:
    linear-gradient(rgba(59, 130, 246, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(59, 130, 246, 0.055) 1px, transparent 1px),
    radial-gradient(circle at 18% 18%, rgba(34, 211, 238, 0.12), transparent 30%),
    radial-gradient(circle at 80% 0%, rgba(59, 130, 246, 0.14), transparent 32%),
    #020817;
  background-size: 32px 32px, 32px 32px, auto, auto, auto;
}

.topology-toolbar,
.topology-hud {
  position: relative;
  z-index: 2;
  border-bottom: 1px solid rgba(56, 189, 248, 0.12);
  background: linear-gradient(180deg, rgba(8, 19, 35, 0.95), rgba(8, 19, 35, 0.74));
}

.topology-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 14px 16px 12px;
}

.topology-toolbar p {
  margin: 0 0 4px;
  color: #67e8f9;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.22em;
}

.topology-toolbar strong {
  display: block;
  color: #f8fbff;
  font-size: 20px;
}

.topology-toolbar span {
  color: rgba(203, 233, 255, 0.74);
  font-size: 12px;
}

.topology-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.blueprint-btn {
  min-height: 34px;
  padding: 7px 12px;
  border: 1px solid rgba(56, 189, 248, 0.24);
  border-radius: 8px;
  background: rgba(2, 8, 23, 0.74);
  color: #e0f2fe;
  cursor: pointer;
}

.blueprint-btn:hover {
  border-color: rgba(103, 232, 249, 0.55);
  background: rgba(8, 47, 73, 0.74);
}

.topology-hud {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr)) minmax(260px, 1.7fr);
  gap: 8px;
  padding: 10px 16px;
}

.topology-hud article {
  display: grid;
  gap: 3px;
  padding: 9px 11px;
  border: 1px solid rgba(56, 189, 248, 0.16);
  border-radius: 9px;
  background: rgba(15, 23, 42, 0.64);
}

.topology-hud article span,
.legend-strip span {
  color: rgba(203, 233, 255, 0.68);
  font-size: 11px;
}

.topology-hud article strong {
  color: #ffffff;
  font-size: 17px;
}

.legend-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;
}

.legend-strip span {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.legend-strip i {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  box-shadow: 0 0 12px currentColor;
}

.legend-strip .physical {
  color: #3b82f6;
  background: #3b82f6;
}

.legend-strip .cross {
  color: #fbbf24;
  background: #fbbf24;
}

.legend-strip .online {
  color: #22c55e;
  background: #22c55e;
}

.legend-strip .offline {
  color: #ef4444;
  background: #ef4444;
}

.legend-strip .alarm {
  color: #fbbf24;
  background: #fbbf24;
}

.visible-blueprint-board {
  position: relative;
  z-index: 2;
  display: grid;
  gap: 14px;
  padding: 14px 16px 18px;
  border-top: 1px solid rgba(56, 189, 248, 0.1);
  background:
    linear-gradient(rgba(59, 130, 246, 0.052) 1px, transparent 1px),
    linear-gradient(90deg, rgba(59, 130, 246, 0.052) 1px, transparent 1px),
    rgba(2, 8, 23, 0.68);
  background-size: 28px 28px;
}

.core-rack {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid rgba(103, 232, 249, 0.22);
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(8, 47, 73, 0.86), rgba(15, 23, 42, 0.82));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 0 24px rgba(34, 211, 238, 0.08);
}

.core-card {
  display: grid;
  gap: 4px;
}

.core-card span,
.core-card small,
.realtime-indicator span,
.switch-dom-head span,
.switch-dom-foot {
  color: rgba(203, 233, 255, 0.72);
  font-size: 12px;
}

.core-card strong {
  color: #ffffff;
  font-size: 18px;
}

.realtime-indicator {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

.realtime-indicator i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 16px rgba(34, 197, 94, 0.88);
  animation: realtimePulse 1.2s ease-in-out infinite;
}

.switch-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(228px, 1fr));
  gap: 12px;
  max-height: 720px;
  overflow: auto;
  padding: 2px 4px 4px 2px;
}

.switch-dom-card {
  display: grid;
  gap: 10px;
  min-width: 0;
  min-height: 148px;
  padding: 12px;
  border: 1px solid rgba(56, 189, 248, 0.22);
  border-radius: 13px;
  background:
    radial-gradient(circle at 14% 0%, rgba(34, 211, 238, 0.16), transparent 42%),
    rgba(15, 23, 42, 0.82);
  color: #f8fbff;
  text-align: left;
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 0 18px rgba(56, 189, 248, 0.08);
}

.switch-dom-card:hover,
.switch-dom-card.selected {
  border-color: rgba(103, 232, 249, 0.7);
  box-shadow: 0 0 28px rgba(103, 232, 249, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.switch-dom-card.alarm {
  border-color: rgba(239, 68, 68, 0.78);
  box-shadow: 0 0 26px rgba(239, 68, 68, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.switch-dom-card.offline {
  border-color: rgba(251, 191, 36, 0.58);
}

.switch-dom-head,
.switch-dom-foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.switch-dom-head div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.switch-dom-head strong {
  overflow: hidden;
  color: #ffffff;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.switch-dom-head small {
  flex: 0 0 auto;
  padding: 3px 7px;
  border: 1px solid rgba(103, 232, 249, 0.2);
  border-radius: 999px;
  color: #bae6fd;
  font-size: 11px;
  background: rgba(8, 47, 73, 0.42);
}

.switch-dom-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.switch-dom-stats span {
  padding: 5px 6px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 800;
  text-align: center;
  background: rgba(2, 8, 23, 0.62);
}

.switch-dom-stats .online {
  color: #86efac;
}

.switch-dom-stats .offline {
  color: #fca5a5;
}

.switch-dom-stats .alarm {
  color: #fde68a;
}

.dom-matrix {
  display: grid;
  grid-template-columns: repeat(24, 4px);
  gap: 4px;
  min-height: 28px;
  align-content: start;
  overflow: hidden;
}

.dom-matrix i {
  width: 4px;
  height: 4px;
  border-radius: 1px;
  background: #22c55e;
  box-shadow: 0 0 7px currentColor;
}

.dom-matrix i.online {
  color: #22c55e;
  background: #22c55e;
}

.dom-matrix i.offline {
  color: #ef4444;
  background: #ef4444;
}

.dom-matrix i.alarm {
  color: #fbbf24;
  background: #fbbf24;
}

.dom-matrix i.unconfigured {
  color: #64748b;
  background: #64748b;
  opacity: 0.5;
}

.blueprint-stage {
  position: relative;
  z-index: 0;
  height: 1px;
  min-height: 1px;
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
}

@keyframes realtimePulse {
  0%,
  100% {
    opacity: 0.45;
    transform: scale(0.8);
  }

  50% {
    opacity: 1;
    transform: scale(1.18);
  }
}

@media (max-width: 1200px) {
  .topology-hud {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .legend-strip {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
}

@media (max-width: 760px) {
  .topology-toolbar {
    flex-direction: column;
  }

  .topology-hud {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
