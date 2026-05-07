<template>
  <section class="page docs-workbench-page">
    <WorkbenchShell leftWidth="300px" rightWidth="364px" maxWidth="1880px">
      <template #title>
        <div class="title-block">
          <p>DOCUMENT WORKBENCH</p>
          <h2>资料中心工作台</h2>
          <span>左边先收资料范围和建议阅读顺序，中间只保留资料主清单，右边固定承接资料详情、打开和复制动作。</span>
        </div>
      </template>

      <template #actions>
        <button class="tool-btn" type="button" @click="loadDocs">刷新文档列表</button>
        <button class="tool-btn" type="button" :disabled="!selectedDoc" @click="openSelectedDoc">
          打开当前资料
        </button>
        <button class="tool-btn primary" type="button" :disabled="!selectedDoc" @click="copySelectedDocLink">
          复制当前链接
        </button>
      </template>

      <template #summary>
        <section class="docs-metrics">
          <article class="metric-card">
            <span>资料总数</span>
            <strong>{{ docs.length }}</strong>
            <small>当前可远程打开的资料条目</small>
          </article>
          <article class="metric-card">
            <span>可访问</span>
            <strong>{{ accessibleCount }}</strong>
            <small>文件已存在，可直接打开</small>
          </article>
          <article class="metric-card">
            <span>缺失文件</span>
            <strong>{{ missingCount }}</strong>
            <small>需要补齐内容或回传文档</small>
          </article>
          <article class="metric-card">
            <span>当前基址</span>
            <strong>{{ originLabel }}</strong>
            <small>远程访问统一走 HTTP 链接</small>
          </article>
          <article class="metric-card">
            <span>当前选中</span>
            <strong>{{ selectedDoc?.title || "等待选择" }}</strong>
            <small>{{ actionMessage }}</small>
          </article>
        </section>
      </template>

      <template #roadmap>
        <section class="docs-roadmap">
          <article class="roadmap-step">
            <span>01</span>
            <strong>先看资料范围</strong>
            <small>先确认是值班说明、初始化、上线导入还是开发运行手册，避免找错入口。</small>
          </article>
          <article class="roadmap-step">
            <span>02</span>
            <strong>再选主条目</strong>
            <small>中间主清单保持稳定，一次只处理一个资料对象，不让信息横向溢出。</small>
          </article>
          <article class="roadmap-step">
            <span>03</span>
            <strong>右侧做动作</strong>
            <small>打开、复制、核查文件存在状态都固定在右栏，便于远程协同和值班转发。</small>
          </article>
          <article class="roadmap-step">
            <span>04</span>
            <strong>后续接入大资料库</strong>
            <small>这页以后可以平滑延展到知识库 / NAS / 文档服务器，不需要再推翻结构。</small>
          </article>
        </section>
      </template>

      <template #left>
        <aside class="docs-left-rail">
          <section class="scope-block">
            <div class="side-head">
              <strong>对象范围</strong>
              <span>{{ docs.length }} 份资料</span>
            </div>
            <div class="scope-list">
              <button class="scope-row" type="button" @click="focusAvailableDocs">
                <strong>只看可访问资料</strong>
                <span>{{ accessibleCount }} 份文件当前可直接打开</span>
              </button>
              <button class="scope-row" type="button" @click="focusMissingDocs">
                <strong>只看缺失资料</strong>
                <span>{{ missingCount }} 份文件仍待补齐</span>
              </button>
              <button class="scope-row" type="button" @click="resetSelection">
                <strong>恢复默认选择</strong>
                <span>回到第一份资料，适合重新开始值班交接</span>
              </button>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>推荐顺序</strong>
              <span>先主线，后细项</span>
            </div>
            <div class="hint-list">
              <button
                v-for="item in recommendedDocs"
                :key="`recommended-${item.slug}`"
                class="hint-row link-row"
                type="button"
                @click="selectDoc(item.slug)"
              >
                <strong>{{ item.title }}</strong>
                <span>{{ item.summary }}</span>
              </button>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>访问说明</strong>
              <span>远程协同</span>
            </div>
            <div class="hint-list">
              <article class="hint-row">
                <strong>打开方式</strong>
                <span>统一走平台链接，不依赖本地磁盘路径。</span>
              </article>
              <article class="hint-row">
                <strong>协同方式</strong>
                <span>复制链接后可以直接发给现场同事、管理员或值班群。</span>
              </article>
              <article class="hint-row">
                <strong>后续能力</strong>
                <span>后面可继续接入更大资料库、附件服务器和知识笔记系统。</span>
              </article>
            </div>
          </section>
        </aside>
      </template>

      <template #default>
        <section class="docs-center">
          <article class="panel workbench-panel">
            <div class="ops-guide-strip">
              <div class="ops-guide-card">
                <span>当前范围</span>
                <strong>{{ currentRangeLabel }}</strong>
                <small>快速确认本轮资料查看对象</small>
              </div>
              <div class="ops-guide-card">
                <span>当前动作</span>
                <strong>{{ selectedDoc ? "查看资料详情" : "等待选择资料" }}</strong>
                <small>{{ selectedDoc ? "右侧可直接打开或复制链接" : "请先在中间主清单选择一项" }}</small>
              </div>
              <div class="ops-guide-card">
                <span>当前链接模式</span>
                <strong>HTTP / 平台直链</strong>
                <small>适合公网或内网远程值班时直接访问</small>
              </div>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">DOCUMENT LIST</p>
                <h3>资料主清单</h3>
                <span>中间只保留条目清单，先选对象，再在右侧执行打开、复制和核查动作。</span>
              </div>
              <div class="list-stats">
                <span>{{ currentRangeLabel }}</span>
                <strong>{{ filteredDocs.length }} 条</strong>
              </div>
            </div>

            <div class="docs-list">
              <button
                v-for="item in filteredDocs"
                :key="item.slug"
                class="doc-row"
                :class="{ active: selectedSlug === item.slug }"
                type="button"
                @click="selectDoc(item.slug)"
              >
                <div class="doc-row-main">
                  <strong>{{ item.title }}</strong>
                  <span>{{ item.summary }}</span>
                  <small>{{ item.filename }}</small>
                </div>
                <div class="doc-row-side">
                  <span class="pill" :class="item.exists ? 'success' : 'danger'">
                    {{ item.exists ? "可打开" : "缺失" }}
                  </span>
                </div>
              </button>

              <article v-if="!filteredDocs.length" class="empty-state">
                <strong>当前范围没有资料</strong>
                <span>可以先恢复默认选择，或回到全部资料范围继续查看。</span>
              </article>
            </div>
          </article>
        </section>
      </template>

      <template #right>
        <aside class="docs-right-rail">
          <section class="scope-block detail-block">
            <div class="side-head">
              <strong>资料详情与处理</strong>
              <span>{{ selectedDoc ? "已选中" : "等待选择" }}</span>
            </div>

            <div v-if="selectedDoc" class="detail-stack">
              <article class="detail-chip">
                <span>资料名称</span>
                <strong>{{ selectedDoc.title }}</strong>
                <small>{{ selectedDoc.summary }}</small>
              </article>
              <article class="detail-chip">
                <span>文件名</span>
                <strong>{{ selectedDoc.filename }}</strong>
                <small>{{ selectedDoc.exists ? "文件已存在，可直接打开" : "当前文件缺失，需要补齐内容" }}</small>
              </article>
              <article class="detail-chip">
                <span>访问链接</span>
                <strong class="mono-text">{{ docLink(selectedDoc.slug) }}</strong>
                <small>复制这个链接即可转发给现场或管理端</small>
              </article>

              <div class="action-row wrap">
                <button class="tool-btn primary" type="button" @click="openSelectedDoc">打开资料</button>
                <button class="tool-btn" type="button" @click="copySelectedDocLink">复制链接</button>
              </div>
            </div>

            <div v-else class="empty-state tight">
              <strong>还没有选中资料</strong>
              <span>请先从中间主清单选择一项，右侧再执行打开或复制动作。</span>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>链接说明</strong>
              <span>当前基址</span>
            </div>
            <div class="hint-list">
              <article class="hint-row">
                <strong>访问入口</strong>
                <span class="mono-text">{{ originLabel }}</span>
              </article>
              <article class="hint-row">
                <strong>说明</strong>
                <span>远程测试时直接从平台打开资料页，再点“打开资料”，不会受本机磁盘路径影响。</span>
              </article>
              <article class="hint-row">
                <strong>动作回显</strong>
                <span>{{ actionMessage }}</span>
              </article>
            </div>
          </section>
        </aside>
      </template>
    </WorkbenchShell>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import WorkbenchShell from "../components/workbench/WorkbenchShell.vue";
import { fetchDocsCatalog } from "../api/client";

const docs = ref([]);
const selectedSlug = ref("");
const actionMessage = ref("点击中间资料条目后，可在右侧直接打开或复制链接。");
const scopeMode = ref("all");

const originLabel = window.location.origin;

const accessibleCount = computed(() => docs.value.filter((item) => item.exists).length);
const missingCount = computed(() => docs.value.filter((item) => !item.exists).length);
const recommendedOrder = ["system-user-guide", "data-initialization-guide", "first-launch-import-checklist", "dev-runbook"];

const filteredDocs = computed(() => {
  if (scopeMode.value === "available") {
    return docs.value.filter((item) => item.exists);
  }
  if (scopeMode.value === "missing") {
    return docs.value.filter((item) => !item.exists);
  }
  return docs.value;
});

const recommendedDocs = computed(() => {
  const orderMap = new Map(recommendedOrder.map((slug, index) => [slug, index]));
  return [...docs.value]
    .filter((item) => orderMap.has(item.slug))
    .sort((a, b) => orderMap.get(a.slug) - orderMap.get(b.slug));
});

const selectedDoc = computed(() => docs.value.find((item) => item.slug === selectedSlug.value) || null);

const currentRangeLabel = computed(() => {
  if (scopeMode.value === "available") {
    return "仅看可访问资料";
  }
  if (scopeMode.value === "missing") {
    return "仅看缺失资料";
  }
  return "全部资料";
});

onMounted(loadDocs);

async function loadDocs() {
  try {
    const data = await fetchDocsCatalog();
    docs.value = data.items || [];
    if (!selectedSlug.value || !docs.value.some((item) => item.slug === selectedSlug.value)) {
      selectedSlug.value = docs.value[0]?.slug || "";
    }
    actionMessage.value = "资料列表已刷新。";
  } catch (error) {
    console.error(error);
    actionMessage.value = "资料列表加载失败，请检查后端服务。";
  }
}

function docLink(slug) {
  return `${window.location.origin}/api/docs/${slug}`;
}

function selectDoc(slug) {
  selectedSlug.value = slug;
  actionMessage.value = "资料已定位，可在右侧打开或复制链接。";
}

function focusAvailableDocs() {
  scopeMode.value = "available";
  if (filteredDocs.value.length) {
    selectedSlug.value = filteredDocs.value[0].slug;
  }
  actionMessage.value = "当前只显示可访问资料。";
}

function focusMissingDocs() {
  scopeMode.value = "missing";
  if (filteredDocs.value.length) {
    selectedSlug.value = filteredDocs.value[0].slug;
  }
  actionMessage.value = "当前只显示缺失资料，便于后续补齐。";
}

function resetSelection() {
  scopeMode.value = "all";
  selectedSlug.value = docs.value[0]?.slug || "";
  actionMessage.value = "已恢复默认资料范围。";
}

function openSelectedDoc() {
  if (!selectedDoc.value) {
    return;
  }
  window.open(docLink(selectedDoc.value.slug), "_blank", "noopener");
  actionMessage.value = "资料已在新窗口打开。";
}

async function copySelectedDocLink() {
  if (!selectedDoc.value) {
    return;
  }
  try {
    await navigator.clipboard.writeText(docLink(selectedDoc.value.slug));
    actionMessage.value = "资料链接已复制。";
  } catch (error) {
    console.error(error);
    actionMessage.value = "复制失败，请手动复制右侧链接。";
  }
}
</script>

<style scoped>
.docs-workbench-page {
  padding-bottom: 20px;
}

.docs-metrics,
.docs-roadmap,
.ops-guide-strip,
.scope-list,
.hint-list,
.detail-stack,
.docs-list {
  display: grid;
  gap: 12px;
}

.docs-metrics {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.docs-roadmap {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.docs-left-rail,
.docs-right-rail,
.docs-center {
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
.doc-row,
.detail-chip,
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
.doc-row,
.detail-chip,
.empty-state {
  border: 1px solid rgba(111, 191, 255, 0.14);
  background: rgba(255, 255, 255, 0.03);
}

.link-row,
.doc-row {
  cursor: pointer;
}

.doc-row {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.doc-row.active {
  border-color: rgba(111, 191, 255, 0.42);
  background: linear-gradient(180deg, rgba(24, 75, 115, 0.52), rgba(14, 43, 70, 0.4));
}

.doc-row-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.doc-row-main span,
.doc-row-main small,
.hint-row span,
.detail-chip small,
.empty-state span {
  color: rgba(207, 231, 255, 0.72);
}

.doc-row-main small,
.mono-text {
  word-break: break-all;
}

.doc-row-side {
  display: flex;
  align-items: center;
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

.pill.success {
  border-color: rgba(52, 211, 153, 0.3);
  color: #9ef6cb;
}

.pill.danger {
  border-color: rgba(248, 113, 113, 0.3);
  color: #ffb4b4;
}

.detail-block {
  min-height: 0;
}

.detail-stack {
  margin-top: 12px;
}

.action-row.wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tool-btn {
  cursor: pointer;
}

.empty-state.tight {
  margin-top: 12px;
}

@media (max-width: 1380px) {
  .docs-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .docs-roadmap,
  .ops-guide-strip {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 960px) {
  .docs-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
