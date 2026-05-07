<template>
  <section class="page user-workbench-page">
    <WorkbenchShell leftWidth="300px" rightWidth="372px" maxWidth="1880px">
      <template #actions>
        <button class="tool-btn" @click="reload">刷新状态</button>
        <button class="tool-btn" :disabled="!canApproveUsers || !pendingCandidate" @click="approveAccountAction(pendingCandidate)">开通待审批</button>
        <button class="tool-btn" @click="resetFilters">恢复默认</button>
        <button class="tool-btn primary" :disabled="!canManageUsers" @click="prepareNewAccount">新建账号</button>
      </template>

      <template #left>
        <aside class="user-left-rail">
          <section class="scope-block">
            <div class="side-head">
              <strong>对象范围</strong>
              <span>{{ scopeSummary }}</span>
            </div>
            <div class="scope-list">
              <button class="scope-row" @click="focusStatus('pending')">
                <strong>待审批账号</strong>
                <span>{{ summary.pending_count || 0 }} 个等待开通</span>
              </button>
              <button class="scope-row" @click="focusStatus('active')">
                <strong>已启用账号</strong>
                <span>{{ summary.active_count || 0 }} 个正在使用</span>
              </button>
              <button class="scope-row" @click="focusRole('technician')">
                <strong>维修人员</strong>
                <span>{{ technicianCount }} 个现场执行账号</span>
              </button>
              <button class="scope-row" @click="resetFilters">
                <strong>恢复全部范围</strong>
                <span>退出筛选，回到完整账号台账</span>
              </button>
            </div>
          </section>

          <section class="filter-panel">
            <div class="side-head">
              <strong>筛选与定位</strong>
              <span>先收范围，再点账号</span>
            </div>
            <div class="filter-stack">
              <input v-model.trim="filters.q" class="field-input" placeholder="搜索登录名、姓名、部门、手机" @keyup.enter="loadAccounts" />
              <select v-model="filters.role" class="field-input">
                <option value="">全部角色</option>
                <option value="admin">管理员</option>
                <option value="manager">值班主管</option>
                <option value="technician">维修人员</option>
                <option value="viewer">只读人员</option>
              </select>
              <select v-model="filters.status" class="field-input">
                <option value="">全部状态</option>
                <option value="pending">待审批</option>
                <option value="active">已启用</option>
                <option value="disabled">已停用</option>
              </select>
              <div class="action-row wrap">
                <button class="tool-btn primary" @click="loadAccounts">立即筛选</button>
                <button class="tool-btn" @click="resetFilters">清空</button>
              </div>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>角色能力矩阵</strong>
              <span>{{ roleMatrix.length }} 类</span>
            </div>
            <div class="scope-list recent-list">
              <article v-for="item in roleMatrix" :key="item.role" class="hint-row">
                <strong>{{ roleLabel(item.role) }}</strong>
                <span>{{ item.capabilities.join(" / ") }}</span>
              </article>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>近期账号变更</strong>
              <span>{{ (summary.recent_accounts || []).length }} 条</span>
            </div>
            <div class="scope-list recent-list">
              <button
                v-for="item in summary.recent_accounts || []"
                :key="item.id"
                class="scope-row recent-row"
                :class="{ active: selectedAccountId === item.id && !draftMode }"
                @click="loadAccount(item)"
              >
                <strong>{{ item.display_name }}</strong>
                <span>{{ item.username }} / {{ roleLabel(item.role) }} / {{ accountStatusLabel(item.status) }}</span>
              </button>
              <p v-if="!(summary.recent_accounts || []).length" class="empty-note">最近还没有账号变更记录。</p>
            </div>
          </section>
        </aside>
      </template>

      <template #default>
        <section class="user-center">
          <article class="panel workbench-panel">
            <div class="ops-guide-strip">
              <div class="ops-guide-card">
                <span>当前登录身份</span>
                <strong>{{ currentUser?.display_name || "-" }}</strong>
                <small>{{ roleLabel(currentUser?.role) }} / {{ accountStatusLabel(currentUser?.status) }}</small>
              </div>
              <div class="ops-guide-card">
                <span>执行建议</span>
                <strong>{{ actionGuide }}</strong>
                <small>先选账号，再在右侧做审批、编辑或口令操作</small>
              </div>
              <div class="ops-guide-card">
                <span>当前模式</span>
                <strong>{{ draftMode ? "新建草稿" : "编辑已选账号" }}</strong>
                <small>{{ draftMode ? "右侧正在准备新账号" : "右侧会跟随当前选中账号" }}</small>
              </div>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">ACCOUNT LIST</p>
                <h3>账号主列表</h3>
                <span>共 {{ accounts.length }} 条，当前选中 {{ selectionTitle }}</span>
              </div>
              <div class="list-actions">
                <button class="tool-btn" :disabled="!canApproveUsers || !selectedAccountRecord || selectedAccountRecord.status === 'active'" @click="approveSelected">开通</button>
                <button class="tool-btn" :disabled="!canApproveUsers || !selectedAccountRecord || selectedAccountRecord.status === 'disabled'" @click="disableSelected">停用</button>
                <button class="tool-btn" :disabled="!canManageUsers || !selectedAccountRecord" @click="resetPasswordSelected">重置口令</button>
              </div>
            </div>

            <div class="table-shell">
              <table class="mini-table">
                <thead>
                  <tr>
                    <th>姓名</th>
                    <th>登录名</th>
                    <th>角色</th>
                    <th>状态</th>
                    <th>部门</th>
                    <th>联系方式</th>
                    <th>最近登录</th>
                    <th>来源</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in accounts"
                    :key="item.id"
                    :class="{ active: selectedAccountId === item.id && !draftMode }"
                    @click="loadAccount(item)"
                  >
                    <td>{{ item.display_name }}</td>
                    <td>{{ item.username }}</td>
                    <td>{{ roleLabel(item.role) }}</td>
                    <td>{{ accountStatusLabel(item.status) }}</td>
                    <td>{{ item.department || "-" }}</td>
                    <td>{{ item.mobile || item.email || "-" }}</td>
                    <td>{{ formatDate(item.last_login_at) }}</td>
                    <td>{{ accountSourceLabel(item.account_source) }}</td>
                    <td>
                      <div class="table-actions">
                        <button v-if="canManageUsers" class="ops-link" @click.stop="loadAccount(item)">编辑</button>
                        <button v-if="canApproveUsers && item.status !== 'active'" class="ops-link primary" @click.stop="approveAccountAction(item)">开通</button>
                        <button v-if="canApproveUsers && item.status !== 'disabled'" class="ops-link danger-link" @click.stop="disableAccountAction(item)">停用</button>
                        <button v-if="canManageUsers" class="ops-link" @click.stop="resetPasswordAction(item)">重置口令</button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="!accounts.length">
                    <td colspan="9" class="empty-cell">暂无账号数据，或当前筛选条件没有结果。</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </section>
      </template>

      <template #right>
        <aside class="user-right-rail">
          <section class="detail-shell">
            <div class="side-head">
              <strong>{{ draftMode ? "新建账号" : "账号详情与处理" }}</strong>
              <span>{{ draftMode ? "右侧草稿模式" : selectionTitle }}</span>
            </div>

            <div class="detail-summary-grid">
              <article class="detail-chip">
                <span>当前登录</span>
                <strong>{{ currentUser?.display_name || "-" }}</strong>
              </article>
              <article class="detail-chip">
                <span>角色</span>
                <strong>{{ selectedAccountRecord ? roleLabel(selectedAccountRecord.role) : roleLabel(form.role) }}</strong>
              </article>
              <article class="detail-chip">
                <span>状态</span>
                <strong>{{ selectedAccountRecord ? accountStatusLabel(selectedAccountRecord.status) : accountStatusLabel(form.status) }}</strong>
              </article>
              <article class="detail-chip">
                <span>来源</span>
                <strong>{{ selectedAccountRecord ? accountSourceLabel(selectedAccountRecord.account_source) : accountSourceLabel(form.account_source) }}</strong>
              </article>
            </div>

            <div class="action-row wrap">
              <button v-if="canManageUsers" class="tool-btn primary" @click="submitForm">{{ draftMode ? "创建账号" : "保存修改" }}</button>
              <button v-if="canManageUsers" class="tool-btn" @click="prepareNewAccount">新建草稿</button>
              <button v-if="canApproveUsers && selectedAccountRecord && selectedAccountRecord.status !== 'active'" class="tool-btn" @click="approveSelected">开通</button>
              <button v-if="canApproveUsers && selectedAccountRecord && selectedAccountRecord.status !== 'disabled'" class="tool-btn danger-btn" @click="disableSelected">停用</button>
            </div>

            <p class="status-line">{{ actionMessage }}</p>

            <div class="form-grid">
              <label>
                <span>登录名</span>
                <input v-model="form.username" class="field-input" placeholder="例如 manager.ops" />
              </label>
              <label>
                <span>显示姓名</span>
                <input v-model="form.display_name" class="field-input" placeholder="例如 值班主管" />
              </label>
              <label>
                <span>角色</span>
                <select v-model="form.role" class="field-input">
                  <option value="admin">管理员</option>
                  <option value="manager">值班主管</option>
                  <option value="technician">维修人员</option>
                  <option value="viewer">只读人员</option>
                </select>
              </label>
              <label>
                <span>状态</span>
                <select v-model="form.status" class="field-input">
                  <option value="pending">待审批</option>
                  <option value="active">已启用</option>
                  <option value="disabled">已停用</option>
                </select>
              </label>
              <label>
                <span>部门</span>
                <input v-model="form.department" class="field-input" placeholder="例如 信息弱电中心" />
              </label>
              <label>
                <span>手机号</span>
                <input v-model="form.mobile" class="field-input" placeholder="例如 13800000000" />
              </label>
              <label>
                <span>邮箱</span>
                <input v-model="form.email" class="field-input" placeholder="例如 ops@example.com" />
              </label>
              <label>
                <span>{{ draftMode ? "初始密码" : "重置密码" }}</span>
                <input
                  v-model="form.initial_password"
                  class="field-input"
                  type="password"
                  autocomplete="new-password"
                  placeholder="可留空，后续可一键重置"
                />
              </label>
              <label>
                <span>来源</span>
                <select v-model="form.account_source" class="field-input">
                  <option value="local">本地账号</option>
                  <option value="wechat_work">企业微信</option>
                  <option value="feishu">飞书</option>
                  <option value="imported">导入账号</option>
                </select>
              </label>
              <label class="switch-row">
                <input v-model="form.password_ready" type="checkbox" />
                <span>已准备登录口令</span>
              </label>
              <label class="full-width">
                <span>备注</span>
                <textarea v-model="form.notes" class="field-input text-area" rows="4" placeholder="记录职责、值班安排、移动端范围等。" />
              </label>
            </div>

            <p class="action-note">不填写初始密码时，可创建后点击“重置口令”。若勾选“已准备登录口令”且留空，后端会写入角色默认临时口令。</p>
          </section>

          <section class="detail-shell">
            <div class="side-head">
              <strong>修改当前密码</strong>
              <span>当前会话安全</span>
            </div>

            <div class="form-grid">
              <label>
                <span>当前密码</span>
                <input v-model="passwordForm.current_password" class="field-input" type="password" placeholder="请输入当前密码" />
              </label>
              <label>
                <span>新密码</span>
                <input v-model="passwordForm.new_password" class="field-input" type="password" placeholder="请输入新密码" />
              </label>
            </div>
            <div class="action-row wrap">
              <button class="tool-btn primary" @click="submitPasswordChange">更新当前密码</button>
            </div>
            <p class="status-line">{{ passwordMessage }}</p>
          </section>
        </aside>
      </template>
    </WorkbenchShell>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import WorkbenchShell from "../components/workbench/WorkbenchShell.vue";
import {
  approveUserAccount,
  changePassword,
  createUserAccount,
  disableUserAccount,
  fetchUserAccounts,
  fetchUserRoleMatrix,
  fetchUserSummary,
  resetUserPassword,
  updateUserAccount,
} from "../api/client";
import { authState } from "../state/auth";

const currentUser = computed(() => authState.user);
const canManageUsers = computed(() => currentUser.value?.role === "admin");
const canApproveUsers = computed(() => ["admin", "manager"].includes(currentUser.value?.role || ""));

const summary = ref({ account_count: 0, active_count: 0, pending_count: 0, role_breakdown: [], recent_accounts: [] });
const roleMatrix = ref([]);
const accounts = ref([]);
const selectedAccountId = ref(null);
const editingId = ref(null);
const draftMode = ref(false);
const actionMessage = ref("先把账号台账、角色、审批和联系方式收进 V2。");
const passwordMessage = ref("如需修改当前密码，请先输入旧密码，再设置新密码。");
const filters = reactive({ q: "", role: "", status: "" });
const form = reactive({
  username: "",
  display_name: "",
  role: "technician",
  status: "pending",
  department: "",
  mobile: "",
  email: "",
  initial_password: "",
  account_source: "local",
  password_ready: false,
  notes: "",
});
const passwordForm = reactive({ current_password: "", new_password: "" });

const selectedAccountRecord = computed(() => {
  if (!selectedAccountId.value) return null;
  return accounts.value.find((item) => item.id === selectedAccountId.value) || summary.value.recent_accounts?.find((item) => item.id === selectedAccountId.value) || null;
});
const pendingCandidate = computed(() => accounts.value.find((item) => item.status === "pending") || null);
const technicianCount = computed(() => accounts.value.filter((item) => item.role === "technician").length);
const scopeSummary = computed(() => {
  const parts = [];
  if (filters.role) parts.push(roleLabel(filters.role));
  if (filters.status) parts.push(accountStatusLabel(filters.status));
  if (filters.q) parts.push(`关键词：${filters.q}`);
  return parts.length ? parts.join(" / ") : "全部账号范围";
});
const selectionTitle = computed(() => {
  if (draftMode.value) return "新建账号草稿";
  return selectedAccountRecord.value?.display_name || "暂未选择账号";
});
const selectionMeta = computed(() => {
  if (draftMode.value) return "右侧正在准备新的账号对象。";
  if (!selectedAccountRecord.value) return "先从中间主列表选中一个账号。";
  const record = selectedAccountRecord.value;
  return `${record.username} / ${roleLabel(record.role)} / ${accountStatusLabel(record.status)}`;
});
const actionGuide = computed(() => {
  if (draftMode.value) return "先把登录名、角色和状态写清，再决定是否立刻开通。";
  const record = selectedAccountRecord.value;
  if (!record) return "先从中间主列表选中一个账号，右侧才会进入真正的处理节奏。";
  if (record.status === "pending") return "建议先核对角色和联系方式，再执行开通。";
  if (record.status === "active") return "当前账号已启用，建议关注权限范围和是否需要重置口令。";
  return "当前账号已停用，如需恢复使用，建议先核对来源和责任人。";
});

onMounted(async () => {
  await reload();
});

watch(() => [filters.q, filters.role, filters.status], async () => {
  await loadAccounts();
});

async function reload() {
  summary.value = await fetchUserSummary();
  roleMatrix.value = await fetchUserRoleMatrix();
  await loadAccounts();
}

async function loadAccounts() {
  accounts.value = await fetchUserAccounts({ q: filters.q, role: filters.role, status: filters.status });
  if (draftMode.value) return;
  if (selectedAccountId.value) {
    const matched = accounts.value.find((item) => item.id === selectedAccountId.value);
    if (matched) {
      syncFormFromItem(matched);
      return;
    }
  }
  if (accounts.value.length) {
    loadAccount(accounts.value[0], true);
  } else {
    selectedAccountId.value = null;
    editingId.value = null;
    clearForm();
  }
}

function clearForm() {
  form.username = "";
  form.display_name = "";
  form.role = "technician";
  form.status = "pending";
  form.department = "";
  form.mobile = "";
  form.email = "";
  form.initial_password = "";
  form.account_source = "local";
  form.password_ready = false;
  form.notes = "";
}

function resetForm() {
  draftMode.value = false;
  editingId.value = null;
  selectedAccountId.value = null;
  clearForm();
}

function prepareNewAccount() {
  draftMode.value = true;
  editingId.value = null;
  selectedAccountId.value = null;
  clearForm();
  actionMessage.value = "已切换到新建账号模式。";
}

function syncFormFromItem(item) {
  form.username = item.username;
  form.display_name = item.display_name;
  form.role = item.role;
  form.status = item.status;
  form.department = item.department || "";
  form.mobile = item.mobile || "";
  form.email = item.email || "";
  form.initial_password = "";
  form.account_source = item.account_source;
  form.password_ready = !!item.password_ready;
  form.notes = item.notes || "";
}

function loadAccount(item, silent = false) {
  draftMode.value = false;
  selectedAccountId.value = item.id;
  editingId.value = item.id;
  syncFormFromItem(item);
  if (!silent) {
    actionMessage.value = `正在编辑：${item.display_name}`;
  }
}

async function submitForm() {
  try {
    const payload = { ...form };
    if (editingId.value && !draftMode.value) {
      await updateUserAccount(editingId.value, payload);
      actionMessage.value = payload.initial_password ? "账号信息已更新，密码也已同步重置。" : "账号信息已更新。";
    } else {
      await createUserAccount(payload);
      draftMode.value = false;
      actionMessage.value =
        payload.initial_password || !payload.password_ready
          ? "账号已创建。"
          : `账号已创建，默认临时密码为：${payload.role}123`;
    }
    await reload();
  } catch (error) {
    console.error(error);
    actionMessage.value = "保存失败，请检查用户名是否重复或查看后端日志。";
  }
}

async function approveAccountAction(item) {
  try {
    await approveUserAccount(item.id);
    actionMessage.value = `已开通账号：${item.display_name}`;
    await reload();
  } catch (error) {
    console.error(error);
    actionMessage.value = "开通失败，请查看后端日志。";
  }
}

async function disableAccountAction(item) {
  try {
    await disableUserAccount(item.id);
    actionMessage.value = `已停用账号：${item.display_name}`;
    await reload();
  } catch (error) {
    console.error(error);
    actionMessage.value = "停用失败，请查看后端日志。";
  }
}

async function resetPasswordAction(item) {
  try {
    const result = await resetUserPassword(item.id);
    actionMessage.value = `已为 ${item.display_name} 重置临时密码：${result.temporary_password}`;
    await reload();
  } catch (error) {
    console.error(error);
    actionMessage.value = "重置口令失败，请查看后端日志。";
  }
}

async function approveSelected() {
  if (!selectedAccountRecord.value) return;
  await approveAccountAction(selectedAccountRecord.value);
}

async function disableSelected() {
  if (!selectedAccountRecord.value) return;
  await disableAccountAction(selectedAccountRecord.value);
}

async function resetPasswordSelected() {
  if (!selectedAccountRecord.value) return;
  await resetPasswordAction(selectedAccountRecord.value);
}

async function submitPasswordChange() {
  try {
    await changePassword(passwordForm.current_password, passwordForm.new_password);
    passwordForm.current_password = "";
    passwordForm.new_password = "";
    passwordMessage.value = "当前账号密码已更新。";
  } catch (error) {
    console.error(error);
    passwordMessage.value = "密码更新失败，请检查旧密码是否正确。";
  }
}

function focusRole(role) {
  filters.role = role;
}

function focusStatus(status) {
  filters.status = status;
}

function resetFilters() {
  filters.q = "";
  filters.role = "";
  filters.status = "";
  actionMessage.value = "已恢复完整账号范围。";
}

function roleLabel(value) {
  return (
    {
      admin: "管理员",
      manager: "值班主管",
      technician: "维修人员",
      viewer: "只读人员",
    }[value] || value || "-"
  );
}

function accountStatusLabel(value) {
  return (
    {
      pending: "待审批",
      active: "已启用",
      disabled: "已停用",
    }[value] || value || "-"
  );
}

function accountSourceLabel(value) {
  return (
    {
      local: "本地账号",
      wechat_work: "企业微信",
      feishu: "飞书",
      imported: "导入账号",
    }[value] || value || "-"
  );
}

function formatDate(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return value;
  }
}
</script>

<style scoped>
.user-workbench-page {
  padding-bottom: 24px;
}

.user-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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
.empty-note,
.status-line,
.action-note {
  color: rgba(207, 231, 255, 0.72);
}

.user-roadmap {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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

.user-left-rail,
.user-center,
.user-right-rail {
  display: grid;
  gap: 12px;
  min-height: 0;
  overflow-x: hidden;
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
.eyebrow {
  color: rgba(207, 231, 255, 0.72);
}

.scope-list,
.filter-stack,
.hint-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.recent-list {
  max-height: 280px;
  overflow: auto;
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

.field-input {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(111, 191, 255, 0.16);
  background: rgba(255, 255, 255, 0.04);
  color: #f4fbff;
  padding: 12px 14px;
}

.action-row.wrap,
.list-actions,
.table-actions,
.switch-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.ops-guide-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.ops-guide-card {
  border-radius: 18px;
  padding: 14px 16px;
  display: grid;
  gap: 4px;
}

.table-shell {
  overflow: auto;
  margin-top: 14px;
  max-width: 100%;
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

.empty-cell {
  text-align: center;
  color: rgba(207, 231, 255, 0.72);
  padding: 24px 12px;
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

.danger-link,
.danger-btn {
  color: #fca5a5;
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

.form-grid label span,
.switch-row span {
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

@media (max-width: 1380px) {
  .ops-guide-strip,
  .detail-summary-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1760px) {
  .mini-table {
    min-width: 860px;
  }

  .mini-table th:nth-child(7),
  .mini-table td:nth-child(7),
  .mini-table th:nth-child(8),
  .mini-table td:nth-child(8) {
    display: none;
  }
}

@media (max-width: 960px) {
  .user-metrics,
  .user-roadmap {
    grid-template-columns: 1fr;
  }
}

/* Anti-Tofu user terminal density */
.user-workbench-page {
  padding-top: 0;
  color: #dbeafe;
  background: #05080f;
}

.user-workbench-page :deep(.workbench-shell) {
  gap: 8px;
}

.user-workbench-page :deep(.workbench-toolbar) {
  padding: 0;
  border-bottom: 1px solid rgba(56, 189, 248, 0.15);
}

.user-workbench-page :deep(.workbench-title) {
  display: none;
}

.user-workbench-page :deep(.workbench-main) {
  grid-template-columns: minmax(220px, 20%) minmax(0, 80%) !important;
  gap: 10px;
  min-height: calc(100vh - 130px);
}

.user-workbench-page :deep(.workbench-side-right) {
  display: none;
}

.user-metrics {
  display: none !important;
}

.scope-block,
.filter-panel,
.panel,
.workbench-panel,
.detail-shell,
.ops-guide-card {
  border: 1px solid rgba(56, 189, 248, 0.15) !important;
  background: transparent !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  border-radius: 0 !important;
}

.scope-block,
.filter-panel,
.workbench-panel {
  padding: 10px !important;
}

.ops-guide-strip {
  display: none !important;
}

.side-head strong,
.list-toolbar h3 {
  font-size: 13px !important;
  letter-spacing: 0.06em;
}

.side-head span,
.list-toolbar span,
.hint-row span,
.scope-row span {
  font-size: 11px !important;
}

.scope-row,
.hint-row {
  padding: 7px 8px !important;
  border-bottom: 1px solid rgba(56, 189, 248, 0.1) !important;
  background: transparent !important;
}

.field-input {
  min-height: 28px !important;
  padding: 5px 8px !important;
  border-color: rgba(56, 189, 248, 0.18) !important;
  background: #080b14 !important;
}

.table-shell {
  margin-top: 8px !important;
  border: 1px solid rgba(56, 189, 248, 0.15);
  background: #080b14;
}

.mini-table th,
.mini-table td {
  padding: 7px 8px !important;
  border-bottom: 1px solid rgba(56, 189, 248, 0.1) !important;
  font-size: 12px !important;
}

.mini-table th {
  color: #38bdf8 !important;
  background: #05080f;
}
</style>
