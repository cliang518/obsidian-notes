<template>
  <aside class="space-tree-shell">
    <div class="space-tree-head">
      <span>SPACE TREE</span>
      <strong>楼层航道</strong>
      <small>区域接口驱动</small>
    </div>

    <el-tree
      :data="floorData"
      :props="treeProps"
      class="space-tree"
      node-key="tree_key"
      :current-node-key="selectedKey"
      :indent="10"
      default-expand-all
      highlight-current
      show-overflow-tooltip
      @node-click="emit('node-select', $event)"
    >
      <template #default="{ node }">
        <el-tooltip :content="node.label" placement="right" :show-after="350" :disabled="!node.label">
          <span class="space-tree-label">{{ node.label }}</span>
        </el-tooltip>
      </template>
    </el-tree>
  </aside>
</template>

<script setup>
defineProps({
  floorData: {
    type: Array,
    default: () => [],
  },
  treeProps: {
    type: Object,
    default: () => ({ label: "label", children: "children" }),
  },
  selectedKey: {
    type: String,
    default: "all",
  },
});

const emit = defineEmits(["node-select"]);
</script>

<style scoped>
.space-tree-shell {
  flex: 0 0 240px;
  width: 240px;
  min-width: 240px;
  height: 100%;
  overflow: hidden;
  border-right: 1px solid rgba(56, 189, 248, 0.15);
  background: transparent;
  color: #dbeafe;
}

.space-tree-head {
  display: grid;
  gap: 2px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.14);
}

.space-tree-head span {
  color: #38bdf8;
  font-family: Consolas, monospace;
  font-size: 10px;
  letter-spacing: 0.16em;
}

.space-tree-head strong {
  color: #e2e8f0;
  font-size: 13px;
  letter-spacing: 0.08em;
}

.space-tree-head small {
  color: rgba(148, 163, 184, 0.7);
  font-size: 11px;
}

.space-tree {
  height: calc(100% - 56px);
  overflow-y: auto;
  padding: 8px 8px 12px;
  background: transparent;
  color: #409eff;
}

.space-tree-label {
  display: inline-block;
  max-width: 172px;
  overflow: hidden;
  color: #7dd3fc;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.space-tree :deep(.el-tree-node) {
  position: relative;
}

.space-tree :deep(.el-tree-node__children) {
  position: relative;
  margin-left: 3px;
  border-left: 1px solid rgba(56, 189, 248, 0.16);
}

.space-tree :deep(.el-tree-node__content) {
  height: 26px;
  border-radius: 0;
  background: transparent;
}

.space-tree :deep(.el-tree-node__content:hover) {
  background: rgba(56, 189, 248, 0.08);
}

.space-tree :deep(.is-current > .el-tree-node__content) {
  background: rgba(64, 158, 255, 0.14);
  box-shadow: inset 2px 0 0 #409eff;
}

.space-tree::-webkit-scrollbar {
  width: 4px;
}

.space-tree::-webkit-scrollbar-thumb {
  background: rgba(56, 189, 248, 0.22);
}
</style>
