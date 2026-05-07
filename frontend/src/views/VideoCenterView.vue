<template>
  <section class="page">
    <header class="section-head">
      <div>
        <p class="eyebrow">视频中心</p>
        <h2>视频接入与媒体能力层</h2>
      </div>
    </header>

    <section class="cards">
      <article class="card">
        <span>当前通道数</span>
        <strong>{{ channels.length }}</strong>
      </article>
      <article class="card">
        <span>协议类型</span>
        <strong>{{ protocolStats.length }}</strong>
      </article>
      <article class="card">
        <span>来源类型</span>
        <strong>{{ sourceTypes.length }}</strong>
      </article>
      <article class="card">
        <span>区域数量</span>
        <strong>{{ areas.length }}</strong>
      </article>
    </section>

    <article class="panel accent-panel">
      <h3>视频层定位</h3>
      <p>
        视频层统一承接平台通道、NVR 通道、摄像头直连和解码输出等入口，先把各类视频资源纳入统一资产模型，
        再逐步打通预览、快照、回放、转码和后续分析能力。
      </p>
    </article>

    <article class="panel">
      <h3>筛选条件</h3>
      <div class="action-row wrap">
        <input
          v-model.trim="filters.q"
          class="filter-input"
          placeholder="搜索通道名称、摄像头 IP、父设备"
          @keyup.enter="loadChannels"
        />

        <select v-model="filters.protocol_type" class="filter-input" @change="loadChannels">
          <option value="">全部协议</option>
          <option v-for="item in protocolStats" :key="item.name" :value="item.name">
            {{ protocolTypeLabel(item.name) }}
          </option>
        </select>

        <select v-model="filters.source_type" class="filter-input" @change="loadChannels">
          <option value="">全部来源</option>
          <option v-for="item in sourceTypes" :key="item.source_type" :value="item.source_type">
            {{ sourceTypeLabel(item.source_type) }}
          </option>
        </select>

        <select v-model="filters.area_id" class="filter-input" @change="loadChannels">
          <option value="">全部区域</option>
          <option v-for="area in areas" :key="area.id" :value="String(area.id)">
            {{ area.display_name }}
          </option>
        </select>

        <button class="ghost-button" @click="resetFilters">重置</button>
      </div>
    </article>

    <section class="panel-grid">
      <article class="panel">
        <h3>协议分布</h3>
        <div class="chip-grid">
          <button
            v-for="item in protocolStats"
            :key="item.name"
            class="info-chip"
            :class="{ active: filters.protocol_type === item.name }"
            @click="toggleProtocol(item.name)"
          >
            <strong>{{ protocolTypeLabel(item.name) }}</strong>
            <span>{{ item.count }} 路</span>
          </button>
        </div>
      </article>

      <article class="panel">
        <h3>当前筛选摘要</h3>
        <ul class="plain-list compact-list">
          <li>协议：{{ filters.protocol_type ? protocolTypeLabel(filters.protocol_type) : "全部" }}</li>
          <li>来源：{{ filters.source_type ? sourceTypeLabel(filters.source_type) : "全部" }}</li>
          <li>区域：{{ selectedAreaLabel }}</li>
          <li>关键词：{{ filters.q || "未设置" }}</li>
        </ul>
      </article>
    </section>

    <article class="panel">
      <h3>视频通道工作台</h3>
      <div class="table-shell asset-table-shell">
        <table class="mini-table">
          <thead>
            <tr>
              <th>来源</th>
              <th>父设备</th>
              <th>通道号</th>
              <th>通道名称</th>
              <th>摄像头</th>
              <th>区域</th>
              <th>协议</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="channel in channels" :key="channel.id">
              <td><span class="pill subtle">{{ sourceTypeLabel(channel.source_type) }}</span></td>
              <td>{{ channel.parent_label || channel.parent_device_id || "-" }}</td>
              <td>{{ channel.channel_no }}</td>
              <td>{{ channel.channel_name || "-" }}</td>
              <td>
                <strong>{{ channel.camera_label || "-" }}</strong>
                <div class="mono">{{ channel.camera_ip || "-" }}</div>
              </td>
              <td>{{ channel.area_display_name || "-" }}</td>
              <td><span class="pill info">{{ protocolTypeLabel(channel.protocol_type) }}</span></td>
              <td>{{ channelStatusLabel(channel.channel_status) }}</td>
            </tr>
            <tr v-if="!channels.length">
              <td colspan="8" class="empty-cell">当前筛选条件下没有视频通道。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { fetchAreas, fetchChannels, fetchSourceTypes } from "../api/client";

const channels = ref([]);
const areas = ref([]);
const sourceTypes = ref([]);

const filters = reactive({
  q: "",
  protocol_type: "",
  source_type: "",
  area_id: "",
});

const protocolStats = computed(() => {
  const counts = new Map();
  for (const item of channels.value) {
    const key = item.protocol_type || "unknown";
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
});

const selectedAreaLabel = computed(() => {
  if (!filters.area_id) return "全部区域";
  return areas.value.find((item) => String(item.id) === filters.area_id)?.display_name || "全部区域";
});

onMounted(async () => {
  try {
    [areas.value, sourceTypes.value] = await Promise.all([fetchAreas(), fetchSourceTypes()]);
    await loadChannels();
  } catch (error) {
    console.error(error);
  }
});

async function loadChannels() {
  try {
    channels.value = await fetchChannels({
      q: filters.q || undefined,
      protocol_type: filters.protocol_type || undefined,
      source_type: filters.source_type || undefined,
      area_id: filters.area_id || undefined,
      limit: 220,
    });
  } catch (error) {
    console.error(error);
  }
}

function resetFilters() {
  filters.q = "";
  filters.protocol_type = "";
  filters.source_type = "";
  filters.area_id = "";
  loadChannels();
}

function toggleProtocol(name) {
  filters.protocol_type = filters.protocol_type === name ? "" : name;
  loadChannels();
}

function protocolTypeLabel(value) {
  const mapping = {
    rtsp: "实时流预览（RTSP）",
    webrtc: "浏览器实时预览（WebRTC）",
    hls: "流媒体播放（HLS）",
    onvif: "设备发现（ONVIF）",
    unknown: "未识别协议",
  };
  return mapping[value] || value || "未识别协议";
}

function sourceTypeLabel(value) {
  const mapping = {
    tg_cos: "TG/COS 平台",
    jvss: "JVSS 平台",
    legacy_ops: "旧运维平台",
    gateway: "网关",
    hikvision_nvr: "海康录像机",
    hikvision_decoder: "海康解码器",
    control_platform_new: "风控新平台",
    control_platform_legacy: "风控老平台",
    camera_direct: "摄像头直连",
    cad_upload: "CAD 导入",
    alert_bridge: "告警桥接",
    unknown: "未识别来源",
  };
  return mapping[value] || value || "未识别来源";
}

function channelStatusLabel(value) {
  const mapping = {
    online: "在线",
    offline: "离线",
    preview_ready: "可预览",
    preview_failed: "预览异常",
    unreachable: "不可达",
    reachable: "可达",
    warning: "警告",
    unknown: "待确认",
  };
  return mapping[value] || value || "-";
}
</script>
