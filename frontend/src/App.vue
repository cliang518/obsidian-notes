<template>
  <router-view v-if="isLoginRoute" />

  <div v-else class="darkstar-shell">
    <aside
      class="cyber-sidebar"
      :class="{ 'is-collapsed': isCollapsed }"
      @mouseenter="isCollapsed = false"
      @mouseleave="isCollapsed = true"
    >
      <div class="sidebar-logo">
        <div class="logo-box">YJ</div>
        <span class="logo-text" v-show="!isCollapsed">永嘉 V2 中枢</span>
      </div>

      <nav class="sidebar-nav">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          active-class="is-active"
        >
          <div class="nav-icon"><i :class="item.icon">{{ item.emoji }}</i></div>
          <span class="nav-label" v-show="!isCollapsed">{{ item.label }}</span>
          <div class="active-glow"></div>
        </router-link>
      </nav>

      <div class="sidebar-footer" v-show="!isCollapsed">
        <div class="sys-version">OS Version 2.0.0-RC1</div>
      </div>
    </aside>

    <main class="cyber-main">
      <header class="cyber-header">
        <div class="header-left">
          <div class="breadcrumb">
            <span class="path-dim">态势感知网络</span>
            <span class="path-separator">/</span>
            <strong class="path-current">{{ currentRouteName }}</strong>
          </div>
        </div>

        <div class="header-right">
          <div class="command-palette">
            <span class="cmd-icon">🔍</span>
            <span class="cmd-text">全局指令模式</span>
            <kbd class="cmd-key">Ctrl K</kbd>
          </div>
          <div class="header-divider"></div>
          <div class="quality-toggle" @click="cycleGraphics" :title="'当前画质: ' + qualityLabel">
            <span class="quality-icon">🖥️</span>
            <span class="quality-text">{{ qualityLabel }}</span>
          </div>
          <div class="header-divider"></div>
          <div class="user-profile">
            <div class="avatar-ring">
              <span style="font-size: 20px;">👨‍💻</span>
            </div>
            <div class="user-info">
              <span class="user-name">平台管理员</span>
              <span class="user-role">Super Admin</span>
            </div>
          </div>
        </div>
      </header>

      <div class="cyber-canvas">
        <router-view v-slot="{ Component }">
          <transition name="fade-transform" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch, watchEffect } from "vue";
import { useRoute } from "vue-router";
import { syncThemeDocument } from "./state/theme";

const route = useRoute();
const isCollapsed = ref(true);
const isLoginRoute = computed(() => route.path === "/login");
const graphicsQuality = ref(localStorage.getItem("YJ_GRAPHICS") || "medium");

const currentRouteName = computed(() => {
  return route.meta?.label || route.meta?.title || route.name || "模块加载中...";
});

const menuItems = ref([
  { path: "/", label: "运行总览", emoji: "🌌" },
  { path: "/assets", label: "设备资产", emoji: "🗄️" },
  { path: "/alerts", label: "告警中心", emoji: "🚨" },
  { path: "/topology", label: "拓扑归属", emoji: "🕸️" },
  { path: "/work-orders", label: "工单中心", emoji: "📋" },
  { path: "/users", label: "人员管理", emoji: "👥" },
  { path: "/mobile", label: "移动工作台", emoji: "📱" },
  { path: "/ai-gateway", label: "AI 中心", emoji: "🧠" },
  { path: "/ai-chat", label: "AI 助手", emoji: "🤖" },
  { path: "/license", label: "授权中心", emoji: "🔐" },
]);

watch(graphicsQuality, (val) => {
  localStorage.setItem("YJ_GRAPHICS", val);
  document.body.classList.remove("graphics-low", "graphics-medium", "graphics-ultra");
  document.body.classList.add(`graphics-${val}`);
  window.dispatchEvent(new CustomEvent("graphics-changed", { detail: val }));
}, { immediate: true });

const cycleGraphics = () => {
  const map = { low: "medium", medium: "ultra", ultra: "low" };
  graphicsQuality.value = map[graphicsQuality.value] || "medium";
};

const qualityLabel = computed(() => {
  const labels = { low: "🚀 极速", medium: "⚖️ 均衡", ultra: "✨ 赛博" };
  return labels[graphicsQuality.value] || labels.medium;
});

watchEffect(() => {
  syncThemeDocument();
});

onMounted(() => {
  syncThemeDocument();
});
</script>

<style scoped>
.darkstar-shell {
  display: flex;
  width: 100vw;
  height: 100vh;
  background-color: #05080f;
  overflow: hidden;
  color: #e2e8f0;
  font-family: "Inter", system-ui, sans-serif;
}

.cyber-sidebar {
  width: 220px;
  height: calc(100vh - 32px);
  margin: 16px 0 16px 16px;
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(14, 165, 233, 0.15);
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.2);
  z-index: 100;
}

.cyber-sidebar.is-collapsed {
  width: 72px;
}

.sidebar-logo {
  height: 72px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.logo-box {
  width: 36px;
  height: 36px;
  min-width: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #0ea5e9, #3b82f6);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 900;
  font-size: 16px;
  color: #fff;
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.4);
}

.logo-text {
  font-size: 15px;
  font-weight: 800;
  white-space: nowrap;
  background: linear-gradient(to right, #fff, #94a3b8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.sidebar-nav {
  flex: 1;
  padding: 20px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  overflow-x: hidden;
}

.sidebar-nav::-webkit-scrollbar {
  width: 4px;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  height: 44px;
  padding: 0 14px;
  border-radius: 10px;
  color: #94a3b8;
  text-decoration: none;
  transition: all 0.2s ease;
  overflow: hidden;
}

.nav-item:hover {
  color: #e2e8f0;
  background: rgba(255, 255, 255, 0.05);
}

.nav-icon {
  width: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  margin-right: 12px;
  transition: transform 0.2s;
}

.nav-item:hover .nav-icon {
  transform: scale(1.1);
}

.nav-label {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.active-glow {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 0;
  background: #38bdf8;
  border-radius: 0 4px 4px 0;
  transition: height 0.3s ease;
  box-shadow: 0 0 12px #38bdf8;
}

.nav-item.is-active {
  color: #fff;
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.15), transparent);
}

.nav-item.is-active .active-glow {
  height: 20px;
}

.sidebar-footer {
  padding: 16px;
  text-align: center;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.sys-version {
  font-size: 11px;
  color: #475569;
  font-family: monospace;
}

.cyber-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.cyber-header {
  height: 64px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: transparent;
  z-index: 10;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.path-dim {
  color: #64748b;
  font-weight: 500;
}

.path-separator {
  color: #334155;
}

.path-current {
  color: #e2e8f0;
  font-weight: 800;
  letter-spacing: 0.5px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.command-palette {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 10px 4px 14px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 999px;
  cursor: text;
  transition: all 0.2s;
}

.command-palette:hover {
  border-color: rgba(56, 189, 248, 0.4);
  background: rgba(15, 23, 42, 0.8);
}

.quality-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}

.quality-toggle:hover {
  background: rgba(56, 189, 248, 0.2);
  border-color: rgba(56, 189, 248, 0.4);
}

.quality-text {
  font-size: 12px;
  color: #e2e8f0;
  font-weight: bold;
}

.cmd-text {
  color: #64748b;
  font-size: 12px;
}

.cmd-key {
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  color: #94a3b8;
  font-family: monospace;
}

.header-divider {
  width: 1px;
  height: 20px;
  background: rgba(255, 255, 255, 0.1);
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.avatar-ring {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(56, 189, 248, 0.1);
  border: 1px solid rgba(56, 189, 248, 0.3);
}

.user-info {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-size: 12px;
  font-weight: 700;
  color: #f8fafc;
}

.user-role {
  font-size: 10px;
  color: #64748b;
}

.cyber-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  padding: 16px 24px 24px 24px;
  box-sizing: border-box;
  min-width: 0;
}

.fade-transform-leave-active,
.fade-transform-enter-active {
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.fade-transform-enter-from {
  opacity: 0;
  transform: translateY(10px) scale(0.99);
}

.fade-transform-leave-to {
  opacity: 0;
  transform: translateY(-10px) scale(0.99);
}

:global(body.graphics-low .cyber-sidebar),
:global(body.graphics-low .cyber-hud-bar),
:global(body.graphics-low .orphan-sidebar) {
  backdrop-filter: none !important;
  background: #0b1120 !important;
}

:global(body.graphics-medium .cyber-sidebar),
:global(body.graphics-medium .cyber-hud-bar),
:global(body.graphics-medium .orphan-sidebar) {
  backdrop-filter: blur(10px) !important;
}

:global(body.graphics-ultra .cyber-sidebar),
:global(body.graphics-ultra .cyber-hud-bar),
:global(body.graphics-ultra .orphan-sidebar) {
  backdrop-filter: blur(20px) !important;
}

@media (max-width: 860px) {
  .cyber-sidebar {
    width: 72px;
  }

  .cyber-header {
    height: 56px;
    padding: 0 14px;
  }

  .command-palette,
  .quality-text,
  .user-info,
  .header-divider {
    display: none;
  }
}
</style>
