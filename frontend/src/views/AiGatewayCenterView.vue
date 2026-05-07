<template>
  <section class="page ai-workbench-page">
    <WorkbenchShell leftWidth="300px" rightWidth="376px" maxWidth="1880px">
      <template #actions>
        <button class="tool-btn" @click="reloadAll">刷新状态</button>
        <button class="tool-btn" @click="runSmokeTask">运行联通测试</button>
        <button class="tool-btn" @click="runDeviceQuery">测试设备查询</button>
        <button class="tool-btn" @click="router.push('/ai-chat')">进入 AI 助手</button>
        <button class="tool-btn primary" @click="loadLogs">刷新日志</button>
      </template>

      <template #summary>
        <section class="ai-metrics">
          <article class="metric-card">
            <span>协调者</span>
            <strong>{{ gateway.coordinator_key || "openclaw" }}</strong>
            <small>唯一任务协调入口</small>
          </article>
          <article class="metric-card">
            <span>连接状态</span>
            <strong>{{ connectionStatusLabel }}</strong>
            <small>{{ lastSeenLabel }}</small>
          </article>
          <article class="metric-card">
            <span>服务密钥</span>
            <strong>{{ serviceKeys.length }}</strong>
            <small>当前白名单入口</small>
          </article>
          <article class="metric-card">
            <span>智能体</span>
            <strong>{{ agents.length }}</strong>
            <small>{{ enabledAgents.length }} 个已启用</small>
          </article>
          <article class="metric-card">
            <span>模型适配器</span>
            <strong>{{ llms.length }}</strong>
            <small>{{ readyLlmCount }} 个已就绪</small>
          </article>
          <article class="metric-card">
            <span>访问记录</span>
            <strong>{{ recentAccess.length }}</strong>
            <small>最近联通与调用痕迹</small>
          </article>
        </section>
      </template>

      <template #left>
        <aside class="ai-left-rail">
          <section class="scope-block">
            <div class="side-head">
              <strong>对象范围</strong>
              <span>{{ connectionStatusLabel }}</span>
            </div>
            <div class="scope-list">
              <button class="scope-row" @click="runSmokeTask">
                <strong>联通测试</strong>
                <span>直接判断 OpenClaw 与 Codex 当前是否可被调度</span>
              </button>
              <button class="scope-row" @click="runDeviceQuery">
                <strong>设备查询测试</strong>
                <span>用实际设备查询验证网关业务能力是否通</span>
              </button>
              <button class="scope-row" @click="router.push('/ai-chat')">
                <strong>进入 AI 助手</strong>
                <span>去会话界面直接体验模型与系统动作联动</span>
              </button>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>服务密钥与白名单</strong>
              <span>{{ serviceKeys.length }} 项</span>
            </div>
            <div class="scope-list recent-list">
              <article v-for="item in serviceKeys" :key="item.key_id" class="hint-row">
                <strong>{{ item.display_name || item.key_id }}</strong>
                <span>{{ item.enabled ? "已启用" : "已停用" }} / {{ item.key_mask || "未生成" }}</span>
                <small>来源：{{ (item.allowed_clients || []).join("、") || "未限制" }}</small>
              </article>
              <p v-if="!serviceKeys.length" class="empty-note">当前还没有服务密钥信息。</p>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>最近访问</strong>
              <span>{{ recentAccess.length }} 条</span>
            </div>
            <div class="scope-list recent-list">
              <article v-for="event in recentAccess.slice(0, 8)" :key="`${event.timestamp}-${event.path}-${event.status_code}`" class="hint-row">
                <strong>{{ event.result || "-" }}</strong>
                <span>{{ formatTime(event.timestamp) }}</span>
                <small>{{ event.client_host || "-" }} {{ event.method || "" }} {{ event.path || "" }}</small>
              </article>
              <p v-if="!recentAccess.length" class="empty-note">暂时没有 OpenClaw 访问记录。</p>
            </div>
          </section>
        </aside>
      </template>

      <template #default>
        <section class="ai-center">
          <article class="panel workbench-panel ai-link-panel">
            <div class="ai-link-shell">
              <div class="openclaw-orb" :class="{ live: connection.live, online: connection.online }">
                <div class="orb-rings"></div>
                <div class="lobster-mark" aria-hidden="true">OC</div>
                <strong>OpenClaw</strong>
                <span>智能协调者</span>
              </div>

              <div class="ai-link-copy">
                <div class="status-pill" :class="{ online: connection.online, live: connection.live }">{{ connectionStatusLabel }}</div>
                <h3>OpenClaw 主链路</h3>
                <p>OpenClaw 作为唯一协调者，统一决定任务分流、记忆和结果汇总；AI 网关负责认证、日志和业务路由。</p>
                <div class="status-grid">
                  <div>
                    <span>网关入口</span>
                    <strong>{{ connection.gateway_url || "http://192.168.119.149:8011/api/ai/gateway" }}</strong>
                  </div>
                  <div>
                    <span>最后客户端</span>
                    <strong>{{ connection.last_client_host || "-" }}</strong>
                  </div>
                  <div>
                    <span>最后路径</span>
                    <strong>{{ connection.last_path || "-" }}</strong>
                  </div>
                  <div>
                    <span>最后成功调用</span>
                    <strong>{{ lastSeenFullLabel }}</strong>
                  </div>
                </div>
              </div>
            </div>

            <div class="ai-flow">
              <div class="flow-node coordinator">
                <span>COORDINATOR</span>
                <strong>OpenClaw</strong>
                <small>理解任务、决策调度、维持上下文和汇总输出</small>
              </div>
              <div class="flow-line"></div>
              <div class="flow-node executor">
                <span>GATEWAY</span>
                <strong>V2 AI 网关</strong>
                <small>密钥校验、访问记录、模型与业务路由</small>
              </div>
              <div class="flow-line"></div>
              <div class="flow-node resource">
                <span>RESOURCE</span>
                <strong>设备 / 告警 / 拓扑 / 报告</strong>
                <small>平台能力通过网关暴露，不直接泄露数据库和内部实现</small>
              </div>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">AGENT REGISTRY</p>
                <h3>智能体与模型概况</h3>
                <span>中间只看注册对象和当前任务测试，不把日志和表单混在一起</span>
              </div>
            </div>

            <div class="table-pair">
              <section class="table-block">
                <div class="table-head">
                  <strong>智能体注册表</strong>
                  <span>{{ agents.length }} 个</span>
                </div>
                <div class="source-card-grid">
                  <div v-for="item in agents" :key="item.agent_key" class="source-card">
                    <div class="source-card-head">
                      <strong>{{ item.display_name }}</strong>
                      <span class="pill" :class="{ resolved: item.enabled }">{{ item.enabled ? "启用" : "停用" }}</span>
                    </div>
                    <p class="source-card-meta">{{ roleLabel(item.role) }} / {{ item.protocol || "tool" }}</p>
                    <p class="source-card-meta">{{ item.description || "暂无说明" }}</p>
                    <div class="mini-chip-row">
                      <span v-for="cap in item.capabilities || []" :key="`${item.agent_key}-${cap}`">{{ cap }}</span>
                    </div>
                  </div>
                </div>
              </section>

              <section class="table-block">
                <div class="table-head">
                  <strong>模型适配器概况</strong>
                  <span>{{ llms.length }} 个 / {{ readyLlmCount }} 个 ready</span>
                </div>
                <div class="source-card-grid">
                  <div v-for="item in llms" :key="item.llm_key" class="source-card">
                    <div class="source-card-head">
                      <strong>{{ item.display_name || item.llm_key }}</strong>
                      <span class="pill" :class="{ resolved: item.ready }">{{ item.ready ? "就绪" : "未就绪" }}</span>
                    </div>
                    <p class="source-card-meta">{{ providerLabel(item.provider_type) }} / {{ item.default_model || "-" }}</p>
                    <p class="source-card-meta">{{ item.enabled ? "已启用" : "未启用" }} / {{ keyStatusLabel(item) }}</p>
                  </div>
                  <p v-if="!llms.length" class="empty-note">当前还没有登记 AI 网关模型适配器。</p>
                </div>
              </section>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">GATEWAY TEST</p>
                <h3>网关测试台</h3>
                <span>把任务直接打给 OpenClaw，验证网关、模型和业务动作是否真的通了</span>
              </div>
            </div>

            <div class="form-grid">
              <label>
                <span>任务类型</span>
                <select v-model="testTask.task_type" class="field-input">
                  <option value="general">通用任务</option>
                  <option value="alert_analyze">告警分析</option>
                  <option value="report_generate">报告生成</option>
                  <option value="device_query">设备查询</option>
                </select>
              </label>
              <label>
                <span>指定智能体</span>
                <input v-model.trim="testTask.requested_agent_key" class="field-input" placeholder="留空交给 OpenClaw 决策" />
              </label>
              <label>
                <span>指定 LLM</span>
                <input v-model.trim="testTask.llm_key" class="field-input" placeholder="留空不调外部模型" />
              </label>
              <label class="full-width">
                <span>任务内容</span>
                <textarea v-model.trim="testTask.task" class="field-input text-area" rows="4" />
              </label>
            </div>
            <div class="action-row wrap top-gap">
              <button class="tool-btn primary" @click="submitGatewayTask">提交给 OpenClaw</button>
            </div>
            <p class="status-line">{{ actionMessage }}</p>
            <pre v-if="lastResult" class="ai-result">{{ formattedResult }}</pre>
          </article>
        </section>
      </template>

      <template #right>
        <aside class="ai-right-rail">
          <section class="detail-shell">
            <div class="side-head">
              <strong>模型适配器</strong>
              <span>{{ editingLlmKey ? `正在编辑 ${editingLlmKey}` : "新建或维护模型" }}</span>
            </div>

            <div class="detail-summary-grid">
              <article class="detail-chip">
                <span>已启用智能体</span>
                <strong>{{ enabledAgents.length }}</strong>
              </article>
              <article class="detail-chip">
                <span>已就绪模型</span>
                <strong>{{ readyLlmCount }}</strong>
              </article>
              <article class="detail-chip">
                <span>最后访问</span>
                <strong>{{ lastSeenLabel }}</strong>
              </article>
              <article class="detail-chip">
                <span>日志页签</span>
                <strong>{{ activeLogTabLabel }}</strong>
              </article>
            </div>

            <div v-if="editingLlmKey" class="edit-banner">
              正在编辑：<strong>{{ editingLlmKey }}</strong>，修改后请点击下方“保存模型适配器”。
            </div>

            <div class="form-grid llm-form">
              <label>
                <span>模型标识</span>
                <input v-model.trim="llmForm.llm_key" class="field-input" :disabled="!!editingLlmKey" placeholder="例如 openai-main" />
              </label>
              <label>
                <span>显示名称</span>
                <input v-model.trim="llmForm.display_name" class="field-input" placeholder="例如 OpenAI 主模型" />
              </label>
              <label>
                <span>提供商类型</span>
                <select v-model="llmForm.provider_type" class="field-input">
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="glm">GLM</option>
                  <option value="minimax">MiniMax</option>
                  <option value="deepseek">DeepSeek</option>
                  <option value="local">本地模型</option>
                  <option value="custom">通用 REST</option>
                </select>
              </label>
              <label>
                <span>默认模型</span>
                <input v-model.trim="llmForm.default_model" class="field-input" placeholder="例如 gpt-5.4" />
              </label>
              <label class="full-width">
                <span>接口地址</span>
                <input v-model.trim="llmForm.base_url" class="field-input" placeholder="例如 https://api.openai.com/v1" />
              </label>
              <label>
                <span>密钥环境变量</span>
                <input v-model.trim="llmForm.api_key_env" class="field-input" placeholder="例如 OPENAI_API_KEY" />
              </label>
              <label>
                <span>API Key</span>
                <input v-model.trim="llmForm.api_key" class="field-input" type="password" placeholder="可以直接粘贴模型 API Key" />
              </label>
              <label>
                <span>聊天接口路径</span>
                <input v-model.trim="llmForm.chat_url" class="field-input" placeholder="可留空，默认 /chat/completions" />
              </label>
              <label>
                <span>向量接口路径</span>
                <input v-model.trim="llmForm.embedding_url" class="field-input" placeholder="可留空，默认 /embeddings" />
              </label>
              <label class="switch-row full-width">
                <input v-model="llmForm.enabled" type="checkbox" />
                <span>启用该模型适配器</span>
              </label>
            </div>

            <div class="action-row wrap">
              <button class="tool-btn primary" type="button" @click="submitLlmForm">
                {{ editingLlmKey ? "保存模型适配器" : "新增模型适配器" }}
              </button>
              <button v-if="editingLlmKey" class="tool-btn" type="button" @click="resetLlmForm">取消编辑</button>
            </div>

            <p class="action-note">这里录入的是 AI 网关真实使用的模型。可以直接填写 API Key；列表只显示脱敏状态，不会明文展示。</p>

            <div class="source-card-grid llm-list">
              <div v-for="item in llms" :key="item.llm_key" class="source-card">
                <div class="source-card-head">
                  <strong>{{ item.display_name || item.llm_key }}</strong>
                  <span class="pill" :class="{ resolved: item.ready }">{{ item.ready ? "就绪" : "未就绪" }}</span>
                </div>
                <p class="source-card-meta">{{ providerLabel(item.provider_type) }} / {{ item.default_model || "-" }}</p>
                <p class="source-card-meta">{{ item.enabled ? "已启用" : "未启用" }} / {{ keyStatusLabel(item) }}</p>
                <div class="mini-actions">
                  <button class="ops-link" type="button" @click="loadLlmForm(item)">编辑</button>
                  <button class="ops-link danger-link" type="button" @click="deleteLlm(item)">删除</button>
                </div>
              </div>
            </div>
          </section>

          <section class="detail-shell">
            <div class="side-head">
              <strong>日志与排障</strong>
              <span>复制给 OpenClaw 最方便</span>
            </div>

            <div class="action-row wrap">
              <button class="tool-btn" @click="copyLogSummary">复制日志摘要</button>
              <button class="tool-btn" @click="loadLogs">刷新日志</button>
              <button class="tool-btn danger-btn" @click="cleanupLogs">清理旧日志</button>
            </div>

            <div class="log-tabs">
              <button :class="{ active: activeLogTab === 'access' }" @click="activeLogTab = 'access'">访问</button>
              <button :class="{ active: activeLogTab === 'gateway' }" @click="activeLogTab = 'gateway'">网关</button>
              <button :class="{ active: activeLogTab === 'tray' }" @click="activeLogTab = 'tray'">托盘</button>
            </div>
            <pre class="ai-result log-output">{{ activeLogText }}</pre>
          </section>
        </aside>
      </template>
    </WorkbenchShell>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import WorkbenchShell from "../components/workbench/WorkbenchShell.vue";
import {
  cleanupAiGatewayLogs,
  deleteAiLlm,
  fetchAiGatewayConnection,
  fetchAiGatewayLogs,
  fetchAiGatewaySummary,
  queryDeviceWithAi,
  registerAiLlm,
  runAiGatewayTask,
} from "../api/client";

const router = useRouter();
const summary = ref({});
const connectionState = ref({});
const logs = ref({ access_events: [], ai_gateway_log_tail: [], tray_log_tail: [] });
const actionMessage = ref("AI 网关已接入后端，当前可以查看连接状态、访问记录并执行联通测试。");
const lastResult = ref(null);
const activeLogTab = ref("access");
const editingLlmKey = ref("");

const testTask = reactive({
  task: "请判断 AI 网关当前是否可以调度 OpenClaw 和 Codex。",
  task_type: "general",
  requested_agent_key: "",
  llm_key: "",
  payload: {},
});

const llmForm = reactive({
  llm_key: "",
  provider_type: "openai",
  display_name: "",
  enabled: true,
  base_url: "",
  api_key_env: "",
  api_key: "",
  default_model: "",
  chat_url: "",
  embedding_url: "",
});

const gateway = computed(() => summary.value.gateway || {});
const agents = computed(() => summary.value.agents || []);
const llms = computed(() => summary.value.llms || []);
const connection = computed(() => connectionState.value || summary.value.connection || {});
const serviceKeys = computed(() => connection.value.service_keys || summary.value.service_keys || []);
const recentAccess = computed(() => connection.value.recent_access || logs.value.access_events || []);
const enabledAgents = computed(() => agents.value.filter((item) => item.enabled));
const readyLlmCount = computed(() => llms.value.filter((item) => item.ready).length);
const formattedResult = computed(() => JSON.stringify(lastResult.value, null, 2));
const connectionStatusLabel = computed(() => connection.value.status_label || (connection.value.online ? "已连接" : "已配置待心跳"));
const activeLogTabLabel = computed(() => {
  return {
    access: "访问日志",
    gateway: "网关日志",
    tray: "托盘日志",
  }[activeLogTab.value] || activeLogTab.value;
});
const lastSeenLabel = computed(() => {
  const age = connection.value.last_seen_age_seconds;
  if (age === null || age === undefined) return "暂无";
  if (age < 60) return `${age} 秒前`;
  if (age < 3600) return `${Math.floor(age / 60)} 分钟前`;
  return `${Math.floor(age / 3600)} 小时前`;
});
const lastSeenFullLabel = computed(() => formatTime(connection.value.last_seen_at) || "暂无");
const activeLogText = computed(() => {
  if (activeLogTab.value === "access") {
    return JSON.stringify(logs.value.access_events || [], null, 2);
  }
  if (activeLogTab.value === "tray") {
    return (logs.value.tray_log_tail || []).join("\n") || "暂无托盘日志。";
  }
  return (logs.value.ai_gateway_log_tail || []).join("\n") || "暂无 AI 网关日志。";
});

onMounted(reloadAll);

async function reloadAll() {
  const [nextSummary, nextConnection] = await Promise.all([fetchAiGatewaySummary(), fetchAiGatewayConnection()]);
  summary.value = nextSummary;
  connectionState.value = nextConnection;
  await loadLogs(false);
}

async function loadLogs(showMessage = true) {
  logs.value = await fetchAiGatewayLogs(160);
  if (showMessage) actionMessage.value = "AI 网关日志已刷新，可复制摘要给 OpenClaw 排查。";
}

async function cleanupLogs() {
  const result = await cleanupAiGatewayLogs({ keep_days: 30, max_lines: 5000 });
  actionMessage.value = `旧访问日志已清理：移除 ${result.access_log?.removed ?? 0} 行，保留最近 30 天。`;
  await reloadAll();
}

async function runSmokeTask() {
  testTask.task_type = "general";
  testTask.task = "请判断 AI 网关当前是否可以调度 OpenClaw 和 Codex。";
  testTask.payload = {};
  await submitGatewayTask();
}

async function runDeviceQuery() {
  lastResult.value = await queryDeviceWithAi({ task: "请查询 10.0.56.149", query: "10.0.56.149" });
  actionMessage.value = "设备查询测试完成，结果已返回。";
  await reloadAll();
}

async function submitGatewayTask() {
  lastResult.value = await runAiGatewayTask({ ...testTask });
  actionMessage.value = "任务已提交给 OpenClaw，调度结果已返回。";
  await reloadAll();
}

async function submitLlmForm() {
  if (!llmForm.llm_key.trim()) {
    actionMessage.value = "请先填写模型标识，例如 openai-main。";
    return;
  }
  if (!llmForm.display_name.trim()) {
    actionMessage.value = "请先填写模型显示名称，方便在 AI 中心识别。";
    return;
  }
  const payload = {
    ...llmForm,
    llm_key: llmForm.llm_key.trim(),
    display_name: llmForm.display_name.trim(),
    provider_type: llmForm.provider_type || "custom",
  };
  if (isUnsafeEnvName(payload.api_key_env) && !payload.api_key) {
    payload.api_key = payload.api_key_env;
    payload.api_key_env = "";
  }
  await registerAiLlm(payload);
  actionMessage.value = `模型适配器 ${payload.llm_key} 已保存，AI 会话里可以选择它进行调用。`;
  resetLlmForm();
  await reloadAll();
}

function loadLlmForm(item) {
  editingLlmKey.value = item.llm_key || "";
  llmForm.llm_key = item.llm_key || "";
  llmForm.provider_type = item.provider_type || "custom";
  llmForm.display_name = item.display_name || "";
  llmForm.enabled = item.enabled !== false;
  llmForm.base_url = item.base_url || "";
  llmForm.api_key_env = item.api_key_env || "";
  llmForm.api_key = "";
  llmForm.default_model = item.default_model || "";
  llmForm.chat_url = item.chat_url || "";
  llmForm.embedding_url = item.embedding_url || "";
  actionMessage.value = `正在编辑模型适配器 ${llmForm.llm_key}。`;
}

function resetLlmForm() {
  editingLlmKey.value = "";
  llmForm.llm_key = "";
  llmForm.provider_type = "openai";
  llmForm.display_name = "";
  llmForm.enabled = true;
  llmForm.base_url = "";
  llmForm.api_key_env = "";
  llmForm.api_key = "";
  llmForm.default_model = "";
  llmForm.chat_url = "";
  llmForm.embedding_url = "";
}

async function deleteLlm(item) {
  const llmKey = String(item?.llm_key || "").trim();
  if (!llmKey) {
    actionMessage.value = "模型标识为空，无法删除。";
    return;
  }
  const displayName = item.display_name || llmKey;
  if (!window.confirm(`确定删除模型适配器“${displayName}”吗？删除后可重新新增。`)) {
    return;
  }
  try {
    await deleteAiLlm(llmKey);
    if (editingLlmKey.value === llmKey) {
      resetLlmForm();
    }
    actionMessage.value = `模型适配器 ${llmKey} 已删除。`;
    await reloadAll();
  } catch (error) {
    actionMessage.value = `删除失败：${error?.response?.data?.detail?.message || error.message || "未知错误"}`;
  }
}

async function copyLogSummary() {
  const payload = {
    connection: connection.value,
    recent_access: recentAccess.value.slice(-12),
    ai_gateway_log_tail: (logs.value.ai_gateway_log_tail || []).slice(-30),
  };
  const text = JSON.stringify(payload, null, 2);
  await navigator.clipboard.writeText(text);
  actionMessage.value = "日志摘要已复制，可以直接发给 OpenClaw 进行分析。";
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function roleLabel(value) {
  return {
    coordinator: "协调者",
    executor: "执行者",
    specialist: "专家",
  }[value] || value || "-";
}

function providerLabel(value) {
  return {
    openai: "OpenAI",
    anthropic: "Anthropic",
    glm: "GLM",
    minimax: "MiniMax",
    deepseek: "DeepSeek",
    local: "本地模型",
    custom: "通用 REST",
  }[value] || value || "-";
}

function isUnsafeEnvName(value) {
  const text = String(value || "").trim();
  if (!text) return false;
  if (/^[A-Z][A-Z0-9_]{2,80}$/.test(text)) return false;
  return text.length > 24 || /[-.]/.test(text) || /[a-z]{6,}/.test(text);
}

function keyStatusLabel(item) {
  if (item.api_key_present) {
    return `API Key 已保存 ${item.api_key_mask || ""}`;
  }
  if (item.api_key_env) {
    return `环境变量 ${displayApiKeyEnv(item.api_key_env)}`;
  }
  return "未配置密钥";
}

function displayApiKeyEnv(value) {
  const text = String(value || "").trim();
  if (!text) return "无";
  if (!isUnsafeEnvName(text)) return text;
  return `${text.slice(0, 6)}...${text.slice(-4)}（已脱敏）`;
}
</script>

<style scoped>
.ai-workbench-page {
  padding-bottom: 24px;
}

.ai-metrics {
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
.source-card {
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
.source-card-meta,
.empty-note,
.status-line,
.action-note {
  color: rgba(207, 231, 255, 0.72);
}

.ai-roadmap {
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

.ai-left-rail,
.ai-center,
.ai-right-rail {
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
.list-toolbar,
.table-head,
.source-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.side-head strong,
.list-toolbar h3,
.table-head strong,
.source-card-head strong {
  color: #f4fbff;
}

.side-head span,
.list-toolbar span,
.eyebrow {
  color: rgba(207, 231, 255, 0.72);
}

.scope-list,
.hint-list,
.source-card-grid {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.recent-list {
  max-height: 300px;
  overflow: auto;
}

.scope-row,
.hint-row,
.source-card {
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

.source-card {
  min-width: 0;
  overflow-wrap: anywhere;
}

.pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 58px;
  padding: 4px 9px;
  border-radius: 999px;
  border: 1px solid rgba(111, 191, 255, 0.2);
  background: rgba(255, 255, 255, 0.05);
  color: rgba(207, 231, 255, 0.8);
  font-size: 12px;
}

.pill.resolved {
  border-color: rgba(92, 210, 154, 0.28);
  color: #c8f5d8;
}

.ai-link-panel {
  overflow: hidden;
  background:
    radial-gradient(circle at 16% 20%, rgba(111, 199, 255, 0.2), transparent 28%),
    radial-gradient(circle at 80% 14%, rgba(242, 216, 138, 0.14), transparent 26%),
    linear-gradient(135deg, rgba(9, 21, 33, 0.96), rgba(14, 52, 70, 0.92));
}

.ai-link-shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
  align-items: center;
}

.openclaw-orb {
  position: relative;
  width: 190px;
  min-height: 190px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  justify-self: center;
  padding: 18px;
  border-radius: 36px;
  border: 1px solid rgba(125, 211, 252, 0.28);
  background:
    radial-gradient(circle at 50% 40%, rgba(244, 114, 182, 0.26), transparent 35%),
    radial-gradient(circle at 50% 50%, rgba(45, 212, 191, 0.2), transparent 48%),
    rgba(5, 16, 30, 0.66);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.34), inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.openclaw-orb.live {
  box-shadow: 0 24px 80px rgba(45, 212, 191, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

.orb-rings,
.orb-rings::before,
.orb-rings::after {
  position: absolute;
  border-radius: 999px;
  border: 1px solid rgba(125, 211, 252, 0.2);
}

.orb-rings {
  inset: 18px;
  animation: orbitPulse 4s ease-in-out infinite;
}

.orb-rings::before,
.orb-rings::after {
  content: "";
}

.orb-rings::before {
  inset: 18px;
}

.orb-rings::after {
  inset: 38px;
  border-color: rgba(251, 191, 36, 0.24);
}

.lobster-mark {
  position: relative;
  width: 78px;
  height: 78px;
  display: grid;
  place-items: center;
  border-radius: 28px 28px 34px 34px;
  background: linear-gradient(145deg, #fb7185, #f97316 48%, #facc15);
  color: #09111f;
  font-weight: 900;
  letter-spacing: 0.08em;
  box-shadow: 0 14px 32px rgba(249, 115, 22, 0.32);
}

.lobster-mark::before,
.lobster-mark::after {
  content: "";
  position: absolute;
  top: 14px;
  width: 34px;
  height: 22px;
  border: 6px solid #fb7185;
  border-bottom: 0;
}

.lobster-mark::before {
  right: 66px;
  border-radius: 24px 24px 0 24px;
  transform: rotate(-24deg);
}

.lobster-mark::after {
  left: 66px;
  border-radius: 24px 24px 24px 0;
  transform: rotate(24deg);
}

.openclaw-orb strong {
  margin-top: 14px;
  font-size: 22px;
  color: #f3f9ff;
}

.openclaw-orb span {
  margin-top: 4px;
  color: rgba(219, 234, 254, 0.72);
  font-size: 12px;
}

.ai-link-copy h3 {
  margin: 12px 0 10px;
  color: #f4fbff;
}

.ai-link-copy p {
  color: rgba(222, 239, 249, 0.78);
  line-height: 1.6;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  min-width: 82px;
  justify-content: center;
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid rgba(111, 191, 255, 0.22);
  background: rgba(9, 22, 36, 0.72);
  color: #f3f9ff;
  font-size: 13px;
}

.status-pill.online {
  border-color: rgba(94, 234, 212, 0.55);
  box-shadow: 0 0 28px rgba(94, 234, 212, 0.2);
}

.status-pill.live {
  border-color: rgba(251, 191, 36, 0.65);
  box-shadow: 0 0 30px rgba(251, 191, 36, 0.22);
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.status-grid div {
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(111, 191, 255, 0.16);
  background: rgba(6, 18, 30, 0.58);
}

.status-grid span {
  display: block;
  color: rgba(207, 231, 255, 0.62);
  font-size: 12px;
  margin-bottom: 6px;
}

.status-grid strong {
  display: block;
  color: #f4fbff;
  overflow-wrap: anywhere;
}

.ai-flow {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 44px minmax(0, 1fr) 44px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  margin-top: 18px;
}

.flow-node {
  min-height: 120px;
  padding: 18px;
  border-radius: 20px;
  border: 1px solid rgba(111, 199, 255, 0.22);
  background: linear-gradient(145deg, rgba(8, 20, 34, 0.9), rgba(17, 55, 78, 0.76));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.flow-node span {
  display: block;
  color: rgba(170, 209, 235, 0.75);
  font-size: 12px;
  letter-spacing: 0.14em;
}

.flow-node strong {
  display: block;
  margin-top: 10px;
  font-size: 21px;
  color: #f4fbff;
}

.flow-node small {
  display: block;
  margin-top: 8px;
  color: rgba(222, 239, 249, 0.72);
  line-height: 1.5;
}

.flow-line {
  height: 2px;
  background: linear-gradient(90deg, rgba(111, 199, 255, 0.15), rgba(111, 199, 255, 0.85));
  box-shadow: 0 0 18px rgba(111, 199, 255, 0.44);
}

.table-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.table-block {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.mini-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.mini-chip-row span {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(111, 191, 255, 0.14);
  color: #e9f6ff;
  font-size: 12px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
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

.field-input {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(111, 191, 255, 0.16);
  background: rgba(255, 255, 255, 0.04);
  color: #f4fbff;
  padding: 12px 14px;
}

.full-width {
  grid-column: 1 / -1;
}

.text-area {
  resize: vertical;
  min-height: 110px;
}

.action-row.wrap,
.mini-actions,
.log-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.detail-shell {
  display: grid;
  gap: 14px;
}

.detail-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.detail-chip {
  border-radius: 16px;
  padding: 12px 14px;
  display: grid;
  gap: 4px;
}

.edit-banner {
  border: 1px solid rgba(251, 191, 36, 0.28);
  border-radius: 14px;
  background: rgba(251, 191, 36, 0.1);
  color: #fde68a;
  padding: 12px 14px;
}

.ops-link {
  border: none;
  background: transparent;
  color: #8acfff;
  padding: 0;
  cursor: pointer;
}

.danger-link,
.danger-btn {
  color: #fca5a5;
}

.log-tabs button {
  border: 1px solid rgba(111, 191, 255, 0.16);
  border-radius: 999px;
  background: rgba(6, 18, 30, 0.52);
  color: rgba(207, 231, 255, 0.72);
  cursor: pointer;
  min-height: 34px;
  padding: 7px 12px;
  font-size: 13px;
}

.log-tabs button.active {
  color: #f4fbff;
  border-color: rgba(111, 199, 255, 0.5);
  background: rgba(32, 94, 130, 0.42);
}

.ai-result {
  max-height: 360px;
  overflow: auto;
  margin: 0;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(111, 191, 255, 0.14);
  background: rgba(4, 12, 22, 0.9);
  color: #dff3ff;
  white-space: pre-wrap;
}

.log-output {
  min-height: 320px;
}

@media (max-width: 1380px) {
  .ai-metrics,
  .ai-roadmap {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .ai-link-shell,
  .table-pair,
  .status-grid,
  .ai-flow,
  .form-grid,
  .detail-summary-grid {
    grid-template-columns: 1fr;
  }

  .flow-line {
    width: 2px;
    height: 34px;
    justify-self: center;
    background: linear-gradient(180deg, rgba(111, 199, 255, 0.15), rgba(111, 199, 255, 0.85));
  }
}

@media (max-width: 960px) {
  .ai-metrics,
  .ai-roadmap {
    grid-template-columns: 1fr;
  }

  .openclaw-orb {
    width: auto;
    min-height: 168px;
  }
}

@keyframes orbitPulse {
  0%,
  100% {
    transform: scale(0.98) rotate(0deg);
    opacity: 0.64;
  }
  50% {
    transform: scale(1.06) rotate(10deg);
    opacity: 1;
  }
}

/* Anti-Tofu AI terminal skin */
.ai-workbench-page {
  color: #39ff88;
  background: #000;
  font-family: Consolas, "Courier New", monospace;
}

.ai-workbench-page :deep(.workbench-shell) {
  gap: 8px;
}

.ai-workbench-page :deep(.workbench-title) {
  display: none;
}

.ai-workbench-page :deep(.workbench-toolbar) {
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(34, 211, 238, 0.2);
}

.ai-workbench-page :deep(.workbench-main) {
  gap: 10px;
  min-height: calc(100vh - 132px);
}

.metric-card,
.panel,
.workbench-panel,
.scope-block,
.detail-shell,
.ops-guide-card,
.source-card,
.ai-link-shell {
  border: 1px solid rgba(34, 211, 238, 0.18) !important;
  background: #000 !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  border-radius: 0 !important;
}

.metric-card,
.scope-block,
.detail-shell,
.workbench-panel,
.source-card {
  padding: 10px !important;
}

.metric-card span,
.panel-title span,
.side-head span,
.source-card-meta,
.hint-row span,
.empty-note {
  color: rgba(57, 255, 136, 0.68) !important;
  font-size: 11px !important;
}

.metric-card strong,
.panel-title h3,
.side-head strong,
.source-card-head strong {
  color: #7dd3fc !important;
  font-size: 13px !important;
  text-shadow: none !important;
}

.tool-btn,
.action-btn,
.ghost-button {
  border: 1px solid rgba(34, 211, 238, 0.22) !important;
  background: transparent !important;
  color: #7dd3fc !important;
  box-shadow: none !important;
}

.openclaw-orb {
  border-radius: 0 !important;
  background: #000 !important;
  box-shadow: none !important;
}
</style>
