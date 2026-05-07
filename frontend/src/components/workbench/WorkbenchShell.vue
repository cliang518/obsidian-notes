<template>
  <section class="workbench-shell" :style="shellStyle">
    <header class="workbench-toolbar">
      <div class="workbench-title">
        <slot name="title" />
      </div>
      <div v-if="$slots.actions" class="workbench-actions">
        <slot name="actions" />
      </div>
    </header>

    <section v-if="$slots.summary" class="workbench-summary">
      <slot name="summary" />
    </section>

    <section v-if="$slots.roadmap" class="workbench-roadmap">
      <slot name="roadmap" />
    </section>

    <main class="workbench-main" :class="layoutClass">
      <aside class="workbench-side workbench-side-left">
        <slot name="left" />
      </aside>
      <section class="workbench-center">
        <slot />
      </section>
      <aside class="workbench-side workbench-side-right">
        <slot name="right" />
      </aside>
    </main>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  leftWidth: {
    type: String,
    default: "292px",
  },
  rightWidth: {
    type: String,
    default: "340px",
  },
  maxWidth: {
    type: String,
    default: "1880px",
  },
});

const layoutClass = computed(() => ({
  "has-left": true,
  "has-right": true,
}));

const shellStyle = computed(() => ({
  "--workbench-left-width": props.leftWidth,
  "--workbench-right-width": props.rightWidth,
  "--workbench-max-width": props.maxWidth,
}));
</script>

<style scoped>
.workbench-shell {
  display: grid;
  gap: 14px;
  overflow-x: hidden;
}

.workbench-toolbar,
.workbench-summary,
.workbench-roadmap,
.workbench-main {
  max-width: var(--workbench-max-width);
  width: 100%;
  margin: 0 auto;
}

.workbench-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: end;
}

.workbench-title {
  min-width: 0;
}

.workbench-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.workbench-summary,
.workbench-roadmap {
  min-width: 0;
}

.workbench-main {
  display: grid;
  grid-template-columns:
    minmax(248px, var(--workbench-left-width))
    minmax(0, 1fr)
    minmax(300px, var(--workbench-right-width));
  gap: 14px;
  align-items: stretch;
  min-height: calc(100vh - 166px);
  position: relative;
  isolation: isolate;
}

.workbench-side,
.workbench-center {
  min-width: 0;
  min-height: 0;
  position: relative;
  overflow-x: hidden;
}

.workbench-center {
  z-index: 1;
}

.workbench-side {
  z-index: 2;
}

.workbench-side > *,
.workbench-center > * {
  max-width: 100%;
}

@media (max-width: 1760px) {
  .workbench-main {
    grid-template-columns: minmax(248px, var(--workbench-left-width)) minmax(0, 1fr);
  }

  .workbench-side-right {
    grid-column: 1 / -1;
  }
}

@media (max-width: 1280px) {
  .workbench-toolbar,
  .workbench-main {
    grid-template-columns: 1fr;
  }
}
</style>
