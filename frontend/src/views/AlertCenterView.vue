<template>
  <div style="height: calc(100vh - 80px); display: flex; overflow: hidden; background: #0a0a0a;">
    <el-main style="flex: 1; height: 100%; overflow-y: auto; padding: 20px;" class="alert-main-shell">
      <div class="alert-main-stack">
        <div class="alert-slim-toolbar">
          <el-button size="small" @click="openLatestAlertAsset" :disabled="!latestAlertCandidate">定位最新异常</el-button>
          <el-button size="small" @click="openTopDeviceAsset" :disabled="!topDeviceCandidate">定位热点设备</el-button>
          <el-button size="small" @click="router.push('/assets')">进入设备资产</el-button>
          <el-button size="small" type="primary" @click="reloadAll" :loading="loading.summary || loading.list">立即刷新</el-button>
        </div>

        <div class="sleek-metric-row">
          <div class="metric-item"><span class="label">待处理</span><strong class="val text-red">{{ summary.open_count || 0 }}</strong></div>
          <div class="metric-divider"></div>
          <div class="metric-item"><span class="label">严重</span><strong class="val text-red">{{ summary.open_critical_count || 0 }}</strong></div>
          <div class="metric-divider"></div>
          <div class="metric-item"><span class="label">未恢复</span><strong class="val text-amber">{{ summary.strict_unresolved_count || 0 }}</strong></div>
          <div class="metric-divider"></div>
          <div class="metric-item"><span class="label">抖动</span><strong class="val text-blue">{{ summary.flap_watch_count || 0 }}</strong></div>
          <div class="metric-divider"></div>
          <div class="metric-item wide"><span class="label">风暴防护</span><strong class="val">{{ stormGuardLabel }}</strong></div>
          <div class="metric-divider"></div>
          <div class="metric-item wide"><span class="label">分页</span><strong class="val">{{ pagination.total_count }} / {{ pagination.page_count }}</strong></div>
        </div>

        <el-card shadow="never" class="filter-card">
          <el-form :inline="true" label-position="top" class="filter-form">
            <el-form-item label="关键词">
              <el-input
                v-model.trim="filters.q"
                placeholder="搜索标题、说明、设备、IP、区域"
                clearable
                @keyup.enter="applyFilters"
              />
            </el-form-item>

            <el-form-item label="状态">
              <el-select v-model="filters.status" placeholder="请选择" clearable>
                <el-option label="待处理" value="open" />
                <el-option label="已确认" value="acknowledged" />
                <el-option label="已恢复" value="resolved" />
              </el-select>
            </el-form-item>

            <el-form-item label="级别">
              <el-select v-model="filters.severity" placeholder="请选择" clearable>
                <el-option label="严重" value="critical" />
                <el-option label="警告" value="warning" />
                <el-option label="提示" value="info" />
              </el-select>
            </el-form-item>

            <el-form-item label="类型">
              <el-select v-model="filters.alert_type" placeholder="请选择" clearable filterable>
                <el-option
                  v-for="item in summary.type_breakdown"
                  :key="item.alert_type"
                  :label="alertTypeLabel(item.alert_type)"
                  :value="item.alert_type"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="来源">
              <el-select v-model="filters.source_type" placeholder="请选择" clearable filterable>
                <el-option
                  v-for="item in summary.source_breakdown"
                  :key="item.source_type"
                  :label="sourceLabel(item.source_type)"
                  :value="item.source_type"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="归因">
              <el-select v-model="filters.attribution_type" placeholder="请选择" clearable filterable>
                <el-option
                  v-for="item in summary.attribution_breakdown"
                  :key="item.attribution_type"
                  :label="attributionLabel(item.attribution_type)"
                  :value="item.attribution_type"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="排序字段">
              <el-select v-model="filters.sort_by" placeholder="请选择">
                <el-option label="按最后出现" value="last_seen_at" />
                <el-option label="按编号" value="id" />
                <el-option label="按级别" value="severity" />
                <el-option label="按状态" value="status" />
              </el-select>
            </el-form-item>

            <el-form-item label="排序方向">
              <el-select v-model="filters.sort_order" placeholder="请选择">
                <el-option label="降序" value="desc" />
                <el-option label="升序" value="asc" />
              </el-select>
            </el-form-item>

            <el-form-item class="filter-actions">
              <el-button type="primary" @click="applyFilters" :loading="loading.list">查询</el-button>
              <el-button @click="resetFilters">重置</el-button>
              <el-button @click="downloadCsv">导出</el-button>
              <el-button @click="focusCriticalOpen">严重待处理</el-button>
              <el-button @click="focusFlapWatch">抖动观察</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" class="table-card">
          <div class="table-toolbar">
            <div class="toolbar-copy">
              <strong>{{ selectionSummary }}</strong>
              <span>{{ actionGuide }}</span>
            </div>
            <div class="toolbar-actions">
              <el-button @click="handleBulk('acknowledge')" :disabled="!selectedAlertIds.length || !canManage">批量确认</el-button>
              <el-button @click="handleBulk('resolve')" :disabled="!selectedAlertIds.length || !canManage">批量恢复</el-button>
              <el-button type="danger" plain @click="handleBulk('delete')" :disabled="!selectedAlertIds.length || !canManage">批量删除</el-button>
            </div>
          </div>

          <el-alert
            :title="actionMessage"
            type="info"
            :closable="false"
            show-icon
            class="message-strip"
          />

          <div class="table-shell">
            <el-table
              :data="alerts"
              :max-height="tableMaxHeight"
              v-loading="loading.list"
              row-key="id"
              border
              stripe
              style="width: 100%"
              @selection-change="handleSelectionChange"
            >
              <el-table-column type="selection" width="52" />

              <el-table-column label="标题 / 说明" min-width="340">
                <template #default="{ row }">
                  <div class="cell-stack">
                    <strong>{{ row.title }}</strong>
                    <span class="muted">{{ row.message || row.evidence_summary || "-" }}</span>
                  </div>
                </template>
              </el-table-column>

              <el-table-column label="来源" min-width="140">
                <template #default="{ row }">
                  <el-tag effect="plain">{{ sourceLabel(row.source_type) }}</el-tag>
                </template>
              </el-table-column>

              <el-table-column label="类型" min-width="160">
                <template #default="{ row }">
                  <el-tag effect="plain" type="info">{{ alertTypeLabel(row.alert_type) }}</el-tag>
                </template>
              </el-table-column>

              <el-table-column label="级别" width="100">
                <template #default="{ row }">
                  <el-tag :type="severityTagType(row.severity)">{{ severityLabel(row.severity) }}</el-tag>
                </template>
              </el-table-column>

              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
                </template>
              </el-table-column>

              <el-table-column label="影响对象" min-width="220">
                <template #default="{ row }">
                  <div class="cell-stack">
                    <strong>{{ row.device_label || row.asset_device_id || "-" }}</strong>
                    <span class="muted">{{ row.management_ip || "-" }}</span>
                    <el-button
                      v-if="row.asset_device_id || row.management_ip"
                      link
                      type="primary"
                      @click="locateAsset(row)"
                    >
                      定位设备
                    </el-button>
                  </div>
                </template>
              </el-table-column>

              <el-table-column prop="area_display_name" label="区域" min-width="160" show-overflow-tooltip />

              <el-table-column label="归因" min-width="190">
                <template #default="{ row }">
                  <div class="cell-stack">
                    <el-tag effect="plain">{{ attributionLabel(row.attribution_type) }}</el-tag>
                    <span v-if="attributionHint(row.attribution_type)" class="muted">
                      {{ attributionHint(row.attribution_type) }}
                    </span>
                  </div>
                </template>
              </el-table-column>

              <el-table-column label="最后出现" width="160">
                <template #default="{ row }">
                  {{ formatTime(row.last_seen_at) }}
                </template>
              </el-table-column>

              <el-table-column label="工单" width="140" fixed="right">
                <template #default="{ row }">
                  <div class="cell-stack">
                    <span v-if="row.linked_work_order_id">
                      #{{ row.linked_work_order_id }} {{ row.linked_work_order_title || "已关联" }}
                    </span>
                    <button 
                      v-else-if="canCreateOrder(row)" 
                      class="cyber-dispatch-btn"
                      @click="createOrder(row)"
                    >
                      <span class="icon">⚡</span> 闪电转派
                    </button>
                    <span v-else class="muted">-</span>
                  </div>
                </template>
              </el-table-column>

              <el-table-column label="移动调度" width="100" fixed="right">
                <template #default="{ row }">
                  <div class="cell-stack">
                    <span>{{ row.linked_dispatch_count || 0 }} 次</span>
                    <el-button v-if="canDispatchMobile(row)" link type="primary" @click="sendToMobile(row)">转移动端</el-button>
                  </div>
                </template>
              </el-table-column>

              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <div class="row-actions">
                    <el-button link type="primary" :disabled="!canManage" @click="handleSingle('acknowledge', row)">确认</el-button>
                    <el-button link type="success" :disabled="!canManage" @click="handleSingle('resolve', row)">恢复</el-button>
                    <el-button link type="danger" :disabled="!canManage" @click="handleSingle('delete', row)">删除</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <div class="pagination-wrap">
            <el-pagination
              v-model:current-page="pagination.page"
              v-model:page-size="pagination.page_size"
              background
              layout="total, sizes, prev, pager, next, jumper"
              :total="pagination.total_count"
              :page-sizes="[20, 50, 100]"
              @current-change="handlePageChange"
              @size-change="handleSizeChange"
            />
          </div>
        </el-card>
      </div>
    </el-main>

    <el-aside style="width: 400px; height: 100%; overflow-y: auto; position: relative; border-left: 1px solid #333;" class="alert-side-shell">
      <div class="side-stack">
        <el-card shadow="never" class="side-glass-card">
          <template #header>
            <div class="side-card-head">
              <strong>大面积异常诊断</strong>
              <el-tag :type="stormGuardTagType">{{ stormGuardLabel }}</el-tag>
            </div>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="观察窗口">{{ summary.storm_guard?.lookback_minutes || 0 }} 分钟</el-descriptions-item>
            <el-descriptions-item label="有效告警">{{ summary.storm_guard?.recent_actionable_count || 0 }} 条</el-descriptions-item>
            <el-descriptions-item label="涉及设备">{{ summary.storm_guard?.distinct_device_count || 0 }} 台</el-descriptions-item>
            <el-descriptions-item label="涉及区域">{{ summary.storm_guard?.distinct_area_count || 0 }} 个</el-descriptions-item>
            <el-descriptions-item label="涉及来源">{{ summary.storm_guard?.distinct_source_count || 0 }} 类</el-descriptions-item>
            <el-descriptions-item label="判断说明">{{ summary.storm_guard?.reason || "-" }}</el-descriptions-item>
          </el-descriptions>
          <el-alert
            v-if="summary.storm_guard?.recommendations?.length"
            :title="summary.storm_guard.recommendations.join('；')"
            type="warning"
            :closable="false"
            show-icon
            class="inline-alert"
          />
        </el-card>

        <el-card shadow="never" class="side-glass-card">
          <template #header>
            <div class="side-card-head">
              <strong>热点设备</strong>
              <span class="muted">{{ summary.top_open_devices.length }} 项</span>
            </div>
          </template>
          <el-empty v-if="!summary.top_open_devices.length" description="当前没有明显热点设备" :image-size="80" />
          <div v-else class="device-list">
            <el-card
              v-for="item in summary.top_open_devices"
              :key="`${item.device_label}-${item.management_ip}`"
              shadow="hover"
              class="device-item side-glass-card nested-side-card"
            >
              <div class="cell-stack">
                <strong>{{ item.device_label }}</strong>
                <span class="muted">{{ item.management_ip || "-" }} / {{ deviceTypeLabel(item.device_type) }} / {{ item.count }} 条</span>
                <div>
                  <el-button link type="primary" @click="locateTopDevice(item)">定位设备</el-button>
                  <el-button link @click="applyDeviceKeyword(item)">筛到相关告警</el-button>
                </div>
              </div>
            </el-card>
          </div>
        </el-card>

        <el-card shadow="never" class="side-glass-card">
          <template #header>
            <div class="side-card-head">
              <strong>防护参数</strong>
              <el-button text @click="reloadGuardSettings">重载参数</el-button>
            </div>
          </template>
          <el-form label-position="top">
            <el-form-item label="观察窗口(分钟)">
              <el-input-number v-model="guardSettings.lookback_minutes" :min="3" :max="60" class="full-width" />
            </el-form-item>
            <el-form-item label="大面积最小事件数">
              <el-input-number v-model="guardSettings.min_events" :min="3" :max="500" class="full-width" />
            </el-form-item>
            <el-form-item label="大面积最小设备数">
              <el-input-number v-model="guardSettings.min_devices" :min="1" :max="500" class="full-width" />
            </el-form-item>
            <el-form-item label="大面积最小区域数">
              <el-input-number v-model="guardSettings.min_areas" :min="1" :max="50" class="full-width" />
            </el-form-item>
            <el-form-item label="大面积最小来源数">
              <el-input-number v-model="guardSettings.min_sources" :min="1" :max="20" class="full-width" />
            </el-form-item>
            <el-form-item label="观察态最小设备数">
              <el-input-number v-model="guardSettings.watch_device_threshold" :min="1" :max="500" class="full-width" />
            </el-form-item>
            <el-form-item label="排除网络抖动观察">
              <el-switch v-model="guardSettings.exclude_flap_watch" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :disabled="!canManage" @click="saveGuardSettings">保存参数</el-button>
            </el-form-item>
          </el-form>
          <el-alert :title="guardMessage" type="info" :closable="false" show-icon />
        </el-card>

        <el-card shadow="never" class="side-glass-card">
          <template #header>
            <div class="side-card-head">
              <strong>历史清理</strong>
              <el-tag type="danger" effect="plain">管理员</el-tag>
            </div>
          </template>
          <el-form label-position="top">
            <el-form-item label="清理状态">
              <el-select v-model="cleanup.status" placeholder="请选择">
                <el-option :label="`清理${statusLabel('resolved')}`" value="resolved" />
                <el-option :label="`清理${statusLabel('acknowledged')}`" value="acknowledged" />
                <el-option :label="`清理${statusLabel('open')}`" value="open" />
              </el-select>
            </el-form-item>
            <el-form-item label="保留天数">
              <el-input-number v-model="cleanup.keep_days" :min="1" :max="3650" class="full-width" />
            </el-form-item>
            <el-form-item label="仅预演">
              <el-switch v-model="cleanup.dry_run" />
            </el-form-item>
            <el-form-item>
              <el-button type="danger" :disabled="!canCleanup" @click="cleanupHistory">执行历史清理</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </div>
    </el-aside>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import {
  bulkActionAlerts,
  cleanupAlerts,
  createMobileDispatchFromAlert,
  createWorkOrderFromAlert,
  exportAlertsCsv,
  fetchAlertGuardSettings,
  fetchAlertSummary,
  fetchAlerts,
  updateAlertGuardSettings,
} from "../api/client";
import { authState } from "../state/auth";

const router = useRouter();

const alerts = ref([]);
const selectedRows = ref([]);
const loading = reactive({
  summary: false,
  list: false,
  guard: false,
});

const filters = reactive({
  q: "",
  status: "",
  alert_type: "",
  severity: "",
  source_type: "",
  attribution_type: "",
  sort_by: "last_seen_at",
  sort_order: "desc",
});

const pagination = reactive({
  page: 1,
  page_size: 20,
  total_count: 0,
  page_count: 1,
});

const cleanup = reactive({
  status: "resolved",
  keep_days: 30,
  dry_run: false,
});

const summary = reactive({
  open_count: 0,
  resolved_count: 0,
  open_critical_count: 0,
  flap_watch_count: 0,
  strict_unresolved_count: 0,
  severity_breakdown: [],
  type_breakdown: [],
  status_breakdown: [],
  source_breakdown: [],
  attribution_breakdown: [],
  scope_breakdown: [],
  latest_open_alerts: [],
  top_open_areas: [],
  top_open_devices: [],
  open_source_breakdown: [],
  storm_guard: {
    level: "normal",
    label: "正常",
    suppression_active: false,
    recent_actionable_count: 0,
    distinct_device_count: 0,
    distinct_area_count: 0,
    distinct_source_count: 0,
    recommendations: [],
    top_sources: [],
    lookback_minutes: 0,
    reason: "",
  },
});

const guardSettings = reactive({
  lookback_minutes: 10,
  min_events: 12,
  min_devices: 8,
  min_areas: 3,
  min_sources: 2,
  watch_device_threshold: 5,
  exclude_flap_watch: true,
  updated_at: null,
  config_path: "",
});

const actionMessage = ref("先筛到区域、设备或类型，再做批量确认、恢复、导出或历史清理。");
const guardMessage = ref("建议先保守调参，观察一轮现场数据后再逐步收紧。");

const canManage = computed(() => ["admin", "manager"].includes(authState.user?.role || ""));
const canCleanup = computed(() => authState.user?.role === "admin");
const selectedAlertIds = computed(() => selectedRows.value.map((item) => item.id));
const stormGuardLabel = computed(() => summary.storm_guard?.label || "正常");
const latestAlertCandidate = computed(() => summary.latest_open_alerts?.[0] || alerts.value[0] || null);
const topDeviceCandidate = computed(() => summary.top_open_devices?.[0] || null);
const tableMaxHeight = "calc(100vh - 350px)";

const selectionSummary = computed(() => {
  if (!selectedAlertIds.value.length) {
    return "当前未选中告警";
  }
  return `已选中 ${selectedAlertIds.value.length} 条告警`;
});

const actionGuide = computed(() => {
  if (selectedAlertIds.value.length) {
    return "可以直接批量确认、恢复或删除，处理后建议回看热点设备与最新异常。";
  }
  if ((summary.open_critical_count || 0) > 0) {
    return "先处理严重待处理告警，优先定位设备，再决定确认、恢复或派工。";
  }
  if ((summary.open_count || 0) > 0) {
    return "先用筛选锁定区域、来源或类型，再进入批量处置。";
  }
  return "当前没有待处理告警，可以导出历史结果或执行预演清理。";
});

onMounted(async () => {
  try {
    await Promise.all([reloadGuardSettings(), refreshSummary()]);
    await loadAlerts();
  } catch (error) {
    console.error(error);
    actionMessage.value = "告警中心初始化失败，请检查后端服务。";
    ElMessage.error(actionMessage.value);
  }
});

async function refreshSummary() {
  loading.summary = true;
  try {
    Object.assign(summary, await fetchAlertSummary());
  } finally {
    loading.summary = false;
  }
}

async function reloadGuardSettings() {
  loading.guard = true;
  try {
    Object.assign(guardSettings, await fetchAlertGuardSettings());
  } finally {
    loading.guard = false;
  }
}

async function loadAlerts() {
  loading.list = true;
  try {
    const data = await fetchAlerts({
      q: filters.q || undefined,
      status: filters.status || undefined,
      alert_type: filters.alert_type || undefined,
      severity: filters.severity || undefined,
      source_type: filters.source_type || undefined,
      attribution_type: filters.attribution_type || undefined,
      sort_by: filters.sort_by || "last_seen_at",
      sort_order: filters.sort_order || "desc",
      page: pagination.page,
      page_size: pagination.page_size,
    });
    alerts.value = data.items || [];
    pagination.total_count = data.total_count || 0;
    pagination.page = data.page || pagination.page;
    pagination.page_size = data.page_size || pagination.page_size;
    pagination.page_count = data.page_count || 1;
    selectedRows.value = selectedRows.value.filter((row) => alerts.value.some((item) => item.id === row.id));
  } finally {
    loading.list = false;
  }
}

async function reloadAll() {
  await Promise.all([refreshSummary(), loadAlerts()]);
}

async function applyFilters() {
  pagination.page = 1;
  await loadAlerts();
}

function resetFilters() {
  filters.q = "";
  filters.status = "";
  filters.alert_type = "";
  filters.severity = "";
  filters.source_type = "";
  filters.attribution_type = "";
  filters.sort_by = "last_seen_at";
  filters.sort_order = "desc";
  pagination.page = 1;
  loadAlerts();
}

function focusCriticalOpen() {
  filters.q = "";
  filters.status = "open";
  filters.alert_type = "";
  filters.severity = "critical";
  filters.source_type = "";
  filters.attribution_type = "";
  filters.sort_by = "last_seen_at";
  filters.sort_order = "desc";
  pagination.page = 1;
  actionMessage.value = "已筛到严重待处理告警。";
  loadAlerts();
}

function focusFlapWatch() {
  filters.q = "";
  filters.status = "open";
  filters.alert_type = "device_flapping";
  filters.severity = "";
  filters.source_type = "";
  filters.attribution_type = "network_flap_watch";
  filters.sort_by = "last_seen_at";
  filters.sort_order = "desc";
  pagination.page = 1;
  actionMessage.value = "已筛到网络抖动观察告警。";
  loadAlerts();
}

function handleSelectionChange(rows) {
  selectedRows.value = rows;
}

async function handleSingle(action, item) {
  await runBulk(action, [item.id]);
}

async function handleBulk(action) {
  await runBulk(action, selectedAlertIds.value);
}

async function runBulk(action, ids) {
  if (!ids?.length) {
    ElMessage.warning("请先勾选需要处理的告警。");
    return;
  }

  if (action === "delete") {
    await ElMessageBox.confirm(`确认删除选中的 ${ids.length} 条告警吗？`, "删除确认", {
      type: "warning",
      confirmButtonText: "确认删除",
      cancelButtonText: "取消",
    });
  }

  try {
    const result = await bulkActionAlerts(action, ids);
    selectedRows.value = [];
    actionMessage.value = `批量${actionLabel(action)}完成：处理 ${result.affected} 条，跳过 ${result.skipped} 条。`;
    ElMessage.success(actionMessage.value);
    await Promise.all([refreshSummary(), loadAlerts()]);
  } catch (error) {
    if (error !== "cancel") {
      console.error(error);
      actionMessage.value = `批量${actionLabel(action)}失败，请检查权限或后端日志。`;
      ElMessage.error(actionMessage.value);
    }
  }
}

async function downloadCsv() {
  try {
    const blob = await exportAlertsCsv({
      q: filters.q || undefined,
      status: filters.status || undefined,
      alert_type: filters.alert_type || undefined,
      severity: filters.severity || undefined,
      source_type: filters.source_type || undefined,
      attribution_type: filters.attribution_type || undefined,
      sort_by: filters.sort_by || "last_seen_at",
      sort_order: filters.sort_order || "desc",
    });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = `告警中心-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
    link.click();
    URL.revokeObjectURL(href);
    ElMessage.success("告警导出成功。");
  } catch (error) {
    console.error(error);
    ElMessage.error("导出失败，请检查后端服务。");
  }
}

async function saveGuardSettings() {
  if (!canManage.value) {
    guardMessage.value = "当前账号没有修改防护参数的权限。";
    ElMessage.warning(guardMessage.value);
    return;
  }

  try {
    Object.assign(
      guardSettings,
      await updateAlertGuardSettings({
        lookback_minutes: guardSettings.lookback_minutes,
        min_events: guardSettings.min_events,
        min_devices: guardSettings.min_devices,
        min_areas: guardSettings.min_areas,
        min_sources: guardSettings.min_sources,
        watch_device_threshold: guardSettings.watch_device_threshold,
        exclude_flap_watch: guardSettings.exclude_flap_watch,
      }),
    );
    guardMessage.value = "防护参数已保存。";
    ElMessage.success(guardMessage.value);
    await refreshSummary();
  } catch (error) {
    console.error(error);
    guardMessage.value = "保存防护参数失败，请查看后端日志。";
    ElMessage.error(guardMessage.value);
  }
}

async function cleanupHistory() {
  if (!cleanup.keep_days || Number(cleanup.keep_days) < 1) {
    ElMessage.warning("请先填写有效的保留天数（>=1）。");
    return;
  }

  const keepDays = Math.min(Math.max(Number(cleanup.keep_days) || 30, 1), 3650);
  const status = cleanup.status || "resolved";
  const statusText = statusLabel(status);
  const dryRun = !!cleanup.dry_run;

  try {
    await ElMessageBox.confirm(
      dryRun
        ? `将试运行清理：状态 ${statusText}，保留 ${keepDays} 天，确认继续？`
        : `将清理 ${keepDays} 天前状态为 ${statusText} 的告警，确认继续？`,
      "历史清理确认",
      {
        type: "warning",
        confirmButtonText: dryRun ? "执行预演" : "确认清理",
        cancelButtonText: "取消",
      },
    );

    const result = await cleanupAlerts({
      keep_days: keepDays,
      status,
      dry_run: dryRun,
    });

    if (dryRun) {
      actionMessage.value = `预演完成：匹配 ${result.matched} 条${statusText}告警，未执行删除。`;
    } else {
      actionMessage.value = `历史清理完成：删除 ${result.deleted} 条${statusText}告警，匹配 ${result.matched} 条。`;
      await Promise.all([refreshSummary(), loadAlerts()]);
    }
    ElMessage.success(actionMessage.value);
  } catch (error) {
    if (error !== "cancel") {
      console.error(error);
      ElMessage.error("历史清理失败，请检查管理员权限和后端日志。");
    }
  }
}

async function createOrder(item) {
  try {
    // 呼叫后端 API 真实创建工单
    const result = await createWorkOrderFromAlert(item.id);
    item.linked_work_order_id = result.work_order_id;
    item.linked_work_order_title = result.work_order_title;
    
    // 弹窗提示
    ElMessage({
      message: `⚡ 告警转派成功！已生成 [WO-${1000 + result.work_order_id}]，正在跃迁至指挥枢纽...`,
      type: 'success',
      duration: 2000
    });

    await Promise.all([refreshSummary(), loadAlerts()]);

    // 🔥 核心魔法：派单成功后，0.8秒后自动跳转到咱们的赛博看板！
    setTimeout(() => {
      router.push('/work-orders');
    }, 800);

  } catch (error) {
    console.error(error);
    ElMessage.error("闪电派发失败，被中央服务器拦截，请检查日志！");
  }
}

async function sendToMobile(item) {
  try {
    const result = await createMobileDispatchFromAlert(item.id, {
      assignee_username: "",
      latest_note: `来自告警：${item.title}`,
    });
    item.linked_dispatch_count = (item.linked_dispatch_count || 0) + 1;
    actionMessage.value = `已派发到移动工作台：${result.title}`;
    ElMessage.success(actionMessage.value);
  } catch (error) {
    console.error(error);
    ElMessage.error("转移动端失败，请检查后端日志或当前权限。");
  }
}

function locateAsset(item) {
  router.push({
    path: "/assets",
    query: {
      from: "alert",
      device_id: item.asset_device_id ? String(item.asset_device_id) : undefined,
      q: item.management_ip || item.device_label || item.title || "",
    },
  });
}

function locateTopDevice(item) {
  router.push({
    path: "/assets",
    query: {
      from: "alert",
      q: item.management_ip || item.device_label || "",
    },
  });
}

function openLatestAlertAsset() {
  if (latestAlertCandidate.value) {
    locateAsset(latestAlertCandidate.value);
  }
}

function openTopDeviceAsset() {
  if (topDeviceCandidate.value) {
    locateTopDevice(topDeviceCandidate.value);
  }
}

function applyDeviceKeyword(item) {
  filters.q = item.management_ip || item.device_label || "";
  pagination.page = 1;
  loadAlerts();
}

function canCreateOrder(item) {
  return canManage.value && item.status !== "resolved";
}

function canDispatchMobile(item) {
  return ["admin", "manager", "technician"].includes(authState.user?.role || "") && item.status !== "resolved";
}

function handlePageChange() {
  loadAlerts();
}

function handleSizeChange() {
  pagination.page = 1;
  loadAlerts();
}

function severityTagType(value) {
  return {
    critical: "danger",
    warning: "warning",
    info: "info",
  }[value] || "info";
}

function statusTagType(value) {
  return {
    open: "danger",
    acknowledged: "warning",
    resolved: "success",
  }[value] || "info";
}

const stormGuardTagType = computed(() => {
  return {
    suppressed: "danger",
    watch: "warning",
    normal: "success",
  }[summary.storm_guard?.level || "normal"] || "info";
});

function actionLabel(action) {
  return {
    acknowledge: "确认",
    resolve: "恢复",
    delete: "删除",
  }[action] || action;
}

function sourceLabel(value) {
  return (
    {
      legacy_ops: "旧系统桥接",
      jvss: "主平台 200",
      tg_cos: "TG/COS 平台",
      gateway: "网关",
      hikvision_nvr: "海康录像机",
      hikvision_decoder: "海康解码器",
      control_platform_new: "风控新平台",
      control_platform_legacy: "风控老平台",
      control_platform_electrical: "电控平台",
      cad_upload: "CAD 导入",
      alert_bridge: "告警桥接",
      unknown: "未分类来源",
    }[value] || fallbackEnumLabel(value, "待补来源")
  );
}

function alertTypeLabel(value) {
  return (
    {
      network_flap: "网络抖动",
      device_flapping: "网络抖动待观察",
      video_loss: "视频丢失",
      device_video_abnormal: "视频取流异常",
      offline: "设备离线",
      device_offline: "设备离线",
      reachable_error: "可达异常",
      observer_path_failure: "观测链路异常",
      network_segment_outage: "区域网络中断",
      device_fault: "设备故障",
      legacy_alert: "历史告警",
      global_outage_watch: "大面积异常观察",
      global_outage_suppressed: "大面积异常抑制",
      stream_probe_failed: "取流探测异常",
      switch_probe_failed: "交换机探测异常",
      platform_sync_abnormal: "平台同步异常",
      unknown: "未识别类型",
    }[value] || fallbackEnumLabel(value, "待补类型")
  );
}

function severityLabel(value) {
  return (
    {
      critical: "严重",
      warning: "警告",
      info: "提示",
      unknown: "待补级别",
    }[value] || fallbackEnumLabel(value, "待补级别")
  );
}

function statusLabel(value) {
  return (
    {
      open: "待处理",
      acknowledged: "已确认",
      resolved: "已恢复",
      unknown: "待补状态",
    }[value] || fallbackEnumLabel(value, "待补状态")
  );
}

function attributionLabel(value) {
  return (
    {
      legacy_bridge: "旧系统桥接",
      network_flap_watch: "网络抖动观察",
      manual_review: "人工复核",
      topology_inferred: "拓扑归因",
      device_unreachable: "设备不可达",
      switch_probe: "交换机探测归因",
      observer_probe: "观测链路归因",
      stream_probe: "取流探测归因",
      unknown: "待补归因",
      global_outage_watch: "大面积异常观察",
      global_outage_suppressed: "大面积异常抑制",
    }[value] || fallbackEnumLabel(value, "待补归因")
  );
}

function attributionHint(value) {
  return (
    {
      legacy_bridge: "来源于旧系统同步",
      network_flap_watch: "短时恢复，默认不计入严格故障",
      manual_review: "等待人工确认",
      topology_inferred: "根据链路与归属关系推断",
      device_unreachable: "IP/取流均异常",
      global_outage_watch: "疑似区域或主干异常",
      global_outage_suppressed: "已进入大面积异常保护",
    }[value] || ""
  );
}

function deviceTypeLabel(value) {
  return (
    {
      camera: "摄像头",
      switch: "交换机",
      gateway: "网关",
      nvr: "录像机",
      decoder: "解码器",
      server: "服务器",
      unknown: "未分类设备",
    }[value] || fallbackEnumLabel(value, "未分类设备")
  );
}

function fallbackEnumLabel(value, emptyLabel = "-") {
  const text = String(value || "").trim();
  if (!text) return emptyLabel;
  if (/[\u4e00-\u9fff]/.test(text)) return text;
  return emptyLabel;
}

function formatTime(value) {
  if (!value) return "-";
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? value : dt.toLocaleString("zh-CN", { hour12: false });
}
</script>

<style scoped>
.alert-main-shell,
.alert-main-stack,
.alert-side-shell,
.side-stack,
.table-card,
.table-shell {
  min-width: 0;
  min-height: 0;
}

.alert-main-stack {
  display: grid;
  gap: 16px;
}

.alert-slim-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-card,
.table-card,
.summary-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);
}

.filter-card :deep(.el-card__body),
.table-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.page-header,
.side-card-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: flex-start;
  gap: 16px;
}

.table-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.page-title h2 {
  margin: 4px 0 8px;
}

.page-title p,
.page-kicker,
.muted {
  color: rgba(255, 255, 255, 0.68);
}

.page-title h2,
.toolbar-copy strong,
.summary-custom strong,
.cell-stack strong,
.side-card-head strong {
  color: #f3f7fb;
}

.page-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  color: #8ec5ff;
}

.page-actions,
.toolbar-actions,
.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.alert-side-shell {
  flex: 0 0 400px;
  padding: 20px 16px;
}

.summary-card {
  height: 100%;
}

.summary-custom {
  display: grid;
  gap: 8px;
  min-height: 76px;
  color: var(--el-text-color-primary);
}

.summary-custom strong {
  font-size: 20px;
  line-height: 1.4;
}

.filter-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 4px 12px;
}

.filter-actions {
  grid-column: 1 / -1;
  margin-left: 0;
}

.toolbar-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.message-strip {
  margin-bottom: 16px;
}

.table-card {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.table-shell {
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: auto;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 16px;
}

.cell-stack {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  overflow-x: auto;
}

.side-stack {
  display: grid;
  gap: 16px;
  align-content: start;
}

.side-glass-card {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(12px);
}

.nested-side-card {
  margin-top: 0;
}

.device-list {
  display: grid;
  gap: 12px;
}

.device-item,
.inline-alert {
  margin-top: 12px;
}

.full-width {
  width: 100%;
}

:deep(.el-card__body),
:deep(.el-card__header),
:deep(.el-form-item),
:deep(.el-table),
:deep(.el-table__inner-wrapper),
:deep(.el-table__body-wrapper),
:deep(.el-descriptions__body),
:deep(.el-pagination) {
  min-width: 0;
}

:deep(.el-table) {
  --el-table-bg-color: var(--el-bg-color);
  --el-table-tr-bg-color: var(--el-bg-color);
  --el-table-expanded-cell-bg-color: var(--el-fill-color-light);
  --el-table-header-bg-color: var(--el-fill-color-light);
  --el-table-row-hover-bg-color: var(--el-fill-color);
  --el-table-border-color: var(--el-border-color-lighter);
  --el-table-text-color: var(--el-text-color-primary);
  --el-table-header-text-color: var(--el-text-color-primary);
}

:deep(.el-table .el-table__inner-wrapper::before) {
  height: 0;
}

:deep(.el-statistic),
:deep(.el-descriptions),
:deep(.el-form),
:deep(.el-pagination) {
  color: var(--el-text-color-primary);
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper),
:deep(.el-textarea__inner) {
  background: rgba(255, 255, 255, 0.04);
}

:deep(.el-card) {
  box-shadow: none;
}

:deep(.el-descriptions__body),
:deep(.el-descriptions__table) {
  background: transparent;
}

@media (max-width: 1200px) {
  .page-header,
  .table-toolbar,
  .side-card-head {
    grid-template-columns: 1fr;
  }

  .pagination-wrap {
    justify-content: flex-start;
  }

  .page-actions,
  .toolbar-actions {
    justify-content: flex-start;
  }

  .alert-side-shell {
    flex-basis: 360px;
  }
}

@media (max-width: 768px) {
  .alert-side-shell {
    display: none;
  }

  .filter-form {
    grid-template-columns: 1fr;
  }
}

/* 🔥 闪电派单按钮专属赛博样式 */
.cyber-dispatch-btn {
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.1), rgba(245, 158, 11, 0.25));
  border: 1px solid #f59e0b;
  color: #fbbf24;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.cyber-dispatch-btn:hover {
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.3), rgba(245, 158, 11, 0.5));
  box-shadow: 0 0 12px rgba(245, 158, 11, 0.5);
  transform: scale(1.05);
}
.cyber-dispatch-btn .icon {
  font-size: 13px;
  filter: drop-shadow(0 0 4px #fbbf24);
}

/* Anti-Tofu DarkStar density pass */
.sleek-metric-row {
  display: flex;
  align-items: stretch;
  min-height: 42px;
  border: 1px solid rgba(56, 189, 248, 0.15);
  background: #080b14;
}

.metric-item {
  flex: 1 1 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  padding: 8px 12px;
}

.metric-item.wide {
  flex: 1.35 1 0;
}

.metric-item .label {
  color: rgba(148, 163, 184, 0.82);
  font-size: 11px;
  letter-spacing: 0.08em;
}

.metric-item .val {
  min-width: 0;
  overflow: hidden;
  color: #e2e8f0;
  font-size: 16px;
  font-family: Consolas, monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-divider {
  width: 1px;
  background: rgba(56, 189, 248, 0.14);
}

.text-red {
  color: #fb7185 !important;
}

.text-amber {
  color: #fbbf24 !important;
}

.text-blue {
  color: #38bdf8 !important;
}

.filter-card,
.table-card,
.summary-card,
.side-card {
  border-color: rgba(56, 189, 248, 0.15) !important;
  background: transparent !important;
  backdrop-filter: none !important;
  box-shadow: none !important;
}

.filter-card :deep(.el-card__body),
.table-card :deep(.el-card__body) {
  padding: 10px !important;
}

.alert-slim-toolbar {
  padding-bottom: 2px;
}

.alert-main-stack {
  gap: 10px;
}

.alert-main-shell :deep(.el-table) {
  --el-table-bg-color: #080b14;
  --el-table-tr-bg-color: #080b14;
  --el-table-header-bg-color: #05080f;
  --el-table-border-color: rgba(56, 189, 248, 0.13);
  font-size: 12px;
}
</style>
