<template>
  <section class="ai-chat-page">
    <div class="quick-row">
      <button
        v-for="item in quickActions"
        :key="item.type"
        type="button"
        class="quick-action"
        @click="runQuickAction(item)"
      >
        <span>{{ item.icon }}</span>
        <strong>{{ item.label }}</strong>
      </button>
    </div>

    <div class="ai-chat-layout">
      <section class="chat-card">
        <div class="panel-title">
          <div>
            <span>CONVERSATION</span>
            <h3>AI 助手窗口</h3>
          </div>
          <div class="panel-actions">
            <button type="button" class="ghost-btn accent" @click="startNewSession">新建会话</button>
            <button type="button" class="ghost-btn" :disabled="!selectedSessionId" @click="deleteSelectedSession">删除会话</button>
            <button type="button" class="ghost-btn" @click="cleanupTestHistory">清理测试</button>
            <button type="button" class="ghost-btn" @click="clearHistory">清空</button>
          </div>
        </div>

        <div ref="historyRef" class="history-list">
          <article
            v-for="message in history"
            :key="message.id"
            class="message"
            :class="`message-${message.role}`"
          >
            <div class="message-avatar">{{ message.role === "user" ? "我" : "AI" }}</div>
            <div class="message-body">
              <div class="message-meta">
                <strong>{{ message.role === "user" ? "用户输入" : "AI 网关" }}</strong>
                <span>{{ message.time }}</span>
              </div>
              <p>{{ message.text }}</p>
              <small v-if="message.endpoint">接口：{{ message.endpoint }}</small>
            </div>
          </article>

          <div v-if="!history.length" class="empty-state">
            <strong>还没有对话</strong>
            <span>可以直接问“查询 10.0.68.4 设备信息”，或点击上方快捷按钮开始。</span>
          </div>
        </div>

        <div class="composer">
          <div class="chat-controls">
            <label>
              <span>模型</span>
              <select v-model="selectedLlmKey">
                <option value="">自动选择可用模型</option>
                <option v-for="item in llms" :key="item.llm_key" :value="item.llm_key">
                  {{ item.display_name || item.llm_key }}{{ item.ready ? "" : "（未就绪）" }}
                </option>
              </select>
            </label>
            <label>
              <span>会话</span>
              <select v-model="selectedSessionId" @change="handleSessionChange">
                <option v-if="pendingNewSession || !sessions.length" value="" disabled>
                  {{ pendingNewSession ? "新会话（待发送）" : "暂无历史会话" }}
                </option>
                <option v-for="item in sessions" :key="item.session_id" :value="item.session_id">
                  {{ formatSessionOption(item) }}
                </option>
              </select>
            </label>
          </div>
          <div class="session-hint">
            {{ selectedSessionId ? "当前默认继续这个会话，只有点击“新建会话”才会开启新的会话记录。" : "当前处于新会话草稿状态，首次发送后会自动创建并持续复用。" }}
          </div>
          <textarea
            ref="composerRef"
            v-model="inputText"
            rows="4"
            placeholder="输入你要让 AI 网关处理的任务，例如：查询 10.0.56.149 这台摄像头"
            @keydown.ctrl.enter.prevent="sendMessage()"
            @keydown.up="handleComposerArrow"
            @keydown.down="handleComposerArrow"
          ></textarea>
          <div class="composer-actions">
            <span>{{ currentTaskTypeLabel }}，Ctrl + Enter 可快速发送</span>
            <button type="button" :class="{ danger: loading }" :disabled="!loading && !inputText.trim()" @click="loading ? stopMessage() : sendMessage()">
              {{ loading ? "停止" : "发送" }}
            </button>
          </div>
        </div>
      </section>

      <aside class="result-card">
        <div class="panel-title">
          <div>
            <span>RESULT</span>
            <h3>结果展示区</h3>
          </div>
          <button type="button" class="ghost-btn" :disabled="loading" @click="refreshLast">刷新</button>
        </div>

        <div v-if="loading" class="loading-box">
          <span class="pulse-dot"></span>
          AI 网关正在处理任务...
        </div>

        <div v-else-if="errorMessage" class="error-box">
          <strong>调用失败</strong>
          <p>{{ errorMessage }}</p>
        </div>

        <div v-else-if="latestResult" class="result-body">
          <div class="reply-box">
            <span>文字回复</span>
            <p>{{ latestReply }}</p>
          </div>

          <div v-if="deviceCards.length" class="card-list">
            <div class="section-head">
              <h4>设备查询结果</h4>
              <span class="section-badge">{{ deviceCards.length }} 条</span>
            </div>
            <article v-for="device in pagedDeviceCards" :key="device.id || device.management_ip" class="data-card">
              <div>
                <strong>{{ device.hostname || device.channel_name || device.management_ip || "未命名设备" }}</strong>
                <span>{{ device.device_type || "设备" }} / {{ device.area_display_name || "未归属区域" }}</span>
              </div>
              <dl>
                <dt>管理 IP</dt>
                <dd>{{ device.management_ip || "-" }}</dd>
                <dt>状态</dt>
                <dd>{{ device.health_state || device.device_status || device.channel_status || "-" }}</dd>
                <dt>RTSP</dt>
                <dd>{{ device.rtsp_main || device.rtsp_sub || "未记录" }}</dd>
              </dl>
            </article>
            <div v-if="devicePageCount > 1" class="pager">
              <button type="button" class="ghost-btn" :disabled="devicePage <= 1" @click="devicePage -= 1">上一页</button>
              <span>第 {{ devicePage }} / {{ devicePageCount }} 页，共 {{ deviceCards.length }} 条</span>
              <button type="button" class="ghost-btn" :disabled="devicePage >= devicePageCount" @click="devicePage += 1">下一页</button>
            </div>
          </div>

          <div v-if="snapshotCard" class="snapshot-card">
            <div class="snapshot-head">
              <div>
                <span>快照调取</span>
                <h4>{{ snapshotCard.selected_channel?.camera_label || snapshotCard.query || "摄像头快照" }}</h4>
              </div>
              <strong :class="`status-${snapshotCard.status}`">{{ snapshotStatusLabel(snapshotCard.status) }}</strong>
            </div>
            <img v-if="snapshotCard.image_url" :src="snapshotCard.image_url" alt="摄像头快照" />
            <p v-else>{{ snapshotCard.message || snapshotCard.error_message || "暂未生成快照。" }}</p>
            <dl>
              <dt>摄像头 IP</dt>
              <dd>{{ snapshotCard.selected_channel?.camera_ip || snapshotCard.query || "-" }}</dd>
              <dt>通道</dt>
              <dd>{{ snapshotCard.selected_channel?.channel_name || snapshotCard.selected_channel?.channel_id || "-" }}</dd>
              <dt>区域</dt>
              <dd>{{ snapshotCard.selected_channel?.area_display_name || "-" }}</dd>
              <dt>交换机</dt>
              <dd>{{ snapshotCard.selected_channel?.switch_label || snapshotCard.selected_channel?.switch_ip || "-" }}</dd>
              <dt>抓图方式</dt>
              <dd>{{ snapshotCard.capture_strategy || (snapshotCard.selected_channel?.has_rtsp ? "RTSP 待执行" : "无 RTSP") }}</dd>
            </dl>
            <div v-if="snapshotCard.next_actions?.length" class="next-actions">
              <strong>下一步建议</strong>
              <span v-for="item in snapshotCard.next_actions" :key="item">{{ item }}</span>
            </div>
          </div>

          <div v-if="alertCards.length || alertSummary" class="card-list">
            <div class="section-head">
              <h4>告警分析结果</h4>
              <span class="section-badge">{{ alertCards.length || (alertSummary?.open_count ?? 0) }} 条</span>
            </div>
            <div v-if="alertSummary" class="metric-grid">
              <span>待处理 {{ alertSummary.open_count ?? 0 }}</span>
              <span>严重 {{ alertSummary.open_critical_count ?? 0 }}</span>
              <span>抖动观察 {{ alertSummary.flap_watch_count ?? 0 }}</span>
            </div>
            <article v-for="alert in pagedAlertCards" :key="alert.id" class="data-card alert-card">
              <div>
                <strong>{{ alert.title || `告警 #${alert.id}` }}</strong>
                <span>{{ alert.severity || "普通" }} / {{ alert.status || "-" }}</span>
              </div>
              <p>{{ alert.attribution_type || alert.source_type || "暂无归因信息" }}</p>
            </article>
            <div v-if="alertPageCount > 1" class="pager">
              <button type="button" class="ghost-btn" :disabled="alertPage <= 1" @click="alertPage -= 1">上一页</button>
              <span>第 {{ alertPage }} / {{ alertPageCount }} 页，共 {{ alertCards.length }} 条</span>
              <button type="button" class="ghost-btn" :disabled="alertPage >= alertPageCount" @click="alertPage += 1">下一页</button>
            </div>
          </div>

          <div v-if="reportCard" class="report-box">
            <div class="section-head">
              <h4>报告生成</h4>
              <span class="section-badge">文本</span>
            </div>
            <pre>{{ reportCard }}</pre>
          </div>

          <div v-if="topologyCard" class="card-list">
            <div class="section-head">
              <h4>拓扑链路结果</h4>
              <span class="section-badge">{{ topologyItems.length }} 条</span>
            </div>
            <div class="metric-grid">
              <span>交换机 {{ topologyCard.summary?.switch_count ?? 0 }}</span>
              <span>摄像头 {{ topologyCard.summary?.camera_count ?? 0 }}</span>
              <span>链路 {{ topologyCard.summary?.link_count ?? 0 }}</span>
            </div>
            <article v-for="item in pagedTopologyItems" :key="item.channel_id" class="data-card">
              <div>
                <strong>{{ item.camera_label || item.camera_ip }}</strong>
                <span>{{ item.switch_label || "未归属交换机" }} / {{ item.switch_port_name || "端口未知" }}</span>
              </div>
              <p>置信度 {{ Math.round((item.topology_confidence || 0) * 100) }}%，证据 {{ item.topology_evidence_type || "暂无" }}</p>
            </article>
            <div v-if="topologyPageCount > 1" class="pager">
              <button type="button" class="ghost-btn" :disabled="topologyPage <= 1" @click="topologyPage -= 1">上一页</button>
              <span>第 {{ topologyPage }} / {{ topologyPageCount }} 页，共 {{ topologyItems.length }} 条</span>
              <button type="button" class="ghost-btn" :disabled="topologyPage >= topologyPageCount" @click="topologyPage += 1">下一页</button>
            </div>
          </div>

          <div v-if="systemStatusCard" class="card-list">
            <div class="section-head">
              <h4>系统状态</h4>
              <span class="section-badge">实时</span>
            </div>
            <div class="metric-grid">
              <span>设备 {{ systemStatusCard.counts?.devices ?? 0 }}</span>
              <span>通道 {{ systemStatusCard.counts?.channels ?? 0 }}</span>
              <span>待处理告警 {{ systemStatusCard.counts?.open_alerts ?? 0 }}</span>
            </div>
            <article class="data-card">
              <div>
                <strong>AI 网关</strong>
                <span>{{ systemStatusCard.ai_connection?.status_label || "未知" }}</span>
              </div>
              <p>最近连接：{{ formatDateTime(systemStatusCard.ai_connection?.last_seen_at) || "暂无" }}</p>
            </article>
          </div>

          <div v-if="featureGuideCard?.guides?.length" class="card-list">
            <div class="section-head">
              <h4>操作引导</h4>
              <span class="section-badge">{{ featureGuideCard.guides.length }} 条</span>
            </div>
            <article v-for="guide in pagedGuideCards" :key="guide.intent" class="data-card">
              <div>
                <strong>{{ guide.intent }}</strong>
                <span>{{ guide.module }}</span>
              </div>
              <p v-for="(step, index) in guide.steps || []" :key="`${guide.intent}-${index}`">{{ index + 1 }}. {{ step }}</p>
              <dl v-if="guide.entrypoints?.length">
                <dt>接口入口</dt>
                <dd>{{ guide.entrypoints.join(" / ") }}</dd>
              </dl>
            </article>
            <div v-if="guidePageCount > 1" class="pager">
              <button type="button" class="ghost-btn" :disabled="guidePage <= 1" @click="guidePage -= 1">上一页</button>
              <span>第 {{ guidePage }} / {{ guidePageCount }} 页，共 {{ featureGuideCard.guides.length }} 条</span>
              <button type="button" class="ghost-btn" :disabled="guidePage >= guidePageCount" @click="guidePage += 1">下一页</button>
            </div>
          </div>

          <div v-if="opsSummaryCard?.sections?.length" class="card-list">
            <div class="section-head">
              <h4>模块概况</h4>
              <span class="section-badge">{{ opsSummaryCard.sections.length }} 组</span>
            </div>
            <article v-for="section in pagedOpsSections" :key="section.module" class="data-card">
              <div>
                <strong>{{ section.label }}</strong>
                <span>{{ section.module }}</span>
              </div>
              <div v-if="section.summary" class="metric-grid">
                <span v-for="(value, key) in section.summary" :key="`${section.module}-${key}`">{{ key }} {{ value || 0 }}</span>
              </div>
              <dl v-if="section.items?.length">
                <template v-for="item in pagedSectionItems(section)" :key="`${section.module}-${item.id}`">
                  <dt>{{ item.title }}</dt>
                  <dd>{{ item.subtitle }}{{ item.updated_at ? ` / ${formatDateTime(item.updated_at)}` : "" }}</dd>
                </template>
              </dl>
              <div v-if="sectionPageCount(section) > 1" class="pager pager-inline">
                <button type="button" class="ghost-btn" :disabled="sectionCurrentPage(section) <= 1" @click="changeSectionPage(section, -1)">上一页</button>
                <span>第 {{ sectionCurrentPage(section) }} / {{ sectionPageCount(section) }} 页，共 {{ (section.items || []).length }} 条</span>
                <button type="button" class="ghost-btn" :disabled="sectionCurrentPage(section) >= sectionPageCount(section)" @click="changeSectionPage(section, 1)">下一页</button>
              </div>
            </article>
            <div v-if="opsSectionPageCount > 1" class="pager">
              <button type="button" class="ghost-btn" :disabled="opsSectionPage <= 1" @click="opsSectionPage -= 1">上一页</button>
              <span>第 {{ opsSectionPage }} / {{ opsSectionPageCount }} 页，共 {{ opsSummaryCard.sections.length }} 个模块</span>
              <button type="button" class="ghost-btn" :disabled="opsSectionPage >= opsSectionPageCount" @click="opsSectionPage += 1">下一页</button>
            </div>
          </div>

          <div v-if="opsSummaryCard?.actions?.length" class="card-list">
            <div class="section-head">
              <h4>执行结果</h4>
              <span class="section-badge">{{ opsSummaryCard.actions.length }} 条</span>
            </div>
            <article
              v-for="action in pagedOpsActions"
              :key="`${action.module}-${action.action}-${action.executed_at}`"
              class="data-card"
            >
              <div>
                <strong>{{ action.title || action.action }}</strong>
                <span>{{ action.module }} / {{ action.ok ? "执行成功" : "执行未完成" }}</span>
              </div>
              <p>{{ action.detail || "已返回执行结果。" }}</p>
              <dl v-if="action.executed_at || Object.keys(action.data || {}).length">
                <dt v-if="action.executed_at">执行时间</dt>
                <dd v-if="action.executed_at">{{ formatDateTime(action.executed_at) }}</dd>
                <dt v-if="Object.keys(action.data || {}).length">结果数据</dt>
                <dd v-if="Object.keys(action.data || {}).length">{{ JSON.stringify(action.data) }}</dd>
              </dl>
            </article>
            <div v-if="opsActionPageCount > 1" class="pager">
              <button type="button" class="ghost-btn" :disabled="opsActionPage <= 1" @click="opsActionPage -= 1">上一页</button>
              <span>第 {{ opsActionPage }} / {{ opsActionPageCount }} 页，共 {{ opsSummaryCard.actions.length }} 条</span>
              <button type="button" class="ghost-btn" :disabled="opsActionPage >= opsActionPageCount" @click="opsActionPage += 1">下一页</button>
            </div>
          </div>
        </div>

        <div v-else class="empty-result">
          <strong>等待任务</strong>
          <span>结果会在这里格式化展示，设备数据会自动变成卡片。</span>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { cleanupAiTestSessions, deleteAiSession, fetchAiLlms, fetchAiSession, fetchAiSessions } from "../api/client";
import { extractPayload, inferTaskType, sendAiChatTask } from "./aiChatClient";

const inputText = ref("");
const history = ref([]);
const latestResult = ref(null);
const latestTask = ref(null);
const loading = ref(false);
const errorMessage = ref("");
const historyRef = ref(null);
const composerRef = ref(null);
const llms = ref([]);
const sessions = ref([]);
const selectedLlmKey = ref("");
const selectedSessionId = ref("");
const activeController = ref(null);
const pendingNewSession = ref(false);
const promptHistory = ref([]);
const promptHistoryIndex = ref(-1);
const promptDraft = ref("");
const devicePage = ref(1);
const alertPage = ref(1);
const topologyPage = ref(1);
const guidePage = ref(1);
const opsSectionPage = ref(1);
const opsActionPage = ref(1);
const sectionItemPages = ref({});
const RESULT_PAGE_SIZE = 5;
const SECTION_PAGE_SIZE = 4;
const SECTION_ITEM_PAGE_SIZE = 6;
const SESSION_STORAGE_KEY = "yj-ai-assistant-active-session";

const TASK_TYPE_LABELS = {
  general: "通用对话",
  device_query: "设备查询",
  snapshot_capture: "快照调取",
  alert_analyze: "告警分析",
  report_generate: "报告生成",
  topology_query: "拓扑链路",
  system_status: "系统状态",
  ops_summary: "模块概况",
};

const quickActions = [
  { icon: "📊", label: "设备查询", type: "device_query", prompt: "查询 10.0.68.4 这台设备的信息" },
  { icon: "📸", label: "调取快照", type: "snapshot_capture", prompt: "调取 10.0.56.149 这个摄像头的快照" },
  { icon: "⚠️", label: "告警分析", type: "alert_analyze", prompt: "分析当前平台告警，给出需要优先处理的设备和建议" },
  { icon: "📝", label: "生成报告", type: "report_generate", prompt: "生成今日弱电视频运维简报" },
  { icon: "🕸", label: "拓扑链路", type: "topology_query", prompt: "查询 10.0.56.149 的交换机归属和链路证据" },
  { icon: "🟢", label: "系统状态", type: "system_status", prompt: "查询平台当前系统状态和 AI 网关状态" },
  { icon: "🧩", label: "模块概况", type: "ops_summary", prompt: "查询当前用户、通知、工单、派工和备份概况" },
  { icon: "🔄", label: "刷新", type: "refresh", prompt: "" },
];

const inferredTaskType = computed(() => inferTaskType(inputText.value));
const currentTaskTypeLabel = computed(
  () => TASK_TYPE_LABELS[inferredTaskType.value] || "通用对话",
);

const taskContext = computed(() => latestResult.value?.task_context || latestResult.value?.context || {});
const skillPayload = computed(() => taskContext.value?.skill_payload || {});

const deviceCards = computed(() => {
  const devices = skillPayload.value.devices || skillPayload.value.results || [];
  return Array.isArray(devices) ? devices : [];
});
const topologyItems = computed(() => {
  const rows = topologyCard.value?.focus_channels || [];
  return Array.isArray(rows) ? rows : [];
});

const pagedDeviceCards = computed(() => paginateItems(deviceCards.value, devicePage.value, RESULT_PAGE_SIZE));
const devicePageCount = computed(() => getPageCount(deviceCards.value, RESULT_PAGE_SIZE));

const pagedAlertCards = computed(() => paginateItems(alertCards.value, alertPage.value, RESULT_PAGE_SIZE));
const alertPageCount = computed(() => getPageCount(alertCards.value, RESULT_PAGE_SIZE));

const pagedTopologyItems = computed(() => paginateItems(topologyItems.value, topologyPage.value, RESULT_PAGE_SIZE));
const topologyPageCount = computed(() => getPageCount(topologyItems.value, RESULT_PAGE_SIZE));

const pagedGuideCards = computed(() => paginateItems(featureGuideCard.value?.guides || [], guidePage.value, RESULT_PAGE_SIZE));
const guidePageCount = computed(() => getPageCount(featureGuideCard.value?.guides || [], RESULT_PAGE_SIZE));

const pagedOpsSections = computed(() => paginateItems(opsSummaryCard.value?.sections || [], opsSectionPage.value, SECTION_PAGE_SIZE));
const opsSectionPageCount = computed(() => getPageCount(opsSummaryCard.value?.sections || [], SECTION_PAGE_SIZE));

const pagedOpsActions = computed(() => paginateItems(opsSummaryCard.value?.actions || [], opsActionPage.value, RESULT_PAGE_SIZE));
const opsActionPageCount = computed(() => getPageCount(opsSummaryCard.value?.actions || [], RESULT_PAGE_SIZE));

const alertSummary = computed(() => skillPayload.value.summary || null);
const alertCards = computed(() => {
  const alerts = skillPayload.value.alerts || skillPayload.value.latest_alerts || [];
  return Array.isArray(alerts) ? alerts : [];
});

const snapshotCard = computed(() => {
  if (skillPayload.value?.tool === "snapshot_capture") {
    return skillPayload.value;
  }
  return null;
});

const topologyCard = computed(() => {
  if (skillPayload.value?.tool === "topology_query") {
    return skillPayload.value;
  }
  return null;
});

const systemStatusCard = computed(() => {
  if (skillPayload.value?.tool === "system_status") {
    return skillPayload.value;
  }
  return null;
});

const featureGuideCard = computed(() => {
  if (skillPayload.value?.tool === "feature_guide") {
    return skillPayload.value;
  }
  return null;
});

const opsSummaryCard = computed(() => {
  if (skillPayload.value?.tool === "ops_summary") {
    return skillPayload.value;
  }
  return null;
});

const effectiveLlmKey = computed(() => {
  if (selectedLlmKey.value) {
    return selectedLlmKey.value;
  }
  return llms.value.find((item) => item.ready)?.llm_key || "";
});

const reportCard = computed(() => {
  if (!latestResult.value) {
    return "";
  }
  if (skillPayload.value.report) {
    return typeof skillPayload.value.report === "string"
      ? skillPayload.value.report
      : JSON.stringify(skillPayload.value.report, null, 2);
  }
  if (latestResult.value.task_type === "report_generate") {
    return JSON.stringify(skillPayload.value || latestResult.value, null, 2);
  }
  return "";
});

const latestReply = computed(() => {
  const result = latestResult.value;
  if (!result) {
    return "";
  }
  if (snapshotCard.value?.message) {
    return appendModelWarning(snapshotCard.value.message, result);
  }
  const toolReply = buildFallbackReply(result, { allowJsonFallback: false });
  if (toolReply) {
    return appendModelWarning(toolReply, result);
  }
  if (result.llm?.status === "failed") {
    return `模型已选择，但调用失败：${friendlyModelError(result.llm.reason)}。`;
  }
  if (result.llm?.status === "skipped") {
    return `模型未实际调用：${result.llm.reason || "模型未就绪"}。请在 AI中心检查模型是否启用、API Key 是否保存。`;
  }
  if (!result.llm?.text && result.decision?.chosen_llm_key) {
    return `模型 ${result.decision.chosen_llm_key} 未返回文字内容，请检查模型接口返回格式。`;
  }
  return (
    result.reply ||
    cleanModelText(result.llm?.text) ||
    result.message ||
    result.result ||
    result.output ||
    result.text ||
    result.summary ||
    result.execution?.summary ||
    result.coordinator?.summary ||
    buildFallbackReply(result)
  );
});

const lastUserPrompt = computed(() => {
  if (latestTask.value?.task) {
    return String(latestTask.value.task);
  }
  const lastUserMessage = [...history.value].reverse().find((item) => item.role === "user");
  return String(lastUserMessage?.text || "");
});

watch(latestResult, () => {
  resetResultPaging();
});

watch(selectedSessionId, () => {
  resetResultPaging();
});

function getPageCount(items, pageSize) {
  const total = Array.isArray(items) ? items.length : 0;
  return Math.max(1, Math.ceil(total / pageSize));
}

function paginateItems(items, page, pageSize) {
  const rows = Array.isArray(items) ? items : [];
  const totalPages = getPageCount(rows, pageSize);
  const safePage = Math.min(Math.max(page || 1, 1), totalPages);
  const start = (safePage - 1) * pageSize;
  return rows.slice(start, start + pageSize);
}

function resetResultPaging() {
  devicePage.value = 1;
  alertPage.value = 1;
  topologyPage.value = 1;
  guidePage.value = 1;
  opsSectionPage.value = 1;
  opsActionPage.value = 1;
  sectionItemPages.value = {};
}

function sectionCurrentPage(section) {
  return sectionItemPages.value?.[section.module] || 1;
}

function sectionPageCount(section) {
  return getPageCount(section?.items || [], SECTION_ITEM_PAGE_SIZE);
}

function pagedSectionItems(section) {
  return paginateItems(section?.items || [], sectionCurrentPage(section), SECTION_ITEM_PAGE_SIZE);
}

function changeSectionPage(section, offset) {
  const current = sectionCurrentPage(section);
  const total = sectionPageCount(section);
  const next = Math.min(Math.max(current + offset, 1), total);
  sectionItemPages.value = {
    ...sectionItemPages.value,
    [section.module]: next,
  };
}

function cleanModelText(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  return text.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
}

function friendlyModelError(reason) {
  const text = String(reason || "未知错误");
  if (text.includes("HTTP 529")) {
    return `${text}。这是模型供应商返回的拥堵/限流类错误，系统已自动重试；如果仍失败，请稍后再试，或切换其他已就绪模型。`;
  }
  if (text.includes("HTTP 401") || text.includes("HTTP 403")) {
    return `${text}。请检查 API Key 是否正确、账号是否有该模型权限。`;
  }
  if (text.includes("HTTP 404")) {
    return `${text}。请检查接口地址或模型名是否正确。`;
  }
  return `${text}。请检查模型 API 地址、模型名、API Key、余额权限或供应商状态。`;
}

onMounted(async () => {
  await reloadAiOptions();
});

async function reloadAiOptions() {
  try {
    const [nextLlms, nextSessions] = await Promise.all([fetchAiLlms(), fetchAiSessions(40)]);
    llms.value = nextLlms;
    sessions.value = nextSessions;
    if (!selectedLlmKey.value || !nextLlms.some((item) => item.llm_key === selectedLlmKey.value)) {
      selectedLlmKey.value = nextLlms.find((item) => item.ready)?.llm_key || "";
    }
    const currentExists = selectedSessionId.value && nextSessions.some((item) => item.session_id === selectedSessionId.value);
    if (currentExists) {
      writeStoredSessionId(selectedSessionId.value);
      return;
    }
    if (pendingNewSession.value) {
      return;
    }
    const storedSessionId = readStoredSessionId();
    const nextDefaultSession =
      nextSessions.find((item) => item.session_id === storedSessionId)?.session_id || nextSessions[0]?.session_id || "";
    if (nextDefaultSession) {
      selectedSessionId.value = nextDefaultSession;
      writeStoredSessionId(nextDefaultSession);
      await loadSelectedSession();
      return;
    }
    selectedSessionId.value = "";
    history.value = [];
    latestResult.value = null;
  } catch (error) {
    console.warn("Failed to load AI chat options.", error);
  }
}

function appendModelWarning(baseText, result) {
  const text = String(baseText || "").trim();
  if (!text) {
    return "";
  }
  if (result?.llm?.status === "failed") {
    const reason = friendlyModelError(result.llm.reason);
    const toolSucceeded = skillPayload.value?.status === "success";
    if (toolSucceeded) {
      return `${text}\n\n本次系统结果已返回。模型补充说明暂时不可用：${reason}。`;
    }
    return `${text}\n\n模型补充说明失败：${reason}。`;
  }
  if (result?.llm?.status === "skipped") {
    return `${text}\n\n模型未实际调用：${result.llm.reason || "模型未就绪"}。`;
  }
  if (!result?.llm?.text && result?.decision?.chosen_llm_key) {
    return `${text}\n\n模型 ${result.decision.chosen_llm_key} 未返回文字内容。`;
  }
  return text;
}

function formatTopologyConfidence(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "";
  }
  return `${Math.round(value * 100)}%`;
}

function buildTopologyFallback(card) {
  const focus = Array.isArray(card?.focus_channels) ? card.focus_channels : [];
  const first = focus[0];
  if (first) {
    const cameraLabel = first.camera_label || first.channel_name || first.camera_ip || "目标摄像头";
    const switchLabel = first.switch_label || first.switch_ip || "未识别交换机";
    const portLabel = first.switch_port_name || "端口未知";
    const vlanLabel = first.switch_vlan_id ? ` / VLAN ${first.switch_vlan_id}` : "";
    const evidenceLabel = first.topology_evidence_type || "暂无证据";
    const confidenceLabel = formatTopologyConfidence(first.topology_confidence);
    const streamStatus = first.stream_probe_status === "ok" ? "，取流诊断正常" : "";
    const confidenceText = confidenceLabel ? `，置信度 ${confidenceLabel}` : "";
    const extraCount = focus.length > 1 ? `；另有 ${focus.length - 1} 条关联链路可展开查看` : "";
    return `${cameraLabel}（${first.camera_ip || card.query || "-" }）当前归属 ${switchLabel} / ${portLabel}${vlanLabel}，证据 ${evidenceLabel}${confidenceText}${streamStatus}${extraCount}。`;
  }
  return `已查询拓扑链路，当前记录链路 ${card?.summary?.link_count ?? 0} 条。`;
}

function buildDeviceFallback(devices) {
  const first = Array.isArray(devices) ? devices[0] : null;
  if (first) {
    const name = first.hostname || first.channel_name || first.management_ip || "目标设备";
    const ip = first.management_ip || first.camera_ip || "-";
    const type = first.device_type || "设备";
    const status = first.status || first.stream_probe_status || "状态未知";
    const area = first.area_display_name ? `，区域 ${first.area_display_name}` : "";
    const switchLabel = first.switch_label || first.switch_ip;
    const switchText = switchLabel ? `，归属 ${switchLabel}${first.switch_port_name ? ` / ${first.switch_port_name}` : ""}` : "";
    const extraCount = devices.length > 1 ? `；另有 ${devices.length - 1} 条结果可继续查看` : "";
    return `${name}（${ip}）类型 ${type}，当前状态 ${status}${area}${switchText}${extraCount}。`;
  }
  return "";
}

function buildFallbackReply(result, options = {}) {
  const allowJsonFallback = options.allowJsonFallback ?? true;
  if (snapshotCard.value) {
    return snapshotCard.value.message || `快照任务状态：${snapshotStatusLabel(snapshotCard.value.status)}。`;
  }
  if (topologyCard.value) {
    return buildTopologyFallback(topologyCard.value);
  }
  if (systemStatusCard.value) {
    return `平台当前设备 ${systemStatusCard.value.counts?.devices ?? 0} 台，通道 ${systemStatusCard.value.counts?.channels ?? 0} 路，待处理告警 ${systemStatusCard.value.counts?.open_alerts ?? 0} 条。`;
  }
  if (featureGuideCard.value?.guides?.length) {
    return `已根据当前问题整理出 ${featureGuideCard.value.guides.length} 组操作引导。`;
  }
  if (opsSummaryCard.value?.sections?.length || opsSummaryCard.value?.actions?.length) {
    if (opsSummaryCard.value?.message) {
      return opsSummaryCard.value.message;
    }
    if (opsSummaryCard.value.actions?.length) {
      const first = opsSummaryCard.value.actions[0];
      const extra = opsSummaryCard.value.actions.length > 1 ? `，另有 ${opsSummaryCard.value.actions.length - 1} 项执行结果` : "";
      return `${first.title || "已执行 AI 助手动作"}：${first.detail || "操作已完成"}${extra}。`;
    }
    const assetSection = opsSummaryCard.value.sections?.find((section) => section.module === "assets");
    if (assetSection?.summary) {
      if (/分布|类型|构成|占比|分类|统计|明细|breakdown|distribution/i.test(lastUserPrompt.value || "")) {
        return `当前设备分布：交换机 ${assetSection.summary.switches ?? 0} 台，摄像头 ${assetSection.summary.cameras ?? 0} 台，录像机 ${assetSection.summary.recorders ?? 0} 台，解码器 ${assetSection.summary.decoders ?? 0} 台，通道 ${assetSection.summary.channels ?? 0} 路。`;
      }
      if (/交换机|switch/i.test(lastUserPrompt.value || "")) {
        return `当前共有 ${assetSection.summary.switches ?? 0} 台交换机。`;
      }
      if (/摄像头|camera/i.test(lastUserPrompt.value || "")) {
        return `当前共有 ${assetSection.summary.cameras ?? 0} 台摄像头。`;
      }
      if (/录像机|nvr|recorder/i.test(lastUserPrompt.value || "")) {
        return `当前共有 ${assetSection.summary.recorders ?? 0} 台录像机。`;
      }
      if (/解码器|decoder/i.test(lastUserPrompt.value || "")) {
        return `当前共有 ${assetSection.summary.decoders ?? 0} 台解码器。`;
      }
      if (/通道|channel/i.test(lastUserPrompt.value || "")) {
        return `当前共有 ${assetSection.summary.channels ?? 0} 路通道。`;
      }
      if (/设备|device/i.test(lastUserPrompt.value || "")) {
        return `当前共有 ${assetSection.summary.devices ?? 0} 台设备。`;
      }
    }
    return `已汇总 ${opsSummaryCard.value.sections.length} 个模块的当前概况。`;
  }
  if (deviceCards.value.length) {
    return buildDeviceFallback(deviceCards.value) || `已查询到 ${deviceCards.value.length} 条设备结果。`;
  }
  if (alertCards.value.length || alertSummary.value) {
    return `已完成告警分析，当前待处理 ${alertSummary.value?.open_count ?? 0} 条。`;
  }
  if (!allowJsonFallback) {
    return "";
  }
  return JSON.stringify(result, null, 2);
}

function snapshotStatusLabel(status) {
  return {
    success: "已生成",
    failed: "抓图失败",
    not_found: "未登记",
    pending: "处理中",
  }[status] || "未知";
}

function formatDateTime(value) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString("zh-CN", { hour12: false });
}

function taskTypeLabel(taskType) {
  return TASK_TYPE_LABELS[String(taskType || "").trim()] || "通用对话";
}

function normalizeSessionTitle(value) {
  let text = String(value || "")
    .replace(/\s+/g, " ")
    .replace(/^OpenClaw 已完成任务决策与汇总。?\s*/i, "")
    .replace(/^AI 网关[:：]?\s*/i, "")
    .trim();
  if (!text || text === "未命名会话") {
    return "";
  }
  if (text.length > 28) {
    text = `${text.slice(0, 28)}...`;
  }
  return text;
}

function sessionStatusLabel(status) {
  return {
    completed: "已完成",
    success: "成功",
    action_executed: "已执行",
    failed: "失败",
    pending: "处理中",
    skipped: "已跳过",
  }[String(status || "").trim()] || "";
}

function formatSessionOption(item) {
  const title = normalizeSessionTitle(item.display_title || item.title || "");
  const type = taskTypeLabel(item.task_type || "general");
  const count = item.message_count || 0;
  const time = formatDateTime(item.updated_at || item.created_at);
  const status = sessionStatusLabel(item.last_status);
  const fallbackTitle = title || `${type}会话`;
  return `${time ? `${time} / ` : ""}${type} / ${count} 条 / ${fallbackTitle}${status ? ` / ${status}` : ""}`;
}

function nowText() {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function readStoredSessionId() {
  if (typeof window === "undefined") {
    return "";
  }
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY) || "";
  } catch (_error) {
    return "";
  }
}

function writeStoredSessionId(sessionId) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    if (sessionId) {
      window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    } else {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  } catch (_error) {
    // ignore localStorage errors
  }
}

function rememberPrompt(task) {
  const text = String(task || "").trim();
  if (!text) {
    return;
  }
  const next = promptHistory.value.filter((item) => item !== text);
  next.push(text);
  promptHistory.value = next.slice(-30);
  promptHistoryIndex.value = -1;
  promptDraft.value = "";
}

function moveComposerCursorToEnd() {
  nextTick(() => {
    const el = composerRef.value;
    if (!el || typeof el.setSelectionRange !== "function") {
      return;
    }
    const length = String(inputText.value || "").length;
    el.focus();
    el.setSelectionRange(length, length);
  });
}

function handleComposerArrow(event) {
  if (loading.value || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
    return;
  }
  const el = event.target;
  if (!el || typeof el.selectionStart !== "number" || typeof el.selectionEnd !== "number") {
    return;
  }
  if (event.key === "ArrowUp") {
    const atTop = el.selectionStart === 0 && el.selectionEnd === 0;
    if (!promptHistory.value.length || (!atTop && inputText.value.trim())) {
      return;
    }
    event.preventDefault();
    if (promptHistoryIndex.value === -1) {
      promptDraft.value = inputText.value;
      promptHistoryIndex.value = promptHistory.value.length - 1;
    } else {
      promptHistoryIndex.value = Math.max(0, promptHistoryIndex.value - 1);
    }
    inputText.value = promptHistory.value[promptHistoryIndex.value] || "";
    moveComposerCursorToEnd();
    return;
  }
  if (event.key === "ArrowDown" && promptHistoryIndex.value !== -1) {
    event.preventDefault();
    const nextIndex = promptHistoryIndex.value + 1;
    if (nextIndex >= promptHistory.value.length) {
      promptHistoryIndex.value = -1;
      inputText.value = promptDraft.value;
    } else {
      promptHistoryIndex.value = nextIndex;
      inputText.value = promptHistory.value[nextIndex] || "";
    }
    moveComposerCursorToEnd();
  }
}

function pushHistory(role, text, endpoint = "") {
  history.value.push({
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    text,
    time: nowText(),
    endpoint,
  });
  nextTick(() => {
    if (historyRef.value) {
      historyRef.value.scrollTop = historyRef.value.scrollHeight;
    }
  });
}

async function sendMessage(override = {}) {
  const task = (override.task || inputText.value).trim();
  const taskType = override.taskType || inferTaskType(task);
  const payload = override.payload || extractPayload(task, taskType);

  if (!task || loading.value) {
    return;
  }

  const llmKey = override.llmKey ?? effectiveLlmKey.value;
  const sessionId = override.forceNewSession || pendingNewSession.value ? "" : override.sessionId ?? selectedSessionId.value;
  latestTask.value = { task, taskType, payload, llmKey, sessionId };
  errorMessage.value = "";
  loading.value = true;
  activeController.value = new AbortController();
  rememberPrompt(task);
  pushHistory("user", task);
  inputText.value = "";

  try {
    const response = await sendAiChatTask({ task, taskType, payload, llmKey, sessionId, signal: activeController.value.signal });
    latestResult.value = {
      ...response.data,
      task_type: response.data?.task_type || taskType,
    };
    if (response.data?.session_id) {
      selectedSessionId.value = response.data.session_id;
      pendingNewSession.value = false;
      writeStoredSessionId(response.data.session_id);
    }
    const reply = response.fallback
      ? `${latestReply.value}\n\n已自动切换到可用网关地址。首次请求错误：${response.primary_error}`
      : latestReply.value;
    pushHistory("assistant", reply, response.endpoint);
  } catch (error) {
    if (error.name === "AbortError") {
      errorMessage.value = "已停止当前 AI 请求。";
      pushHistory("assistant", "已停止当前 AI 请求。");
      return;
    }
    const detail = error.primary_error
      ? `${error.message}；直连错误：${error.primary_error}`
      : error.message || "未知错误";
    errorMessage.value = detail;
    pushHistory("assistant", `调用失败：${detail}`);
  } finally {
    loading.value = false;
    activeController.value = null;
    reloadAiOptions();
  }
}

function stopMessage() {
  if (activeController.value) {
    activeController.value.abort();
  }
}

function runQuickAction(item) {
  if (item.type === "refresh") {
    refreshLast();
    return;
  }
  sendMessage({
    task: item.prompt,
    taskType: item.type,
    payload: extractPayload(item.prompt, item.type),
  });
}

function refreshLast() {
  if (latestTask.value) {
    sendMessage(latestTask.value);
    return;
  }
  inputText.value = "查询平台当前 AI 网关状态和设备运维概况";
  sendMessage();
}

function clearHistory() {
  history.value = [];
  latestResult.value = null;
  latestTask.value = null;
  errorMessage.value = "";
}

function startNewSession() {
  pendingNewSession.value = true;
  selectedSessionId.value = "";
  writeStoredSessionId("");
  clearHistory();
}

async function loadSelectedSession() {
  if (!selectedSessionId.value) {
    history.value = [];
    latestResult.value = null;
    return;
  }
  const session = await fetchAiSession(selectedSessionId.value);
  const rows = Array.isArray(session.messages) ? session.messages : [];
  history.value = rows.map((row, index) => ({
    id: `${session.session_id}-${index}`,
    role: row.role === "assistant" ? "assistant" : "user",
    text: summarizeSessionMessage(row.content, row.role),
    time: row.created_at ? new Date(row.created_at).toLocaleTimeString("zh-CN", { hour12: false }) : "",
    endpoint: "",
  }));
  latestResult.value = null;
  pendingNewSession.value = false;
  writeStoredSessionId(selectedSessionId.value);
  nextTick(() => {
    if (historyRef.value) {
      historyRef.value.scrollTop = historyRef.value.scrollHeight;
    }
  });
}

async function handleSessionChange() {
  await loadSelectedSession();
}

function summarizeSessionMessage(content, role) {
  if (typeof content === "string") {
    return content;
  }
  if (!content || typeof content !== "object") {
    return String(content || "");
  }
  if (role === "user") {
    return content.task || JSON.stringify(content.payload || content, null, 2);
  }
  const skill = content.task_context?.skill_payload;
  if (skill?.message) {
    return skill.message;
  }
  return (
    content.reply ||
    cleanModelText(content.llm?.text) ||
    content.execution?.summary ||
    content.coordinator?.summary ||
    JSON.stringify(content, null, 2)
  );
}

async function deleteSelectedSession() {
  if (!selectedSessionId.value) {
    return;
  }
  const target = selectedSessionId.value;
  await deleteAiSession(target);
  if (selectedSessionId.value === target) {
    selectedSessionId.value = "";
    writeStoredSessionId("");
    clearHistory();
  }
  await reloadAiOptions();
}

async function cleanupTestHistory() {
  await cleanupAiTestSessions({ keep_latest: 12 });
  if (selectedSessionId.value) {
    selectedSessionId.value = "";
    writeStoredSessionId("");
    clearHistory();
  }
  await reloadAiOptions();
}
</script>

<style scoped>
.ai-chat-page {
  display: grid;
  gap: 14px;
  color: var(--text-strong, #f4fbff);
}

.chat-card,
.result-card,
.quick-action {
  border: 1px solid rgba(94, 212, 255, 0.2);
  background:
    radial-gradient(circle at 20% 0%, rgba(57, 220, 174, 0.16), transparent 34%),
    linear-gradient(135deg, rgba(7, 30, 47, 0.96), rgba(5, 17, 32, 0.94));
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.28);
}

.eyebrow,
.panel-title span {
  display: block;
  color: rgba(153, 213, 237, 0.72);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.24em;
}

.quick-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.quick-action {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 62px;
  border-radius: 18px;
  padding: 14px 16px;
  color: inherit;
  cursor: pointer;
}

.quick-action span {
  font-size: 22px;
}

.quick-action strong {
  font-size: 14px;
  font-weight: 700;
}

.quick-action:hover,
.ghost-btn:hover {
  border-color: rgba(96, 224, 255, 0.52);
  transform: translateY(-1px);
}

.ai-chat-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.34fr) minmax(300px, 0.66fr);
  gap: 14px;
}

.chat-card,
.result-card {
  min-width: 0;
  border-radius: 22px;
  padding: 16px;
}

.result-card {
  align-self: start;
  position: sticky;
  top: 12px;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.panel-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.panel-title h3 {
  margin: 5px 0 0;
  font-size: 17px;
}

.ghost-btn {
  border: 1px solid rgba(129, 209, 240, 0.22);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  cursor: pointer;
  padding: 7px 12px;
  font-size: 12px;
}

.ghost-btn.accent {
  border-color: rgba(94, 212, 255, 0.42);
  color: #95ebff;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 360px;
  max-height: 52vh;
  overflow: auto;
  padding: 10px;
  border-radius: 18px;
  background: rgba(2, 12, 24, 0.48);
}

.message {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 9px;
}

.message-user {
  margin-left: 8%;
}

.message-avatar {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 12px;
  background: rgba(70, 210, 176, 0.2);
  color: #baf7e9;
  font-size: 12px;
  font-weight: 800;
}

.message-user .message-avatar {
  background: rgba(101, 169, 255, 0.2);
  color: #cae0ff;
}

.message-body {
  min-width: 0;
  border: 1px solid rgba(118, 204, 235, 0.14);
  border-radius: 16px;
  padding: 10px 12px;
  background: rgba(9, 30, 50, 0.78);
}

.message-body p,
.reply-box p,
.error-box p {
  margin: 6px 0 0;
  font-size: 14px;
  line-height: 1.7;
  color: rgba(224, 243, 250, 0.86);
  white-space: pre-wrap;
  word-break: break-word;
}

.message-body small {
  display: block;
  margin-top: 8px;
  font-size: 11px;
  color: rgba(154, 207, 227, 0.62);
}

.message-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: rgba(218, 241, 250, 0.74);
  font-size: 11px;
}

.empty-state,
.empty-result,
.loading-box,
.error-box,
.reply-box,
.report-box {
  border: 1px solid rgba(114, 206, 238, 0.14);
  border-radius: 18px;
  padding: 14px;
  background: rgba(4, 16, 30, 0.58);
}

.empty-state,
.empty-result,
.loading-box {
  display: grid;
  place-items: center;
  min-height: 180px;
  color: rgba(217, 237, 246, 0.72);
  text-align: center;
}

.composer {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.chat-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
}

.session-hint {
  color: rgba(185, 226, 241, 0.74);
  font-size: 12px;
  line-height: 1.5;
}

.chat-controls label {
  display: grid;
  gap: 6px;
  color: rgba(179, 218, 232, 0.78);
  font-size: 11px;
}

.chat-controls select {
  width: 100%;
  border: 1px solid rgba(105, 204, 239, 0.18);
  border-radius: 12px;
  outline: none;
  background: rgba(1, 11, 22, 0.76);
  color: inherit;
  padding: 9px 11px;
  font-size: 13px;
}

.composer textarea {
  width: 100%;
  resize: vertical;
  border: 1px solid rgba(105, 204, 239, 0.18);
  border-radius: 16px;
  outline: none;
  background: rgba(1, 11, 22, 0.68);
  color: inherit;
  padding: 12px;
  min-height: 108px;
  font-size: 14px;
  line-height: 1.6;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: rgba(179, 218, 232, 0.72);
  font-size: 12px;
}

.composer-actions button {
  min-width: 118px;
  border: 0;
  border-radius: 999px;
  background: linear-gradient(135deg, #48e4bf, #5ba7ff);
  color: #031321;
  cursor: pointer;
  font-weight: 900;
  padding: 10px 16px;
  font-size: 13px;
}

.composer-actions button.danger {
  background: linear-gradient(135deg, #ff7a7a, #ffb15a);
  color: #2a0907;
}

.composer-actions button:disabled,
.ghost-btn:disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.result-body,
.card-list {
  display: grid;
  gap: 10px;
}

.result-body {
  max-height: 72vh;
  overflow: auto;
  padding-right: 4px;
}

.reply-box span,
.card-list h4,
.report-box h4 {
  margin: 0;
  color: #b6f7ea;
  font-size: 13px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.section-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: #d6f8ff;
}

.section-badge {
  flex-shrink: 0;
  border: 1px solid rgba(118, 214, 244, 0.18);
  border-radius: 999px;
  background: rgba(73, 176, 255, 0.1);
  color: rgba(205, 239, 250, 0.84);
  padding: 4px 8px;
  font-size: 11px;
  line-height: 1;
}

.data-card {
  border: 1px solid rgba(127, 216, 244, 0.15);
  border-radius: 16px;
  padding: 12px;
  background: rgba(8, 29, 48, 0.76);
}

.data-card > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.data-card strong {
  font-size: 14px;
  line-height: 1.5;
}

.data-card span,
.data-card p,
.data-card dd {
  color: rgba(215, 236, 244, 0.72);
  font-size: 13px;
  line-height: 1.6;
}

.data-card dl {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 7px 10px;
  margin: 0;
}

.data-card dt {
  color: rgba(135, 196, 220, 0.74);
  font-size: 12px;
}

.data-card dd {
  min-width: 0;
  margin: 0;
  word-break: break-all;
}

.snapshot-card {
  display: grid;
  gap: 12px;
  border: 1px solid rgba(74, 240, 193, 0.2);
  border-radius: 18px;
  padding: 12px;
  background:
    radial-gradient(circle at 85% 0%, rgba(91, 167, 255, 0.18), transparent 34%),
    rgba(5, 20, 35, 0.82);
}

.snapshot-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.snapshot-head h4 {
  margin: 4px 0 0;
  font-size: 15px;
}

.snapshot-head span,
.next-actions strong {
  color: rgba(169, 229, 244, 0.76);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.snapshot-head strong {
  border-radius: 999px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.08);
  font-size: 12px;
}

.snapshot-head .status-success {
  color: #b8ffec;
  background: rgba(49, 220, 167, 0.18);
}

.snapshot-head .status-failed,
.snapshot-head .status-not_found {
  color: #ffd4d4;
  background: rgba(255, 118, 118, 0.16);
}

.snapshot-card img {
  width: 100%;
  max-height: 420px;
  object-fit: contain;
  border: 1px solid rgba(126, 217, 244, 0.18);
  border-radius: 18px;
  background: #020a14;
}

.snapshot-card dl {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 7px 10px;
  margin: 0;
}

.snapshot-card dt {
  color: rgba(135, 196, 220, 0.74);
}

.snapshot-card dd {
  min-width: 0;
  margin: 0;
  color: rgba(220, 241, 249, 0.78);
  word-break: break-all;
}

.next-actions {
  display: grid;
  gap: 6px;
  border-radius: 16px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.05);
}

.next-actions span {
  color: rgba(222, 241, 248, 0.76);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
  gap: 8px;
}

.metric-grid span {
  border: 1px solid rgba(91, 206, 239, 0.12);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(63, 211, 170, 0.12), rgba(61, 118, 255, 0.08));
  color: #d8fff4;
  padding: 9px 10px;
  text-align: center;
  font-size: 12px;
  line-height: 1.5;
}

.report-box pre {
  max-height: 340px;
  overflow: auto;
  color: rgba(226, 244, 251, 0.82);
  white-space: pre-wrap;
}

.pulse-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-bottom: 10px;
  border-radius: 999px;
  background: #4af0c1;
  box-shadow: 0 0 0 0 rgba(74, 240, 193, 0.55);
  animation: pulse 1.5s infinite;
}

.error-box {
  border-color: rgba(255, 119, 119, 0.28);
  background: rgba(80, 18, 22, 0.32);
}

.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-top: 1px solid rgba(127, 216, 244, 0.12);
  padding-top: 8px;
  color: rgba(186, 220, 235, 0.74);
  font-size: 12px;
}

.pager-inline {
  margin-top: 8px;
}

.pager span {
  flex: 1;
  text-align: center;
}

@keyframes spinRing {
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse {
  70% {
    box-shadow: 0 0 0 18px rgba(74, 240, 193, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(74, 240, 193, 0);
  }
}

@media (max-width: 1080px) {
  .ai-chat-layout,
  .quick-row {
    grid-template-columns: 1fr;
  }

  .result-card {
    min-width: 0;
    position: static;
  }
}

@media (max-width: 720px) {
  .message-user {
    margin-left: 0;
  }

  .chat-controls {
    grid-template-columns: 1fr;
  }

  .composer-actions,
  .data-card > div {
    align-items: stretch;
    flex-direction: column;
  }

  .composer-actions button {
    width: 100%;
  }
}

/* Anti-Tofu AI assistant console */
.ai-chat-page {
  gap: 8px !important;
  color: #39ff88;
  background: #000;
  font-family: Consolas, "Courier New", monospace;
}

.chat-card,
.result-card,
.quick-action,
.data-card,
.snapshot-card,
.report-box,
.composer,
.history-list,
.result-content,
.empty-state {
  border: 1px solid rgba(34, 211, 238, 0.18) !important;
  background: #000 !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  border-radius: 0 !important;
}

.quick-row {
  gap: 6px !important;
}

.quick-action {
  min-height: 34px !important;
  padding: 6px 10px !important;
}

.quick-action strong,
.panel-title h3 {
  color: #7dd3fc !important;
  font-size: 13px !important;
}

.panel-title {
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(34, 211, 238, 0.18);
}

.history-list {
  padding: 8px !important;
}

.message {
  display: grid !important;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
  padding: 6px 0 !important;
  border-bottom: 1px solid rgba(34, 211, 238, 0.08);
  background: transparent !important;
}

.message-avatar {
  width: auto !important;
  height: auto !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  color: #22d3ee !important;
  font-size: 11px !important;
}

.message-body {
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
}

.message-meta strong::before {
  content: "[System] ";
  color: #39ff88;
}

.message-body p {
  margin: 4px 0 0 !important;
  color: #d1fae5 !important;
  font-size: 12px !important;
}

textarea,
select,
input {
  border-color: rgba(34, 211, 238, 0.18) !important;
  background: #020403 !important;
  color: #39ff88 !important;
  font-family: Consolas, "Courier New", monospace !important;
}

.ghost-btn,
.composer-actions button {
  border: 1px solid rgba(34, 211, 238, 0.22) !important;
  background: transparent !important;
  color: #7dd3fc !important;
  box-shadow: none !important;
}
</style>
