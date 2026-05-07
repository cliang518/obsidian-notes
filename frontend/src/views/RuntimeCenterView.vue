<template>
  <section class="page runtime-workbench-page">
    <WorkbenchShell leftWidth="296px" rightWidth="352px" maxWidth="1880px">
      <template #title>
        <div class="title-block">
          <p>RUNTIME WORKBENCH</p>
          <h2>运行监控工作台</h2>
          <span>左边先收运行范围和备份策略，中间只保留系统状态与备份主表，右边固定承接服务判断、值守说明和动作反馈。</span>
        </div>
      </template>

      <template #actions>
        <button class="tool-btn" type="button" @click="toggleAutoRefresh">
          {{ autoRefresh ? "关闭自动刷新" : "开启自动刷新" }}
        </button>
        <button class="tool-btn primary" type="button" @click="loadRuntime">立即刷新</button>
        <button class="tool-btn" type="button" :disabled="backupBusy" @click="triggerBackup">
          {{ backupBusy ? "正在创建备份..." : "创建系统备份" }}
        </button>
      </template>

      <template #summary>
        <section class="runtime-metrics">
          <article class="metric-card" :class="healthClass(runtime.cpu_percent, 65, 85)">
            <span>处理器占用</span>
            <strong>{{ runtime.cpu_percent ?? "-" }}%</strong>
            <small>{{ healthLabel(runtime.cpu_percent, 65, 85) }}</small>
          </article>
          <article class="metric-card" :class="healthClass(runtime.memory?.used_percent, 70, 85)">
            <span>内存占用</span>
            <strong>{{ runtime.memory?.used_percent ?? "-" }}%</strong>
            <small>{{ healthLabel(runtime.memory?.used_percent, 70, 85) }}</small>
          </article>
          <article class="metric-card">
            <span>可用内存</span>
            <strong>{{ runtime.memory?.available_gb ?? "-" }} GB</strong>
            <small>当前空闲资源</small>
          </article>
          <article class="metric-card" :class="healthClass(runtime.disk?.used_percent, 75, 90)">
            <span>磁盘占用</span>
            <strong>{{ runtime.disk?.used_percent ?? "-" }}%</strong>
            <small>{{ healthLabel(runtime.disk?.used_percent, 75, 90) }}</small>
          </article>
          <article class="metric-card">
            <span>运行版本</span>
            <strong>{{ runtime.app_version || "-" }}</strong>
            <small>{{ generatedAtText }}</small>
          </article>
          <article class="metric-card">
            <span>备份数量</span>
            <strong>{{ backups.length }}</strong>
            <small>{{ backupMessage || "支持一键创建和清理备份" }}</small>
          </article>
        </section>
      </template>

      <template #roadmap>
        <section class="runtime-roadmap">
          <article class="roadmap-step">
            <span>01</span>
            <strong>先看资源健康</strong>
            <small>先判断 CPU、内存、磁盘是否异常，不被单个进程现象带偏。</small>
          </article>
          <article class="roadmap-step">
            <span>02</span>
            <strong>再看服务监听</strong>
            <small>8011 和 3011 是主线，先确认监听再判断页面或托盘异常。</small>
          </article>
          <article class="roadmap-step">
            <span>03</span>
            <strong>看关键进程</strong>
            <small>把核心进程和全系统高占用进程放在中段主表里，便于快速对照。</small>
          </article>
          <article class="roadmap-step">
            <span>04</span>
            <strong>最后做备份动作</strong>
            <small>备份、清理、下载都放在同一工作台，收工前直接完成。</small>
          </article>
        </section>
      </template>

      <template #left>
        <aside class="runtime-left-rail">
          <section class="scope-block">
            <div class="side-head">
              <strong>对象范围</strong>
              <span>{{ autoRefresh ? "自动刷新已开启" : "当前手动刷新" }}</span>
            </div>
            <div class="scope-list">
              <button class="scope-row" @click="loadRuntime">
                <strong>刷新运行状态</strong>
                <span>重新采样 CPU、内存、磁盘和端口监听状态</span>
              </button>
              <button class="scope-row" @click="loadBackups">
                <strong>刷新备份列表</strong>
                <span>重新加载备份文件清单和大小、时间信息</span>
              </button>
              <button class="scope-row" @click="toggleAutoRefresh">
                <strong>{{ autoRefresh ? "关闭自动刷新" : "开启自动刷新" }}</strong>
                <span>当前 {{ autoRefresh ? "每 10 秒自动采样一次" : "仅手动采样" }}</span>
              </button>
            </div>
          </section>

          <section class="filter-panel">
            <div class="side-head">
              <strong>备份策略</strong>
              <span>直接在这里设策略</span>
            </div>
            <div class="filter-stack">
              <label class="field-block">
                <span>仅保留最近份数</span>
                <input v-model.number="pruneKeepLatest" class="field-input" type="number" min="1" max="365" />
              </label>
              <label class="switch-row">
                <input v-model="pruneDryRun" type="checkbox" />
                <span>仅预演（不删除）</span>
              </label>
              <div class="action-row wrap">
                <button class="tool-btn primary" type="button" :disabled="pruneBusy" @click="pruneBackups">
                  {{ pruneBusy ? "处理中..." : "执行清理" }}
                </button>
                <button class="tool-btn" type="button" @click="loadBackups">刷新列表</button>
              </div>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>值守提示</strong>
              <span>判断顺序固定下来</span>
            </div>
            <div class="hint-list">
              <article class="hint-row">
                <strong>先看监听再看页面</strong>
                <span>前端打不开时，先判断 3011 是否监听，避免只盯浏览器表象。</span>
              </article>
              <article class="hint-row">
                <strong>高占用要结合上下文</strong>
                <span>瞬时占用不一定异常，要和关键进程、采样时间、端口状态一起看。</span>
              </article>
              <article class="hint-row">
                <strong>收工前做备份</strong>
                <span>版本更新、数据调整、结构重建前后都应留下可回退的备份点。</span>
              </article>
            </div>
          </section>
        </aside>
      </template>

      <template #default>
        <section class="runtime-center">
          <article class="panel workbench-panel">
            <div class="ops-guide-strip">
              <div class="ops-guide-card">
                <span>当前刷新方式</span>
                <strong>{{ autoRefresh ? "自动采样" : "手动采样" }}</strong>
                <small>{{ autoRefresh ? "每 10 秒采样一次" : "由值班人员手动刷新" }}</small>
              </div>
              <div class="ops-guide-card">
                <span>系统目录</span>
                <strong>{{ runtime.runtime_dir || "-" }}</strong>
                <small>运行目录与值守脚本参考位置</small>
              </div>
              <div class="ops-guide-card">
                <span>数据库位置</span>
                <strong>{{ runtime.database_path || "-" }}</strong>
                <small>备份和排障时优先保护的数据核心</small>
              </div>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">PROCESS WATCH</p>
                <h3>进程与资源主表</h3>
                <span>左边收范围，中间只看关键进程与高占用进程</span>
              </div>
            </div>

            <div class="table-pair">
              <section class="table-block">
                <div class="table-head">
                  <strong>关键进程</strong>
                  <span>{{ (runtime.tracked_processes || []).length }} 项</span>
                </div>
                <div class="table-shell">
                  <table class="mini-table">
                    <thead>
                      <tr>
                        <th>进程</th>
                        <th>进程号</th>
                        <th>内存</th>
                        <th>处理器占用</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in runtime.tracked_processes || []" :key="`${item.name}-${item.pid}`">
                        <td>{{ item.name }}</td>
                        <td>{{ item.pid }}</td>
                        <td>{{ item.memory_mb }} MB</td>
                        <td>{{ item.cpu_percent }}%</td>
                      </tr>
                      <tr v-if="!(runtime.tracked_processes || []).length">
                        <td colspan="4">当前没有关键进程样本</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>

              <section class="table-block">
                <div class="table-head">
                  <strong>系统高占用进程</strong>
                  <span>{{ (runtime.top_processes || []).length }} 项</span>
                </div>
                <div class="table-shell">
                  <table class="mini-table">
                    <thead>
                      <tr>
                        <th>进程</th>
                        <th>进程号</th>
                        <th>内存</th>
                        <th>处理器占用</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in runtime.top_processes || []" :key="`top-${item.pid}`">
                        <td>{{ item.name }}</td>
                        <td>{{ item.pid }}</td>
                        <td>{{ item.memory_mb }} MB</td>
                        <td>{{ item.cpu_percent }}%</td>
                      </tr>
                      <tr v-if="!(runtime.top_processes || []).length">
                        <td colspan="4">当前没有高占用进程样本</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">BACKUP TABLE</p>
                <h3>系统备份主表</h3>
                <span>{{ backups.length }} 份备份，支持下载和删除</span>
              </div>
              <div class="list-actions">
                <button class="tool-btn" type="button" @click="loadBackups">刷新列表</button>
              </div>
            </div>

            <div class="table-shell">
              <table class="mini-table">
                <thead>
                  <tr>
                    <th>文件名</th>
                    <th>大小</th>
                    <th>时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in backups" :key="item.filename">
                    <td class="mono">{{ item.filename }}</td>
                    <td>{{ formatSize(item.size_bytes) }}</td>
                    <td class="mono">{{ formatTime(item.updated_at) }}</td>
                    <td>
                      <div class="row-actions">
                        <a class="ops-link primary" :href="backupDownloadLink(item.filename)" target="_blank" rel="noopener">下载</a>
                        <button
                          class="ops-link danger-link"
                          type="button"
                          :disabled="deletingFilename === item.filename"
                          @click="removeBackup(item.filename)"
                        >
                          {{ deletingFilename === item.filename ? "删除中..." : "删除" }}
                        </button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="!backups.length">
                    <td colspan="4" class="mono">暂无备份记录</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </section>
      </template>

      <template #right>
        <aside class="runtime-right-rail">
          <section class="detail-shell">
            <div class="side-head">
              <strong>服务监听状态</strong>
              <span>8011 / 3011 是主线入口</span>
            </div>

            <div class="detail-summary-grid">
              <article class="detail-chip" :class="serviceClass(runtime.services?.backend_8011)">
                <span>后端 8011</span>
                <strong>{{ serviceStatus(runtime.services?.backend_8011) }}</strong>
                <small>进程号 {{ runtime.services?.backend_8011?.pid ?? "-" }}</small>
              </article>
              <article class="detail-chip" :class="serviceClass(runtime.services?.frontend_3011)">
                <span>前端 3011</span>
                <strong>{{ serviceStatus(runtime.services?.frontend_3011) }}</strong>
                <small>进程号 {{ runtime.services?.frontend_3011?.pid ?? "-" }}</small>
              </article>
            </div>

            <div class="action-row wrap">
              <button class="tool-btn primary" type="button" @click="loadRuntime">刷新状态</button>
              <button class="tool-btn" type="button" :disabled="backupBusy" @click="triggerBackup">
                {{ backupBusy ? "备份中..." : "立即备份" }}
              </button>
              <button class="tool-btn" type="button" @click="toggleAutoRefresh">
                {{ autoRefresh ? "关闭自动刷新" : "开启自动刷新" }}
              </button>
            </div>

            <p class="status-line">{{ backupMessage || "托盘会持续巡检 8011 和 3011，缺失时尝试自愈，并把结果写入运行日志。" }}</p>

            <section class="advice-block">
              <strong>值守说明</strong>
              <ul class="plain-list compact-list">
                <li>若出现瞬时高处理器占用，请结合关键进程和端口监听状态综合判断，不要只看单次采样。</li>
                <li>发布新版本前执行一次备份，便于快速回滚。</li>
                <li>建议把 `backups` 目录同步到异机或 NAS，避免单机风险。</li>
              </ul>
            </section>
          </section>
        </aside>
      </template>
    </WorkbenchShell>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import WorkbenchShell from "../components/workbench/WorkbenchShell.vue";
import {
  createSystemBackup,
  deleteSystemBackup,
  fetchSystemBackups,
  fetchSystemRuntime,
  pruneSystemBackups,
} from "../api/client";
import { authState } from "../state/auth";

const runtime = ref({});
const backups = ref([]);
const autoRefresh = ref(true);
const backupBusy = ref(false);
const pruneBusy = ref(false);
const deletingFilename = ref("");
const pruneKeepLatest = ref(20);
const pruneDryRun = ref(true);
const backupMessage = ref("");
let timerId = null;

onMounted(async () => {
  await Promise.all([loadRuntime(), loadBackups()]);
  ensureTimer();
});

onUnmounted(() => {
  clearTimer();
});

const generatedAtText = computed(() => {
  if (!runtime.value.generated_at) {
    return "等待采样";
  }
  return `采样时间 ${runtime.value.generated_at}`;
});

async function loadRuntime() {
  try {
    runtime.value = await fetchSystemRuntime();
  } catch (error) {
    console.error(error);
  }
}

async function loadBackups() {
  try {
    const data = await fetchSystemBackups(80);
    backups.value = data.items || [];
  } catch (error) {
    console.error(error);
  }
}

async function triggerBackup() {
  if (backupBusy.value) return;
  backupBusy.value = true;
  backupMessage.value = "正在创建备份，请稍候...";
  try {
    const result = await createSystemBackup();
    const backup = result.backup || {};
    backupMessage.value = `备份完成：${backup.filename || "-"}，${formatSize(backup.size_bytes || 0)}`;
    await loadBackups();
  } catch (error) {
    console.error(error);
    backupMessage.value = "备份失败，请检查后端日志。";
  } finally {
    backupBusy.value = false;
  }
}

async function removeBackup(filename) {
  if (!filename) return;
  const ok = window.confirm(`确认删除备份文件：${filename}？`);
  if (!ok) return;

  deletingFilename.value = filename;
  try {
    await deleteSystemBackup(filename);
    backupMessage.value = `已删除备份：${filename}`;
    await loadBackups();
  } catch (error) {
    console.error(error);
    backupMessage.value = `删除失败：${filename}`;
  } finally {
    deletingFilename.value = "";
  }
}

async function pruneBackups() {
  if (pruneBusy.value) return;
  const keepLatest = Number(pruneKeepLatest.value || 20);
  if (!Number.isFinite(keepLatest) || keepLatest < 1) {
    backupMessage.value = "保留份数必须大于等于 1。";
    return;
  }

  pruneBusy.value = true;
  try {
    const response = await pruneSystemBackups({
      keep_latest: keepLatest,
      dry_run: pruneDryRun.value,
    });
    const result = response.result || {};
    const action = result.dry_run ? "预演" : "清理";
    backupMessage.value = `${action}完成：候选 ${result.candidate_count || 0}，处理 ${result.deleted_count || 0}，失败 ${result.failed_count || 0}`;
    if (!result.dry_run) {
      await loadBackups();
    }
  } catch (error) {
    console.error(error);
    backupMessage.value = "备份清理失败，请检查后端日志。";
  } finally {
    pruneBusy.value = false;
  }
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value;
  if (autoRefresh.value) {
    ensureTimer();
  } else {
    clearTimer();
  }
}

function ensureTimer() {
  clearTimer();
  if (!autoRefresh.value) {
    return;
  }
  timerId = window.setInterval(loadRuntime, 10000);
}

function clearTimer() {
  if (timerId) {
    window.clearInterval(timerId);
    timerId = null;
  }
}

function serviceStatus(item) {
  if (!item) {
    return "-";
  }
  return item.listening ? "监听中" : "未监听";
}

function serviceClass(item) {
  if (!item) {
    return "risk";
  }
  return item.listening ? "healthy" : "risk";
}

function healthLabel(value, warn, risk) {
  if (value == null) {
    return "等待采样";
  }
  if (value >= risk) {
    return "偏高";
  }
  if (value >= warn) {
    return "关注";
  }
  return "稳定";
}

function healthClass(value, warn, risk) {
  if (value == null) {
    return "";
  }
  if (value >= risk) {
    return "risk";
  }
  if (value >= warn) {
    return "warning";
  }
  return "healthy";
}

function formatSize(value) {
  const bytes = Number(value || 0);
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatTime(value) {
  if (!value) return "-";
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? value : dt.toLocaleString("zh-CN", { hour12: false });
}

function backupDownloadLink(filename) {
  const token = authState.token || "";
  if (!token) {
    return "#";
  }
  return `${window.location.origin}/api/system/backups/${encodeURIComponent(filename)}?access_token=${encodeURIComponent(token)}`;
}
</script>

<style scoped>
.runtime-workbench-page {
  padding-bottom: 24px;
}

.runtime-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.metric-card,
.scope-block,
.filter-panel,
.panel,
.detail-shell,
.ops-guide-card,
.detail-chip {
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
.scope-row span {
  color: rgba(207, 231, 255, 0.72);
}

.metric-card.healthy,
.detail-chip.healthy {
  border-color: rgba(92, 210, 154, 0.28);
}

.metric-card.warning {
  border-color: rgba(246, 193, 86, 0.3);
}

.metric-card.risk,
.detail-chip.risk {
  border-color: rgba(255, 102, 102, 0.34);
}

.runtime-roadmap {
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

.runtime-left-rail,
.runtime-center,
.runtime-right-rail {
  display: grid;
  gap: 12px;
  min-height: 0;
}

.scope-block,
.filter-panel,
.panel,
.detail-shell {
  border-radius: 20px;
  padding: 16px;
}

.side-head,
.list-toolbar,
.table-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.side-head strong,
.list-toolbar h3,
.table-head strong {
  color: #f4fbff;
}

.side-head span,
.list-toolbar span,
.eyebrow,
.status-line {
  color: rgba(207, 231, 255, 0.72);
}

.scope-list,
.filter-stack,
.hint-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.scope-row,
.hint-row {
  width: 100%;
  text-align: left;
  border-radius: 16px;
  border: 1px solid rgba(111, 191, 255, 0.14);
  background: rgba(255, 255, 255, 0.03);
  padding: 12px 14px;
  display: grid;
  gap: 4px;
  color: #f4fbff;
}

.field-block {
  display: grid;
  gap: 8px;
  color: #dff2ff;
}

.field-block span {
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

.switch-row,
.action-row.wrap,
.list-actions,
.row-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
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

.table-shell {
  overflow: auto;
}

.mini-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 480px;
}

.mini-table th,
.mini-table td {
  padding: 12px 10px;
  border-bottom: 1px solid rgba(111, 191, 255, 0.1);
  color: #e9f6ff;
  vertical-align: top;
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

.danger-link {
  color: #ff7b86;
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

.advice-block {
  display: grid;
  gap: 8px;
  border-top: 1px solid rgba(111, 191, 255, 0.1);
  padding-top: 12px;
}

.advice-block strong,
.plain-list {
  color: #f4fbff;
}

.compact-list {
  display: grid;
  gap: 8px;
  padding-left: 18px;
}

@media (max-width: 1380px) {
  .runtime-metrics,
  .runtime-roadmap {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .ops-guide-strip,
  .table-pair {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 960px) {
  .runtime-metrics,
  .runtime-roadmap,
  .detail-summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
