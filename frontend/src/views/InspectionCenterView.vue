<template>
  <section class="page inspection-workbench-page">
    <WorkbenchShell leftWidth="300px" rightWidth="368px" maxWidth="1880px">
      <template #title>
        <div class="title-block">
          <p>INSPECTION WORKBENCH</p>
          <h2>巡检执行工作台</h2>
          <span>左边先收巡检范围，中间只保留任务主列表，右边固定承接任务编辑、结果回写和转移动执行。</span>
        </div>
      </template>

      <template #actions>
        <button class="tool-btn" @click="router.push('/work-orders')">回到工单中心</button>
        <button class="tool-btn" @click="router.push('/mobile')">进入移动工作台</button>
        <button class="tool-btn primary" :disabled="!canManageInspection" @click="prepareNewTask">新建巡检</button>
        <button class="tool-btn" @click="reload">立即刷新</button>
      </template>

      <template #summary>
        <section class="inspection-metrics">
          <article class="metric-card">
            <span>任务总数</span>
            <strong>{{ summary.total_count || 0 }}</strong>
            <small>当前完整巡检台账</small>
          </article>
          <article class="metric-card">
            <span>待执行</span>
            <strong>{{ summary.scheduled_count || 0 }}</strong>
            <small>等待排期与签到</small>
          </article>
          <article class="metric-card">
            <span>执行中</span>
            <strong>{{ summary.in_progress_count || 0 }}</strong>
            <small>现场仍在推进</small>
          </article>
          <article class="metric-card">
            <span>已完成</span>
            <strong>{{ summary.completed_count || 0 }}</strong>
            <small>进入结果沉淀</small>
          </article>
          <article class="metric-card">
            <span>逾期</span>
            <strong>{{ summary.overdue_count || 0 }}</strong>
            <small>需要优先拉回</small>
          </article>
          <article class="metric-card">
            <span>当前定位</span>
            <strong>{{ selectionTitle }}</strong>
            <small>{{ selectionMeta }}</small>
          </article>
        </section>
      </template>

      <template #roadmap>
        <section class="inspection-roadmap">
          <article class="roadmap-step">
            <span>01</span>
            <strong>收巡检范围</strong>
            <small>先按状态、关键词和最近任务收紧对象，再进入主列表定位。</small>
          </article>
          <article class="roadmap-step">
            <span>02</span>
            <strong>统一任务对象</strong>
            <small>区域巡检、网段巡检、工单复核都先落成巡检任务，不让执行动作飘散。</small>
          </article>
          <article class="roadmap-step">
            <span>03</span>
            <strong>右侧直接回写</strong>
            <small>结果、备注、负责人和状态固定在右栏完成，保证留痕一致。</small>
          </article>
          <article class="roadmap-step">
            <span>04</span>
            <strong>转移动执行</strong>
            <small>需要现场落地时直接转到移动工作台，让巡检和派工天然勾连。</small>
          </article>
        </section>
      </template>

      <template #left>
        <aside class="inspection-left-rail">
          <section class="scope-block">
            <div class="side-head">
              <strong>对象范围</strong>
              <span>{{ scopeSummary }}</span>
            </div>
            <div class="scope-list">
              <button class="scope-row" @click="focusStatus('scheduled')">
                <strong>待执行任务</strong>
                <span>{{ summary.scheduled_count || 0 }} 条等待现场执行</span>
              </button>
              <button class="scope-row" @click="focusStatus('in_progress')">
                <strong>执行中任务</strong>
                <span>{{ summary.in_progress_count || 0 }} 条现场处理中</span>
              </button>
              <button class="scope-row" @click="focusTargetType('work_order_followup')">
                <strong>工单复核</strong>
                <span>{{ workOrderFollowupCount }} 条和工单闭环直接相关</span>
              </button>
              <button class="scope-row" @click="resetFilters">
                <strong>恢复全部范围</strong>
                <span>退出筛选，回到完整巡检台账</span>
              </button>
            </div>
          </section>

          <section class="filter-panel">
            <div class="side-head">
              <strong>筛选与定位</strong>
              <span>先收范围，再点任务</span>
            </div>
            <div class="filter-stack">
              <input
                v-model.trim="filters.q"
                class="field-input"
                placeholder="搜索标题、计划、区域、负责人"
                @keyup.enter="reload"
              />
              <select v-model="filters.status" class="field-input">
                <option value="">全部状态</option>
                <option value="scheduled">待执行</option>
                <option value="in_progress">执行中</option>
                <option value="completed">已完成</option>
              </select>
              <select v-model="filters.target_type" class="field-input">
                <option value="">全部目标类型</option>
                <option value="area">区域巡检</option>
                <option value="network_segment">网络段巡检</option>
                <option value="video_platform">视频平台巡检</option>
                <option value="control_platform">控制平台巡检</option>
                <option value="work_order_followup">工单复核</option>
              </select>
              <div class="action-row wrap">
                <button class="tool-btn primary" @click="reload">立即筛选</button>
                <button class="tool-btn" @click="resetFilters">清空</button>
              </div>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>最近巡检</strong>
              <span>{{ (summary.recent_tasks || []).length }} 条</span>
            </div>
            <div class="scope-list recent-list">
              <button
                v-for="item in summary.recent_tasks || []"
                :key="item.id"
                class="scope-row recent-row"
                :class="{ active: selectedTaskId === item.id && !draftMode }"
                @click="loadItem(item)"
              >
                <strong>{{ item.title }}</strong>
                <span>{{ inspectionStatusLabel(item.status) }} / {{ item.plan_name || "未命名计划" }} / {{ item.area_name || "未归区" }}</span>
              </button>
              <p v-if="!(summary.recent_tasks || []).length" class="empty-note">最近还没有巡检留痕。</p>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>使用提示</strong>
              <span>让巡检成为执行链的一部分</span>
            </div>
            <div class="hint-list">
              <article class="hint-row">
                <strong>巡检不是孤立模块</strong>
                <span>它负责现场复核和计划检查，要和工单、移动端共享同一条执行链。</span>
              </article>
              <article class="hint-row">
                <strong>先写结果再转移动</strong>
                <span>右侧先明确巡检目标和结果摘要，再派到移动端，现场动作更清晰。</span>
              </article>
              <article class="hint-row">
                <strong>工单复核要单独看</strong>
                <span>和工单相关的巡检要能单独收出来，便于判断闭环是否真正完成。</span>
              </article>
            </div>
          </section>
        </aside>
      </template>

      <template #default>
        <section class="inspection-center">
          <article class="panel workbench-panel">
            <div class="ops-guide-strip">
              <div class="ops-guide-card">
                <span>当前范围</span>
                <strong>{{ scopeSummary }}</strong>
                <small>{{ items.length }} 条进入主列表</small>
              </div>
              <div class="ops-guide-card">
                <span>执行建议</span>
                <strong>{{ actionGuide }}</strong>
                <small>先选任务，再到右侧回写和派发</small>
              </div>
              <div class="ops-guide-card">
                <span>当前模式</span>
                <strong>{{ draftMode ? "新建草稿" : "编辑已选任务" }}</strong>
                <small>{{ draftMode ? "右侧正在准备新的巡检任务" : "右侧会跟随当前选中任务" }}</small>
              </div>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">INSPECTION LIST</p>
                <h3>巡检任务主列表</h3>
                <span>{{ items.length }} 条结果，当前选中 {{ selectionTitle }}</span>
              </div>
              <div class="list-actions">
                <button class="tool-btn" :disabled="!canDispatchMobile(selectedTaskRecord)" @click="sendToMobileSelected">转移动</button>
                <button class="tool-btn" :disabled="!selectedTaskRecord && !draftMode" @click="prepareNewTask">新建草稿</button>
              </div>
            </div>

            <div class="table-shell inspection-table-shell">
              <table class="mini-table">
                <thead>
                  <tr>
                    <th>标题</th>
                    <th>计划</th>
                    <th>状态</th>
                    <th>区域</th>
                    <th>目标类型</th>
                    <th>负责人</th>
                    <th>移动调度</th>
                    <th>更新时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in items"
                    :key="item.id"
                    :class="{ active: selectedTaskId === item.id && !draftMode }"
                    @click="loadItem(item)"
                  >
                    <td>
                      <div class="table-title-cell">
                        <strong>{{ item.title }}</strong>
                        <small>{{ item.result_summary || "等待补充巡检结果摘要" }}</small>
                      </div>
                    </td>
                    <td>{{ item.plan_name || "-" }}</td>
                    <td>{{ inspectionStatusLabel(item.status) }}</td>
                    <td>{{ item.area_name || "-" }}</td>
                    <td>{{ inspectionTargetTypeLabel(item.target_type) }}</td>
                    <td>{{ item.owner_username || "-" }}</td>
                    <td>{{ item.linked_dispatch_count || 0 }}</td>
                    <td>{{ formatDate(item.updated_at) }}</td>
                    <td>
                      <div class="table-actions">
                        <button class="ops-link" @click.stop="loadItem(item)">编辑</button>
                        <button v-if="canDispatchMobile(item)" class="ops-link primary" @click.stop="sendToMobile(item)">转移动</button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="!items.length" class="empty-shell">
              <strong>当前范围内没有巡检任务</strong>
              <span>可以清空筛选，或者右侧直接新建一条巡检任务。</span>
            </div>
          </article>
        </section>
      </template>

      <template #right>
        <aside class="inspection-right-rail">
          <section class="detail-shell">
            <div class="side-head">
              <strong>{{ draftMode ? "新建巡检任务" : "巡检详情与回写" }}</strong>
              <span>{{ draftMode ? "右侧草稿模式" : selectionTitle }}</span>
            </div>

            <div class="detail-summary-grid">
              <article class="detail-chip">
                <span>当前模式</span>
                <strong>{{ draftMode ? "新建" : "编辑" }}</strong>
              </article>
              <article class="detail-chip">
                <span>状态</span>
                <strong>{{ selectedTaskRecord ? inspectionStatusLabel(selectedTaskRecord.status) : "待填写" }}</strong>
              </article>
              <article class="detail-chip">
                <span>目标类型</span>
                <strong>{{ selectedTaskRecord ? inspectionTargetTypeLabel(selectedTaskRecord.target_type) : inspectionTargetTypeLabel(form.target_type) }}</strong>
              </article>
              <article class="detail-chip">
                <span>最后更新</span>
                <strong>{{ selectedTaskRecord ? formatDate(selectedTaskRecord.updated_at) : "新草稿" }}</strong>
              </article>
            </div>

            <div class="action-row wrap">
              <button v-if="canManageInspection" class="tool-btn primary" @click="submitForm">{{ draftMode ? "创建任务" : "保存任务" }}</button>
              <button v-if="canManageInspection" class="tool-btn" @click="prepareNewTask">新建草稿</button>
              <button class="tool-btn" :disabled="!canDispatchMobile(selectedTaskRecord)" @click="sendToMobileSelected">转移动</button>
              <button class="tool-btn" @click="router.push('/mobile')">查看移动端</button>
            </div>

            <p class="status-line">{{ actionMessage }}</p>

            <div class="form-grid">
              <label>
                <span>任务标题</span>
                <input v-model="form.title" class="field-input" placeholder="例如 VLAN 2 日常巡检" />
              </label>
              <label>
                <span>计划名称</span>
                <input v-model="form.plan_name" class="field-input" placeholder="例如 监控网络日常巡检" />
              </label>
              <label>
                <span>状态</span>
                <select v-model="form.status" class="field-input">
                  <option value="scheduled">待执行</option>
                  <option value="in_progress">执行中</option>
                  <option value="completed">已完成</option>
                </select>
              </label>
              <label>
                <span>区域</span>
                <input v-model="form.area_name" class="field-input" placeholder="例如 B2 停车场" />
              </label>
              <label>
                <span>目标类型</span>
                <select v-model="form.target_type" class="field-input">
                  <option value="area">区域巡检</option>
                  <option value="network_segment">网络段巡检</option>
                  <option value="video_platform">视频平台巡检</option>
                  <option value="control_platform">控制平台巡检</option>
                  <option value="work_order_followup">工单复核</option>
                </select>
              </label>
              <label>
                <span>负责人</span>
                <input v-model="form.owner_username" class="field-input" placeholder="例如 tech.field" />
              </label>
              <label class="full-width">
                <span>巡检结果</span>
                <textarea
                  v-model="form.result_summary"
                  class="field-input text-area"
                  rows="5"
                  placeholder="记录已发现问题、核验结论和下一步动作。"
                />
              </label>
              <label class="full-width">
                <span>备注</span>
                <textarea
                  v-model="form.notes"
                  class="field-input text-area"
                  rows="4"
                  placeholder="补充现场说明、扫码要求、图纸定位等。"
                />
              </label>
            </div>

            <div class="detail-footer">
              <strong>当前建议</strong>
              <span>{{ actionGuide }}</span>
            </div>
          </section>
        </aside>
      </template>
    </WorkbenchShell>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import WorkbenchShell from "../components/workbench/WorkbenchShell.vue";
import {
  createInspectionTask,
  createMobileDispatchFromInspection,
  fetchInspectionSummary,
  fetchInspectionTasks,
  updateInspectionTask,
} from "../api/client";
import { authState } from "../state/auth";

const router = useRouter();
const summary = ref({
  total_count: 0,
  scheduled_count: 0,
  in_progress_count: 0,
  completed_count: 0,
  overdue_count: 0,
  recent_tasks: [],
});
const items = ref([]);
const selectedTaskId = ref(null);
const editingId = ref(null);
const draftMode = ref(false);
const actionMessage = ref("先把网络、平台和控制域的例行巡检统一收进台账，后续再和移动签收、现场照片联动。");
const filters = reactive({ q: "", status: "", target_type: "" });
const form = reactive({
  title: "",
  plan_name: "",
  status: "scheduled",
  area_name: "",
  target_type: "area",
  owner_username: "",
  result_summary: "",
  notes: "",
});

const canManageInspection = computed(() => ["admin", "manager"].includes(authState.user?.role || ""));
const selectedTaskRecord = computed(() => {
  if (!selectedTaskId.value) return null;
  return items.value.find((item) => item.id === selectedTaskId.value) || summary.value.recent_tasks?.find((item) => item.id === selectedTaskId.value) || null;
});
const workOrderFollowupCount = computed(() => items.value.filter((item) => item.target_type === "work_order_followup").length);
const scopeSummary = computed(() => {
  const parts = [];
  if (filters.status) parts.push(inspectionStatusLabel(filters.status));
  if (filters.target_type) parts.push(inspectionTargetTypeLabel(filters.target_type));
  if (filters.q) parts.push(`关键词：${filters.q}`);
  return parts.length ? parts.join(" / ") : "全部巡检范围";
});
const selectionTitle = computed(() => {
  if (draftMode.value) return "新建巡检草稿";
  return selectedTaskRecord.value?.title || "暂未选择巡检任务";
});
const selectionMeta = computed(() => {
  if (draftMode.value) return "右侧正在准备新的巡检任务。";
  if (!selectedTaskRecord.value) return "先在中间主列表里选中一条巡检任务。";
  const record = selectedTaskRecord.value;
  return `${inspectionStatusLabel(record.status)} / ${inspectionTargetTypeLabel(record.target_type)} / ${record.area_name || "未归区"}`;
});
const actionGuide = computed(() => {
  if (draftMode.value) return "先明确巡检目标、区域和负责人，再决定是否立刻派到移动端执行。";
  const record = selectedTaskRecord.value;
  if (!record) return "先从中间主列表选中一条巡检任务，右侧才会进入真正的回写节奏。";
  if (record.status === "scheduled") return "建议先补齐计划、负责人和执行范围，再派到移动端现场签到。";
  if (record.status === "in_progress") return "建议及时补写巡检结果摘要，避免现场做完但系统没有留痕。";
  return "当前巡检已经完成，建议再核对结果说明是否足够支撑后续复盘。";
});

onMounted(async () => {
  await reload();
});

watch(
  () => [filters.q, filters.status, filters.target_type],
  async () => {
    await reloadItems();
  },
);

async function reload() {
  summary.value = await fetchInspectionSummary();
  await reloadItems();
}

async function reloadItems() {
  items.value = await fetchInspectionTasks({ q: filters.q, status: filters.status, target_type: filters.target_type });
  if (draftMode.value) return;
  if (selectedTaskId.value) {
    const matched = items.value.find((item) => item.id === selectedTaskId.value);
    if (matched) {
      syncFormFromItem(matched);
      return;
    }
  }
  if (items.value.length) {
    loadItem(items.value[0], true);
  } else {
    selectedTaskId.value = null;
    editingId.value = null;
    clearForm();
  }
}

function clearForm() {
  form.title = "";
  form.plan_name = "";
  form.status = "scheduled";
  form.area_name = "";
  form.target_type = "area";
  form.owner_username = "";
  form.result_summary = "";
  form.notes = "";
}

function syncFormFromItem(item) {
  form.title = item.title;
  form.plan_name = item.plan_name || "";
  form.status = item.status;
  form.area_name = item.area_name || "";
  form.target_type = item.target_type || "area";
  form.owner_username = item.owner_username || "";
  form.result_summary = item.result_summary || "";
  form.notes = item.notes || "";
}

function loadItem(item, silent = false) {
  draftMode.value = false;
  selectedTaskId.value = item.id;
  editingId.value = item.id;
  syncFormFromItem(item);
  if (!silent) {
    actionMessage.value = `已切到巡检任务 #${item.id}，可以在右侧继续回写、补结果或转移动。`;
  }
}

function prepareNewTask() {
  draftMode.value = true;
  selectedTaskId.value = null;
  editingId.value = null;
  clearForm();
  actionMessage.value = "已切换到新建巡检任务模式。";
}

async function submitForm() {
  try {
    const payload = { ...form };
    if (editingId.value && !draftMode.value) {
      await updateInspectionTask(editingId.value, payload);
      actionMessage.value = "巡检任务已更新。";
    } else {
      await createInspectionTask(payload);
      draftMode.value = false;
      actionMessage.value = "巡检任务已创建。";
    }
    await reload();
  } catch (error) {
    console.error(error);
    actionMessage.value = "巡检任务保存失败，请检查权限或后端日志。";
  }
}

async function sendToMobile(item) {
  try {
    const result = await createMobileDispatchFromInspection(item.id, {
      assignee_username: item.owner_username || "",
      latest_note: `来自巡检：${item.title}`,
    });
    item.linked_dispatch_count = (item.linked_dispatch_count || 0) + 1;
    actionMessage.value = `已派发到移动工作台：${result.title}`;
  } catch (error) {
    console.error(error);
    actionMessage.value = "巡检转移动失败，请稍后重试。";
  }
}

async function sendToMobileSelected() {
  if (!selectedTaskRecord.value) return;
  await sendToMobile(selectedTaskRecord.value);
}

function resetFilters() {
  filters.q = "";
  filters.status = "";
  filters.target_type = "";
  actionMessage.value = "已恢复完整巡检范围。";
}

function focusStatus(status) {
  filters.status = status;
}

function focusTargetType(type) {
  filters.target_type = type;
}

function canDispatchMobile(item) {
  if (!item) return false;
  return ["admin", "manager", "technician"].includes(authState.user?.role || "") && item.status !== "completed";
}

function formatDate(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return value;
  }
}

function inspectionStatusLabel(value) {
  return {
    scheduled: "待执行",
    in_progress: "执行中",
    completed: "已完成",
    overdue: "已逾期",
  }[value] || value || "-";
}

function inspectionTargetTypeLabel(value) {
  return {
    area: "区域巡检",
    network_segment: "网络段巡检",
    video_platform: "视频平台巡检",
    control_platform: "控制平台巡检",
    work_order_followup: "工单复核",
  }[value] || value || "-";
}
</script>

<style scoped>
.inspection-workbench-page {
  padding-bottom: 24px;
}

.inspection-metrics {
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
.scope-row span,
.detail-footer span {
  color: rgba(207, 231, 255, 0.72);
}

.inspection-roadmap {
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

.inspection-left-rail,
.inspection-center,
.inspection-right-rail {
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
.eyebrow,
.empty-note,
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

.scope-row.active {
  border-color: rgba(111, 191, 255, 0.42);
  background: linear-gradient(180deg, rgba(24, 75, 115, 0.52), rgba(14, 43, 70, 0.4));
}

.recent-list {
  max-height: 280px;
  overflow: auto;
}

.field-input {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(111, 191, 255, 0.16);
  background: rgba(255, 255, 255, 0.04);
  color: #f4fbff;
  padding: 12px 14px;
}

.action-row.wrap,
.list-actions {
  display: flex;
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

.inspection-table-shell {
  margin-top: 14px;
  overflow: auto;
}

.mini-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 960px;
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

.table-title-cell {
  display: grid;
  gap: 4px;
}

.table-title-cell strong {
  color: #f4fbff;
}

.table-title-cell small {
  color: rgba(207, 231, 255, 0.68);
}

.table-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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

.empty-shell {
  display: grid;
  gap: 6px;
  justify-items: center;
  padding: 24px 12px 8px;
  color: rgba(207, 231, 255, 0.72);
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

.full-width {
  grid-column: 1 / -1;
}

.text-area {
  resize: vertical;
  min-height: 108px;
}

.detail-footer {
  display: grid;
  gap: 4px;
  border-top: 1px solid rgba(111, 191, 255, 0.1);
  padding-top: 12px;
}

.detail-footer strong {
  color: #f4fbff;
}

@media (max-width: 1380px) {
  .inspection-metrics,
  .inspection-roadmap {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .ops-guide-strip {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 960px) {
  .inspection-metrics,
  .inspection-roadmap,
  .detail-summary-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
