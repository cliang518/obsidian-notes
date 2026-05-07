<template>
  <section class="page video-page">
    <header class="section-head video-hero">
      <div class="video-hero-copy">
        <p class="eyebrow">VIDEO CONSOLE</p>
        <h2>视频工作台</h2>
        <p class="hero-lead">
          这里不是单纯看地址，而是围绕具体通道处理视频、快照和排障。能在浏览器里直接看的就直接看，不能直接播的就给出明确诊断和下一步动作。
        </p>

        <div class="video-scan-stage">
          <div class="scan-grid"></div>
          <div class="scan-line"></div>
          <div class="scan-ring scan-ring-a"></div>
          <div class="scan-ring scan-ring-b"></div>
          <div class="video-signal-bars">
            <div v-for="item in channelSignals" :key="item.label" class="video-signal-row">
              <span>{{ item.label }}</span>
              <div class="video-signal-track">
                <i :style="{ width: `${item.width}%` }"></i>
              </div>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </div>
      </div>

      <div class="video-hero-metrics">
        <article class="card">
          <span>通道数量</span>
          <strong>{{ channels.length }}</strong>
        </article>
        <article class="card">
          <span>可预览</span>
          <strong>{{ previewReadyCount }}</strong>
        </article>
        <article class="card">
          <span>带快照</span>
          <strong>{{ snapshotReadyCount }}</strong>
        </article>
        <article class="card">
          <span>协议类型</span>
          <strong>{{ protocolStats.length }}</strong>
        </article>
      </div>
    </header>

    <section class="action-row wrap video-launch-row">
      <button class="action-btn subtle" @click="goTo('/assets')">打开设备资产</button>
      <button class="action-btn subtle" @click="goTo('/alerts')">查看告警</button>
      <button class="action-btn subtle" @click="goTo('/')">返回总览</button>
      <button class="action-btn" @click="loadChannels">立即刷新</button>
    </section>

    <article v-if="actionMessage" class="panel video-feedback-panel">
      <strong>{{ actionMessage }}</strong>
      <span>最近刷新：{{ lastUpdatedLabel }}</span>
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
        <h3>状态筛选</h3>
        <div class="chip-grid">
          <button
            v-for="item in quickStatusOptions"
            :key="item.key"
            class="info-chip"
            :class="{ active: quickStatusFilter === item.key }"
            @click="quickStatusFilter = item.key"
          >
            <strong>{{ item.label }}</strong>
            <span>{{ item.count }}</span>
          </button>
        </div>
      </article>
    </section>

    <section v-if="selectedChannel" class="mobile-quick-dock video-mobile-dock">
      <button class="mobile-quick-card" @click="openSelectedAsset">
        <span>V-A</span>
        <strong>回设备</strong>
      </button>
      <button class="mobile-quick-card" @click="openSnapshot(selectedSnapshotUrl)">
        <span>V-S</span>
        <strong>开快照</strong>
      </button>
      <button class="mobile-quick-card" @click="copyDiagnosticBundle">
        <span>V-D</span>
        <strong>复制诊断</strong>
      </button>
      <button class="mobile-quick-card" @click="refreshSnapshotPreview">
        <span>V-R</span>
        <strong>刷新快照</strong>
      </button>
    </section>

    <article v-if="selectedChannel" class="panel video-mobile-spotlight">
      <div class="mobile-video-spotlight-head">
        <strong>{{ selectedChannel.channel_name || selectedChannel.camera_label || `通道 ${selectedChannel.id}` }}</strong>
        <span>{{ channelStatusLabel(selectedChannel.channel_status) }}</span>
      </div>
      <div class="mobile-video-spotlight-meta">
        <span>{{ selectedChannel.camera_ip || "-" }}</span>
        <span>{{ selectedChannel.parent_label || "-" }}</span>
        <span>{{ selectedChannel.area_display_name || "-" }}</span>
      </div>
    </article>

    <section class="video-layout">
      <article class="panel video-table-panel">
        <h3>视频通道清单</h3>
        <div class="table-shell asset-table-shell">
          <table class="mini-table video-table">
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
              <tr
                v-for="channel in filteredChannels"
                :key="channel.id"
                :class="{ active: selectedChannelId === channel.id }"
                @click="selectChannel(channel)"
              >
                <td><span class="pill subtle">{{ sourceTypeLabel(channel.source_type) }}</span></td>
                <td>{{ channel.parent_label || "-" }}</td>
                <td>{{ channel.channel_no || "-" }}</td>
                <td>{{ channel.channel_name || "-" }}</td>
                <td>
                  <strong>{{ channel.camera_label || "-" }}</strong>
                  <div class="mono">{{ channel.camera_ip || "-" }}</div>
                </td>
                <td>{{ channel.area_display_name || "-" }}</td>
                <td><span class="pill info">{{ protocolTypeLabel(channel.protocol_type) }}</span></td>
                <td>{{ channelStatusLabel(channel.channel_status) }}</td>
              </tr>
              <tr v-if="!filteredChannels.length">
                <td colspan="8" class="empty-cell">当前筛选条件下没有视频通道。</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="mobile-channel-list">
          <button
            v-for="channel in filteredChannels"
            :key="`mobile-${channel.id}`"
            class="mobile-channel-card"
            :class="{ active: selectedChannelId === channel.id }"
            @click="selectChannel(channel)"
          >
            <div class="mobile-channel-head">
              <strong>{{ channel.channel_name || channel.camera_label || `通道 ${channel.id}` }}</strong>
              <span>{{ channelStatusLabel(channel.channel_status) }}</span>
            </div>
            <div class="mobile-channel-meta">
              <span>{{ sourceTypeLabel(channel.source_type) }}</span>
              <span>{{ protocolTypeLabel(channel.protocol_type) }}</span>
            </div>
            <div class="mobile-channel-ip">
              <label>摄像头</label>
              <strong>{{ channel.camera_ip || "-" }}</strong>
            </div>
            <div class="mobile-channel-meta">
              <span>{{ channel.parent_label || "-" }}</span>
              <span>{{ channel.area_display_name || "-" }}</span>
            </div>
          </button>
          <div v-if="!filteredChannels.length" class="mobile-channel-empty">当前筛选条件下没有视频通道。</div>
        </div>
      </article>

      <article class="panel video-detail-panel accent-panel">
        <h3>选中通道详情</h3>
        <template v-if="selectedChannel">
          <div class="detail-stack">
            <div class="device-hero">
              <strong>{{ selectedChannel.channel_name || selectedChannel.camera_label || "未命名通道" }}</strong>
              <span>{{ protocolTypeLabel(selectedChannel.protocol_type) }} / {{ channelStatusLabel(selectedChannel.channel_status) }}</span>
            </div>

            <div class="detail-grid">
              <div>
                <label>父设备</label>
                <strong>{{ selectedChannel.parent_label || "-" }}</strong>
              </div>
              <div>
                <label>摄像头 IP</label>
                <strong>{{ selectedChannel.camera_ip || "-" }}</strong>
              </div>
              <div>
                <label>区域</label>
                <strong>{{ selectedChannel.area_display_name || "-" }}</strong>
              </div>
              <div>
                <label>来源</label>
                <strong>{{ sourceTypeLabel(selectedChannel.source_type) }}</strong>
              </div>
            </div>

            <div class="split-panel">
              <div>
                <h4>RTSP 主码流</h4>
                <p class="code-box">{{ selectedChannel.rtsp_main || "暂无地址" }}</p>
                <div class="action-row wrap">
                  <button class="action-btn subtle" :disabled="!selectedChannel.rtsp_main" @click="copyText(selectedChannel.rtsp_main, '主码流地址已复制')">
                    复制主码流
                  </button>
                </div>
              </div>
              <div>
                <h4>RTSP 子码流</h4>
                <p class="code-box">{{ selectedChannel.rtsp_sub || "暂无地址" }}</p>
                <div class="action-row wrap">
                  <button class="action-btn subtle" :disabled="!selectedChannel.rtsp_sub" @click="copyText(selectedChannel.rtsp_sub, '子码流地址已复制')">
                    复制子码流
                  </button>
                </div>
              </div>
            </div>

            <div>
              <h4>V2 快照地址</h4>
              <p class="code-box">{{ selectedSnapshotUrl || "暂无地址" }}</p>
              <div class="action-row wrap">
                <button class="action-btn" :disabled="!selectedSnapshotUrl" @click="openSnapshot(selectedSnapshotUrl)">打开快照</button>
                <button class="action-btn subtle" :disabled="!selectedSnapshotUrl" @click="copyText(selectedSnapshotUrl, '快照地址已复制')">复制快照</button>
                <button class="ghost-button" :disabled="!selectedChannel" @click="refreshSnapshotPreview">刷新快照</button>
              </div>
            </div>

            <div class="preview-diagnosis-card">
              <div class="preview-diagnosis-head">
                <h4>预览诊断</h4>
                <span>{{ previewDiagnostic.level }}</span>
              </div>
              <ul class="plain-list compact-list">
                <li>当前策略：{{ previewDiagnostic.strategy }}</li>
                <li>浏览器能力：{{ previewDiagnostic.browser }}</li>
                <li>推荐动作：{{ previewDiagnostic.nextStep }}</li>
              </ul>
              <div class="action-row wrap">
                <button class="action-btn subtle" @click="copyDiagnosticBundle">复制诊断包</button>
                <button class="ghost-button" @click="openSelectedAsset">回设备</button>
              </div>
            </div>

            <div class="preview-console-shell">
              <div class="preview-console-head">
                <h4>浏览器内预览</h4>
                <span>{{ previewConsoleLabel }}</span>
              </div>

              <div class="preview-mode-switch">
                <button
                  v-for="item in previewModeOptions"
                  :key="item.key"
                  class="ghost-button"
                  :class="{ active: previewPreference === item.key }"
                  :disabled="!item.available"
                  @click="previewPreference = item.key"
                >
                  {{ item.label }}
                </button>
              </div>

              <div class="preview-console-frame">
                <video
                  v-if="previewKind === 'flv'"
                  ref="liveVideoRef"
                  class="browser-preview-video"
                  controls
                  muted
                  autoplay
                  playsinline
                  @loadeddata="markLiveReady"
                  @playing="markLiveReady"
                  @error="handlePreviewError"
                ></video>

                <video
                  v-else-if="previewKind === 'video'"
                  :key="browserPreviewSrc"
                  :src="browserPreviewSrc"
                  class="browser-preview-video"
                  controls
                  playsinline
                  preload="metadata"
                  @error="handlePreviewError"
                ></video>

                <img
                  v-else-if="previewKind === 'image'"
                  :src="browserPreviewSrc"
                  alt="浏览器预览"
                  class="browser-preview-image"
                  @error="handlePreviewError"
                />

                <div v-else class="preview-fallback">
                  <strong>浏览器预览代理尚未生成画面</strong>
                  <span>{{ previewFallbackText }}</span>
                  <div class="action-row wrap">
                    <button class="action-btn subtle" :disabled="!selectedChannel.rtsp_main" @click="copyText(selectedChannel.rtsp_main, '主码流地址已复制，可粘贴到播放器')">
                      复制到外部播放器
                    </button>
                    <button class="action-btn subtle" :disabled="!selectedSnapshotUrl" @click="openSnapshot(selectedSnapshotUrl)">
                      改用快照查看
                    </button>
                  </div>
                </div>
                <div v-if="previewKind === 'flv' && liveMessage" class="asset-live-status">
                  {{ liveMessage }}
                </div>
              </div>
            </div>

            <div v-if="snapshotPreviewUrl" class="snapshot-preview-shell">
              <div class="snapshot-preview-head">
                <h4>快照预览</h4>
                <span>当前预览直接走 V2 自主抓帧链</span>
              </div>
              <div class="snapshot-preview-frame" @click="snapshotModalVisible = true">
                <img
                  :src="snapshotPreviewUrl"
                  alt="快照预览"
                  class="snapshot-preview-image"
                  @error="handleSnapshotError"
                />
              </div>
            </div>
            <div v-else class="snapshot-preview-shell muted">
              <div class="snapshot-preview-head">
                <h4>快照预览</h4>
                <span>当前还没有可直接显示的快照图片，可先复制 RTSP 到外部播放器排查。</span>
              </div>
            </div>

            <div>
              <h4>补充信息</h4>
              <ul class="plain-list compact-list">
                <li>通道号：{{ selectedChannel.channel_no || "-" }}</li>
                <li>交换机：{{ selectedChannel.switch_label || selectedChannel.switch_ip || "待补链路" }}</li>
                <li>端口 / VLAN：{{ selectedChannel.switch_port_name || "-" }} / {{ selectedChannel.switch_port_vlan_id || "-" }}</li>
                <li>拓扑证据：{{ selectedChannel.topology_evidence_summary || "暂无" }}</li>
                <li>直采状态：{{ selectedChannel.direct_rtsp_status || "-" }} / {{ selectedChannel.direct_record_status || "-" }}</li>
                <li>备注：{{ selectedChannel.note_summary || selectedChannel.notes || "暂无备注" }}</li>
              </ul>
            </div>
          </div>
        </template>
        <p v-else>请先从左侧列表里选中一条通道，右侧会显示 RTSP、快照和状态详情。</p>
      </article>
    </section>

    <div v-if="snapshotModalVisible" class="snapshot-modal" @click="closeSnapshotModal">
      <div class="snapshot-modal-shell" @click.stop>
        <div class="snapshot-modal-head">
          <strong>快照大图预览</strong>
          <button class="mini-action" type="button" @click="closeSnapshotModal">关闭</button>
        </div>
        <img :src="snapshotPreviewUrl" alt="快照大图" class="snapshot-modal-image" />
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import flvjs from "flv.js";
import {
  buildChannelFlvUrl,
  buildChannelMjpegUrl,
  buildChannelSnapshotUrl,
  fetchAreas,
  fetchChannels,
  fetchSourceTypes,
} from "../api/client";

const router = useRouter();
const route = useRoute();
const channels = ref([]);
const areas = ref([]);
const sourceTypes = ref([]);
const selectedChannelId = ref(null);
const actionMessage = ref("");
const lastUpdatedAt = ref(null);
const snapshotModalVisible = ref(false);
const previewPreference = ref("snapshot");
const quickStatusFilter = ref("all");
const snapshotRefreshSeed = ref(0);
const liveVideoRef = ref(null);
const liveMessage = ref("");
let refreshTimer = null;
let liveFlvPlayer = null;
let liveStartTimer = null;

const filters = reactive({
  q: "",
  protocol_type: "",
  source_type: "",
  area_id: "",
});

function channelSnapshotUrl(channel, refreshSeed = 0) {
  if (!channel) return "";
  if (channel.snapshot_capture_enabled || channel.snapshot_capture_url) {
    return buildChannelSnapshotUrl(channel.id, {
      refresh: refreshSeed > 0,
      cacheBust: true,
    });
  }
  return "";
}

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

const filteredChannels = computed(() =>
  channels.value.filter((item) => {
    if (quickStatusFilter.value === "preview_ready") return Boolean(item.rtsp_main || item.rtsp_sub);
    if (quickStatusFilter.value === "snapshot_ready") return Boolean(channelSnapshotUrl(item));
    if (quickStatusFilter.value === "preview_failed") return item.channel_status === "preview_failed";
    if (quickStatusFilter.value === "reachable") return item.channel_status === "reachable";
    return true;
  }),
);

const selectedChannel = computed(
  () =>
    filteredChannels.value.find((item) => item.id === selectedChannelId.value) ||
    channels.value.find((item) => item.id === selectedChannelId.value) ||
    null,
);

const selectedSnapshotUrl = computed(() => channelSnapshotUrl(selectedChannel.value, snapshotRefreshSeed.value));
const selectedMjpegUrl = computed(() =>
  selectedChannel.value && (selectedChannel.value.rtsp_main || selectedChannel.value.rtsp_sub)
    ? buildChannelMjpegUrl(selectedChannel.value.id)
    : "",
);
const selectedFlvUrl = computed(() =>
  selectedChannel.value && (selectedChannel.value.rtsp_main || selectedChannel.value.rtsp_sub)
    ? buildChannelFlvUrl(selectedChannel.value.id)
    : "",
);
const snapshotPreviewUrl = computed(() => normalizePreviewUrl(selectedSnapshotUrl.value));

const previewReadyCount = computed(() => channels.value.filter((item) => item.rtsp_main || item.rtsp_sub).length);
const snapshotReadyCount = computed(() => channels.value.filter((item) => item.snapshot_capture_enabled).length);

const previewModeOptions = computed(() => [
  { key: "snapshot", label: "快照", available: Boolean(selectedSnapshotUrl.value) },
  { key: "flv", label: "RTSP 直播", available: Boolean(selectedFlvUrl.value) },
  { key: "live", label: "轻量桥接", available: Boolean(selectedMjpegUrl.value) },
]);

const resolvedPreviewCandidate = computed(() => {
  const candidates =
    previewPreference.value === "flv"
      ? [{ url: selectedFlvUrl.value, source: "RTSP 直播" }]
      : previewPreference.value === "live"
      ? [{ url: selectedMjpegUrl.value, source: "实时桥接" }]
      : previewPreference.value === "snapshot"
        ? [{ url: snapshotPreviewUrl.value, source: "快照" }]
        : [
            { url: snapshotPreviewUrl.value, source: "快照" },
            { url: selectedFlvUrl.value, source: "RTSP 直播" },
            { url: selectedMjpegUrl.value, source: "实时桥接" },
          ];
  return candidates.find((item) => item.url) || { url: "", source: "无可用预览" };
});

const browserPreviewSrc = computed(() => resolvedPreviewCandidate.value.url);
const previewKind = computed(() => detectPreviewKind(browserPreviewSrc.value));

const previewConsoleLabel = computed(() => {
  if (!browserPreviewSrc.value) return "等待可用地址";
  if (previewKind.value === "flv") return `${resolvedPreviewCandidate.value.source} 已通过后台转码直播`;
  if (previewKind.value === "video") return `${resolvedPreviewCandidate.value.source} 已切换为浏览器视频流`;
  if (previewKind.value === "image") return `${resolvedPreviewCandidate.value.source} 已切换为图片预览`;
  return `${resolvedPreviewCandidate.value.source} 需要外部播放器`;
});

const previewFallbackText = computed(() => {
  if (!selectedChannel.value) return "请先选择一条通道。";
  if (selectedChannel.value.rtsp_main || selectedChannel.value.rtsp_sub) {
    return "系统已把 RTSP 交给后台 FFmpeg 转码，若直播未出画面，请切换快照或轻量桥接继续核验。";
  }
  return "当前通道缺少快照和 RTSP 地址，请先补齐通道资料。";
});

const quickStatusOptions = computed(() => [
  { key: "all", label: "全部通道", count: `${channels.value.length} 路` },
  { key: "preview_ready", label: "可预览", count: `${previewReadyCount.value} 路` },
  { key: "snapshot_ready", label: "带快照", count: `${snapshotReadyCount.value} 路` },
  {
    key: "preview_failed",
    label: "预览异常",
    count: `${channels.value.filter((item) => item.channel_status === "preview_failed").length} 路`,
  },
  {
    key: "reachable",
    label: "仅可达",
    count: `${channels.value.filter((item) => item.channel_status === "reachable").length} 路`,
  },
]);

const channelSignals = computed(() => {
  const total = Math.max(channels.value.length, 1);
  const items = [
    { label: "可预览", value: previewReadyCount.value },
    { label: "预览异常", value: channels.value.filter((item) => item.channel_status === "preview_failed").length },
    { label: "仅可达", value: channels.value.filter((item) => item.channel_status === "reachable").length },
    { label: "带快照", value: snapshotReadyCount.value },
  ];
  return items.map((item) => ({
    ...item,
    width: Math.max(8, Math.round((item.value / total) * 100)),
  }));
});

const lastUpdatedLabel = computed(() => {
  if (!lastUpdatedAt.value) return "等待首次加载";
  return formatDateTime(lastUpdatedAt.value);
});

const previewDiagnostic = computed(() => {
  if (!selectedChannel.value) {
    return {
      level: "等待通道",
      strategy: "请先从列表中选择通道。",
      browser: "未开始检测",
      nextStep: "选中通道后自动给出建议。",
    };
  }
  if (previewKind.value === "flv") {
    return {
      level: "RTSP 直播",
      strategy: `${resolvedPreviewCandidate.value.source} 已通过后台 FFmpeg 转成 FLV`,
      browser: "浏览器播放的是转码后的 FLV，不是裸 RTSP",
      nextStep: "如果直播卡住，切换快照确认画面，再检查 RTSP 账号、密码和链路。",
    };
  }
  if (previewKind.value === "video") {
    return {
      level: "可直接预览",
      strategy: `${resolvedPreviewCandidate.value.source} 已匹配浏览器视频流`,
      browser: "当前浏览器可直接加载该媒体地址",
      nextStep: "优先在当前页查看，必要时再复制到外部播放器。",
    };
  }
  if (previewKind.value === "image") {
    return {
      level: "快照可直看",
      strategy: `${resolvedPreviewCandidate.value.source} 已匹配浏览器图片流`,
      browser: "当前浏览器可直接显示图片快照",
      nextStep: "先用快照核对画面，再决定是否复制 RTSP 去播放器。",
    };
  }
  if (selectedChannel.value.rtsp_main || selectedChannel.value.rtsp_sub) {
    return {
      level: "等待桥接",
      strategy: "RTSP 已登记，正在通过 V2 直播、快照或轻量桥接转成浏览器可看的画面",
      browser: "浏览器不直接播放 RTSP，系统通过后台代理后再显示",
      nextStep: "先点 RTSP 直播；如不出画面，再切换快照或轻量桥接。",
    };
  }
  return {
    level: "地址不足",
    strategy: "当前通道缺少可直接使用的浏览器媒体地址",
    browser: "没有发现可渲染的视频或图片流",
    nextStep: "补齐快照或播放代理后再测试。",
  };
});

function destroyLiveFlvPlayer() {
  if (liveStartTimer) {
    clearTimeout(liveStartTimer);
    liveStartTimer = null;
  }
  liveMessage.value = "";
  if (!liveFlvPlayer) {
    return;
  }
  try {
    liveFlvPlayer.pause?.();
    liveFlvPlayer.unload?.();
    liveFlvPlayer.detachMediaElement?.();
    liveFlvPlayer.destroy?.();
  } catch (error) {
    console.warn("销毁视频中心 FLV 播放器失败。", error);
  } finally {
    liveFlvPlayer = null;
  }
}

async function initLiveFlvPlayer() {
  await nextTick();
  destroyLiveFlvPlayer();
  if (previewKind.value !== "flv" || !browserPreviewSrc.value || !liveVideoRef.value) {
    return;
  }
  if (!flvjs.isSupported()) {
    actionMessage.value = "当前浏览器不支持 FLV 直播播放，请换 Chrome/Edge 或使用快照预览。";
    return;
  }
  liveMessage.value = "正在连接 RTSP 直播，请稍候...";
  liveStartTimer = setTimeout(() => {
    liveMessage.value = "直播仍未出画面：请先用快照核验，再检查该通道 RTSP 地址、账号密码和网络链路。";
    actionMessage.value = liveMessage.value;
  }, 12000);
  liveFlvPlayer = flvjs.createPlayer(
    {
      type: "flv",
      isLive: true,
      url: browserPreviewSrc.value,
    },
    {
      enableStashBuffer: false,
      stashInitialSize: 128,
      autoCleanupSourceBuffer: true,
    },
  );
  liveFlvPlayer.on(flvjs.Events.ERROR, (errorType, errorDetail) => {
    console.warn("Video center FLV preview failed.", errorType, errorDetail);
    if (liveStartTimer) {
      clearTimeout(liveStartTimer);
      liveStartTimer = null;
    }
    liveMessage.value = "RTSP 直播加载失败，可切换快照或轻量桥接继续核验。";
    actionMessage.value = "RTSP 直播加载失败，可切换快照或轻量桥接继续核验。";
  });
  liveFlvPlayer.attachMediaElement(liveVideoRef.value);
  liveFlvPlayer.load();
  try {
    await liveVideoRef.value.play();
  } catch (error) {
    console.warn("浏览器阻止自动播放，等待用户手动点击播放。", error);
  }
}

function markLiveReady() {
  if (liveStartTimer) {
    clearTimeout(liveStartTimer);
    liveStartTimer = null;
  }
  liveMessage.value = "";
}

onMounted(async () => {
  hydrateFiltersFromRoute();
  [areas.value, sourceTypes.value] = await Promise.all([fetchAreas(), fetchSourceTypes()]);
  await loadChannels();
  refreshTimer = window.setInterval(() => {
    loadChannels();
  }, 45000);
});

onUnmounted(() => {
  destroyLiveFlvPlayer();
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
});

watch(quickStatusFilter, () => {
  if (!filteredChannels.value.some((item) => item.id === selectedChannelId.value)) {
    selectedChannelId.value = filteredChannels.value[0]?.id || channels.value[0]?.id || null;
  }
});

watch(
  () => route.query,
  () => {
    hydrateFiltersFromRoute();
    loadChannels();
  },
);

watch(
  () => [previewKind.value, browserPreviewSrc.value, selectedChannel.value?.id],
  () => {
    if (previewKind.value === "flv") {
      initLiveFlvPlayer();
      return;
    }
    destroyLiveFlvPlayer();
  },
  { flush: "post" },
);

async function loadChannels() {
  try {
    const routeChannelId = Number(route.query.channel_id || 0);
    const loadedChannels = await fetchChannels({
      q: filters.q || undefined,
      protocol_type: filters.protocol_type || undefined,
      source_type: filters.source_type || undefined,
      area_id: filters.area_id || undefined,
      limit: 220,
    });
    if (routeChannelId && !loadedChannels.some((item) => item.id === routeChannelId)) {
      const exactRows = await fetchChannels({
        channel_id: routeChannelId,
        limit: 20,
      });
      if (exactRows.length) {
        loadedChannels.unshift(exactRows[0]);
      }
    }
    channels.value = loadedChannels;
    if (routeChannelId && channels.value.some((item) => item.id === routeChannelId)) {
      selectedChannelId.value = routeChannelId;
      previewPreference.value = "snapshot";
    } else if (!selectedChannelId.value || !filteredChannels.value.some((item) => item.id === selectedChannelId.value)) {
      selectedChannelId.value = filteredChannels.value[0]?.id || channels.value[0]?.id || null;
    }
    lastUpdatedAt.value = new Date();
  } catch (error) {
    console.error(error);
    actionMessage.value = "视频通道加载失败，请查看后端日志。";
  }
}

function hydrateFiltersFromRoute() {
  filters.q = typeof route.query.q === "string" ? route.query.q : "";
}

function resetFilters() {
  filters.q = "";
  filters.protocol_type = "";
  filters.source_type = "";
  filters.area_id = "";
  quickStatusFilter.value = "all";
  loadChannels();
}

function toggleProtocol(name) {
  filters.protocol_type = filters.protocol_type === name ? "" : name;
  loadChannels();
}

function selectChannel(channel) {
  selectedChannelId.value = channel.id;
  previewPreference.value = "snapshot";
  snapshotRefreshSeed.value = 0;
  actionMessage.value = `已选中 ${channel.channel_name || channel.camera_label || channel.camera_ip || `通道 ${channel.id}`}`;
}

function goTo(path) {
  router.push(path);
}

function openSelectedAsset() {
  if (!selectedChannel.value) return;
  router.push({
    path: "/assets",
    query: {
      device_id: selectedChannel.value.parent_device_id ? String(selectedChannel.value.parent_device_id) : undefined,
      channel_id: selectedChannel.value.id ? String(selectedChannel.value.id) : undefined,
      q: selectedChannel.value.camera_ip || selectedChannel.value.channel_name || selectedChannel.value.parent_label || "",
    },
  });
}

async function copyText(value, successMessage) {
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    actionMessage.value = successMessage;
  } catch (error) {
    console.error(error);
    actionMessage.value = "复制失败，请检查浏览器权限。";
  }
}

function openSnapshot(url) {
  if (!url) return;
  if (/^(https?:)?\/\//i.test(url) || url.startsWith("/")) {
    window.open(url, "_blank", "noopener,noreferrer");
    actionMessage.value = "已在新窗口打开快照。";
    return;
  }
  copyText(url, "快照地址已复制");
}

function refreshSnapshotPreview() {
  snapshotRefreshSeed.value = Date.now();
  actionMessage.value = "已刷新当前通道快照。";
}

function handleSnapshotError() {
  actionMessage.value = "快照预览加载失败，可能需要重新抓帧或该地址暂时不可用。";
}

function handlePreviewError() {
  actionMessage.value = "浏览器内预览加载失败，建议改用快照或轻量桥接。";
}

function closeSnapshotModal() {
  snapshotModalVisible.value = false;
}

async function copyDiagnosticBundle() {
  if (!selectedChannel.value) return;
  const payload = [
    `通道名称：${selectedChannel.value.channel_name || "-"}`,
    `摄像头 IP：${selectedChannel.value.camera_ip || "-"}`,
    `父设备：${selectedChannel.value.parent_label || selectedChannel.value.parent_device_id || "-"}`,
    `区域：${selectedChannel.value.area_display_name || "-"}`,
    `协议：${protocolTypeLabel(selectedChannel.value.protocol_type)}`,
    `状态：${channelStatusLabel(selectedChannel.value.channel_status)}`,
    `主码流：${selectedChannel.value.rtsp_main || "-"}`,
    `子码流：${selectedChannel.value.rtsp_sub || "-"}`,
    `快照：${selectedSnapshotUrl.value || "-"}`,
    `预览诊断：${previewDiagnostic.value.nextStep}`,
  ].join("\n");
  await copyText(payload, "诊断包已复制，可直接发给维修人员或值班群。");
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
    control_platform_legacy: "风控旧平台",
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
    reachable: "仅可达",
    warning: "警告",
    unknown: "待确认",
  };
  return mapping[value] || value || "-";
}

function normalizePreviewUrl(value) {
  const url = (value || "").trim();
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith("/")) return url;
  return "";
}

function detectPreviewKind(url) {
  if (!url) return "none";
  if (/\/flv(\?|$)/i.test(url)) return "flv";
  if (/\/mjpeg(\?|$)/i.test(url)) return "image";
  if (/\.(m3u8|mp4|webm|ogg)(\?.*)?$/i.test(url)) return "video";
  if (/\.(jpg|jpeg|png|webp|bmp|gif)(\?.*)?$/i.test(url)) return "image";
  if (/\/snapshot(\.jpg)?(\?|$)/i.test(url)) return "image";
  return "none";
}

function formatDateTime(value) {
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      hour12: false,
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(value);
  } catch (error) {
    return "-";
  }
}
</script>
