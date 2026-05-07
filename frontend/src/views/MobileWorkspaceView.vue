<template>
  <section class="page mobile-ops-page">
    <section class="mobile-account-strip">
      <div>
        <span>当前账号</span>
        <strong>{{ board.viewer.display_name || board.viewer.username || "未登录" }}</strong>
        <small>{{ roleLabel(board.viewer.role) }} · {{ themeMode === "dark" ? "深色主题" : "浅色主题" }}</small>
      </div>
      <button class="action-btn subtle" type="button" @click="toggleTheme">切换为{{ themeMode === "dark" ? "浅色" : "深色" }}</button>
    </section>

    <section class="mobile-kpis">
      <article v-for="item in kpis" :key="item.label" class="mobile-kpi">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.hint }}</small>
      </article>
    </section>

    <nav class="mobile-tabs">
      <button v-for="tab in tabs" :key="tab.key" class="mobile-tab" :class="{ active: activeTab === tab.key }" type="button" @click="activeTab = tab.key">
        <span>{{ tab.code }}</span><strong>{{ tab.label }}</strong>
      </button>
    </nav>

    <section v-if="activeTab === 'camera'" class="mobile-panel">
      <div class="mobile-panel-head">
        <div><p class="hero-kicker">CAMERA</p><h3>现场摄像头核验</h3></div>
        <button class="ghost-button" type="button" @click="reload">刷新</button>
      </div>

      <label class="mobile-filter">
        <span>快速搜索</span>
        <input v-model.trim="channelFilter" class="filter-input" placeholder="输入 IP、名称、区域、交换机" />
      </label>

      <div class="mobile-camera-grid">
        <div class="mobile-camera-list">
          <button v-for="item in visibleChannels" :key="item.id" class="mobile-camera" :class="{ active: selectedChannel?.id === item.id }" type="button" @click="selectChannel(item)">
            <div class="mobile-row">
              <strong>{{ cameraTitle(item) }}</strong>
              <span :class="['mini-state', item.switch_binding_state === 'bound' ? 'ok' : 'warn']">{{ item.switch_binding_state === "bound" ? "已归属" : "待核实" }}</span>
            </div>
            <div class="mobile-row muted"><span>{{ item.camera_ip || "-" }}</span><span>{{ item.area_display_name || item.area_name || "未分区" }}</span></div>
            <small>{{ item.switch_label || item.switch_ip || "未绑定交换机" }}</small>
          </button>
          <div v-if="!visibleChannels.length" class="mobile-empty">没有匹配的摄像头。</div>
        </div>

        <article class="mobile-preview">
          <template v-if="selectedChannel">
            <div class="mobile-panel-head">
              <div><strong>{{ cameraTitle(selectedChannel) }}</strong><span>{{ selectedChannel.camera_ip || "-" }}</span></div>
              <button class="ghost-button" type="button" @click="refreshSnapshot">刷新快照</button>
            </div>
            <div class="mobile-preview-stage">
              <img :src="previewMode === 'live' ? liveUrl : snapshotUrl" class="mobile-preview-image" :class="{ live: previewMode === 'live' }" :alt="selectedChannel.camera_ip || 'camera'" />
            </div>
            <div class="mobile-actions">
              <button class="action-btn" :class="{ subtle: previewMode !== 'snapshot' }" type="button" @click="previewMode = 'snapshot'">当前快照</button>
              <button class="action-btn" :class="{ subtle: previewMode !== 'live' }" type="button" @click="previewMode = 'live'">手动直播</button>
            </div>
            <div class="mobile-info">
              <div><span>RTSP</span><strong>{{ selectedChannel.rtsp_main ? "已配置" : "缺失" }}</strong></div>
              <div><span>来源</span><strong>{{ selectedChannel.source_key || selectedChannel.primary_source_type || "-" }}</strong></div>
              <div><span>交换机</span><strong>{{ selectedChannel.switch_label || selectedChannel.switch_ip || "待核实" }}</strong></div>
              <div><span>端口</span><strong>{{ selectedChannel.switch_port_name || "待核实" }}</strong></div>
            </div>
          </template>
          <div v-else class="mobile-empty">选择摄像头后显示快照、直播入口和归属资料。</div>
        </article>
      </div>
    </section>

    <section v-if="activeTab === 'alerts'" class="mobile-panel">
      <div class="mobile-panel-head">
        <div><p class="hero-kicker">ALERTS</p><h3>告警处置</h3></div>
        <button class="ghost-button" type="button" @click="reload">刷新</button>
      </div>
      <div class="mobile-stack">
        <article v-for="item in board.alerts" :key="`alert-${item.id}`" class="mobile-task">
          <div class="mobile-row"><strong>{{ item.title }}</strong><span :class="['mini-state', severityClass(item.severity)]">{{ severityLabel(item.severity) }}</span></div>
          <p>{{ item.alert_type }} · {{ formatDate(item.last_seen_at) }}</p>
          <button class="text-link" type="button" @click="dispatchFromAlert(item)">转入移动调度</button>
        </article>
        <div v-if="!board.alerts.length" class="mobile-empty">当前没有打开告警。</div>
      </div>
    </section>

    <section v-if="activeTab === 'orders'" class="mobile-panel">
      <div class="mobile-panel-head"><div><p class="hero-kicker">WORK ORDERS</p><h3>工单与巡检</h3></div><button class="ghost-button" type="button" @click="reload">刷新</button></div>
      <div class="mobile-two">
        <article>
          <h4>待处理工单</h4>
          <div class="mobile-stack">
            <div v-for="item in board.work_orders" :key="`wo-${item.id}`" class="mobile-task">
              <div class="mobile-row"><strong>{{ item.title }}</strong><span class="mini-state warn">{{ priorityLabel(item.priority) }}</span></div>
              <p>{{ orderStatusLabel(item.status) }} · {{ item.area_name || "未填写区域" }}</p>
              <button class="text-link" type="button" @click="dispatchFromWorkOrder(item)">派到移动端</button>
            </div>
            <div v-if="!board.work_orders.length" class="mobile-empty">当前没有待处理工单。</div>
          </div>
        </article>
        <article>
          <h4>待执行巡检</h4>
          <div class="mobile-stack">
            <div v-for="item in board.inspections" :key="`inspection-${item.id}`" class="mobile-task">
              <div class="mobile-row"><strong>{{ item.title }}</strong><span class="mini-state">{{ inspectionStatusLabel(item.status) }}</span></div>
              <p>{{ item.plan_name || "临时巡检" }} · {{ item.area_name || "未填写区域" }}</p>
              <button class="text-link" type="button" @click="dispatchFromInspection(item)">派到移动端</button>
            </div>
            <div v-if="!board.inspections.length" class="mobile-empty">当前没有待执行巡检。</div>
          </div>
        </article>
      </div>
    </section>

    <section v-if="activeTab === 'dispatch'" class="mobile-panel">
      <div class="mobile-panel-head"><div><p class="hero-kicker">DISPATCH</p><h3>移动调度台账</h3></div><span class="panel-tag">{{ dispatchSummary.active_count || 0 }} 项进行中</span></div>
      <div class="mobile-stack">
        <article v-for="item in board.dispatch_items" :key="`dispatch-${item.id}`" class="mobile-task">
          <div class="mobile-row"><strong>{{ item.title }}</strong><span :class="['mini-state', dispatchClass(item.status)]">{{ statusLabel(item.status) }}</span></div>
          <p>{{ dispatchTypeLabel(item.dispatch_type) }} · {{ item.area_name || item.device_label || "未填写位置" }}</p>
          <small>{{ item.summary || "暂无补充说明" }}</small>
          <div class="mobile-actions">
            <button v-if="item.status === 'queued'" class="ghost-button" type="button" @click="changeDispatchStatus(item, 'acknowledged')">签收</button>
            <button v-if="item.status !== 'in_progress' && item.status !== 'completed'" class="ghost-button" type="button" @click="changeDispatchStatus(item, 'in_progress')">开始</button>
            <button v-if="item.status !== 'completed'" class="action-btn" type="button" @click="changeDispatchStatus(item, 'completed')">完成</button>
          </div>
        </article>
        <div v-if="!board.dispatch_items.length" class="mobile-empty">没有待签收或处理中调度项。</div>
      </div>
    </section>

    <section v-if="activeTab === 'workflow'" class="mobile-panel">
      <div class="mobile-panel-head"><div><p class="hero-kicker">WORKFLOW</p><h3>移动入口配置</h3></div><span class="panel-tag">{{ mobileChannels.length }} 个入口</span></div>
      <div class="mobile-two">
        <article class="mobile-form">
          <h4>{{ editingId ? "编辑移动工作流" : "登记移动工作流" }}</h4>
          <div class="mobile-form-grid">
            <label><span>工作流标识</span><input v-model.trim="form.channel_key" class="filter-input" placeholder="mobile-alert-workspace" /></label>
            <label><span>显示名称</span><input v-model.trim="form.display_name" class="filter-input" placeholder="移动告警工作台" /></label>
            <label><span>目标平台</span><input v-model.trim="form.target_platform" class="filter-input" placeholder="企业微信 / 飞书 / 微信" /></label>
            <label><span>状态</span><select v-model="form.status" class="filter-input"><option value="planned">规划中</option><option value="ready">可设计</option><option value="testing">测试中</option><option value="active">已启用</option></select></label>
          </div>
          <textarea v-model.trim="form.notes" class="filter-input mobile-notes" rows="4" placeholder="记录移动入口、跳转方式、消息入口和现场使用说明。" />
          <div class="mobile-actions"><button class="action-btn" type="button" @click="submitForm">{{ editingId ? "保存" : "登记" }}</button><button v-if="editingId" class="ghost-button" type="button" @click="resetForm">取消编辑</button></div>
        </article>
        <article>
          <h4>已登记入口</h4>
          <div class="mobile-stack">
            <button v-for="item in mobileChannels" :key="item.id" class="mobile-channel-row" type="button" @click="loadChannel(item)">
              <strong>{{ item.display_name }}</strong><span>{{ item.target_platform || "待定平台" }} · {{ scopeLabel(item.scope) }} · {{ statusLabel(item.status) }}</span>
            </button>
            <div v-if="!mobileChannels.length" class="mobile-empty">还没有移动入口配置。</div>
          </div>
        </article>
      </div>
    </section>

    <p class="mobile-message">{{ message }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import {
  buildChannelMjpegUrl,
  buildChannelSnapshotUrl,
  createMobileChannel,
  createMobileDispatchFromAlert,
  createMobileDispatchFromInspection,
  createMobileDispatchFromWorkOrder,
  fetchAssetSummary,
  fetchChannels,
  fetchMobileChannels,
  fetchMobileDispatchBoard,
  fetchMobileDispatchSummary,
  fetchMobileSummary,
  fetchRuntimeCounts,
  updateMobileChannel,
  updateMobileDispatchItem,
} from "../api/client";
import { setThemeMode, themeState } from "../state/theme";

const tabs = [
  { key: "camera", label: "摄像头", code: "CAM" },
  { key: "alerts", label: "告警", code: "ALT" },
  { key: "orders", label: "工单", code: "JOB" },
  { key: "dispatch", label: "调度", code: "DSP" },
  { key: "workflow", label: "入口", code: "APP" },
];
const activeTab = ref("camera");
const themeMode = computed(() => themeState.mode);
const runtimeCounts = ref({});
const assetSummary = ref({});
const summary = ref({});
const mobileChannels = ref([]);
const channels = ref([]);
const selectedChannel = ref(null);
const channelFilter = ref("");
const snapshotSeed = ref(0);
const previewMode = ref("snapshot");
const editingId = ref(null);
const message = ref("移动端已接入 PC 主线数据，适合手机现场测试。");
const board = ref({
  viewer: { username: "", display_name: "", role: "" },
  counts: { open_alerts: 0, open_work_orders: 0, open_inspections: 0, pending_accounts: 0, dispatch_items: 0 },
  alerts: [],
  work_orders: [],
  inspections: [],
  dispatch_items: [],
});
const dispatchSummary = ref({});
const form = reactive({
  channel_key: "",
  display_name: "",
  channel_type: "workspace",
  target_platform: "",
  entry_mode: "h5",
  deep_link_scheme: "",
  auth_mode: "session",
  scope: "field_ops",
  enabled: true,
  mobile_first: true,
  status: "planned",
  notes: "",
});

const kpis = computed(() => [
  { label: "资产总量", value: assetSummary.value.device_count || runtimeCounts.value.total_devices || 0, hint: "同步资产中心" },
  { label: "视频通道", value: runtimeCounts.value.video_channels || channels.value.length || 0, hint: "快照 / 直播" },
  { label: "打开告警", value: board.value.counts.open_alerts || 0, hint: "可转调度" },
  { label: "待办工单", value: board.value.counts.open_work_orders || 0, hint: "现场闭环" },
  { label: "巡检任务", value: board.value.counts.open_inspections || 0, hint: "移动执行" },
  { label: "调度进行", value: board.value.counts.dispatch_items || 0, hint: "签收处理" },
]);
const visibleChannels = computed(() => {
  const keyword = channelFilter.value.toLowerCase();
  const list = channels.value || [];
  if (!keyword) return list.slice(0, 18);
  return list.filter((item) => [
    item.channel_name,
    item.camera_ip,
    item.area_name,
    item.area_display_name,
    item.switch_label,
    item.switch_ip,
    item.rtsp_main,
  ].filter(Boolean).join(" ").toLowerCase().includes(keyword)).slice(0, 30);
});
const snapshotUrl = computed(() => selectedChannel.value?.id ? buildChannelSnapshotUrl(selectedChannel.value.id, { refresh: snapshotSeed.value > 0, cacheBust: true }) : "");
const liveUrl = computed(() => selectedChannel.value?.id ? buildChannelMjpegUrl(selectedChannel.value.id, { cacheBust: true }) : "");

onMounted(reload);

async function reload() {
  const [runtimeData, assetData, summaryData, mobileChannelData, dispatchSummaryData, dispatchData, channelData] = await Promise.all([
    fetchRuntimeCounts(),
    fetchAssetSummary(),
    fetchMobileSummary(),
    fetchMobileChannels(),
    fetchMobileDispatchSummary(),
    fetchMobileDispatchBoard(),
    fetchChannels({ limit: 80 }),
  ]);
  runtimeCounts.value = runtimeData || {};
  assetSummary.value = assetData || {};
  summary.value = summaryData || {};
  mobileChannels.value = mobileChannelData || [];
  dispatchSummary.value = dispatchSummaryData || {};
  board.value = dispatchData || board.value;
  channels.value = channelData || [];
  if (!selectedChannel.value && channels.value.length) selectedChannel.value = channels.value[0];
}
function toggleTheme() {
  setThemeMode(themeState.mode === "dark" ? "light" : "dark");
}
function selectChannel(item) {
  selectedChannel.value = item;
  previewMode.value = "snapshot";
  snapshotSeed.value += 1;
}
function refreshSnapshot() {
  snapshotSeed.value += 1;
  previewMode.value = "snapshot";
}
function resetForm() {
  editingId.value = null;
  Object.assign(form, { channel_key: "", display_name: "", channel_type: "workspace", target_platform: "", entry_mode: "h5", deep_link_scheme: "", auth_mode: "session", scope: "field_ops", enabled: true, mobile_first: true, status: "planned", notes: "" });
}
function loadChannel(item) {
  editingId.value = item.id;
  Object.assign(form, {
    channel_key: item.channel_key || "",
    display_name: item.display_name || "",
    channel_type: item.channel_type || "workspace",
    target_platform: item.target_platform || "",
    entry_mode: item.entry_mode || "h5",
    deep_link_scheme: item.deep_link_scheme || "",
    auth_mode: item.auth_mode || "session",
    scope: item.scope || "field_ops",
    enabled: !!item.enabled,
    mobile_first: !!item.mobile_first,
    status: item.status || "planned",
    notes: item.notes || "",
  });
}
async function submitForm() {
  try {
    editingId.value ? await updateMobileChannel(editingId.value, { ...form }) : await createMobileChannel({ ...form });
    message.value = editingId.value ? "移动工作流已更新。" : "移动工作流已创建。";
    await reload();
    resetForm();
  } catch {
    message.value = "保存失败，请检查工作流标识是否重复，或查看后端日志。";
  }
}
async function dispatchFromAlert(item) {
  await runDispatch(() => createMobileDispatchFromAlert(item.id, { latest_note: "手机端转派告警" }), "告警已转入移动调度。");
}
async function dispatchFromWorkOrder(item) {
  await runDispatch(() => createMobileDispatchFromWorkOrder(item.id, { latest_note: "手机端派发工单" }), "工单已派到移动调度。");
}
async function dispatchFromInspection(item) {
  await runDispatch(() => createMobileDispatchFromInspection(item.id, { latest_note: "手机端派发巡检" }), "巡检已派到移动调度。");
}
async function runDispatch(task, okMessage) {
  try {
    await task();
    message.value = okMessage;
    activeTab.value = "dispatch";
    await reload();
  } catch {
    message.value = "派发失败，可能已存在调度项或权限不足。";
  }
}
async function changeDispatchStatus(item, status) {
  try {
    await updateMobileDispatchItem(item.id, {
      status,
      assignee_username: item.assignee_username || board.value.viewer.username || "",
      mobile_channel_key: item.mobile_channel_key || "",
      latest_note: item.latest_note || "",
    });
    message.value = `调度项已更新为：${statusLabel(status)}`;
    await reload();
  } catch {
    message.value = "更新调度状态失败，请查看后端日志。";
  }
}
function cameraTitle(item) {
  return item?.channel_name || item?.camera_ip || `通道 ${item?.id || "-"}`;
}
function scopeLabel(value) {
  return ({ field_ops: "现场运维", alert_ops: "告警处理", workorder_ops: "工单处理", inspection_ops: "巡检执行" }[value] || value || "-");
}
function statusLabel(value) {
  return ({ planned: "规划中", ready: "可设计", testing: "测试中", active: "已启用", queued: "待派发", acknowledged: "已签收", in_progress: "处理中", completed: "已完成" }[value] || value || "-");
}
function dispatchTypeLabel(value) {
  return ({ alert: "告警转派", work_order: "工单转派", inspection: "巡检转派" }[value] || value || "-");
}
function roleLabel(value) {
  return ({ admin: "管理员", manager: "值班主管", technician: "维修人员", viewer: "只读人员" }[value] || value || "访客");
}
function severityLabel(value) {
  return ({ critical: "严重", warning: "警告", info: "提示" }[value] || value || "-");
}
function severityClass(value) {
  return value === "critical" ? "danger" : value === "warning" ? "warn" : "ok";
}
function orderStatusLabel(value) {
  return ({ open: "待处理", in_progress: "处理中", resolved: "已解决", closed: "已关闭" }[value] || value || "-");
}
function inspectionStatusLabel(value) {
  return ({ scheduled: "待执行", in_progress: "执行中", completed: "已完成", overdue: "已逾期" }[value] || value || "-");
}
function priorityLabel(value) {
  return ({ low: "低", medium: "中", high: "高", critical: "紧急" }[value] || value || "-");
}
function dispatchClass(value) {
  return { ok: value === "completed", warn: value === "acknowledged", danger: value === "in_progress" };
}
function formatDate(value) {
  if (!value) return "-";
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? value : dt.toLocaleString("zh-CN", { hour12: false });
}
</script>

<style scoped>
.mobile-account-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border-soft);
  border-radius: 18px;
  background: radial-gradient(circle at 88% 12%, rgba(201, 109, 45, 0.1), transparent 36%), linear-gradient(180deg, var(--panel-strong), var(--panel));
  box-shadow: var(--shadow-soft);
}

.mobile-account-strip div {
  display: grid;
  gap: 3px;
}

.mobile-account-strip span,
.mobile-account-strip small {
  color: var(--text-muted);
  font-size: 12px;
}

.mobile-account-strip strong {
  color: var(--text-main);
  font-size: 15px;
}

.mobile-kpi,
.mobile-panel,
.mobile-preview,
.mobile-task,
.mobile-form,
.mobile-filter,
.mobile-channel-row {
  border: 1px solid var(--border-soft);
  background: radial-gradient(circle at 88% 12%, rgba(201, 109, 45, 0.1), transparent 36%), linear-gradient(180deg, var(--panel-strong), var(--panel));
  box-shadow: var(--shadow-soft);
}
.mobile-kpi span,
.mobile-kpi small,
.mobile-row.muted,
.mobile-task p,
.mobile-task small,
.mobile-camera small,
.mobile-info span,
.mobile-channel-row span,
.mobile-filter span {
  color: var(--text-muted);
}
.mobile-kpis {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}
.mobile-kpi {
  display: grid;
  gap: 7px;
  padding: 15px;
  border-radius: 20px;
}
.mobile-kpi strong {
  font-size: 26px;
}
.mobile-tabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}
.mobile-tab {
  display: grid;
  gap: 6px;
  padding: 13px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 18px;
  background: var(--surface);
  color: var(--text-main);
  cursor: pointer;
  text-align: left;
}
.mobile-tab span {
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 0.16em;
}
.mobile-tab.active {
  border-color: var(--accent-weak);
  background: radial-gradient(circle at 88% 12%, var(--accent-soft), transparent 36%), linear-gradient(180deg, var(--panel-strong), var(--panel));
}
.mobile-panel {
  display: grid;
  gap: 16px;
  padding: 18px;
  border-radius: 26px;
}
.mobile-panel-head,
.mobile-row,
.mobile-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.mobile-panel-head h3,
.mobile-two h4,
.mobile-form h4 {
  margin: 0;
}
.mobile-filter {
  display: grid;
  gap: 8px;
  padding: 14px;
  border-radius: 18px;
}
.mobile-camera-grid,
.mobile-two {
  display: grid;
  grid-template-columns: minmax(260px, 0.85fr) minmax(0, 1.15fr);
  gap: 14px;
}
.mobile-camera-list,
.mobile-stack {
  display: grid;
  gap: 10px;
}
.mobile-camera-list {
  max-height: 620px;
  overflow: auto;
  padding-right: 4px;
}
.mobile-camera,
.mobile-task,
.mobile-channel-row {
  display: grid;
  gap: 9px;
  width: 100%;
  padding: 14px;
  border: 1px solid var(--border-soft);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.48);
  color: var(--text-main);
  text-align: left;
}
.mobile-camera {
  cursor: pointer;
}
.mobile-camera.active {
  border-color: var(--accent-weak);
}
.mobile-preview {
  display: grid;
  gap: 14px;
  align-content: start;
  min-width: 0;
  padding: 16px;
  border-radius: 22px;
}
.mobile-preview-stage {
  overflow: hidden;
  min-height: 260px;
  border-radius: 20px;
  border: 1px solid var(--border-soft);
  background: radial-gradient(circle at center, rgba(14, 165, 233, 0.16), transparent 44%), #07111d;
}
.mobile-preview-image {
  width: 100%;
  height: 100%;
  min-height: 260px;
  object-fit: contain;
  display: block;
}
.mobile-preview-image.live {
  object-fit: cover;
}
.mobile-info,
.mobile-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.mobile-info div {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 12px;
  border-radius: 16px;
  background: rgba(148, 163, 184, 0.08);
}
.mobile-info strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mobile-task,
.mobile-form {
  border-radius: 20px;
}
.mobile-task p {
  margin: 0;
}
.mobile-form {
  display: grid;
  gap: 10px;
  padding: 15px;
}
.mobile-form-grid label {
  display: grid;
  gap: 7px;
  color: var(--text-muted);
}
.mobile-notes {
  width: 100%;
  resize: vertical;
}
.mini-state {
  display: inline-flex;
  padding: 5px 9px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.12);
  color: #2563eb;
  font-size: 12px;
}
.mini-state.ok {
  background: rgba(34, 197, 94, 0.14);
  color: #15803d;
}
.mini-state.warn {
  background: rgba(245, 158, 11, 0.16);
  color: #b45309;
}
.mini-state.danger {
  background: rgba(239, 68, 68, 0.14);
  color: #dc2626;
}
.mobile-empty,
.mobile-message {
  padding: 14px;
  border-radius: 18px;
  border: 1px dashed var(--border-soft);
  color: var(--text-muted);
  background: rgba(148, 163, 184, 0.08);
}
.mobile-message {
  margin: 0;
}
html[data-theme="dark"] .mobile-kpi,
html[data-theme="dark"] .mobile-panel,
html[data-theme="dark"] .mobile-preview,
html[data-theme="dark"] .mobile-task,
html[data-theme="dark"] .mobile-form,
html[data-theme="dark"] .mobile-filter,
html[data-theme="dark"] .mobile-camera,
html[data-theme="dark"] .mobile-tab,
html[data-theme="dark"] .mobile-channel-row {
  border-color: rgba(125, 211, 252, 0.16);
  background: radial-gradient(circle at 88% 10%, rgba(56, 189, 248, 0.14), transparent 36%), radial-gradient(circle at 12% 92%, rgba(245, 158, 11, 0.1), transparent 34%), linear-gradient(180deg, rgba(13, 31, 50, 0.82), rgba(7, 19, 32, 0.72));
}
html[data-theme="dark"] .mobile-account-strip,
html[data-theme="dark"] .mobile-info div,
html[data-theme="dark"] .mobile-empty,
html[data-theme="dark"] .mobile-message {
  border-color: rgba(125, 211, 252, 0.16);
  background: rgba(125, 211, 252, 0.08);
}
html[data-theme="dark"] .mini-state {
  color: #7dd3fc;
}
html[data-theme="dark"] .mini-state.ok {
  color: #86efac;
}
html[data-theme="dark"] .mini-state.warn {
  color: #fbbf24;
}
html[data-theme="dark"] .mini-state.danger {
  color: #fca5a5;
}
@media (max-width: 1180px) {
  .mobile-kpis {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .mobile-camera-grid,
  .mobile-two {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 720px) {
  .mobile-panel {
    padding: 15px;
    border-radius: 22px;
  }
  .mobile-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 9px;
  }
  .mobile-tabs {
    position: sticky;
    top: 118px;
    z-index: 9;
    display: flex;
    overflow-x: auto;
    padding: 4px 0;
  }
  .mobile-tab {
    min-width: 104px;
  }
  .mobile-preview-stage,
  .mobile-preview-image {
    min-height: 210px;
  }
  .mobile-info,
  .mobile-form-grid {
    grid-template-columns: 1fr;
  }
  .mobile-camera-list {
    max-height: none;
    overflow: visible;
    padding-right: 0;
  }
}

/* Anti-Tofu mobile field console */
.mobile-ops-page {
  gap: 8px !important;
  color: #dbeafe;
  background: #05080f;
}

.mobile-account-strip,
.mobile-kpi,
.mobile-panel,
.mobile-preview,
.mobile-task,
.mobile-form,
.mobile-filter,
.mobile-camera,
.mobile-tab,
.mobile-channel-row {
  border: 1px solid rgba(56, 189, 248, 0.15) !important;
  background: transparent !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  border-radius: 0 !important;
}

.mobile-account-strip {
  min-height: 34px;
  padding: 7px 10px !important;
}

.mobile-account-strip span,
.mobile-account-strip small,
.mobile-kpi span,
.mobile-kpi small {
  font-size: 10px !important;
}

.mobile-kpis {
  display: flex !important;
  gap: 0 !important;
  border: 1px solid rgba(56, 189, 248, 0.15);
  background: #080b14;
}

.mobile-kpi {
  flex: 1 1 0;
  padding: 6px 8px !important;
  border-width: 0 1px 0 0 !important;
}

.mobile-kpi:last-child {
  border-right: 0 !important;
}

.mobile-kpi strong {
  font-size: 15px !important;
  font-family: Consolas, monospace;
}

.mobile-tabs {
  gap: 6px !important;
}

.mobile-tab {
  min-height: 32px !important;
  padding: 6px 10px !important;
}

.mobile-tab strong {
  font-size: 12px !important;
}

.mobile-panel {
  padding: 10px !important;
}

.mobile-panel-head h3,
.mobile-two h4 {
  font-size: 13px !important;
}

.mobile-camera,
.mobile-task,
.mobile-channel-row {
  padding: 8px !important;
}

.ghost-button,
.action-btn,
.text-link {
  border-color: rgba(56, 189, 248, 0.22) !important;
  background: transparent !important;
  box-shadow: none !important;
}
</style>
