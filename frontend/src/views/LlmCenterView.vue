<template>
  <section class="page">
    <header class="hero">
      <div class="hero-copy">
        <p class="eyebrow">模型接入层</p>
        <h2>模型接入中心</h2>
        <p class="lead">
          模型层负责统一管理外部大模型、本地模型网关和未来的混合推理入口。
          当前遵循“提供商抽象 + 环境变量密钥 + 审计留痕”的方式，避免把平台逻辑绑定到单一厂商。
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
            <label>密钥就绪</label>
            <strong>{{ summary.key_ready_count || 0 }}</strong>
          </div>
        </div>
      </div>
    </header>

    <section class="cards">
      <article class="card">
        <span>提供商总数</span>
        <strong>{{ summary.provider_count || 0 }}</strong>
      </article>
      <article class="card">
        <span>启用数量</span>
        <strong>{{ summary.enabled_count || 0 }}</strong>
      </article>
      <article class="card">
        <span>密钥就绪</span>
        <strong>{{ summary.key_ready_count || 0 }}</strong>
      </article>
      <article class="card">
        <span>提供商类型</span>
        <strong>{{ summary.provider_type_breakdown?.length || 0 }}</strong>
      </article>
    </section>

    <section class="panel-grid">
      <article class="panel accent-panel">
        <h3>接入策略</h3>
        <ul class="plain-list compact-list">
          <li v-for="(item, index) in summary.design_notes || []" :key="`note-${index}`">
            {{ item }}
          </li>
        </ul>
      </article>

      <article class="panel">
        <h3>可承接场景</h3>
        <div class="stack-list">
          <div v-for="item in summary.planned_use_cases || []" :key="item.name" class="stack-item">
            <strong>{{ item.name }}</strong>
            <span>{{ item.mode }}</span>
          </div>
        </div>
      </article>
    </section>

    <section class="panel-grid">
      <article class="panel">
        <h3>{{ editingId ? "编辑提供商" : "新增提供商" }}</h3>
        <div class="form-grid">
          <label>
            <span>提供方标识</span>
            <input v-model.trim="form.provider_key" class="filter-input" placeholder="例如 openai-prod" />
          </label>
          <label>
            <span>显示名称</span>
            <input
              v-model.trim="form.display_name"
              class="filter-input"
              placeholder="例如 OpenAI 生产接入"
            />
          </label>
          <label>
            <span>提供商类型</span>
            <input
              v-model.trim="form.provider_type"
              class="filter-input"
              placeholder="例如 openai_compatible"
            />
          </label>
          <label>
            <span>接口地址</span>
            <input
              v-model.trim="form.base_url"
              class="filter-input"
              placeholder="例如 https://api.openai.com/v1"
            />
          </label>
          <label>
            <span>默认模型</span>
            <input v-model.trim="form.default_model" class="filter-input" placeholder="例如 gpt-5.4" />
          </label>
          <label>
            <span>密钥环境变量</span>
            <input
              v-model.trim="form.api_key_env_name"
              class="filter-input"
              placeholder="例如 OPENAI_API_KEY"
            />
          </label>
          <label class="form-switch">
            <input v-model="form.enabled" type="checkbox" />
            <span>启用该提供商</span>
          </label>
          <label class="full-width">
            <span>备注</span>
            <textarea
              v-model.trim="form.notes"
              class="filter-input textarea-input"
              rows="4"
              placeholder="记录用途、适配模块、费用策略、速率限制和部署边界。"
            />
          </label>
        </div>

        <div class="action-row wrap top-gap">
          <button class="action-btn" type="button" @click="submitForm">
            {{ editingId ? "保存修改" : "创建提供商" }}
          </button>
          <button v-if="editingId" class="action-btn subtle" type="button" @click="resetForm">
            取消编辑
          </button>
        </div>
        <p class="action-note">{{ actionMessage }}</p>
      </article>

      <article class="panel">
        <h3>提供商类型分布</h3>
        <div v-if="summary.provider_type_breakdown?.length" class="chip-grid">
          <div
            v-for="item in summary.provider_type_breakdown"
            :key="item.provider_type"
            class="chip-card"
          >
            <strong>{{ providerTypeLabel(item.provider_type) }}</strong>
            <span>{{ item.count }} 个</span>
          </div>
        </div>
        <p v-else class="action-note">当前还没有提供商类型分布数据。</p>

        <h3 class="subhead">部署提醒</h3>
        <div class="stack-list">
          <div class="stack-item">
            <strong>密钥不入库</strong>
            <span>正式部署时在服务器环境变量中配置 API 密钥</span>
          </div>
          <div class="stack-item">
            <strong>按能力分流</strong>
            <span>轻模型做摘要，中模型做报表，强模型做归因建议</span>
          </div>
          <div class="stack-item">
            <strong>可随时替换</strong>
            <span>保持接口地址和模型名可配置，避免厂商锁定</span>
          </div>
        </div>
      </article>
    </section>

    <article class="panel">
      <div class="panel-head">
        <h3>提供商列表</h3>
        <span class="panel-tip">当前 V2 使用统一模型提供层，后续可接入本地网关和多厂商通道</span>
      </div>
      <div class="table-shell">
        <table class="mini-table">
          <thead>
            <tr>
              <th>显示名称</th>
              <th>类型</th>
              <th>接口地址</th>
              <th>默认模型</th>
              <th>环境变量</th>
              <th>密钥状态</th>
              <th>启用</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in providers" :key="item.id">
              <td>{{ item.display_name }}</td>
              <td>{{ providerTypeLabel(item.provider_type) }}</td>
              <td>{{ item.base_url || "-" }}</td>
              <td>{{ item.default_model || "-" }}</td>
              <td>{{ item.api_key_env_name || "-" }}</td>
              <td>{{ item.api_key_present ? "已就绪" : "未检测到" }}</td>
              <td>{{ item.enabled ? "启用" : "停用" }}</td>
              <td>
                <button class="text-link" type="button" @click="loadProvider(item)">编辑</button>
              </td>
            </tr>
            <tr v-if="!providers.length">
              <td colspan="8" class="empty-cell">当前还没有登记模型提供商。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { createLlmProvider, fetchLlmProviders, fetchLlmSummary, updateLlmProvider } from "../api/client";

const summary = ref({
  stage: "",
  strategy: "",
  provider_count: 0,
  enabled_count: 0,
  key_ready_count: 0,
  provider_type_breakdown: [],
  design_notes: [],
  planned_use_cases: [],
});

const providers = ref([]);
const editingId = ref(null);
const actionMessage = ref("可以先登记模型提供商，再到服务器环境变量中补齐 API 密钥。");

const form = reactive({
  provider_key: "",
  display_name: "",
  provider_type: "",
  base_url: "",
  default_model: "",
  api_key_env_name: "",
  enabled: true,
  notes: "",
});

onMounted(async () => {
  await reload();
});

async function reload() {
  summary.value = await fetchLlmSummary();
  providers.value = await fetchLlmProviders();
}

function resetForm() {
  editingId.value = null;
  form.provider_key = "";
  form.display_name = "";
  form.provider_type = "";
  form.base_url = "";
  form.default_model = "";
  form.api_key_env_name = "";
  form.enabled = true;
  form.notes = "";
}

function loadProvider(item) {
  editingId.value = item.id;
  form.provider_key = item.provider_key;
  form.display_name = item.display_name;
  form.provider_type = item.provider_type;
  form.base_url = item.base_url || "";
  form.default_model = item.default_model || "";
  form.api_key_env_name = item.api_key_env_name || "";
  form.enabled = !!item.enabled;
  form.notes = item.notes || "";
}

async function submitForm() {
  try {
    const payload = { ...form };
    if (editingId.value) {
      await updateLlmProvider(editingId.value, payload);
      actionMessage.value = "模型提供商已更新。";
    } else {
      await createLlmProvider(payload);
      actionMessage.value = "模型提供商已创建。";
    }
    await reload();
    resetForm();
  } catch (error) {
    console.error(error);
    actionMessage.value = "保存失败，请检查 provider_key 是否重复，或查看后端日志。";
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
    provider_layer: "提供商抽象层",
  };
  return mapping[value] || value || "-";
}

function providerTypeLabel(value) {
  const mapping = {
    openai_compatible: "OpenAI Compatible",
    anthropic_style: "Anthropic 风格",
    local_gateway: "本地网关",
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

.subhead {
  margin-top: 20px;
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
