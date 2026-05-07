<template>
  <section class="page storage-workbench-page">
    <WorkbenchShell leftWidth="300px" rightWidth="376px" maxWidth="1880px">
      <template #title>
        <div class="title-block">
          <p>STORAGE WORKBENCH</p>
          <h2>存储与资源工作台</h2>
          <span>左边先收存储范围和迁移策略，中间只保留存储主表，右边固定承接登记编辑、当前运行目录和推荐存储栈。</span>
        </div>
      </template>

      <template #actions>
        <button class="tool-btn" type="button" @click="reload">刷新状态</button>
        <button class="tool-btn" type="button" @click="prepareNewProvider">新建存储</button>
        <button class="tool-btn primary" type="button" @click="submitForm">
          {{ editingId ? "保存修改" : "登记存储" }}
        </button>
      </template>

      <template #summary>
        <section class="storage-metrics">
          <article class="metric-card">
            <span>存储总数</span>
            <strong>{{ summary.provider_count || 0 }}</strong>
            <small>完整存储台账</small>
          </article>
          <article class="metric-card">
            <span>已启用</span>
            <strong>{{ summary.enabled_count || 0 }}</strong>
            <small>当前已接入的平台存储目标</small>
          </article>
          <article class="metric-card">
            <span>可写目标</span>
            <strong>{{ summary.writable_count || 0 }}</strong>
            <small>可承接缓存、资料或归档写入</small>
          </article>
          <article class="metric-card">
            <span>推荐组件</span>
            <strong>{{ summary.recommended_stack?.length || 0 }}</strong>
            <small>当前建议的目标存储栈</small>
          </article>
          <article class="metric-card">
            <span>当前阶段</span>
            <strong>{{ stageLabel(summary.stage) }}</strong>
            <small>{{ actionMessage }}</small>
          </article>
        </section>
      </template>

      <template #roadmap>
        <section class="storage-roadmap">
          <article class="roadmap-step">
            <span>01</span>
            <strong>先建抽象层</strong>
            <small>先把本地、对象存储、WebDAV、海康存储登记进统一台账，不让系统绑定在单机目录上。</small>
          </article>
          <article class="roadmap-step">
            <span>02</span>
            <strong>再分用途</strong>
            <small>把运行缓存、视频缓存、资料文档、归档资源分开，让后续迁移和替换更平滑。</small>
          </article>
          <article class="roadmap-step">
            <span>03</span>
            <strong>右侧做登记</strong>
            <small>编辑和新建全部固定在右栏，避免列表、表单和说明上下跳动。</small>
          </article>
          <article class="roadmap-step">
            <span>04</span>
            <strong>后续平滑外迁</strong>
            <small>等独立存储服务器就位后，这页可以直接承接，不需要重新设计整个系统。</small>
          </article>
        </section>
      </template>

      <template #left>
        <aside class="storage-left-rail">
          <section class="scope-block">
            <div class="side-head">
              <strong>对象范围</strong>
              <span>{{ providers.length }} 个已登记目标</span>
            </div>
            <div class="scope-list">
              <button class="scope-row" type="button" @click="focusEnabledProviders">
                <strong>只看已启用存储</strong>
                <span>{{ summary.enabled_count || 0 }} 个当前可用目标</span>
              </button>
              <button class="scope-row" type="button" @click="focusWritableProviders">
                <strong>只看可写目标</strong>
                <span>{{ summary.writable_count || 0 }} 个可承接实际写入</span>
              </button>
              <button class="scope-row" type="button" @click="focusDocumentsProviders">
                <strong>资料存储范围</strong>
                <span>优先看承接文档资料的入口</span>
              </button>
              <button class="scope-row" type="button" @click="resetScope">
                <strong>恢复全部范围</strong>
                <span>回到完整台账视角，重新梳理当前部署</span>
              </button>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>迁移建议</strong>
              <span>分阶段推进</span>
            </div>
            <div class="hint-list">
              <article class="hint-row">
                <strong>当前阶段</strong>
                <span>本地运行目录承接数据库、缓存和临时文件。</span>
              </article>
              <article class="hint-row">
                <strong>稳定阶段</strong>
                <span>对象存储承接视频缓存和大文件，WebDAV 承接协作文档。</span>
              </article>
              <article class="hint-row">
                <strong>正式部署</strong>
                <span>按用途拆分运行缓存、资料归档、图片视频和录像回放入口。</span>
              </article>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>目标类型</strong>
              <span>{{ summary.provider_targets?.length || 0 }} 类</span>
            </div>
            <div class="hint-list">
              <article
                v-for="item in summary.provider_targets || []"
                :key="`target-${item.name}`"
                class="hint-row"
              >
                <strong>{{ providerTypeLabel(item.name) }}</strong>
                <span>{{ item.role }}</span>
              </article>
            </div>
          </section>
        </aside>
      </template>

      <template #default>
        <section class="storage-center">
          <article class="panel workbench-panel">
            <div class="ops-guide-strip">
              <div class="ops-guide-card">
                <span>当前范围</span>
                <strong>{{ scopeLabel }}</strong>
                <small>{{ filteredProviders.length }} 个目标进入主表</small>
              </div>
              <div class="ops-guide-card">
                <span>当前策略</span>
                <strong>{{ strategyLabel(summary.strategy) }}</strong>
                <small>先抽象，后拆分，再外迁</small>
              </div>
              <div class="ops-guide-card">
                <span>当前模式</span>
                <strong>{{ editingId ? "编辑已登记存储" : "新建存储草稿" }}</strong>
                <small>{{ editingId ? "右侧已锁定当前条目" : "右侧可直接登记新的存储提供方" }}</small>
              </div>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">PROVIDER TABLE</p>
                <h3>存储主表</h3>
                <span>中间主区只保留已登记存储台账，先选对象，再在右侧完成登记、编辑和迁移说明。</span>
              </div>
              <div class="list-stats">
                <span>{{ scopeLabel }}</span>
                <strong>{{ filteredProviders.length }} 项</strong>
              </div>
            </div>

            <div class="provider-list">
              <button
                v-for="item in filteredProviders"
                :key="item.id"
                class="provider-row"
                :class="{ active: selectedProviderId === item.id }"
                type="button"
                @click="loadProvider(item)"
              >
                <div class="provider-main">
                  <strong>{{ item.display_name }}</strong>
                  <span>{{ providerTypeLabel(item.provider_type) }} / {{ usageScopeLabel(item.usage_scope) }}</span>
                  <small>{{ item.endpoint_url || item.bucket_or_share || "-" }}</small>
                </div>
                <div class="provider-side">
                  <span class="pill">{{ statusLabel(item.status) }}</span>
                  <small>{{ item.writable ? "可写" : "只读" }}</small>
                </div>
              </button>

              <article v-if="!filteredProviders.length" class="empty-state">
                <strong>当前范围没有存储目标</strong>
                <span>可以恢复全部范围，或直接在右侧新建一个新的存储登记。</span>
              </article>
            </div>
          </article>
        </section>
      </template>

      <template #right>
        <aside class="storage-right-rail">
          <section class="scope-block">
            <div class="side-head">
              <strong>{{ editingId ? "存储详情与编辑" : "登记存储提供方" }}</strong>
              <span>{{ editingId ? "编辑模式" : "新建模式" }}</span>
            </div>

            <div class="form-grid">
              <label>
                <span>存储标识</span>
                <input v-model.trim="form.provider_key" class="field-input" placeholder="例如 seaweedfs-planned" />
              </label>
              <label>
                <span>显示名称</span>
                <input v-model.trim="form.display_name" class="field-input" placeholder="例如 SeaweedFS 对象存储" />
              </label>
              <label>
                <span>存储类型</span>
                <select v-model="form.provider_type" class="field-input">
                  <option value="local_filesystem">本地文件系统</option>
                  <option value="s3_compatible">S3 兼容</option>
                  <option value="webdav">WebDAV</option>
                  <option value="hikvision_storage">海康存储</option>
                </select>
              </label>
              <label>
                <span>入口地址</span>
                <input v-model.trim="form.endpoint_url" class="field-input" placeholder="例如 http://10.0.10.10:8333/" />
              </label>
              <label>
                <span>桶 / 共享 / 根目录</span>
                <input v-model.trim="form.bucket_or_share" class="field-input" placeholder="例如 runtime-cache" />
              </label>
              <label>
                <span>认证方式</span>
                <select v-model="form.auth_mode" class="field-input">
                  <option value="none">无认证</option>
                  <option value="access_key">访问密钥</option>
                  <option value="token">令牌</option>
                  <option value="session">会话</option>
                </select>
              </label>
              <label>
                <span>用途范围</span>
                <select v-model="form.usage_scope" class="field-input">
                  <option value="runtime_cache">运行缓存</option>
                  <option value="media_cache">视频缓存</option>
                  <option value="documents">文档资料</option>
                  <option value="archive">归档</option>
                </select>
              </label>
              <label>
                <span>当前状态</span>
                <select v-model="form.status" class="field-input">
                  <option value="planned">计划中</option>
                  <option value="ready">可接入</option>
                  <option value="testing">测试中</option>
                  <option value="active">已启用</option>
                </select>
              </label>
              <label class="switch-row">
                <input v-model="form.enabled" type="checkbox" />
                <span>启用该存储</span>
              </label>
              <label class="switch-row">
                <input v-model="form.writable" type="checkbox" />
                <span>允许写入</span>
              </label>
              <label class="full-width">
                <span>备注</span>
                <textarea
                  v-model.trim="form.notes"
                  class="field-input textarea-input"
                  rows="4"
                  placeholder="记录用途、部署位置、后续迁移策略和依赖约束。"
                />
              </label>
            </div>

            <div class="action-row wrap">
              <button class="tool-btn primary" type="button" @click="submitForm">
                {{ editingId ? "保存修改" : "登记存储" }}
              </button>
              <button class="tool-btn" type="button" @click="prepareNewProvider">
                {{ editingId ? "取消编辑" : "清空草稿" }}
              </button>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>当前运行存储</strong>
              <span>{{ stageLabel(summary.stage) }}</span>
            </div>
            <div class="hint-list">
              <article class="hint-row">
                <strong>运行目录</strong>
                <span>{{ summary.current_runtime_storage?.runtime_dir || "-" }}</span>
              </article>
              <article class="hint-row">
                <strong>数据库</strong>
                <span>{{ summary.current_runtime_storage?.database_path || "-" }}</span>
              </article>
              <article class="hint-row">
                <strong>当前策略</strong>
                <span>{{ strategyLabel(summary.strategy) }}</span>
              </article>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>推荐存储栈</strong>
              <span>{{ summary.recommended_stack?.length || 0 }} 项</span>
            </div>
            <div class="hint-list">
              <article
                v-for="item in summary.recommended_stack || []"
                :key="`stack-${item.name}`"
                class="hint-row"
              >
                <strong>{{ item.name }}</strong>
                <span>{{ item.role }}</span>
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
import { createStorageProvider, fetchStorageProviders, fetchStorageSummary, updateStorageProvider } from "../api/client";

const summary = ref({
  stage: "",
  provider_count: 0,
  enabled_count: 0,
  writable_count: 0,
  current_runtime_storage: {},
  provider_targets: [],
  recommended_stack: [],
  strategy: "",
});

const providers = ref([]);
const editingId = ref(null);
const selectedProviderId = ref(null);
const actionMessage = ref("先把存储接入纳入台账，后续再按阶段切换缓存、文档和对象存储。");
const scopeMode = ref("all");

const form = reactive({
  provider_key: "",
  display_name: "",
  provider_type: "local_filesystem",
  endpoint_url: "",
  bucket_or_share: "",
  auth_mode: "none",
  usage_scope: "runtime_cache",
  enabled: true,
  writable: false,
  status: "planned",
  notes: "",
});

const filteredProviders = computed(() => {
  if (scopeMode.value === "enabled") {
    return providers.value.filter((item) => item.enabled);
  }
  if (scopeMode.value === "writable") {
    return providers.value.filter((item) => item.writable);
  }
  if (scopeMode.value === "documents") {
    return providers.value.filter((item) => item.usage_scope === "documents");
  }
  return providers.value;
});

const scopeLabel = computed(() => {
  if (scopeMode.value === "enabled") {
    return "仅看已启用存储";
  }
  if (scopeMode.value === "writable") {
    return "仅看可写目标";
  }
  if (scopeMode.value === "documents") {
    return "仅看资料存储";
  }
  return "全部存储目标";
});

onMounted(async () => {
  await reload();
});

async function reload() {
  summary.value = await fetchStorageSummary();
  providers.value = await fetchStorageProviders();
  if (!selectedProviderId.value && providers.value.length) {
    selectedProviderId.value = providers.value[0].id;
  }
}

function resetForm() {
  editingId.value = null;
  form.provider_key = "";
  form.display_name = "";
  form.provider_type = "local_filesystem";
  form.endpoint_url = "";
  form.bucket_or_share = "";
  form.auth_mode = "none";
  form.usage_scope = "runtime_cache";
  form.enabled = true;
  form.writable = false;
  form.status = "planned";
  form.notes = "";
}

function prepareNewProvider() {
  selectedProviderId.value = null;
  resetForm();
  actionMessage.value = "已切回新建存储模式。";
}

function loadProvider(item) {
  selectedProviderId.value = item.id;
  editingId.value = item.id;
  form.provider_key = item.provider_key;
  form.display_name = item.display_name;
  form.provider_type = item.provider_type;
  form.endpoint_url = item.endpoint_url || "";
  form.bucket_or_share = item.bucket_or_share || "";
  form.auth_mode = item.auth_mode;
  form.usage_scope = item.usage_scope;
  form.enabled = !!item.enabled;
  form.writable = !!item.writable;
  form.status = item.status;
  form.notes = item.notes || "";
  actionMessage.value = `已载入 ${item.display_name}，可在右侧直接修改。`;
}

async function submitForm() {
  try {
    const payload = { ...form };
    if (editingId.value) {
      await updateStorageProvider(editingId.value, payload);
      actionMessage.value = "存储信息已更新。";
    } else {
      await createStorageProvider(payload);
      actionMessage.value = "存储信息已创建。";
    }
    await reload();
    prepareNewProvider();
  } catch (error) {
    console.error(error);
    actionMessage.value = "保存失败，请检查存储标识是否重复，或查看后端日志。";
  }
}

function focusEnabledProviders() {
  scopeMode.value = "enabled";
  actionMessage.value = "当前只显示已启用存储。";
}

function focusWritableProviders() {
  scopeMode.value = "writable";
  actionMessage.value = "当前只显示可写目标。";
}

function focusDocumentsProviders() {
  scopeMode.value = "documents";
  actionMessage.value = "当前只显示文档资料类存储。";
}

function resetScope() {
  scopeMode.value = "all";
  actionMessage.value = "已恢复完整存储范围。";
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
    provider_abstraction: "存储抽象层",
  };
  return mapping[value] || value || "-";
}

function providerTypeLabel(value) {
  const mapping = {
    local_filesystem: "本地文件系统",
    s3_compatible: "对象存储（S3）",
    webdav: "文档网关（WebDAV）",
    hikvision_storage: "海康存储",
  };
  return mapping[value] || value || "-";
}

function usageScopeLabel(value) {
  const mapping = {
    runtime_cache: "运行缓存",
    media_cache: "视频缓存",
    documents: "文档资料",
    archive: "归档",
  };
  return mapping[value] || value || "-";
}

function statusLabel(value) {
  const mapping = {
    planned: "计划中",
    ready: "可接入",
    testing: "测试中",
    active: "已启用",
  };
  return mapping[value] || value || "-";
}
</script>

<style scoped>
.storage-workbench-page {
  padding-bottom: 20px;
}

.storage-metrics,
.storage-roadmap,
.ops-guide-strip,
.scope-list,
.hint-list,
.provider-list {
  display: grid;
  gap: 12px;
}

.storage-metrics {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.storage-roadmap {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.storage-left-rail,
.storage-right-rail,
.storage-center {
  display: grid;
  gap: 12px;
}

.scope-block,
.workbench-panel {
  border-radius: 24px;
  border: 1px solid rgba(111, 191, 255, 0.14);
  background: linear-gradient(180deg, rgba(9, 25, 44, 0.96), rgba(11, 34, 58, 0.92));
  box-shadow: 0 26px 50px rgba(3, 10, 20, 0.28);
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

.scope-row,
.hint-row,
.provider-row,
.empty-state {
  width: 100%;
  text-align: left;
  border-radius: 16px;
  padding: 12px 14px;
  display: grid;
  gap: 4px;
  color: #f4fbff;
}

.scope-row,
.hint-row,
.provider-row,
.empty-state {
  border: 1px solid rgba(111, 191, 255, 0.14);
  background: rgba(255, 255, 255, 0.03);
}

.provider-row {
  cursor: pointer;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.provider-row.active {
  border-color: rgba(111, 191, 255, 0.42);
  background: linear-gradient(180deg, rgba(24, 75, 115, 0.52), rgba(14, 43, 70, 0.4));
}

.provider-main,
.provider-side {
  display: grid;
  gap: 4px;
}

.provider-main span,
.provider-main small,
.hint-row span,
.empty-state span,
.provider-side small {
  color: rgba(207, 231, 255, 0.72);
}

.provider-main small {
  word-break: break-all;
}

.provider-side {
  text-align: right;
  justify-items: end;
}

.ops-guide-strip {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.list-stats {
  display: grid;
  gap: 4px;
  text-align: right;
  color: rgba(207, 231, 255, 0.72);
}

.list-stats strong {
  color: #f4fbff;
  font-size: 20px;
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

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.form-grid label {
  display: grid;
  gap: 6px;
  color: rgba(207, 231, 255, 0.78);
}

.field-input {
  width: 100%;
}

.full-width {
  grid-column: 1 / -1;
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.action-row.wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.tool-btn {
  cursor: pointer;
}

@media (max-width: 1380px) {
  .storage-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .storage-roadmap,
  .ops-guide-strip,
  .form-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 960px) {
  .storage-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
