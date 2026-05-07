<template>
  <section class="page notification-workbench-page">
    <WorkbenchShell leftWidth="300px" rightWidth="376px" maxWidth="1880px">
      <template #title>
        <div class="title-block">
          <p>NOTIFICATION WORKBENCH</p>
          <h2>通知配置工作台</h2>
          <span>左边先收通道范围和风暴防护，中间只保留推送作战与通道主表，右边固定承接通道编辑、联调和投递记录。</span>
        </div>
      </template>

      <template #actions>
        <button class="tool-btn" type="button" @click="reload">刷新状态</button>
        <button class="tool-btn" type="button" :disabled="dispatching" @click="runDispatch">
          {{ dispatching ? "执行中..." : "执行告警推送" }}
        </button>
        <button class="tool-btn" type="button" @click="resetForm">恢复默认</button>
        <button class="tool-btn primary" type="button" @click="prepareNewChannel">新增通道</button>
      </template>

      <template #summary>
        <section class="notification-metrics">
          <article class="metric-card">
            <span>通道总数</span>
            <strong>{{ summary.channel_count || 0 }}</strong>
            <small>完整通知台账</small>
          </article>
          <article class="metric-card">
            <span>已启用</span>
            <strong>{{ summary.enabled_count || 0 }}</strong>
            <small>当前正在使用的通道</small>
          </article>
          <article class="metric-card">
            <span>恢复通知</span>
            <strong>{{ summary.resolved_enabled_count || 0 }}</strong>
            <small>支持恢复消息的通道</small>
          </article>
          <article class="metric-card">
            <span>投递成功</span>
            <strong>{{ summary.delivery_success_count || 0 }}</strong>
            <small>最近累计成功记录</small>
          </article>
          <article class="metric-card">
            <span>投递失败</span>
            <strong>{{ summary.delivery_failed_count || 0 }}</strong>
            <small>需要排障的投递异常</small>
          </article>
          <article class="metric-card">
            <span>风暴防护</span>
            <strong>{{ stormGuardLabel }}</strong>
            <small>{{ selectionMeta }}</small>
          </article>
        </section>
      </template>

      <template #roadmap>
        <section class="notification-roadmap">
          <article class="roadmap-step">
            <span>01</span>
            <strong>先看防护状态</strong>
            <small>先判断是否处在大面积异常保护期，避免误把抑制当成通道故障。</small>
          </article>
          <article class="roadmap-step">
            <span>02</span>
            <strong>再看推送范围</strong>
            <small>按目标范围和通道状态收紧对象，再决定联调还是正式投递。</small>
          </article>
          <article class="roadmap-step">
            <span>03</span>
            <strong>右侧改通道</strong>
            <small>通道地址、认证、冷却和抖动抑制都固定在右栏，不再上下找表单。</small>
          </article>
          <article class="roadmap-step">
            <span>04</span>
            <strong>看投递痕迹</strong>
            <small>联调和真实推送的记录都留在右侧，便于快速判断是抑制还是失败。</small>
          </article>
        </section>
      </template>

      <template #left>
        <aside class="notification-left-rail">
          <section class="scope-block">
            <div class="side-head">
              <strong>对象范围</strong>
              <span>{{ scopeSummary }}</span>
            </div>
            <div class="scope-list">
              <button class="scope-row" @click="focusEnabledChannels">
                <strong>已启用通道</strong>
                <span>{{ summary.enabled_count || 0 }} 条当前可投递</span>
              </button>
              <button class="scope-row" @click="focusResolvedChannels">
                <strong>恢复通知通道</strong>
                <span>{{ summary.resolved_enabled_count || 0 }} 条支持恢复消息</span>
              </button>
              <button class="scope-row" @click="focusStormSensitive">
                <strong>风暴敏感范围</strong>
                <span>{{ stormGuardLabel }} / 先看防护再下发</span>
              </button>
              <button class="scope-row" @click="reload">
                <strong>刷新投递现状</strong>
                <span>重拉摘要、通道和投递记录</span>
              </button>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>当前防护状态</strong>
              <span>{{ stormGuardLabel }}</span>
            </div>
            <div class="hint-list">
              <article class="hint-row">
                <strong>观察窗口</strong>
                <span>{{ summary.storm_guard?.lookback_minutes || 0 }} 分钟</span>
              </article>
              <article class="hint-row">
                <strong>有效告警</strong>
                <span>{{ summary.storm_guard?.recent_actionable_count || 0 }} 条 / {{ summary.storm_guard?.distinct_device_count || 0 }} 台设备</span>
              </article>
              <article class="hint-row">
                <strong>说明</strong>
                <span>{{ summary.storm_guard?.reason || "当前没有额外说明" }}</span>
              </article>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>当前建议</strong>
              <span>值班快速判断</span>
            </div>
            <div class="hint-list">
              <article v-for="(item, index) in summary.storm_guard?.recommendations || []" :key="index" class="hint-row">
                <strong>建议 {{ index + 1 }}</strong>
                <span>{{ item }}</span>
              </article>
              <article v-if="!(summary.storm_guard?.recommendations || []).length" class="hint-row">
                <strong>当前建议</strong>
                <span>先用预演检查，确认不会刷屏后再正式发送。</span>
              </article>
            </div>
          </section>
        </aside>
      </template>

      <template #default>
        <section class="notification-center">
          <article class="panel workbench-panel">
            <div class="ops-guide-strip">
              <div class="ops-guide-card">
                <span>当前通道范围</span>
                <strong>{{ scopeSummary }}</strong>
                <small>{{ channels.length }} 条进入主列表</small>
              </div>
              <div class="ops-guide-card">
                <span>调度建议</span>
                <strong>{{ dispatchGuide }}</strong>
                <small>先预演，后正式推送</small>
              </div>
              <div class="ops-guide-card">
                <span>当前模式</span>
                <strong>{{ draftMode ? "新建草稿" : "编辑已选通道" }}</strong>
                <small>{{ draftMode ? "右侧正在准备新的通知通道" : "右侧会跟随当前选中通道" }}</small>
              </div>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">DISPATCH DESK</p>
                <h3>告警推送调度</h3>
                <span>按最近告警执行批量推送，支持预演检查，先验证再正式下发</span>
              </div>
            </div>
            <div class="dispatch-toolbar">
              <label class="field-block narrow">
                <span>回看分钟</span>
                <input v-model.number="dispatchForm.lookback_minutes" class="field-input" type="number" min="1" max="1440" />
              </label>
              <label class="field-block narrow">
                <span>扫描上限</span>
                <input v-model.number="dispatchForm.max_alerts" class="field-input" type="number" min="1" max="1000" />
              </label>
              <label class="switch-row">
                <input v-model="dispatchForm.dry_run" type="checkbox" />
                <span>预演检查</span>
              </label>
              <label class="switch-row">
                <input v-model="dispatchForm.force_dispatch" type="checkbox" />
                <span>强制下发</span>
              </label>
              <button class="tool-btn primary" type="button" :disabled="dispatching" @click="runDispatch">
                {{ dispatching ? "执行中..." : "执行告警推送" }}
              </button>
            </div>
            <p class="status-line">{{ dispatchMessage }}</p>

            <div v-if="lastDispatchResult" class="dispatch-result-grid">
              <article class="detail-chip">
                <span>执行模式</span>
                <strong>{{ lastDispatchResult.dry_run ? "预演检查" : "正式推送" }}</strong>
                <small>{{ lastDispatchResult.force_dispatch ? "强制下发开启" : "按默认保护规则执行" }}</small>
              </article>
              <article class="detail-chip">
                <span>防护级别</span>
                <strong>{{ lastDispatchResult.storm_guard?.label || "正常" }}</strong>
                <small>{{ lastDispatchResult.storm_guard?.reason || "无额外防护说明" }}</small>
              </article>
              <article class="detail-chip">
                <span>扫描告警</span>
                <strong>{{ lastDispatchResult.alerts_scanned || 0 }}</strong>
                <small>跳过 {{ lastDispatchResult.skipped || 0 }} 条</small>
              </article>
              <article class="detail-chip">
                <span>{{ lastDispatchResult.dry_run ? "模拟数量" : "发送数量" }}</span>
                <strong>{{ lastDispatchResult.dry_run ? (lastDispatchResult.simulated || 0) : (lastDispatchResult.sent || 0) }}</strong>
                <small>按本次结果统计</small>
              </article>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">CHANNEL TABLE</p>
                <h3>通知通道主列表</h3>
                <span>{{ channels.length }} 条通道，当前选中 {{ selectionTitle }}</span>
              </div>
              <div class="list-actions">
                <button class="tool-btn" type="button" :disabled="!selectedChannelRecord || testingId === selectedChannelRecord.id" @click="runChannelTest(selectedChannelRecord)">
                  {{ selectedChannelRecord && testingId === selectedChannelRecord.id ? "联调中..." : "联调测试" }}
                </button>
              </div>
            </div>

            <div class="table-shell">
              <table class="mini-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>类型</th>
                    <th>入口</th>
                    <th>范围</th>
                    <th>状态</th>
                    <th>恢复通知</th>
                    <th>最近检查</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in channels"
                    :key="item.id"
                    :class="{ active: selectedChannelId === item.id && !draftMode }"
                    @click="loadChannel(item)"
                  >
                    <td>{{ item.display_name }}</td>
                    <td>{{ channelTypeLabel(item.channel_type) }}</td>
                    <td class="truncate-cell">{{ item.endpoint_url || "-" }}</td>
                    <td>{{ targetScopeLabel(item.target_scope) }}</td>
                    <td>{{ statusLabel(item.status) }}</td>
                    <td>{{ item.send_resolved ? "开启" : "关闭" }}</td>
                    <td>{{ item.last_checked_at ? formatTime(item.last_checked_at) : "-" }}</td>
                    <td class="action-cell">
                      <div class="table-actions">
                        <button class="ops-link" type="button" @click.stop="loadChannel(item)">编辑</button>
                        <button class="ops-link primary" type="button" :disabled="testingId === item.id" @click.stop="runChannelTest(item)">
                          {{ testingId === item.id ? "联调中" : "联调测试" }}
                        </button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="!channels.length">
                    <td colspan="8" class="empty-cell">当前还没有登记通知通道。</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </section>
      </template>

      <template #right>
        <aside class="notification-right-rail">
          <section class="detail-shell">
            <div class="side-head">
              <strong>{{ draftMode ? "新增通知通道" : "通道详情与编辑" }}</strong>
              <span>{{ draftMode ? "右侧草稿模式" : selectionTitle }}</span>
            </div>

            <div class="detail-summary-grid">
              <article class="detail-chip">
                <span>当前状态</span>
                <strong>{{ selectedChannelRecord ? statusLabel(selectedChannelRecord.status) : statusLabel(form.status) }}</strong>
              </article>
              <article class="detail-chip">
                <span>目标范围</span>
                <strong>{{ selectedChannelRecord ? targetScopeLabel(selectedChannelRecord.target_scope) : targetScopeLabel(form.target_scope) }}</strong>
              </article>
              <article class="detail-chip">
                <span>恢复通知</span>
                <strong>{{ (selectedChannelRecord ? selectedChannelRecord.send_resolved : form.send_resolved) ? "开启" : "关闭" }}</strong>
              </article>
              <article class="detail-chip">
                <span>抖动抑制</span>
                <strong>{{ (selectedChannelRecord ? selectedChannelRecord.suppress_flap_watch : form.suppress_flap_watch) ? "开启" : "关闭" }}</strong>
              </article>
            </div>

            <div class="form-grid">
              <label>
                <span>通道键名</span>
                <input v-model="form.channel_key" class="field-input" placeholder="例如 wecom-bot" />
              </label>
              <label>
                <span>显示名称</span>
                <input v-model="form.display_name" class="field-input" placeholder="例如 企业微信机器人" />
              </label>
              <label>
                <span>通道类型</span>
                <select v-model="form.channel_type" class="field-input">
                  <option value="webhook">回调通道（Webhook）</option>
                  <option value="wecom_bot">企业微信机器人</option>
                  <option value="feishu_bot">飞书机器人</option>
                  <option value="wechat_workspace">微信工作台</option>
                </select>
              </label>
              <label>
                <span>入口地址</span>
                <input v-model="form.endpoint_url" class="field-input" placeholder="例如 https://example.com/webhook" />
              </label>
              <label>
                <span>认证方式</span>
                <select v-model="form.auth_mode" class="field-input">
                  <option value="none">无认证</option>
                  <option value="token">令牌</option>
                  <option value="apikey">API 密钥</option>
                  <option value="session">会话</option>
                </select>
              </label>
              <label>
                <span>适用范围</span>
                <select v-model="form.target_scope" class="field-input">
                  <option value="alerts">仅告警</option>
                  <option value="alerts_workorders">告警 + 工单</option>
                  <option value="inspection">巡检</option>
                  <option value="full_ops">全运维</option>
                </select>
              </label>
              <label>
                <span>当前状态</span>
                <select v-model="form.status" class="field-input">
                  <option value="planned">规划中</option>
                  <option value="ready">可联调</option>
                  <option value="testing">测试中</option>
                  <option value="active">已启用</option>
                </select>
              </label>
              <label>
                <span>告警冷却(秒)</span>
                <input v-model.number="form.alert_cooldown_seconds" class="field-input" type="number" min="0" max="86400" />
              </label>
              <label class="switch-row">
                <input v-model="form.enabled" type="checkbox" />
                <span>启用该通道</span>
              </label>
              <label class="switch-row">
                <input v-model="form.send_resolved" type="checkbox" />
                <span>发送恢复通知</span>
              </label>
              <label class="switch-row">
                <input v-model="form.suppress_flap_watch" type="checkbox" />
                <span>抑制网络抖动告警</span>
              </label>
              <label class="full-width">
                <span>备注</span>
                <textarea
                  v-model="form.notes"
                  class="field-input text-area"
                  rows="4"
                  placeholder="记录接收群、使用场景、推送规则和后续接入计划。"
                />
              </label>
            </div>

            <div class="action-row wrap">
              <button class="tool-btn primary" type="button" @click="submitForm">
                {{ draftMode ? "创建通道" : "保存修改" }}
              </button>
              <button class="tool-btn" type="button" :disabled="!selectedChannelRecord || testingId === selectedChannelRecord.id" @click="runChannelTest(selectedChannelRecord)">
                {{ selectedChannelRecord && testingId === selectedChannelRecord.id ? "联调中..." : "联调测试" }}
              </button>
              <button class="tool-btn" type="button" @click="prepareNewChannel">新建草稿</button>
            </div>
            <p class="status-line">{{ actionMessage }}</p>
          </section>

          <section class="detail-shell">
            <div class="side-head">
              <strong>最近投递记录</strong>
              <span>联调与真实下发痕迹</span>
            </div>

            <div class="delivery-list">
              <article v-for="item in deliveries" :key="item.id" class="delivery-row">
                <strong>{{ item.channel_name }} / {{ eventTypeLabel(item.event_type) }}</strong>
                <span>{{ formatTime(item.created_at) }} / {{ item.ok ? "成功" : "失败" }} / {{ item.status_code ?? "-" }}</span>
                <small>{{ item.response_detail }}</small>
              </article>
              <article v-if="!deliveries.length" class="delivery-row">
                <strong>暂无投递记录</strong>
                <span>当前还没有联调或真实推送记录。</span>
              </article>
            </div>
          </section>
        </aside>
      </template>
    </WorkbenchShell>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import WorkbenchShell from "../components/workbench/WorkbenchShell.vue";
import {
  createNotificationChannel,
  dispatchAlertNotifications,
  fetchNotificationChannels,
  fetchNotificationDeliveries,
  fetchNotificationSummary,
  testNotificationChannel,
  updateNotificationChannel,
} from "../api/client";

const summary = ref({
  stage: "",
  channel_count: 0,
  enabled_count: 0,
  resolved_enabled_count: 0,
  delivery_count: 0,
  delivery_success_count: 0,
  delivery_failed_count: 0,
  planned_targets: [],
  recommended_flows: [],
  storm_guard: {
    label: "正常",
    level: "normal",
    lookback_minutes: 0,
    recent_actionable_count: 0,
    distinct_device_count: 0,
    reason: "",
    recommendations: [],
  },
});
const channels = ref([]);
const deliveries = ref([]);
const selectedChannelId = ref(null);
const editingId = ref(null);
const testingId = ref(null);
const draftMode = ref(false);
const actionMessage = ref("先把通知通道登记起来，后续再逐步接入真实消息推送与移动值班联动。");
const dispatching = ref(false);
const dispatchMessage = ref("建议先用预演检查，确认不会刷屏后再正式发送。");
const lastDispatchResult = ref(null);
const dispatchForm = reactive({
  lookback_minutes: 30,
  max_alerts: 200,
  dry_run: true,
  force_dispatch: false,
});
const stormGuardLabel = computed(() => summary.value?.storm_guard?.label || "正常");

const form = reactive({
  channel_key: "",
  display_name: "",
  channel_type: "webhook",
  endpoint_url: "",
  auth_mode: "none",
  target_scope: "alerts",
  enabled: true,
  send_resolved: true,
  alert_cooldown_seconds: 300,
  suppress_flap_watch: true,
  status: "planned",
  notes: "",
});

const selectedChannelRecord = computed(() => {
  if (!selectedChannelId.value) return null;
  return channels.value.find((item) => item.id === selectedChannelId.value) || null;
});
const scopeSummary = computed(() => {
  if (draftMode.value) return "新建通知通道";
  return selectedChannelRecord.value ? `${targetScopeLabel(selectedChannelRecord.value.target_scope)} / ${statusLabel(selectedChannelRecord.value.status)}` : "全部通知通道";
});
const selectionTitle = computed(() => {
  if (draftMode.value) return "新建通知通道草稿";
  return selectedChannelRecord.value?.display_name || "暂未选择通道";
});
const selectionMeta = computed(() => {
  if (draftMode.value) return "右侧正在准备新的通知通道。";
  if (!selectedChannelRecord.value) return "先从中间主列表选中一个通知通道。";
  const record = selectedChannelRecord.value;
  return `${channelTypeLabel(record.channel_type)} / ${statusLabel(record.status)} / ${record.send_resolved ? "恢复通知开启" : "恢复通知关闭"}`;
});
const dispatchGuide = computed(() => {
  if (summary.value?.storm_guard?.level === "suppressed") return "当前处在风暴抑制级别，建议先预演检查，不要直接逐条推送。";
  if (dispatchForm.dry_run) return "当前为预演模式，适合先验证防抖、冷却和通道可达性。";
  return "当前为正式推送模式，建议确认风暴防护和通道状态后再执行。";
});

onMounted(async () => {
  await reload();
});

async function reload() {
  summary.value = await fetchNotificationSummary();
  channels.value = await fetchNotificationChannels();
  deliveries.value = await fetchNotificationDeliveries(20);
  if (draftMode.value) return;
  if (selectedChannelId.value) {
    const matched = channels.value.find((item) => item.id === selectedChannelId.value);
    if (matched) {
      syncFormFromItem(matched);
      return;
    }
  }
  if (channels.value.length) {
    loadChannel(channels.value[0], true);
  } else {
    selectedChannelId.value = null;
    editingId.value = null;
    clearForm();
  }
}

function clearForm() {
  form.channel_key = "";
  form.display_name = "";
  form.channel_type = "webhook";
  form.endpoint_url = "";
  form.auth_mode = "none";
  form.target_scope = "alerts";
  form.enabled = true;
  form.send_resolved = true;
  form.alert_cooldown_seconds = 300;
  form.suppress_flap_watch = true;
  form.status = "planned";
  form.notes = "";
}

function resetForm() {
  draftMode.value = false;
  editingId.value = null;
  selectedChannelId.value = null;
  clearForm();
}

function prepareNewChannel() {
  draftMode.value = true;
  editingId.value = null;
  selectedChannelId.value = null;
  clearForm();
  actionMessage.value = "已切换到新增通知通道模式。";
}

function syncFormFromItem(item) {
  form.channel_key = item.channel_key;
  form.display_name = item.display_name;
  form.channel_type = item.channel_type;
  form.endpoint_url = item.endpoint_url || "";
  form.auth_mode = item.auth_mode;
  form.target_scope = item.target_scope;
  form.enabled = !!item.enabled;
  form.send_resolved = !!item.send_resolved;
  form.alert_cooldown_seconds = Number(item.alert_cooldown_seconds || 300);
  form.suppress_flap_watch = !!item.suppress_flap_watch;
  form.status = item.status;
  form.notes = item.notes || "";
}

function loadChannel(item, silent = false) {
  draftMode.value = false;
  selectedChannelId.value = item.id;
  editingId.value = item.id;
  syncFormFromItem(item);
  if (!silent) {
    actionMessage.value = `正在编辑通道：${item.display_name}`;
  }
}

async function submitForm() {
  try {
    const payload = { ...form };
    if (editingId.value && !draftMode.value) {
      await updateNotificationChannel(editingId.value, payload);
      actionMessage.value = "通知通道已更新。";
    } else {
      await createNotificationChannel(payload);
      draftMode.value = false;
      actionMessage.value = "通知通道已创建。";
    }
    await reload();
  } catch (error) {
    console.error(error);
    actionMessage.value = "保存失败，请检查通道标识是否重复，或查看后端日志。";
  }
}

async function runChannelTest(item) {
  if (!item) return;
  testingId.value = item.id;
  try {
    const result = await testNotificationChannel(item.id);
    actionMessage.value = result.detail || "通知联调已完成。";
    await reload();
  } catch (error) {
    console.error(error);
    actionMessage.value = "联调测试失败，请检查入口地址、代理或后端日志。";
  } finally {
    testingId.value = null;
  }
}

async function runDispatch() {
  if (dispatching.value) return;
  dispatching.value = true;
  try {
    const result = await dispatchAlertNotifications({
      lookback_minutes: dispatchForm.lookback_minutes,
      max_alerts: dispatchForm.max_alerts,
      dry_run: dispatchForm.dry_run,
      force_dispatch: dispatchForm.force_dispatch,
    });
    lastDispatchResult.value = result;
    const guardText = result.storm_guard?.label ? ` 当前防护：${result.storm_guard.label}。` : "";
    dispatchMessage.value = dispatchForm.dry_run
      ? `预演完成：扫描 ${result.alerts_scanned} 条，模拟 ${result.simulated} 条，跳过 ${result.skipped} 条。${guardText}`
      : `推送完成：扫描 ${result.alerts_scanned} 条，发送 ${result.sent} 条，跳过 ${result.skipped} 条。${guardText}`;
    await reload();
  } catch (error) {
    console.error(error);
    dispatchMessage.value = "推送执行失败，请检查后端日志或通知通道配置。";
  } finally {
    dispatching.value = false;
  }
}

function focusEnabledChannels() {
  const target = channels.value.find((item) => item.enabled);
  if (target) loadChannel(target);
}

function focusResolvedChannels() {
  const target = channels.value.find((item) => item.send_resolved);
  if (target) loadChannel(target);
}

function focusStormSensitive() {
  dispatchForm.dry_run = true;
  dispatchMessage.value = "已切回预演检查，建议先判断风暴防护和抖动抑制。";
}

function channelTypeLabel(value) {
  return {
    webhook: "回调通道（Webhook）",
    wecom_bot: "企业微信机器人",
    feishu_bot: "飞书机器人",
    wechat_workspace: "微信工作台",
  }[value] || value;
}

function targetScopeLabel(value) {
  return {
    alerts: "仅告警",
    alerts_workorders: "告警 + 工单",
    inspection: "巡检",
    full_ops: "全运维",
  }[value] || value;
}

function statusLabel(value) {
  return {
    planned: "规划中",
    ready: "可联调",
    testing: "测试中",
    active: "已启用",
  }[value] || value;
}

function formatTime(value) {
  try {
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return value;
  }
}

function eventTypeLabel(value) {
  return (
    {
      alert_created: "告警创建",
      alert_resolved: "告警恢复",
      alert_acknowledged: "告警确认",
      dispatch_success: "投递成功",
      dispatch_failed: "投递失败",
    }[value] || value || "-"
  );
}
</script>

<style scoped>
.notification-workbench-page {
  padding-bottom: 24px;
}

.notification-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.metric-card,
.scope-block,
.panel,
.detail-shell,
.ops-guide-card,
.detail-chip,
.delivery-row {
  border: 1px solid rgba(111, 191, 255, 0.14);
  background: linear-gradient(180deg, rgba(9, 35, 58, 0.94), rgba(7, 24, 40, 0.94));
  box-shadow: 0 18px 48px rgba(5, 10, 18, 0.26);
}

.metric-card {
  border-radius: 18px;
  padding: 16px 18px;
  display: grid;
  gap: 4px;
}

.metric-card span,
.detail-chip span,
.ops-guide-card span {
  font-size: 12px;
  color: rgba(207, 231, 255, 0.68);
}

.metric-card strong,
.detail-chip strong,
.ops-guide-card strong {
  font-size: 20px;
  color: #f4fbff;
}

.metric-card small,
.detail-chip small,
.ops-guide-card small,
.roadmap-step small,
.hint-row span,
.scope-row span,
.status-line,
.action-note,
.empty-note,
.delivery-row span,
.delivery-row small {
  color: rgba(207, 231, 255, 0.72);
}

.notification-roadmap {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.roadmap-step {
  border-radius: 18px;
  padding: 16px 18px;
  border: 1px solid rgba(111, 191, 255, 0.14);
  background: linear-gradient(180deg, rgba(12, 42, 67, 0.96), rgba(8, 28, 45, 0.92));
  display: grid;
  gap: 6px;
}

.roadmap-step span {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(73, 169, 255, 0.18);
  color: #9fd6ff;
  font-size: 12px;
  font-weight: 700;
}

.notification-left-rail,
.notification-center,
.notification-right-rail {
  display: grid;
  gap: 12px;
  min-height: 0;
}

.scope-block,
.panel,
.detail-shell {
  border-radius: 20px;
  padding: 16px;
}

.side-head,
.list-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.side-head strong,
.list-toolbar h3 {
  color: #f4fbff;
}

.side-head span,
.list-toolbar span,
.eyebrow {
  color: rgba(207, 231, 255, 0.72);
}

.scope-list,
.hint-list,
.delivery-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.scope-row,
.hint-row,
.delivery-row {
  width: 100%;
  text-align: left;
  border-radius: 16px;
  padding: 12px 14px;
  display: grid;
  gap: 4px;
  color: #f4fbff;
}

.scope-row,
.hint-row {
  border: 1px solid rgba(111, 191, 255, 0.14);
  background: rgba(255, 255, 255, 0.03);
}

.ops-guide-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.ops-guide-card {
  border-radius: 18px;
  padding: 14px 16px;
  display: grid;
  gap: 4px;
}

.dispatch-toolbar,
.action-row.wrap,
.list-actions,
.table-actions,
.switch-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.field-block {
  display: grid;
  gap: 8px;
  color: #dff2ff;
}

.field-block span,
.switch-row span {
  font-size: 13px;
  color: rgba(207, 231, 255, 0.74);
}

.field-block.narrow {
  width: 140px;
}

.field-input {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(111, 191, 255, 0.16);
  background: rgba(255, 255, 255, 0.04);
  color: #f4fbff;
  padding: 12px 14px;
}

.dispatch-result-grid,
.detail-summary-grid,
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.detail-chip {
  border-radius: 16px;
  padding: 12px 14px;
  display: grid;
  gap: 4px;
}

.table-shell {
  overflow: auto;
  margin-top: 14px;
}

.mini-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 1080px;
}

.mini-table th,
.mini-table td {
  padding: 12px 10px;
  border-bottom: 1px solid rgba(111, 191, 255, 0.1);
  color: #e9f6ff;
  vertical-align: top;
}

.mini-table tbody tr {
  cursor: pointer;
  transition: background 0.16s ease, box-shadow 0.16s ease;
}

.mini-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.03);
}

.mini-table tbody tr.active {
  background: linear-gradient(90deg, rgba(52, 130, 199, 0.22), rgba(32, 86, 133, 0.12));
  box-shadow: inset 3px 0 0 #6fc5ff;
}

.truncate-cell {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ops-link {
  border: none;
  background: transparent;
  color: #8acfff;
  padding: 0;
  cursor: pointer;
}

.ops-link.primary {
  color: #b4f6cf;
}

.form-grid label {
  display: grid;
  gap: 8px;
  color: #dff2ff;
}

.form-grid label span {
  font-size: 13px;
  color: rgba(207, 231, 255, 0.74);
}

.full-width {
  grid-column: 1 / -1;
}

.text-area {
  resize: vertical;
  min-height: 110px;
}

.empty-cell {
  text-align: center;
  color: rgba(207, 231, 255, 0.72);
  padding: 18px 12px;
}

@media (max-width: 1380px) {
  .notification-metrics,
  .notification-roadmap {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .ops-guide-strip,
  .dispatch-result-grid,
  .detail-summary-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1760px) {
  .mini-table {
    min-width: 880px;
  }

  .mini-table th:nth-child(6),
  .mini-table td:nth-child(6),
  .mini-table th:nth-child(7),
  .mini-table td:nth-child(7) {
    display: none;
  }

  .truncate-cell {
    max-width: 220px;
  }
}

@media (max-width: 960px) {
  .notification-metrics,
  .notification-roadmap {
    grid-template-columns: 1fr;
  }
}
</style>
