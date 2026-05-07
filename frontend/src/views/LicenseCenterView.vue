<template>
  <section class="license-vault-page">
    <main class="vault-frame">
      <div class="vault-status">
        <span>LICENSE CORE</span>
        <strong :class="{ invalid: !status.active }">STATUS: {{ status.active ? "VALID" : "INVALID" }}</strong>
        <small>{{ status.reason || "等待授权核心返回状态。" }}</small>
      </div>

      <section class="vault-grid">
        <article class="vault-panel">
          <h3>AUTH.IDENTITY</h3>
          <ul class="vault-list">
            <li><span>PRODUCT</span><strong>{{ status.product_name || "-" }}</strong></li>
            <li><span>ISSUED_TO</span><strong>{{ status.issued_to || "-" }}</strong></li>
            <li><span>CONTACT</span><strong>{{ status.contact || "-" }}</strong></li>
            <li><span>TYPE</span><strong>{{ status.license_type || "-" }}</strong></li>
            <li><span>EXPIRES_AT</span><strong>{{ status.expires_at || "-" }}</strong></li>
            <li><span>GRACE</span><strong>{{ status.in_grace_period ? "YES" : "NO" }} / {{ status.grace_deadline || "-" }}</strong></li>
            <li><span>DAYS_LEFT</span><strong>{{ status.days_remaining ?? "-" }}</strong></li>
            <li><span>MACHINE</span><strong>{{ shortMachineCode }}</strong></li>
          </ul>
        </article>

        <article class="vault-panel">
          <h3>IMPORT.KEY</h3>
          <textarea v-model="licenseJson" class="terminal-input" placeholder="paste license json here"></textarea>
          <div class="vault-actions">
            <button class="terminal-btn primary" type="button" @click="submitActivation">导入授权</button>
            <button class="terminal-btn" type="button" @click="copyRequest">复制注册请求</button>
            <button class="terminal-btn" type="button" @click="refreshStatus">刷新状态</button>
          </div>
          <p class="terminal-message">> {{ actionMessage }}</p>
        </article>
      </section>

      <section class="vault-console">
        <div class="console-head">
          <span>REGISTRATION.REQUEST.JSON</span>
          <button class="copy-icon" type="button" @click="copyRequest">COPY</button>
        </div>
        <pre><code>{{ requestJson }}</code></pre>
      </section>
    </main>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { activateLicense, fetchLicenseStatus } from "../api/client";

const status = ref({
  active: false,
  request_payload: {},
});
const licenseJson = ref("");
const actionMessage = ref("请先导出注册请求，再导入注册机生成的授权信息。");

const requestJson = computed(() => JSON.stringify(status.value.request_payload || {}, null, 2));
const shortMachineCode = computed(() => {
  const code = status.value.machine_code || "";
  return code || "-";
});

onMounted(async () => {
  await refreshStatus();
});

async function refreshStatus() {
  try {
    status.value = await fetchLicenseStatus();
  } catch (error) {
    console.error(error);
    actionMessage.value = "授权状态读取失败。";
  }
}

async function submitActivation() {
  try {
    const payload = JSON.parse(licenseJson.value.trim());
    const result = await activateLicense(payload);
    status.value = result.status;
    actionMessage.value = result.message || "授权已更新。";
  } catch (error) {
    console.error(error);
    actionMessage.value = error?.response?.data?.detail || "授权导入失败。";
  }
}

async function copyRequest() {
  try {
    await navigator.clipboard.writeText(requestJson.value);
    actionMessage.value = "注册请求已复制到剪贴板。";
  } catch (error) {
    console.error(error);
    actionMessage.value = "复制失败，请手动复制。";
  }
}
</script>

<style scoped>
.license-vault-page {
  min-height: 100%;
  display: grid;
  place-items: center;
  padding: 24px;
  color: #7dd3fc;
  background: #000;
  font-family: Consolas, "Courier New", monospace;
}

.vault-frame {
  width: min(1180px, 100%);
  display: grid;
  gap: 14px;
  padding: 18px;
  border: 1px solid rgba(34, 211, 238, 0.32);
  background: #020403;
  box-shadow: inset 0 0 0 1px rgba(34, 197, 94, 0.08), 0 0 42px rgba(34, 211, 238, 0.08);
}

.vault-status {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(34, 211, 238, 0.2);
}

.vault-status span,
.vault-panel h3,
.console-head span {
  color: #22d3ee;
  font-size: 11px;
  letter-spacing: 0.22em;
}

.vault-status strong {
  color: #39ff88;
  font-size: clamp(26px, 5vw, 48px);
  line-height: 1;
  text-shadow: 0 0 16px rgba(57, 255, 136, 0.5);
}

.vault-status strong.invalid {
  color: #fb7185;
  text-shadow: 0 0 16px rgba(251, 113, 133, 0.42);
}

.vault-status small,
.terminal-message {
  color: rgba(125, 211, 252, 0.72);
}

.vault-grid {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 14px;
}

.vault-panel,
.vault-console {
  border: 1px solid rgba(34, 211, 238, 0.18);
  background: #000;
}

.vault-panel {
  padding: 12px;
}

.vault-panel h3 {
  margin: 0 0 10px;
}

.vault-list {
  display: grid;
  gap: 0;
  padding: 0;
  margin: 0;
  list-style: none;
}

.vault-list li {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px solid rgba(34, 211, 238, 0.1);
}

.vault-list span {
  color: rgba(34, 197, 94, 0.78);
  font-size: 11px;
}

.vault-list strong {
  min-width: 0;
  overflow: hidden;
  color: #e0f2fe;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.terminal-input {
  width: 100%;
  min-height: 170px;
  resize: vertical;
  padding: 10px;
  border: 1px solid rgba(34, 197, 94, 0.24);
  outline: none;
  color: #39ff88;
  background: #000;
  font: 12px/1.5 Consolas, "Courier New", monospace;
}

.vault-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.terminal-btn,
.copy-icon {
  border: 1px solid rgba(34, 211, 238, 0.28);
  color: #7dd3fc;
  background: transparent;
  font: 11px Consolas, "Courier New", monospace;
  cursor: pointer;
}

.terminal-btn {
  padding: 7px 10px;
}

.terminal-btn.primary {
  color: #39ff88;
  border-color: rgba(57, 255, 136, 0.38);
}

.copy-icon {
  padding: 4px 8px;
}

.vault-console {
  min-height: 220px;
}

.console-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(34, 211, 238, 0.18);
}

.vault-console pre {
  max-height: 330px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  color: #39ff88;
  font-size: 12px;
  line-height: 1.55;
}

@media (max-width: 980px) {
  .vault-grid {
    grid-template-columns: 1fr;
  }
}
</style>
