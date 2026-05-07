<template>
  <main class="asset-table-shell">
    <div class="asset-command-strip">
      <el-button size="small" type="primary" @click="c.actions.openDeviceForm()">添加资产</el-button>
      <el-button size="small" @click="c.actions.exportCurrentAssets()">导出当前列表</el-button>
      <el-button size="small" @click="c.actions.resetFilters()">恢复默认</el-button>
      <el-button size="small" type="primary" :loading="c.assetLoading" @click="c.actions.refreshStreamDiagnostics()">
        {{ c.streamDiagnosticButtonLabel }}
      </el-button>
      <el-button size="small" @click="c.actions.quickPlatform('10.0.59.200')">主平台 200</el-button>
      <el-button size="small" @click="c.actions.quickPlatform('10.0.59.205')">205 分平台</el-button>
      <el-button size="small" @click="c.actions.quickBinding('pending')">待补归属</el-button>
      <el-button size="small" :loading="c.fieldValidationImportBusy" @click="c.actions.triggerFieldValidationImport()">
        {{ c.fieldValidationImportBusy ? "导入中..." : "导入现场补录表" }}
      </el-button>
      <el-button size="small" :loading="c.switchGapImportBusy" @click="c.actions.triggerSwitchGapImport()">
        {{ c.switchGapImportBusy ? "导入中..." : "导入交换机核实表" }}
      </el-button>
    </div>

    <div class="asset-metric-rail">
      <div class="metric-cell">
        <span>当前范围</span>
        <strong>{{ c.visibleAssetCount }}</strong>
        <small>{{ c.filters.device_type === "switch" ? "台交换机" : "路摄像头" }}</small>
      </div>
      <div class="metric-cell">
        <span>已选对象</span>
        <strong>{{ c.currentSelectionTitle || "未选择" }}</strong>
        <small>{{ c.currentSelectionMeta }}</small>
      </div>
      <div class="metric-cell">
        <span>状态概览</span>
        <strong>{{ c.filters.device_type === "switch" ? c.switchReviewCount : c.streamAbnormalCount }}</strong>
        <small>{{ c.filters.device_type === "switch" ? "待核实交换机" : "视频待核验" }}</small>
      </div>
      <div class="metric-cell">
        <span>最近刷新</span>
        <strong>{{ c.lastUpdatedLabel }}</strong>
        <small>{{ c.feedbackMessage || "暂无回写提示" }}</small>
      </div>
    </div>

    <section class="asset-filter-terminal">
      <el-form :inline="true" class="asset-filter-form" label-position="top">
        <el-form-item label="设备名">
          <el-input v-model.trim="c.filters.device_name" clearable placeholder="例如 2F 南区摄像头" @keyup.enter="c.actions.applyAssetFilters()" />
        </el-form-item>
        <el-form-item label="IP">
          <el-input v-model.trim="c.filters.device_ip" clearable placeholder="例如 10.0.58.86" @keyup.enter="c.actions.applyAssetFilters()" />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model.trim="c.filters.q" clearable placeholder="摄像头名称、通道号、交换机" @keyup.enter="c.actions.applyAssetFilters()" />
        </el-form-item>
        <el-form-item label="设备类型">
          <el-select v-model="c.filters.device_type" placeholder="请选择" @change="c.actions.loadChannels()">
            <el-option label="摄像头" value="camera" />
            <el-option label="交换机" value="switch" />
          </el-select>
        </el-form-item>
        <el-form-item label="区域">
          <el-select v-model="c.filters.area_id" placeholder="请选择" clearable filterable @change="c.actions.loadChannels()">
            <el-option label="全部区域" value="" />
            <el-option v-for="area in c.areas" :key="area.id" :label="c.helpers.areaOptionLabel(area)" :value="String(area.id)" />
          </el-select>
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="c.filters.source_management_ip" placeholder="请选择" clearable @change="c.actions.loadChannels()">
            <el-option label="全部平台" value="" />
            <el-option label="主平台 200" value="10.0.59.200" />
            <el-option label="205 分平台" value="10.0.59.205" />
          </el-select>
        </el-form-item>
        <template v-if="c.filters.device_type === 'camera'">
          <el-form-item label="归属">
            <el-select v-model="c.filters.switch_binding_state" placeholder="请选择" clearable @change="c.actions.loadChannels()">
              <el-option label="全部归属" value="" />
              <el-option label="已归属交换机" value="bound" />
              <el-option label="待补归属" value="pending" />
            </el-select>
          </el-form-item>
          <el-form-item label="视频验收">
            <el-select v-model="c.filters.stream_probe_state" placeholder="请选择" clearable @change="c.actions.loadChannels()">
              <el-option label="全部验收状态" value="" />
              <el-option label="取流未通过" value="abnormal" />
              <el-option label="取流通过" value="ok" />
              <el-option label="历史通过 / 待复测" value="stale_ok" />
              <el-option label="过期待复测" value="stale_abnormal" />
              <el-option label="未检测" value="unknown" />
            </el-select>
          </el-form-item>
          <el-form-item label="排序">
            <el-select :model-value="c.sortMode" placeholder="请选择" @update:model-value="emit('update:sort-mode', $event)">
              <el-option label="通道号倒序" value="channel_desc" />
              <el-option label="通道号正序" value="channel_asc" />
              <el-option label="IP 正序" value="ip_asc" />
              <el-option label="区域优先" value="area_asc" />
              <el-option label="待补优先" value="binding_first" />
              <el-option label="待核验优先" value="stream_failed_first" />
            </el-select>
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="交换机角色">
            <el-select v-model="c.filters.switch_role_state" placeholder="请选择" clearable @change="c.actions.loadChannels()">
              <el-option label="全部角色" value="" />
              <el-option label="接入交换机" value="camera_access" />
              <el-option label="疑似汇聚/级联" value="suspected_aggregation" />
              <el-option label="待现场核实" value="unknown" />
              <el-option label="不可达 / Telnet 关闭" value="unreachable" />
              <el-option label="系统已自动标记" value="auto_flagged" />
            </el-select>
          </el-form-item>
          <el-form-item label="排序">
            <el-select :model-value="c.switchSortMode" placeholder="请选择" @update:model-value="emit('update:switch-sort-mode', $event)">
              <el-option label="IP 正序" value="ip_asc" />
              <el-option label="疑似汇聚优先" value="aggregation_first" />
              <el-option label="接入交换机优先" value="access_first" />
              <el-option label="命中摄像头优先" value="camera_match_desc" />
              <el-option label="L2 MAC 多的优先" value="mac_desc" />
            </el-select>
          </el-form-item>
        </template>
        <el-form-item>
          <div class="filter-actions">
            <el-button size="small" type="primary" :loading="c.assetLoading" @click="c.actions.applyAssetFilters()">立即筛选</el-button>
            <el-button size="small" :disabled="c.assetLoading" @click="c.actions.resetFilters()">清空</el-button>
            <el-button size="small" @click="c.actions.exportCurrentAssets()">导出</el-button>
            <el-button size="small" @click="c.actions.selectFirstVisible()">定位首条</el-button>
          </div>
        </el-form-item>
      </el-form>
    </section>

    <section class="asset-table-terminal">
      <div class="list-toolbar">
        <div>
          <p class="eyebrow">{{ c.filters.device_type === "switch" ? "SWITCH LIST" : "CAMERA LIST" }}</p>
          <h3>{{ c.filters.device_type === "switch" ? "交换机清单" : "摄像头清单" }}</h3>
          <span>第 {{ c.page }} / {{ c.totalPages }} 页，每页 {{ c.pageSize }} {{ c.filters.device_type === "switch" ? "台" : "路" }}</span>
        </div>
        <div class="pager">
          <el-button size="small" @click="c.actions.ensureSelectedPage()">定位已选项</el-button>
          <el-button size="small" :disabled="c.page <= 1" @click="c.actions.prevPage()">上一页</el-button>
          <el-button size="small" :disabled="c.page >= c.totalPages" @click="c.actions.nextPage()">下一页</el-button>
        </div>
      </div>

      <div class="asset-table-scroll">
        <el-table
          :data="c.tableRows"
          height="100%"
          v-loading="c.assetLoading"
          stripe
          highlight-current-row
          class="asset-table"
          @row-click="emit('row-click', $event)"
        >
          <el-table-column v-if="c.filters.device_type === 'camera'" label="点位 / 状态" min-width="250">
            <template #default="scope">
              <div class="table-cell-stack">
                <strong>{{ c.helpers.cameraTitle(scope.row) }}</strong>
                <span class="table-cell-sub">{{ scope.row.camera_label || scope.row.camera_ip || "-" }}</span>
                <el-tag size="small" :type="c.helpers.assetStatusTagType(scope.row)">{{ c.helpers.assetStatusLabel(scope.row) }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="c.filters.device_type === 'camera'" label="IP / 通道 / 平台" min-width="220">
            <template #default="scope">
              <div class="table-cell-stack">
                <span class="mono">{{ scope.row.camera_ip || "-" }}</span>
                <span>通道 {{ scope.row.channel_no || "-" }}</span>
                <span>{{ c.helpers.platformLabel(scope.row) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="c.filters.device_type === 'camera'" label="区域 / 精度" min-width="200">
            <template #default="scope">
              <div class="table-cell-stack">
                <span>{{ c.helpers.shortArea(scope.row.area_menu_label || scope.row.area_display_name || scope.row.direct_area) }}</span>
                <el-tag v-if="c.helpers.areaAccuracyLabel(scope.row)" size="small" effect="plain">{{ c.helpers.areaAccuracyLabel(scope.row) }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="c.filters.device_type === 'camera'" label="交换机 / 端口" min-width="220">
            <template #default="scope">
              <div class="table-cell-stack">
                <span>{{ scope.row.switch_label || scope.row.switch_ip || "未归属" }}</span>
                <span class="table-cell-sub">{{ scope.row.switch_port_name ? `端口 ${scope.row.switch_port_name}` : "待现场补齐" }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="c.filters.device_type === 'camera'" label="归属 / 验收" min-width="200">
            <template #default="scope">
              <div class="table-cell-stack">
                <span>{{ c.helpers.bindingLabel(scope.row) }}</span>
                <span class="table-cell-sub">{{ c.helpers.streamProbeDisplayLabel(scope.row) || "未检测" }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="c.filters.device_type === 'camera'" label="操作" min-width="320">
            <template #default="scope">
              <div class="table-actions">
                <el-button size="small" @click.stop="c.actions.selectChannel(scope.row); c.actions.openPreview(scope.row)">预览</el-button>
                <el-button size="small" @click.stop="c.actions.selectChannel(scope.row); c.actions.refreshSelectedSnapshot()">快照</el-button>
                <el-button size="small" @click.stop="c.actions.selectChannel(scope.row); c.actions.openBindingDialog(scope.row)">归属</el-button>
                <el-button size="small" @click.stop="c.actions.selectChannel(scope.row); c.actions.openDeviceForm(scope.row)">编辑</el-button>
                <el-button size="small" @click.stop="c.actions.selectChannel(scope.row); c.actions.openSelectedChannelTopology()">拓扑</el-button>
              </div>
            </template>
          </el-table-column>

          <el-table-column v-if="c.filters.device_type === 'switch'" label="交换机 / 状态" min-width="250">
            <template #default="scope">
              <div class="table-cell-stack">
                <strong>{{ c.helpers.clean(scope.row.hostname || scope.row.display_name || scope.row.management_ip || "-") }}</strong>
                <span class="table-cell-sub">{{ c.helpers.clean(scope.row.display_name || scope.row.hostname || scope.row.management_ip || "-") }}</span>
                <el-tag size="small" :type="c.helpers.assetStatusTagType(scope.row)">{{ c.helpers.assetStatusLabel(scope.row) }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="c.filters.device_type === 'switch'" label="管理 IP / 厂商 / 型号" min-width="240">
            <template #default="scope">
              <div class="table-cell-stack">
                <span class="mono">{{ scope.row.management_ip || "-" }}</span>
                <span>{{ c.helpers.clean(scope.row.vendor || "-") }}</span>
                <span>{{ c.helpers.clean(scope.row.model || "-") }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="c.filters.device_type === 'switch'" label="区域 / 角色" min-width="200">
            <template #default="scope">
              <div class="table-cell-stack">
                <span>{{ c.helpers.clean(scope.row.area_display_name || scope.row.area_name || "-") }}</span>
                <span class="table-cell-sub">{{ scope.row.topology_role_label || "待现场核实" }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="c.filters.device_type === 'switch'" label="探测 / 来源" min-width="200">
            <template #default="scope">
              <div class="table-cell-stack">
                <span>{{ c.helpers.healthStateLabel(scope.row.health_state) }}</span>
                <span class="table-cell-sub">{{ c.helpers.clean(scope.row.primary_source_type || "manual") }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="c.filters.device_type === 'switch'" label="操作" min-width="300">
            <template #default="scope">
              <div class="table-actions">
                <el-button size="small" :disabled="c.switchProbeBusy" @click.stop="c.actions.selectSwitch(scope.row); c.actions.probeSelectedSwitch()">探测</el-button>
                <el-button size="small" :disabled="!scope.row.management_ip" @click.stop="c.actions.selectSwitch(scope.row); c.actions.openSelectedSwitchTopology()">拓扑</el-button>
                <el-button size="small" @click.stop="c.actions.selectSwitch(scope.row); c.actions.openExistingDeviceForm(scope.row)">编辑</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="asset-table-footer">
        <el-pagination
          :current-page="c.page"
          :page-size="c.pageSize"
          :total="c.visibleAssetCount"
          layout="total, prev, pager, next, jumper"
          small
          @current-change="emit('update:page', $event)"
        />
      </div>
    </section>
  </main>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  context: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(["row-click", "update:sort-mode", "update:switch-sort-mode", "update:page"]);
const c = computed(() => props.context);
</script>

<style scoped>
.asset-table-shell {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  background: transparent;
  color: #dbeafe;
}

.asset-command-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.14);
}

.asset-metric-rail {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: 8px;
  border: 1px solid rgba(56, 189, 248, 0.15);
  background: #080b14;
}

.metric-cell {
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 7px 10px;
  border-right: 1px solid rgba(56, 189, 248, 0.12);
}

.metric-cell:last-child {
  border-right: 0;
}

.metric-cell span,
.metric-cell small {
  overflow: hidden;
  color: rgba(148, 163, 184, 0.76);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-cell strong {
  overflow: hidden;
  color: #e2e8f0;
  font-family: Consolas, monospace;
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-filter-terminal {
  margin-top: 8px;
  padding: 8px 10px 2px;
  border: 1px solid rgba(56, 189, 248, 0.15);
  background: transparent;
}

.asset-filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 10px;
  align-items: flex-end;
}

.asset-filter-form :deep(.el-form-item) {
  width: 150px;
  margin: 0;
}

.asset-filter-form :deep(.el-form-item__label) {
  margin-bottom: 2px;
  color: #7dd3fc;
  font-size: 10px;
  letter-spacing: 0.08em;
}

.asset-filter-form :deep(.el-input__wrapper),
.asset-filter-form :deep(.el-select__wrapper) {
  min-height: 28px;
  border-radius: 0;
  background: #080b14;
  box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.15);
}

.filter-actions {
  display: flex;
  gap: 6px;
}

.asset-table-terminal {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  margin-top: 8px;
  border: 1px solid rgba(56, 189, 248, 0.15);
  background: transparent;
}

.list-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.14);
}

.eyebrow {
  margin: 0 0 2px;
  color: #38bdf8;
  font-family: Consolas, monospace;
  font-size: 10px;
  letter-spacing: 0.16em;
}

.list-toolbar h3 {
  margin: 0;
  color: #e2e8f0;
  font-size: 13px;
}

.list-toolbar span {
  color: rgba(148, 163, 184, 0.72);
  font-size: 11px;
}

.pager {
  display: flex;
  gap: 6px;
}

.asset-table-scroll {
  flex: 1;
  min-height: 280px;
  height: 0;
  overflow: hidden;
}

.asset-table {
  --el-table-bg-color: #080b14;
  --el-table-tr-bg-color: #080b14;
  --el-table-header-bg-color: #05080f;
  --el-table-row-hover-bg-color: rgba(56, 189, 248, 0.08);
  --el-table-border-color: transparent;
  --el-table-text-color: #dbeafe;
  --el-table-header-text-color: #38bdf8;
  height: 100%;
  font-size: 12px;
}

.asset-table :deep(.el-table__cell) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
}

.asset-table :deep(th.el-table__cell) {
  color: #38bdf8;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.asset-table :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.table-cell-stack {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.table-cell-stack strong,
.table-cell-stack span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-cell-sub {
  color: rgba(148, 163, 184, 0.72);
  font-size: 11px;
}

.mono {
  font-family: Consolas, monospace;
}

.table-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.asset-table-footer {
  display: flex;
  justify-content: flex-end;
  padding: 6px 10px;
  border-top: 1px solid rgba(56, 189, 248, 0.12);
}

.asset-table-scroll :deep(.el-table__body-wrapper)::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.asset-table-scroll :deep(.el-table__body-wrapper)::-webkit-scrollbar-thumb {
  background: rgba(56, 189, 248, 0.28);
}

@media (max-width: 1300px) {
  .asset-metric-rail {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
