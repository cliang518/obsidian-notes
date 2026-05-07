<template>
  <section class="page">
    <header class="hero">
      <div class="hero-copy">
        <p class="eyebrow">智能接口网关</p>
        <h2>智能接口中心 / 模型能力网关（MCP）</h2>
        <p class="lead">
          这一层负责把平台内的资产、告警、拓扑、视频、知识资料和工单能力安全暴露给智能体。
          当前主线是“只读优先、审计留痕、逐步开放”，先把查询与辅助诊断做稳，再按权限开放写入型动作。
        </p>
      </div>

      <div class="hero-side">
        <div class="hero-badge">
          <span>当前阶段</span>
          <strong>{{ stageLabel(summary.stage) }}</strong>
        </div>
        <div class="hero-metrics">
          <div>
            <label>接入策略</label>
            <strong>{{ strategyLabel(summary.strategy) }}</strong>
          </div>
          <div>
            <label>服务总数</label>
            <strong>{{ summary.service_count || 0 }}</strong>
          </div>
        </div>
      </div>
    </header>

    <section class="cards">
      <article class="card">
        <span>已登记服务</span>
        <strong>{{ summary.service_count || 0 }}</strong>
      </article>
      <article class="card">
        <span>启用服务</span>
        <strong>{{ summary.enabled_count || 0 }}</strong>
      </article>
      <article class="card">
        <span>只读优先</span>
        <strong>{{ summary.read_only_count || 0 }}</strong>
      </article>
      <article class="card">
        <span>规划工具</span>
        <strong>{{ summary.planned_tools?.length || 0 }}</strong>
      </article>
    </section>

    <section class="panel-grid">
      <article class="panel">
        <h3>接入原则</h3>
        <ul class="plain-list compact-list">
          <li v-for="(item, index) in summary.design_notes || []" :key="`note-${index}`">
            {{ item }}
          </li>
        </ul>
      </article>

      <article class="panel accent-panel">
        <h3>对接目标</h3>
        <div class="stack-list">
          <div v-for="item in summary.mcp_targets || []" :key="item.name" class="stack-item">
            <strong>{{ item.name }}</strong>
            <span>{{ statusLabel(item.status) }}</span>
          </div>
        </div>
      </article>
    </section>

    <section class="panel-grid">
      <article class="panel">
        <h3>服务类型分布</h3>
        <div v-if="summary.service_type_breakdown?.length" class="chip-grid">
          <div
            v-for="item in summary.service_type_breakdown"
            :key="item.service_type"
            class="chip-card"
          >
            <strong>{{ serviceTypeLabel(item.service_type) }}</strong>
            <span>{{ item.count }} 项</span>
          </div>
        </div>
        <p v-else class="action-note">当前还没有服务类型统计数据。</p>
      </article>

      <article class="panel">
        <h3>规划开放工具</h3>
        <div class="source-card-grid">
          <div v-for="item in summary.planned_tools || []" :key="item.tool_name" class="source-card">
            <div class="source-card-head">
              <strong>{{ item.tool_name }}</strong>
              <span class="pill subtle">规划中</span>
            </div>
            <p class="source-card-meta">{{ item.scope }}</p>
          </div>
        </div>
      </article>
    </section>

    <section class="panel-grid">
      <article class="panel">
        <h3>{{ editingId ? "编辑服务登记" : "登记智能体 / 模型能力服务" }}</h3>
        <div class="form-grid">
          <label>
            <span>服务标识</span>
            <input v-model.trim="form.service_key" class="filter-input" placeholder="例如 openclaw" />
          </label>
          <label>
            <span>显示名称</span>
            <input
              v-model.trim="form.display_name"
              class="filter-input"
              placeholder="例如 OpenClaw 智能体"
            />
          </label>
          <label>
            <span>服务类型</span>
            <select v-model="form.service_type" class="filter-input">
              <option value="mcp">模型能力工具（MCP）</option>
              <option value="rest_agent">接口智能体（REST）</option>
              <option value="webhook">回调通道（Webhook）</option>
              <option value="local_bridge">本地桥接</option>
            </select>
          </label>
          <label>
            <span>入口地址</span>
            <input
              v-model.trim="form.endpoint_url"
              class="filter-input"
              placeholder="例如 http://127.0.0.1:8787/"
            />
          </label>
          <label>
            <span>认证方式</span>
            <select v-model="form.auth_mode" class="filter-input">
              <option value="none">无认证</option>
              <option value="token">令牌</option>
              <option value="apikey">API 密钥</option>
              <option value="session">会话</option>
            </select>
          </label>
          <label>
            <span>访问范围</span>
            <select v-model="form.access_scope" class="filter-input">
              <option value="read_only">只读</option>
              <option value="assist_write">辅助写入</option>
              <option value="workflow">工作流执行</option>
            </select>
          </label>
          <label>
            <span>当前状态</span>
            <select v-model="form.status" class="filter-input">
              <option value="planned">规划中</option>
              <option value="ready">可接入</option>
              <option value="testing">测试中</option>
              <option value="active">已启用</option>
            </select>
          </label>
          <label class="form-switch">
            <input v-model="form.enabled" type="checkbox" />
            <span>启用该服务</span>
          </label>
          <label class="form-switch">
            <input v-model="form.read_only_first" type="checkbox" />
            <span>只读优先</span>
          </label>
          <label class="full-width">
            <span>备注</span>
            <textarea
              v-model.trim="form.notes"
              class="filter-input textarea-input"
              rows="4"
              placeholder="记录用途、能力边界、权限策略、后续接入计划和现场限制。"
            />
          </label>
        </div>

        <div class="action-row wrap top-gap">
          <button class="action-btn" type="button" @click="submitForm">
            {{ editingId ? "保存修改" : "登记服务" }}
          </button>
          <button v-if="editingId" class="action-btn subtle" type="button" @click="resetForm">
            取消编辑
          </button>
        </div>
        <p class="action-note">{{ actionMessage }}</p>
      </article>

      <article class="panel">
        <h3>接入建议</h3>
        <div class="stack-list">
          <div class="stack-item">
            <strong>第一阶段</strong>
            <span>优先开放资产、告警、拓扑、知识库等只读检索能力。</span>
          </div>
          <div class="stack-item">
            <strong>第二阶段</strong>
            <span>开放工单建议写入、诊断摘要和截图调取等辅助能力。</span>
          </div>
          <div class="stack-item">
            <strong>第三阶段</strong>
            <span>在审计与权限闭环完善后，再开放工作流编排和自动执行能力。</span>
          </div>
        </div>
      </article>
    </section>

    <article class="panel">
      <div class="panel-head">
        <h3>已登记服务</h3>
        <span class="panel-tip">统一管理模型能力工具、接口智能体、回调通道和本地桥接服务。</span>
      </div>
      <div class="table-shell">
        <table class="mini-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>入口</th>
              <th>认证</th>
              <th>范围</th>
              <th>状态</th>
              <th>策略</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in services" :key="item.id">
              <td>{{ item.display_name }}</td>
              <td>{{ serviceTypeLabel(item.service_type) }}</td>
              <td>{{ item.endpoint_url || "-" }}</td>
              <td>{{ authModeLabel(item.auth_mode) }}</td>
              <td>{{ scopeLabel(item.access_scope) }}</td>
              <td>{{ statusLabel(item.status) }}</td>
              <td>{{ item.read_only_first ? "只读优先" : "按需开放" }}</td>
              <td>
                <button class="text-link" type="button" @click="loadService(item)">编辑</button>
              </td>
            </tr>
            <tr v-if="!services.length">
              <td colspan="8" class="empty-cell">当前还没有登记服务。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import {
  createAgentService,
  fetchAgentGatewaySummary,
  fetchAgentServices,
  updateAgentService,
} from "../api/client";

const summary = ref({
  stage: "",
  strategy: "",
  service_count: 0,
  enabled_count: 0,
  read_only_count: 0,
  design_notes: [],
  mcp_targets: [],
  planned_tools: [],
  service_type_breakdown: [],
});

const services = ref([]);
const editingId = ref(null);
const actionMessage = ref("先把智能体 / 模型能力服务纳入台账，后续再按只读优先策略逐个接入。");

const form = reactive({
  service_key: "",
  display_name: "",
  service_type: "mcp",
  endpoint_url: "",
  auth_mode: "none",
  access_scope: "read_only",
  enabled: true,
  read_only_first: true,
  status: "planned",
  notes: "",
});

onMounted(async () => {
  await reload();
});

async function reload() {
  summary.value = await fetchAgentGatewaySummary();
  services.value = await fetchAgentServices();
}

function resetForm() {
  editingId.value = null;
  form.service_key = "";
  form.display_name = "";
  form.service_type = "mcp";
  form.endpoint_url = "";
  form.auth_mode = "none";
  form.access_scope = "read_only";
  form.enabled = true;
  form.read_only_first = true;
  form.status = "planned";
  form.notes = "";
}

function loadService(item) {
  editingId.value = item.id;
  form.service_key = item.service_key;
  form.display_name = item.display_name;
  form.service_type = item.service_type;
  form.endpoint_url = item.endpoint_url || "";
  form.auth_mode = item.auth_mode;
  form.access_scope = item.access_scope;
  form.enabled = !!item.enabled;
  form.read_only_first = !!item.read_only_first;
  form.status = item.status;
  form.notes = item.notes || "";
}

async function submitForm() {
  try {
    const payload = { ...form };
    if (editingId.value) {
      await updateAgentService(editingId.value, payload);
      actionMessage.value = "智能接口服务已更新。";
    } else {
      await createAgentService(payload);
      actionMessage.value = "智能接口服务已创建。";
    }
    await reload();
    resetForm();
  } catch (error) {
    console.error(error);
    actionMessage.value = "保存失败，请检查服务标识是否重复，或查看后端日志。";
  }
}

function stageLabel(value) {
  const mapping = {
    planned_foundation: "规划打底",
    testing: "联调测试",
    active: "正式运行",
  };
  return mapping[value] || value || "-";
}

function strategyLabel(value) {
  const mapping = {
    rest_plus_mcp: "REST + 模型能力双轨",
  };
  return mapping[value] || value || "-";
}

function serviceTypeLabel(value) {
  const mapping = {
    mcp: "模型能力工具（MCP）",
    rest_agent: "接口智能体（REST）",
    webhook: "回调通道（Webhook）",
    local_bridge: "本地桥接",
  };
  return mapping[value] || value || "-";
}

function authModeLabel(value) {
  const mapping = {
    none: "无认证",
    token: "令牌",
    apikey: "API 密钥",
    session: "会话",
  };
  return mapping[value] || value || "-";
}

function scopeLabel(value) {
  const mapping = {
    read_only: "只读",
    assist_write: "辅助写入",
    workflow: "工作流执行",
  };
  return mapping[value] || value || "-";
}

function statusLabel(value) {
  const mapping = {
    planned: "规划中",
    ready: "可接入",
    testing: "测试中",
    active: "已启用",
  };
  return mapping[value] || value || "-";
}
</script>

<style scoped>
.chip-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 14px;
}

.chip-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 18px;
  border-radius: 16px;
  background: rgba(9, 30, 66, 0.05);
  border: 1px solid rgba(63, 114, 175, 0.14);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-tip {
  color: rgba(54, 79, 107, 0.74);
  font-size: 13px;
}

.empty-cell {
  text-align: center;
  color: rgba(54, 79, 107, 0.74);
  padding: 18px 12px;
}
</style>
