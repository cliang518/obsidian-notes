import { createRouter, createWebHistory } from "vue-router";
import { fetchCurrentUser } from "../api/client";
import { authState, clearAuthSession, markAuthReady, setAuthSession } from "../state/auth";

import AgentCenterView from "../views/AgentCenterView.vue";
import AiChatView from "../ai_chat/AiChatView.vue";
import AiGatewayCenterView from "../views/AiGatewayCenterView.vue";
import AlertCenterView from "../views/AlertCenterView.vue";
import AssetCenterView from "../views/AssetCenterView.vue";
import ControlPlatformView from "../views/ControlPlatformView.vue";
import DashboardView from "../views/DashboardView.vue";
import DocsCenterView from "../views/DocsCenterView.vue";
import FloorPlanCenterView from "../views/FloorPlanCenterView.vue";
import InspectionCenterView from "../views/InspectionCenterView.vue";
import IntegrationCenterView from "../views/IntegrationCenterView.vue";
import LearningCenterView from "../views/LearningCenterView.vue";
import LicenseCenterView from "../views/LicenseCenterView.vue";
import LlmCenterView from "../views/LlmCenterView.vue";
import LoginView from "../views/LoginView.vue";
import MobileWorkspaceView from "../views/MobileWorkspaceView.vue";
import NotificationCenterView from "../views/NotificationCenterView.vue";
import RuntimeCenterView from "../views/RuntimeCenterView.vue";
import StorageCenterView from "../views/StorageCenterView.vue";
import TopologyCenterView from "../views/TopologyCenterView.vue";
import TopologyEditorView from "../views/TopologyEditorView.vue";
import UserCenterView from "../views/UserCenterView.vue";
import VideoCenterView from "../views/VideoCenterProView.vue";
import WorkOrderCenterView from "../views/WorkOrderCenterView.vue";

export const appRoutes = [
  { path: "/login", component: LoginView, meta: { public: true } },
  { path: "/", component: DashboardView, meta: { label: "运行总览" } },
  { path: "/runtime", component: RuntimeCenterView, meta: { label: "运行中心", roles: ["admin", "manager"], hidden: true } },
  { path: "/assets", component: AssetCenterView, meta: { label: "设备资产" } },
  { path: "/alerts", component: AlertCenterView, meta: { label: "告警中心" } },
  { path: "/topology", component: TopologyEditorView, meta: { label: "拓扑归属" } },
  { path: "/topology-editor", component: TopologyEditorView, meta: { label: "拓扑编辑器", hidden: true } },
  { path: "/video", component: VideoCenterView, meta: { label: "视频诊断", hidden: true } },
  { path: "/work-orders", component: WorkOrderCenterView, meta: { label: "工单中心" } },
  { path: "/inspection", component: InspectionCenterView, meta: { label: "巡检中心", hidden: true } },
  { path: "/integrations", component: IntegrationCenterView, meta: { label: "数据接入", roles: ["admin", "manager"], hidden: true } },
  { path: "/users", component: UserCenterView, meta: { label: "人员管理", roles: ["admin", "manager"] } },
  { path: "/notifications", component: NotificationCenterView, meta: { label: "通知配置", roles: ["admin", "manager"], hidden: true } },
  { path: "/mobile", component: MobileWorkspaceView, meta: { label: "移动工作台" } },
  { path: "/ai-gateway", component: AiGatewayCenterView, meta: { label: "AI中心", roles: ["admin", "manager"] } },
{ path: "/ai-chat", component: AiChatView, meta: { label: "AI助手", roles: ["admin", "manager"] } },
  { path: "/license", component: LicenseCenterView, meta: { label: "授权中心", roles: ["admin"] } },
  {
    path: "/control-platform",
    component: ControlPlatformView,
    meta: { label: "风控电控", roles: ["admin", "manager"], hidden: true },
  },
  { path: "/docs", component: DocsCenterView, meta: { label: "资料中心", roles: ["admin", "manager"], hidden: true } },
  { path: "/floor-plans", component: FloorPlanCenterView, meta: { label: "CAD 图纸", roles: ["admin", "manager"], hidden: true } },
  { path: "/llm", component: LlmCenterView, meta: { label: "模型中心", roles: ["admin"], hidden: true } },
  { path: "/agents", component: AgentCenterView, meta: { label: "智能接口", roles: ["admin", "manager"], hidden: true } },
  { path: "/storage", component: StorageCenterView, meta: { label: "存储资源", roles: ["admin", "manager"], hidden: true } },
  { path: "/learning", component: LearningCenterView, meta: { label: "学习中心", roles: ["admin", "manager"], hidden: true } },
];

const router = createRouter({
  history: createWebHistory(),
  routes: appRoutes,
});

let authBootstrapPromise = null;

async function ensureAuthReady() {
  if (authState.ready) {
    return;
  }
  if (!authBootstrapPromise) {
    authBootstrapPromise = (async () => {
      if (!authState.token) {
        markAuthReady();
        return;
      }
      try {
        const user = await fetchCurrentUser();
        setAuthSession(authState.token, user);
      } catch (error) {
        console.warn("Failed to restore V2 auth session.", error);
        clearAuthSession();
        markAuthReady();
      }
    })().finally(() => {
      authBootstrapPromise = null;
    });
  }
  await authBootstrapPromise;
}

router.beforeEach((to, from, next) => {
  // await ensureAuthReady();
  // if (to.meta.public) {
  //   if (to.path === "/login" && authState.user) {
  //     return "/";
  //   }
  //   return true;
  // }
  // if (!authState.user) {
  //   return {
  //     path: "/login",
  //     query: { redirect: to.fullPath },
  //   };
  // }
  // const allowedRoles = to.meta?.roles;
  // if (Array.isArray(allowedRoles) && allowedRoles.length && !allowedRoles.includes(authState.user.role)) {
  //   return "/";
  // }
  // return true;
  next();
});

export default router;
