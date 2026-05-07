<template>
  <section class="login-page theme-stage">
    <div class="login-shell">
      <div class="login-copy">
        <div class="login-topline">
          <p class="eyebrow">认证中心</p>
          <div class="theme-switch">
            <button class="theme-pill" :class="{ active: themeMode === 'dark' }" @click="setTheme('dark')">
              暗色
            </button>
            <button class="theme-pill" :class="{ active: themeMode === 'light' }" @click="setTheme('light')">
              白色
            </button>
          </div>
        </div>

        <h1>永嘉集团信息弱电综合运维平台</h1>
        <p class="lead">
          一套面向视频监控、拓扑归因、告警闭环、工单协同、控制平台接入和模型扩展的统一入口。
          先选主题，再进入系统，确保 PC 和手机都保持一致的专业视觉体验。
        </p>

        <div class="login-bullets">
          <span>统一资产底座</span>
          <span>拓扑归因</span>
          <span>视频预览 / 快照</span>
          <span>手机自适应</span>
        </div>

        <div class="login-radar">
          <div class="radar-orb"></div>
          <div class="radar-grid"></div>
          <div class="radar-text">
            <strong>专业科技感界面</strong>
            <span>暗色 / 白色主题可切换</span>
          </div>
        </div>
      </div>

      <article class="login-card">
        <header>
          <h2>账号登录</h2>
          <p>使用已开通账号进入运维平台。首次使用可先提交注册申请，等待管理员开通。</p>
        </header>

        <label class="login-field">
          <span>登录名</span>
          <input v-model="form.username" class="text-input" placeholder="请输入登录名" @keyup.enter="submit" />
        </label>

        <label class="login-field">
          <span>密码</span>
          <input
            v-model="form.password"
            class="text-input"
            type="password"
            placeholder="请输入密码"
            @keyup.enter="submit"
          />
        </label>

        <div class="login-actions">
          <button class="action-btn" :disabled="submitting" @click="submit">
            {{ submitting ? "登录中..." : "进入系统" }}
          </button>
        </div>

        <p class="login-feedback" :class="{ error: feedbackType === 'error' }">{{ feedback }}</p>

        <footer class="login-footer">
          <span>支持管理员、值班主管、维修人员分层使用</span>
          <span>登录后可切换到 PC / 手机适配页面</span>
        </footer>
      </article>

      <article class="login-card secondary-card">
        <header>
          <h2>自助注册</h2>
          <p>现场协同人员可先提交申请，等待管理员审核后开通权限。</p>
        </header>

        <label class="login-field">
          <span>登录名</span>
          <input v-model="registerForm.username" class="text-input" placeholder="例如 tech.night" />
        </label>
        <label class="login-field">
          <span>显示名称</span>
          <input v-model="registerForm.display_name" class="text-input" placeholder="例如 夜班维修员" />
        </label>
        <label class="login-field">
          <span>密码</span>
          <input v-model="registerForm.password" type="password" class="text-input" placeholder="设置初始密码" />
        </label>
        <label class="login-field">
          <span>手机号</span>
          <input v-model="registerForm.mobile" class="text-input" placeholder="可选，方便值班联系" />
        </label>

        <div class="login-actions">
          <button class="action-btn subtle" :disabled="registering" @click="submitRegister">
            {{ registering ? "提交中..." : "提交注册申请" }}
          </button>
        </div>
        <p class="login-feedback" :class="{ error: registerFeedbackType === 'error' }">{{ registerFeedback }}</p>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { loginWithPassword, registerWithPassword } from "../api/client";
import { setAuthSession } from "../state/auth";
import { setThemeMode, themeState } from "../state/theme";

const router = useRouter();
const route = useRoute();

const form = reactive({
  username: "",
  password: "",
});

const submitting = ref(false);
const feedback = ref("请选择主题后登录系统。");
const feedbackType = ref("info");
const registering = ref(false);
const registerFeedback = ref("新注册账号会进入待审批状态。");
const registerFeedbackType = ref("info");

const registerForm = reactive({
  username: "",
  display_name: "",
  password: "",
  mobile: "",
});

const themeMode = computed(() => themeState.mode);

function setTheme(mode) {
  setThemeMode(mode);
}

async function submit() {
  if (!form.username.trim() || !form.password.trim()) {
    feedback.value = "请输入登录名和密码。";
    feedbackType.value = "error";
    return;
  }

  submitting.value = true;
  feedback.value = "正在校验账号...";
  feedbackType.value = "info";

  try {
    const result = await loginWithPassword(form.username.trim(), form.password);
    setAuthSession(result.access_token, result.user);
    feedback.value = "登录成功，正在进入平台。";
    feedbackType.value = "info";
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/";
    await router.replace(redirect || "/");
  } catch (error) {
    console.error(error);
    const status = error?.response?.status;
    const detail = error?.response?.data?.detail;
    if (status === 401 || detail === "invalid_username_or_password") {
      feedback.value = "登录失败：账号或密码不正确。";
    } else if (status === 403 || detail === "account_not_active") {
      feedback.value = "登录失败：账号未开通或已被停用。";
    } else if (!error?.response) {
      feedback.value = "登录失败：前端暂时无法连接后端服务。";
    } else {
      feedback.value = "登录失败：请检查后端运行状态后重试。";
    }
    feedbackType.value = "error";
  } finally {
    submitting.value = false;
  }
}

async function submitRegister() {
  if (!registerForm.username.trim() || !registerForm.display_name.trim() || !registerForm.password.trim()) {
    registerFeedback.value = "请填写登录名、显示名称和密码。";
    registerFeedbackType.value = "error";
    return;
  }

  registering.value = true;
  registerFeedback.value = "正在提交注册申请...";
  registerFeedbackType.value = "info";

  try {
    await registerWithPassword({
      username: registerForm.username.trim(),
      display_name: registerForm.display_name.trim(),
      password: registerForm.password,
      mobile: registerForm.mobile.trim(),
    });
    registerFeedback.value = "注册申请已提交，请等待管理员开通。";
    registerFeedbackType.value = "info";
    registerForm.username = "";
    registerForm.display_name = "";
    registerForm.password = "";
    registerForm.mobile = "";
  } catch (error) {
    console.error(error);
    registerFeedback.value = "注册失败：登录名可能已存在，或后端暂时不可用。";
    registerFeedbackType.value = "error";
  } finally {
    registering.value = false;
  }
}
</script>

