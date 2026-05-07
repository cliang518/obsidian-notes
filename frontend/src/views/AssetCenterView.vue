<template>
  <div class="asset-page-wrapper" style="height: calc(100vh - 80px); overflow: hidden; background: #0a0a0a;">
    <el-container style="height: 100%; width: 100%; overflow: hidden;">
      <el-aside width="240px" style="width: 240px; min-width: 240px; max-width: 300px; flex: 0 0 240px; flex-shrink: 0; background: transparent; border-right: 1px solid rgba(255, 255, 255, 0.1); overflow: hidden;" class="asset-floor-aside">
        <div class="asset-floor-panel">
          <div class="asset-floor-head">
            <p class="eyebrow">SPACE TREE</p>
            <h3>楼层导航</h3>
            <span>由资产区域接口生成的真实空间树</span>
          </div>
          <el-tree
            :data="floorData"
            :props="floorTreeProps"
            style="background: transparent; color: #409EFF;"
            class="asset-floor-tree"
            node-key="tree_key"
            :current-node-key="selectedFloorKey"
            :indent="10"
            default-expand-all
            highlight-current
            show-overflow-tooltip
            @node-click="handleNodeClick"
          >
            <template #default="{ node }">
              <el-tooltip :content="node.label" placement="right" :show-after="350" :disabled="!node.label">
                <span class="asset-tree-label">{{ node.label }}</span>
              </el-tooltip>
            </template>
          </el-tree>
        </div>
      </el-aside>

      <el-container class="asset-content-shell" style="height: 100%; flex: 1; min-width: 0; overflow: hidden;">
        <el-main class="asset-main-shell asset-primary-col" style="flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; overflow: hidden; padding: 20px;">
            <div class="asset-primary-stack">
              <div class="asset-slim-toolbar">
                <el-button size="small" type="primary" @click="openDeviceForm()">添加资产</el-button>
                <el-button size="small" @click="exportCurrentAssets">导出当前列表</el-button>
                <el-button size="small" @click="resetFilters">恢复默认</el-button>
                <el-button size="small" type="primary" :loading="assetLoading" @click="refreshStreamDiagnostics">{{ streamDiagnosticButtonLabel }}</el-button>
                <el-button size="small" @click="quickPlatform('10.0.59.200')">主平台 200</el-button>
                <el-button size="small" @click="quickPlatform('10.0.59.205')">205 分平台</el-button>
                <el-button size="small" @click="quickBinding('pending')">待补归属</el-button>
                <el-button size="small" :loading="fieldValidationImportBusy" @click="triggerFieldValidationImport">
                  {{ fieldValidationImportBusy ? '导入中...' : '导入现场补录表' }}
                </el-button>
                <el-button size="small" :loading="switchGapImportBusy" @click="triggerSwitchGapImport">
                  {{ switchGapImportBusy ? '导入中...' : '导入交换机核实表' }}
                </el-button>
                <input ref="fieldValidationInputRef" type="file" accept=".csv,text/csv" style="display: none" @change="handleFieldValidationImport" />
                <input ref="switchGapInputRef" type="file" accept=".csv,text/csv" style="display: none" @change="handleSwitchGapImport" />
              </div>

              <div class="asset-kpi-grid">
                <article class="metric-card">
                  <span>当前范围</span>
                  <strong>{{ visibleAssetCount }}</strong>
                  <small>{{ filters.device_type === 'switch' ? '台交换机' : '路摄像头' }}</small>
                </article>
                <article class="metric-card">
                  <span>已选对象</span>
                  <strong>{{ currentSelectionTitle || '未选择' }}</strong>
                  <small>{{ currentSelectionMeta }}</small>
                </article>
                <article class="metric-card">
                  <span>状态概览</span>
                  <strong>{{ filters.device_type === 'switch' ? switchReviewCount : streamAbnormalCount }}</strong>
                  <small>{{ filters.device_type === 'switch' ? '待核实交换机' : '视频待核验' }}</small>
                </article>
                <article class="metric-card">
                  <span>最近刷新</span>
                  <strong>{{ lastUpdatedLabel }}</strong>
                  <small>{{ feedbackMessage || '暂无回写提示' }}</small>
                </article>
              </div>

              <el-card class="asset-filter-panel" shadow="never">
                <el-form :inline="true" class="asset-filter-form" label-position="top">
                  <el-form-item label="设备名">
                    <el-input v-model.trim="filters.device_name" clearable placeholder="例如 2F 南区摄像头" @keyup.enter="applyAssetFilters" />
                  </el-form-item>
                  <el-form-item label="IP">
                    <el-input v-model.trim="filters.device_ip" clearable placeholder="例如 10.0.58.86" @keyup.enter="applyAssetFilters" />
                  </el-form-item>
                  <el-form-item label="关键词">
                    <el-input v-model.trim="filters.q" clearable placeholder="摄像头名称、通道号、交换机" @keyup.enter="applyAssetFilters" />
                  </el-form-item>
                  <el-form-item label="设备类型">
                    <el-select v-model="filters.device_type" placeholder="请选择" @change="loadChannels">
                      <el-option label="摄像头" value="camera" />
                      <el-option label="交换机" value="switch" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="区域">
                    <el-select v-model="filters.area_id" placeholder="请选择" clearable filterable @change="loadChannels">
                      <el-option label="全部区域" value="" />
                      <el-option v-for="area in areas" :key="area.id" :label="areaOptionLabel(area)" :value="String(area.id)" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="平台">
                    <el-select v-model="filters.source_management_ip" placeholder="请选择" clearable @change="loadChannels">
                      <el-option label="全部平台" value="" />
                      <el-option label="主平台 200" value="10.0.59.200" />
                      <el-option label="205 分平台" value="10.0.59.205" />
                    </el-select>
                  </el-form-item>
                  <template v-if="filters.device_type === 'camera'">
                    <el-form-item label="归属">
                      <el-select v-model="filters.switch_binding_state" placeholder="请选择" clearable @change="loadChannels">
                        <el-option label="全部归属" value="" />
                        <el-option label="已归属交换机" value="bound" />
                        <el-option label="待补归属" value="pending" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="视频验收">
                      <el-select v-model="filters.stream_probe_state" placeholder="请选择" clearable @change="loadChannels">
                        <el-option label="全部验收状态" value="" />
                        <el-option label="取流未通过" value="abnormal" />
                        <el-option label="取流通过" value="ok" />
                        <el-option label="历史通过 / 待复测" value="stale_ok" />
                        <el-option label="过期待复测" value="stale_abnormal" />
                        <el-option label="未检测" value="unknown" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="排序">
                      <el-select v-model="sortMode" placeholder="请选择">
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
                      <el-select v-model="filters.switch_role_state" placeholder="请选择" clearable @change="loadChannels">
                        <el-option label="全部角色" value="" />
                        <el-option label="接入交换机" value="camera_access" />
                        <el-option label="疑似汇聚/级联" value="suspected_aggregation" />
                        <el-option label="待现场核实" value="unknown" />
                        <el-option label="不可达 / Telnet 关闭" value="unreachable" />
                        <el-option label="系统已自动标记" value="auto_flagged" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="排序">
                      <el-select v-model="switchSortMode" placeholder="请选择">
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
                      <el-button size="small" type="primary" :loading="assetLoading" @click="applyAssetFilters">立即筛选</el-button>
                      <el-button :disabled="assetLoading" @click="resetFilters">清空</el-button>
                      <el-button @click="exportCurrentAssets">导出</el-button>
                      <el-button @click="selectFirstVisible">定位首条</el-button>
                    </div>
                  </el-form-item>
                </el-form>
              </el-card>

              <el-card class="asset-list-panel" shadow="never">
                <template #header>
                  <div class="list-toolbar">
                    <div>
                      <p class="eyebrow">{{ filters.device_type === 'switch' ? 'SWITCH LIST' : 'CAMERA LIST' }}</p>
                      <h3>{{ filters.device_type === 'switch' ? '交换机清单' : '摄像头清单' }}</h3>
                      <span>第 {{ page }} / {{ totalPages }} 页，每页 {{ pageSize }} {{ filters.device_type === 'switch' ? '台' : '路' }}</span>
                    </div>
                    <div class="pager">
                      <el-button size="small" @click="ensureSelectedPage">定位已选项</el-button>
                      <el-button size="small" :disabled="page <= 1" @click="prevPage">上一页</el-button>
                      <el-button size="small" :disabled="page >= totalPages" @click="nextPage">下一页</el-button>
                    </div>
                  </div>
                </template>

                <div class="asset-table-scroll">
                  <el-table
                    :data="tableRows"
                    height="100%"
                    v-loading="assetLoading"
                    stripe
                    border
                    highlight-current-row
                    class="asset-table"
                    @row-click="onAssetRowClick"
                  >
                    <el-table-column v-if="filters.device_type === 'camera'" label="点位 / 状态" min-width="250">
                      <template #default="scope">
                        <div class="table-cell-stack">
                          <strong>{{ cameraTitle(scope.row) }}</strong>
                          <span class="table-cell-sub">{{ scope.row.camera_label || scope.row.camera_ip || '-' }}</span>
                          <el-tag size="small" :type="assetStatusTagType(scope.row)">{{ assetStatusLabel(scope.row) }}</el-tag>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="filters.device_type === 'camera'" label="IP / 通道 / 平台" min-width="220">
                      <template #default="scope">
                        <div class="table-cell-stack">
                          <span class="mono">{{ scope.row.camera_ip || '-' }}</span>
                          <span>通道 {{ scope.row.channel_no || '-' }}</span>
                          <span>{{ platformLabel(scope.row) }}</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="filters.device_type === 'camera'" label="区域 / 精度" min-width="200">
                      <template #default="scope">
                        <div class="table-cell-stack">
                          <span>{{ shortArea(scope.row.area_menu_label || scope.row.area_display_name || scope.row.direct_area) }}</span>
                          <el-tag v-if="areaAccuracyLabel(scope.row)" size="small" effect="plain">{{ areaAccuracyLabel(scope.row) }}</el-tag>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="filters.device_type === 'camera'" label="交换机 / 端口" min-width="220">
                      <template #default="scope">
                        <div class="table-cell-stack">
                          <span>{{ scope.row.switch_label || scope.row.switch_ip || '未归属' }}</span>
                          <span class="table-cell-sub">{{ scope.row.switch_port_name ? `端口 ${scope.row.switch_port_name}` : '待现场补齐' }}</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="filters.device_type === 'camera'" label="归属 / 验收" min-width="200">
                      <template #default="scope">
                        <div class="table-cell-stack">
                          <span>{{ bindingLabel(scope.row) }}</span>
                          <span class="table-cell-sub">{{ streamProbeDisplayLabel(scope.row) || '未检测' }}</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="filters.device_type === 'camera'" label="操作" min-width="320">
                      <template #default="scope">
                        <div class="table-actions">
                          <el-button size="small" @click.stop="selectChannel(scope.row); openPreview(scope.row)">预览</el-button>
                          <el-button size="small" @click.stop="selectChannel(scope.row); refreshSelectedSnapshot()">快照</el-button>
                          <el-button size="small" @click.stop="selectChannel(scope.row); openBindingDialog(scope.row)">归属</el-button>
                          <el-button size="small" @click.stop="selectChannel(scope.row); openDeviceForm(scope.row)">编辑</el-button>
                          <el-button size="small" @click.stop="selectChannel(scope.row); openSelectedChannelTopology()">拓扑</el-button>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="filters.device_type === 'switch'" label="交换机 / 状态" min-width="250">
                      <template #default="scope">
                        <div class="table-cell-stack">
                          <strong>{{ clean(scope.row.hostname || scope.row.display_name || scope.row.management_ip || '-') }}</strong>
                          <span class="table-cell-sub">{{ clean(scope.row.display_name || scope.row.hostname || scope.row.management_ip || '-') }}</span>
                          <el-tag size="small" :type="assetStatusTagType(scope.row)">{{ assetStatusLabel(scope.row) }}</el-tag>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="filters.device_type === 'switch'" label="管理 IP / 厂商 / 型号" min-width="240">
                      <template #default="scope">
                        <div class="table-cell-stack">
                          <span class="mono">{{ scope.row.management_ip || '-' }}</span>
                          <span>{{ clean(scope.row.vendor || '-') }}</span>
                          <span>{{ clean(scope.row.model || '-') }}</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="filters.device_type === 'switch'" label="区域 / 角色" min-width="200">
                      <template #default="scope">
                        <div class="table-cell-stack">
                          <span>{{ clean(scope.row.area_display_name || scope.row.area_name || '-') }}</span>
                          <span class="table-cell-sub">{{ scope.row.topology_role_label || '待现场核实' }}</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="filters.device_type === 'switch'" label="探测 / 来源" min-width="200">
                      <template #default="scope">
                        <div class="table-cell-stack">
                          <span>{{ healthStateLabel(scope.row.health_state) }}</span>
                          <span class="table-cell-sub">{{ clean(scope.row.primary_source_type || 'manual') }}</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="filters.device_type === 'switch'" label="操作" min-width="300">
                      <template #default="scope">
                        <div class="table-actions">
                          <el-button size="small" :disabled="switchProbeBusy" @click.stop="selectSwitch(scope.row); probeSelectedSwitch()">探测</el-button>
                          <el-button size="small" :disabled="!scope.row.management_ip" @click.stop="selectSwitch(scope.row); openSelectedSwitchTopology()">拓扑</el-button>
                          <el-button size="small" @click.stop="selectSwitch(scope.row); openExistingDeviceForm(scope.row)">编辑</el-button>
                        </div>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>

                <div class="asset-table-footer">
                  <el-pagination
                    v-model:current-page="page"
                    :page-size="pageSize"
                    :total="visibleAssetCount"
                    layout="total, prev, pager, next, jumper"
                    background
                    @current-change="selectFirstVisible"
                  />
                </div>
              </el-card>
            </div>
        </el-main>

        <el-aside width="400px" style="position: sticky; top: 0; height: 100%; overflow-y: auto; width: 400px; min-width: 400px; max-width: 400px; border-left: 1px solid rgba(255, 255, 255, 0.1); background: rgba(25, 25, 25, 0.7); backdrop-filter: blur(15px);" class="asset-side-sticky">
            <div class="asset-side-panel">
              <el-card class="selected-overview asset-detail-panel" shadow="never" style="background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(15px);">
                <el-scrollbar class="asset-detail-scrollbar">
                  <article v-if="feedbackMessage" class="asset-toast">
                    <strong>{{ feedbackMessage }}</strong>
                    <span>最近刷新：{{ lastUpdatedLabel }}</span>
                  </article>

                  <template v-if="filters.device_type === 'camera' && selectedChannel">
                    <div class="selected-head">
                      <div>
                        <p class="eyebrow">SELECTED CAMERA</p>
                        <h3>{{ cameraTitle(selectedChannel) }}</h3>
                        <span class="mono">{{ selectedChannel.camera_ip || '-' }}</span>
                      </div>
                      <el-tag :type="assetStatusTagType(selectedChannel)">{{ assetStatusLabel(selectedChannel) }}</el-tag>
                    </div>

                    <div class="summary-kpis">
                      <article class="summary-chip"><span>视频验收</span><strong>{{ streamProbeDisplayLabel(selectedChannel) || '未扫描' }}</strong></article>
                      <article class="summary-chip"><span>链路置信</span><strong>{{ selectedChannel.topology_confidence ? `${Math.round(selectedChannel.topology_confidence * 100)}%` : '待确认' }}</strong></article>
                      <article class="summary-chip"><span>所属平台</span><strong>{{ platformLabel(selectedChannel) }}</strong></article>
                      <article class="summary-chip"><span>区域精度</span><strong>{{ areaAccuracyLabel(selectedChannel) || '常规口径' }}</strong></article>
                    </div>

                    <div class="primary-ops">
                      <el-button type="primary" @click="openPreview(selectedChannel)">打开预览窗口</el-button>
                      <el-button @click="refreshSelectedSnapshot">刷新快照</el-button>
                      <el-button @click="openBindingDialog(selectedChannel)">修改链路归属</el-button>
                      <el-button @click="openDeviceForm(selectedChannel)">编辑资产</el-button>
                      <el-button @click="copyRtsp(selectedChannel)">复制 RTSP</el-button>
                    </div>

                    <div class="preview-card">
                      <div class="preview-head">
                        <div>
                          <strong>实时快照</strong>
                          <span>{{ selectedChannel.snapshot_capture_enabled ? '来自 RTSP 当前帧' : '当前通道暂不可抓帧' }}</span>
                        </div>
                        <el-button size="small" @click="refreshSelectedSnapshot">刷新快照</el-button>
                      </div>
                      <div class="snapshot-stage">
                        <img v-if="selectedSnapshotUrl" :src="selectedSnapshotUrl" :alt="selectedChannel.camera_ip || 'snapshot'" class="snapshot-image" />
                        <div v-else class="snapshot-placeholder">当前通道暂时抓不到实时快照，请检查 RTSP 地址、账号密码与网络链路。</div>
                      </div>
                      <div class="preview-actions">
                        <el-button @click="openSnapshot(selectedChannel)">放大快照</el-button>
                        <el-button :disabled="!selectedChannel.switch_ip" @click="openSelectedChannelTopology">在拓扑中查看</el-button>
                        <el-button type="danger" @click="archiveSelectedDevice">归档当前资产</el-button>
                      </div>
                    </div>

                    <div class="detail-section">
                      <div class="section-mini-head">
                        <strong>链路归属</strong>
                        <span>{{ selectedChannel.topology_confidence ? `置信度 ${Math.round(selectedChannel.topology_confidence * 100)}%` : '待确认' }}</span>
                      </div>
                      <div class="link-card" :class="{ muted: selectedChannel.switch_binding_state !== 'bound' }">
                        <div><label>交换机</label><strong>{{ clean(selectedChannel.switch_label || selectedChannel.switch_ip || '待补归属') }}</strong></div>
                        <div><label>端口 / VLAN</label><strong>{{ selectedChannel.switch_port_name || '-' }}<template v-if="selectedChannel.switch_port_vlan_id"> / VLAN {{ selectedChannel.switch_port_vlan_id }}</template></strong></div>
                        <div><label>归属来源</label><strong>{{ topologyEvidenceLabel(selectedChannel) }}</strong></div>
                        <p>{{ clean(selectedChannel.topology_evidence_summary || '暂无链路证据，请通过拓扑补齐或现场核验。') }}</p>
                      </div>
                    </div>

                    <div class="detail-section">
                      <div class="section-mini-head">
                        <strong>视频验收证据</strong>
                        <el-button size="small" @click="copyDiagnostic(selectedChannel)">复制摘要</el-button>
                      </div>
                      <div class="rtsp-box">
                        <label>主码流 RTSP</label>
                        <p class="mono">{{ selectedChannel.rtsp_main || '当前通道没有主码流地址' }}</p>
                      </div>
                      <div class="stream-diagnostic-card" :class="streamStatusClass(selectedChannel)">
                        <div>
                          <strong>{{ streamProbeDisplayLabel(selectedChannel) || '未扫描' }}</strong>
                          <span>最近扫描：{{ formatProbeTime(selectedChannel.stream_probe_checked_at) }}</span>
                        </div>
                        <p>{{ streamAdvice(selectedChannel) }}</p>
                        <small v-if="selectedChannel.stream_probe_error">{{ clean(selectedChannel.stream_probe_error) }}</small>
                      </div>
                      <p class="diagnostic-scope-note">这里是资产验收证据，只证明最近一次视频取流是否可用；不会直接生成告警、工单或通知。是否进入告警中心，由连续失败、持续时间、影响范围和网络抖动规则统一判断。</p>
                    </div>

                    <div class="detail-section">
                      <div class="section-mini-head"><strong>基础资料</strong><span>{{ sourceLineageLabel(selectedChannel) }}</span></div>
                      <div class="detail-grid">
                        <div><label>所属平台</label><p>{{ platformLabel(selectedChannel) }}</p></div>
                        <div><label>通道号</label><p>{{ selectedChannel.channel_no || '-' }}</p></div>
                        <div>
                          <label>区域</label>
                          <div class="detail-area-stack">
                            <p>{{ clean(selectedChannel.area_menu_label || selectedChannel.area_display_name || selectedChannel.direct_area || '-') }}</p>
                            <span v-if="areaAccuracyLabel(selectedChannel)" class="area-badge">{{ areaAccuracyLabel(selectedChannel) }}</span>
                          </div>
                          <small class="detail-area-note">{{ areaScopeNote(selectedChannel) }}</small>
                        </div>
                        <div><label>平台状态</label><p>{{ platformStatusLabel(selectedChannel.direct_platform_status) }}</p></div>
                      </div>
                      <div class="maintenance-actions">
                        <el-button @click="openDeviceForm(null, selectedChannel)">按当前通道补建资产</el-button>
                      </div>
                    </div>
                  </template>

                  <template v-else-if="filters.device_type === 'switch' && selectedSwitch">
                    <div class="selected-head">
                      <div>
                        <p class="eyebrow">SELECTED SWITCH</p>
                        <h3>{{ clean(selectedSwitch.hostname || selectedSwitch.display_name || '-') }}</h3>
                        <span class="mono">{{ selectedSwitch.management_ip || '-' }}</span>
                      </div>
                      <el-tag :type="assetStatusTagType(selectedSwitch)">{{ assetStatusLabel(selectedSwitch) }}</el-tag>
                    </div>

                    <div class="summary-kpis">
                      <article class="summary-chip"><span>实时探测</span><strong>{{ healthStateLabel(selectedSwitch.live_probe_status) }}</strong></article>
                      <article class="summary-chip"><span>拓扑角色</span><strong>{{ clean(selectedSwitch.topology_role_label || selectedSwitch.topology_gap_label || '待确认') }}</strong></article>
                      <article class="summary-chip"><span>命中摄像头</span><strong>{{ selectedSwitch.live_probe_camera_match_count || 0 }}</strong></article>
                      <article class="summary-chip"><span>L2 MAC</span><strong>{{ selectedSwitch.live_probe_l2_mac_count || 0 }}</strong></article>
                    </div>

                    <div class="primary-ops">
                      <el-button type="primary" :loading="switchProbeBusy" @click="probeSelectedSwitch">{{ switchProbeBusy ? '实采中...' : '实时探测交换机' }}</el-button>
                      <el-button :disabled="!selectedSwitch.management_ip" @click="openSelectedSwitchTopology">切到拓扑核实</el-button>
                      <el-button @click="openExistingDeviceForm(selectedSwitch)">编辑交换机资产</el-button>
                    </div>

                    <div class="detail-section">
                      <div class="section-mini-head">
                        <strong>实时探测</strong>
                        <span>{{ selectedSwitch.live_probe_checked_at ? selectedSwitch.live_probe_checked_at.replace('T', ' ') : '尚未实采' }}</span>
                      </div>
                      <div v-if="selectedSwitch.topology_role_label" class="switch-judgement-banner" :class="{ warning: selectedSwitch.topology_auto_flagged }">
                        <strong>{{ selectedSwitch.topology_role_label }}</strong>
                        <span>{{ clean(selectedSwitch.topology_judgement_summary || '系统已根据交换机实采结果自动标记。') }}</span>
                      </div>
                      <div class="detail-grid">
                        <div><label>探测状态</label><p>{{ healthStateLabel(selectedSwitch.live_probe_status) }}</p></div>
                        <div><label>版本</label><p>{{ clean(selectedSwitch.live_probe_version_text || '-') }}</p></div>
                        <div><label>Telnet</label><p class="mono">{{ clean(selectedSwitch.live_probe_telnet_status || '-') }}</p></div>
                        <div><label>HTTP / HTTPS</label><p class="mono">{{ clean(selectedSwitch.live_probe_http_status || '-') }} / {{ clean(selectedSwitch.live_probe_https_status || '-') }}</p></div>
                        <div><label>ARP 条目</label><p>{{ selectedSwitch.live_probe_arp_entry_count || 0 }}</p></div>
                        <div><label>命中摄像头</label><p>{{ selectedSwitch.live_probe_camera_match_count || 0 }}</p></div>
                        <div><label>自动判定</label><p>{{ clean(selectedSwitch.topology_gap_label || '-') }}</p></div>
                        <div><label>拓扑角色</label><p>{{ clean(selectedSwitch.topology_role_label || '-') }}</p></div>
                      </div>
                      <div class="link-card">
                        <div><label>L2 MAC 条目</label><strong>{{ selectedSwitch.live_probe_l2_mac_count || 0 }}</strong></div>
                        <p>{{ clean(selectedSwitch.live_probe_error_message || '本次实采未返回错误信息。') }}</p>
                      </div>
                    </div>

                    <div class="detail-section">
                      <div class="section-mini-head"><strong>基础资料</strong><span>{{ clean(selectedSwitch.primary_source_type || 'manual') }}</span></div>
                      <div class="detail-grid">
                        <div><label>区域</label><p>{{ clean(selectedSwitch.area_display_name || selectedSwitch.area_name || '-') }}</p></div>
                        <div><label>厂商</label><p>{{ clean(selectedSwitch.vendor || '-') }}</p></div>
                        <div><label>型号</label><p>{{ clean(selectedSwitch.model || '-') }}</p></div>
                        <div><label>资产状态</label><p>{{ deviceStatusLabel(selectedSwitch.device_status) }}</p></div>
                      </div>
                    </div>

                    <div class="detail-section">
                      <div class="section-mini-head"><strong>网络信息</strong><span>{{ healthStateLabel(selectedSwitch.health_state) }}</span></div>
                      <div class="detail-grid">
                        <div><label>管理 IP</label><p class="mono">{{ selectedSwitch.management_ip || '-' }}</p></div>
                        <div><label>业务 IP</label><p class="mono">{{ selectedSwitch.service_ip || '-' }}</p></div>
                        <div><label>MAC</label><p class="mono">{{ clean(selectedSwitch.mac_address || '-') }}</p></div>
                        <div><label>序列号</label><p>{{ clean(selectedSwitch.serial_number || '-') }}</p></div>
                      </div>
                    </div>

                    <div class="detail-section">
                      <div class="section-mini-head"><strong>备注</strong></div>
                      <div class="link-card">
                        <p>{{ clean(selectedSwitch.notes || '暂无备注') }}</p>
                      </div>
                    </div>
                  </template>

                  <template v-else>
                    <article class="empty-state detail-empty detail-empty-card">
                      <p class="eyebrow">{{ filters.device_type === 'switch' ? 'SELECT A SWITCH' : 'SELECT A CAMERA' }}</p>
                      <strong>{{ visibleAssetCount > 0 ? '右侧处理区已就绪，先从中间清单选中对象。' : '当前筛选范围里还没有可处理对象。' }}</strong>
                      <span>{{ visibleAssetCount > 0 ? currentSelectionGuide : '可以先恢复默认筛选，或直接新增资产后再继续处理。' }}</span>
                      <div class="primary-ops">
                        <el-button v-if="visibleAssetCount > 0" type="primary" @click="selectFirstVisible">定位当前页第一项</el-button>
                        <el-button @click="resetFilters">恢复默认筛选</el-button>
                        <el-button @click="openDeviceForm()">添加资产</el-button>
                      </div>
                    </article>
                  </template>
                </el-scrollbar>
              </el-card>
            </div>
        </el-aside>
      </el-container>
    </el-container>

    <div v-if="previewDialog.visible" class="dialog-backdrop" @click.self="closePreviewDialog">
      <div class="dialog-shell video-dialog-shell">
        <div class="dialog-head">
          <div><strong>{{ cameraTitle(previewDialog.channel) || "视频预览" }}</strong><span>{{ previewDialog.channel?.camera_ip || "-" }}</span></div>
          <button class="ghost-button" @click="closePreviewDialog">关闭</button>
        </div>
        <div class="dialog-tabs">
          <button class="ghost-button" :class="{ active: previewDialog.mode === 'snapshot' }" @click="previewDialog.mode = 'snapshot'">实时快照</button>
          <button class="ghost-button" :class="{ active: previewDialog.mode === 'flv' }" @click="previewDialog.mode = 'flv'">RTSP 直播</button>
          <button class="ghost-button" @click="refreshDialogSnapshot">刷新快照</button>
        </div>
        <div class="dialog-stage">
          <template v-if="previewDialog.mode === 'snapshot'">
            <img v-if="dialogSnapshotUrl" :src="dialogSnapshotUrl" class="dialog-stage-image" alt="snapshot" />
            <div v-else class="snapshot-placeholder">当前通道暂时抓不到实时快照。</div>
          </template>
          <template v-else>
            <video ref="flvVideoRef" class="dialog-stage-video" controls autoplay muted playsinline @loadeddata="markFlvReady"></video>
            <div v-if="flvMessage" class="dialog-hint">{{ flvMessage }}</div>
          </template>
        </div>
      </div>
    </div>

    <div v-if="bindingDialog.visible" class="dialog-backdrop" @click.self="closeBindingDialog">
      <div class="dialog-shell device-dialog-shell compact-dialog-shell">
        <div class="dialog-head">
          <div>
            <strong>修改现场链路归属</strong>
            <span>用于现场确认摄像头换到新交换机端口后的人工修正，会覆盖该摄像头当前展示链路。</span>
          </div>
          <button class="ghost-button" @click="closeBindingDialog">关闭</button>
        </div>

        <div class="device-form-grid">
          <label>
            <span>摄像头</span>
            <input :value="bindingDialog.cameraLabel" class="text-input" disabled />
          </label>
          <label>
            <span>摄像头 IP</span>
            <input :value="bindingDialog.cameraIp" class="text-input mono" disabled />
          </label>
          <label>
            <span>交换机 IP</span>
            <input v-model.trim="bindingForm.switch_ip" class="text-input mono" placeholder="例如 10.0.68.5" />
          </label>
          <label>
            <span>端口号</span>
            <input v-model.trim="bindingForm.port_name" class="text-input mono" placeholder="例如 2" />
          </label>
          <label>
            <span>VLAN，可选</span>
            <input v-model.trim="bindingForm.vlan_id" class="text-input mono" placeholder="不知道可留空" />
          </label>
          <label>
            <span>现场备注，可选</span>
            <input v-model.trim="bindingForm.evidence_note" class="text-input" placeholder="例如 巡检确认已改到2号口" />
          </label>
        </div>

        <div class="dialog-actions">
          <button class="action-btn" @click="submitBindingDialog">保存链路修正</button>
          <button class="ghost-button" @click="closeBindingDialog">取消</button>
          <span>{{ bindingDialog.message }}</span>
        </div>
      </div>
    </div>

    <div v-if="deviceDialog.visible" class="dialog-backdrop" @click.self="closeDeviceDialog">
      <div class="dialog-shell device-dialog-shell">
        <div class="dialog-head">
          <div>
            <strong>{{ deviceDialog.editingId ? "编辑资产资料" : "添加现场资产" }}</strong>
            <span>现场核实后可补全名称、IP、区域、厂家型号、MAC 和备注。</span>
          </div>
          <button class="ghost-button" @click="closeDeviceDialog">关闭</button>
        </div>

        <div class="device-form-grid">
          <label>
            <span>设备类型</span>
            <select v-model="deviceForm.device_type" class="text-input">
              <option value="camera">摄像头</option>
              <option value="switch">交换机</option>
              <option value="nvr">录像机</option>
              <option value="decoder">解码器</option>
              <option value="server">服务器</option>
              <option value="gateway">网关</option>
              <option value="platform_node">平台节点</option>
            </select>
          </label>
          <label>
            <span>显示名称 / 点位名称</span>
            <input v-model.trim="deviceForm.hostname" class="text-input" placeholder="例如 2F 南区电梯口摄像头" />
          </label>
          <label>
            <span>管理 IP</span>
            <input v-model.trim="deviceForm.management_ip" class="text-input mono" placeholder="例如 10.0.58.86" />
          </label>
          <label>
            <span>业务 IP / 服务 IP</span>
            <input v-model.trim="deviceForm.service_ip" class="text-input mono" placeholder="可选" />
          </label>
          <label>
            <span>区域</span>
            <select v-model="deviceForm.area_id" class="text-input">
              <option :value="null">未指定区域</option>
              <option v-for="area in areas" :key="area.id" :value="area.id">{{ areaOptionLabel(area) }}</option>
            </select>
          </label>
          <label>
            <span>厂家</span>
            <input v-model.trim="deviceForm.vendor" class="text-input" placeholder="例如 海康 / 大华 / 锐捷" />
          </label>
          <label>
            <span>型号</span>
            <input v-model.trim="deviceForm.model" class="text-input" placeholder="设备型号" />
          </label>
          <label>
            <span>MAC 地址</span>
            <input v-model.trim="deviceForm.mac_address" class="text-input mono" placeholder="可选" />
          </label>
          <label>
            <span>健康状态</span>
            <select v-model="deviceForm.health_state" class="text-input">
              <option value="unknown">待确认</option>
              <option value="online">在线</option>
              <option value="offline">离线</option>
              <option value="warning">异常</option>
              <option value="archived">已归档</option>
            </select>
          </label>
          <label>
            <span>资产状态</span>
            <select v-model="deviceForm.device_status" class="text-input">
              <option value="manual">人工维护</option>
              <option value="verified">现场已核实</option>
              <option value="discovered">系统发现</option>
              <option value="imported">导入资产</option>
              <option value="archived">已归档</option>
            </select>
          </label>
          <label>
            <span>来源类型</span>
            <select v-model="deviceForm.primary_source_type" class="text-input">
              <option value="manual">人工维护</option>
              <option value="jvss">JVSS 平台</option>
              <option value="tg_cos">TG/COS</option>
              <option value="switch_scan">交换机扫描</option>
              <option value="hikvision_nvr">海康录像机</option>
              <option value="imported">导入数据</option>
            </select>
          </label>
          <label>
            <span>序列号</span>
            <input v-model.trim="deviceForm.serial_number" class="text-input" placeholder="可选" />
          </label>
          <label class="full-span">
            <span>现场备注</span>
            <textarea v-model.trim="deviceForm.notes" class="text-area" rows="4" placeholder="记录现场位置、弱电井、归属交换机、核实人、核实时间等。" />
          </label>
        </div>

        <div class="dialog-actions">
          <button class="action-btn" @click="submitDeviceForm">{{ deviceDialog.editingId ? "保存资产" : "添加资产" }}</button>
          <button class="ghost-button" @click="closeDeviceDialog">取消</button>
          <span>{{ deviceDialog.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import flvjs from "flv.js";
import {
  archiveDevice,
  buildChannelFlvUrl,
  buildChannelSnapshotUrl,
  createDevice,
  fetchAreas,
  fetchChannels,
  fetchDevices,
  fetchDeviceDetail,
  fetchFieldValidationProgressSummary,
  fetchLatestStreamDiagnosticReportStatus,
  fetchStreamDiagnosticSummary,
  importFieldValidationCameraSheet,
  importFieldValidationSwitchGapSheet,
  importLatestStreamDiagnostics,
  fetchTopologyUnattributedLinks,
  runTopologySwitchLiveProbe,
  updateChannelTopologyBinding,
  updateDevice,
} from "../api/client";
import { downloadFieldValidationTemplate } from "../utils/fieldValidationExport";

const DEFAULT_SOURCE_TYPE = "jvss";
const PAGE_SIZE = 72;
const ASSET_FETCH_LIMIT = 5000;
const ASSET_NAME_FIELDS = [
  "camera_label",
  "channel_name",
  "direct_name",
  "hostname",
  "display_name",
  "parent_label",
  "switch_label",
];
const ASSET_IP_FIELDS = [
  "camera_ip",
  "management_ip",
  "service_ip",
  "switch_ip",
  "source_management_ip",
  "direct_point_ip",
];
const ASSET_GLOBAL_FIELDS = [
  ...ASSET_NAME_FIELDS,
  ...ASSET_IP_FIELDS,
  "area_menu_label",
  "area_display_name",
  "area_name",
  "direct_area",
  "vendor",
  "model",
  "serial_number",
  "notes",
  "note_summary",
  "topology_role_label",
  "topology_gap_label",
];
const ASSET_FLOOR_FIELDS = [
  "area_menu_label",
  "area_display_name",
  "area_name",
  "direct_area",
  "hostname",
  "display_name",
  "camera_label",
  "channel_name",
  "management_ip",
  "camera_ip",
];
const route = useRoute();
const router = useRouter();
const areas = ref([]);
const channels = ref([]);
const selectedChannel = ref(null);
const switchDevices = ref([]);
const selectedSwitch = ref(null);
const assetLoading = ref(false);
const assetLoadError = ref("");
const switchProbeBusy = ref(false);
const fieldValidationImportBusy = ref(false);
const switchGapImportBusy = ref(false);
const feedbackMessage = ref("");
const fieldValidationResult = ref(null);
const fieldValidationProgress = ref(null);
const activeFollowupGroup = ref(null);
const topologyWorkbenchFeedback = ref(null);
const topologyWorkbenchSwitch = ref(null);
const lastUpdatedAt = ref(null);
const streamDiagnosticStatus = ref(null);
const streamDiagnosticSummary = ref(null);
const snapshotSeed = ref(0);
const dialogSnapshotSeed = ref(0);
const flvVideoRef = ref(null);
const fieldValidationInputRef = ref(null);
const switchGapInputRef = ref(null);
const flvMessage = ref("");
const sortMode = ref("channel_desc");
const switchSortMode = ref("ip_asc");
const listViewMode = ref("full");
const page = ref(1);
const pageJumpInput = ref("1");
const pageSize = PAGE_SIZE;
const selectedFloorKey = ref("all");
const selectedFloorScope = ref({ key: "all", label: "全场", terms: [], areaId: "" });
const floorData = ref(createFallbackFloorTree());
const floorTreeProps = { label: "label", children: "children" };
const filters = reactive({
  q: "",
  device_name: "",
  device_ip: "",
  area_id: "",
  source_management_ip: "",
  switch_binding_state: "",
  stream_probe_state: "",
  switch_role_state: "",
  device_type: "camera",
});
const previewDialog = reactive({ visible: false, mode: "snapshot", channel: null });
const deviceDialog = reactive({ visible: false, editingId: null, message: "" });
const bindingDialog = reactive({ visible: false, channelId: null, cameraLabel: "", cameraIp: "", message: "" });
const bindingForm = reactive({ switch_ip: "", port_name: "", vlan_id: "", evidence_note: "" });
const deviceForm = reactive({
  device_type: "camera",
  vendor: "",
  model: "",
  serial_number: "",
  hostname: "",
  management_ip: "",
  service_ip: "",
  mac_address: "",
  area_id: null,
  parent_device_id: null,
  platform_source_id: null,
  health_state: "unknown",
  device_status: "manual",
  source_priority: 50,
  primary_source_type: "manual",
  notes: "",
});
let feedbackTimer = null;
let flvPlayer = null;
let flvStartTimer = null;
let assetRequestSeq = 0;
let switchProbeSeq = 0;
const assetSearchIndexCache = new WeakMap();

const summary200 = computed(() => channels.value.filter((item) => item.source_management_ip === "10.0.59.200").length);
const summary205 = computed(() => channels.value.filter((item) => item.source_management_ip === "10.0.59.205").length);
const boundCount = computed(() => channels.value.filter((item) => item.switch_binding_state === "bound").length);
const pendingCount = computed(() => channels.value.filter((item) => item.switch_binding_state === "pending").length);
const snapshotCount = computed(() => channels.value.filter((item) => item.snapshot_capture_enabled).length);
const streamAbnormalCount = computed(() => Number(streamDiagnosticSummary.value?.abnormal || 0));
const streamHistoricalPassCount = computed(() => Number(streamDiagnosticSummary.value?.stale_ok || 0));
const streamHistoricalAbnormalCount = computed(() => Number(streamDiagnosticSummary.value?.stale_abnormal || 0));
const streamUnknownCount = computed(() => Number(streamDiagnosticSummary.value?.unknown || 0));
const filteredSwitchDevices = computed(() => applySwitchRoleFilter(switchDevices.value).filter(matchesFloorScope).filter(matchesAssetSearch));
const switchCount = computed(() => filteredSwitchDevices.value.length);
const switchAccessCount = computed(() => switchDevices.value.filter((item) => item.topology_role_guess === "camera_access").length);
const switchAggregationCount = computed(() => switchDevices.value.filter((item) => item.topology_role_guess === "suspected_aggregation").length);
const switchReviewCount = computed(() => switchDevices.value.filter((item) => item.topology_role_guess === "unknown").length);
const switchUnreachableCount = computed(() => switchDevices.value.filter((item) => item.topology_role_guess === "unreachable").length);
const selectedSnapshotUrl = computed(() => snapshotUrl(selectedChannel.value, snapshotSeed.value));
const dialogSnapshotUrl = computed(() => snapshotUrl(previewDialog.channel, dialogSnapshotSeed.value));
const activeFollowupGroupLabel = computed(() => {
  const group = activeFollowupGroup.value;
  if (!group) return "";
  return group.display_label || [group.bucket_label, group.suggested_area || "待现场判定区域", group.camera_ip_range || ""].filter(Boolean).join(" / ");
});
const visibleChannels = computed(() => {
  const group = activeFollowupGroup.value;
  const rows = !group ? channels.value : channels.value.filter((item) => cameraMatchesFollowupGroup(item, group));
  return rows.filter(matchesFloorScope).filter(matchesAssetSearch);
});
const sortedChannels = computed(() => sortChannels(visibleChannels.value));
const sortedSwitchDevices = computed(() => {
  const rows = [...filteredSwitchDevices.value];
  rows.sort(sortSwitchDevices);
  return rows;
});
const totalPages = computed(() => {
  const total = filters.device_type === "switch" ? sortedSwitchDevices.value.length : sortedChannels.value.length;
  return Math.max(1, Math.ceil(total / pageSize));
});
const currentTablePage = computed(() => {
  const rawPage = Number(page.value);
  const normalizedPage = Number.isFinite(rawPage) ? Math.floor(rawPage) : 1;
  return Math.min(totalPages.value, Math.max(1, normalizedPage));
});
const tableSliceStart = computed(() => (currentTablePage.value - 1) * pageSize);
const tableSliceEnd = computed(() => tableSliceStart.value + pageSize);
const pagedChannels = computed(() => sortedChannels.value.slice(tableSliceStart.value, tableSliceEnd.value));
const pagedSwitchDevices = computed(() => sortedSwitchDevices.value.slice(tableSliceStart.value, tableSliceEnd.value));
const tableRows = computed(() => {
  const rows = filters.device_type === "switch" ? pagedSwitchDevices.value : pagedChannels.value;
  console.log("tableRows 渲染切片:", {
    deviceType: filters.device_type,
    page: page.value,
    currentTablePage: currentTablePage.value,
    pageSize,
    start: tableSliceStart.value,
    end: tableSliceEnd.value,
    total: filters.device_type === "switch" ? sortedSwitchDevices.value.length : sortedChannels.value.length,
    returned: rows.length,
    first: rows[0] || null,
  });
  return rows;
});
const assetSearchKeywords = computed(() => ({
  name: normalizeKeyword(filters.device_name),
  ip: normalizeKeyword(filters.device_ip),
  global: normalizeKeyword(filters.q),
}));
const visibleAssetCount = computed(() => (filters.device_type === "switch" ? sortedSwitchDevices.value.length : sortedChannels.value.length));
const pageWindowLabel = computed(() => {
  if (!visibleAssetCount.value) return "当前没有命中结果";
  const start = (page.value - 1) * pageSize + 1;
  const end = Math.min(page.value * pageSize, visibleAssetCount.value);
  return `当前显示 ${start}-${end} / 共 ${visibleAssetCount.value}`;
});
const activeSortLabel = computed(() => {
  if (filters.device_type === "switch") {
    const switchMap = {
      ip_asc: "IP 正序",
      aggregation_first: "疑似汇聚优先",
      access_first: "接入交换机优先",
      camera_match_desc: "命中摄像头优先",
      mac_desc: "L2 MAC 多的优先",
    };
    return switchMap[switchSortMode.value] || "IP 正序";
  }
  const cameraMap = {
    channel_desc: "通道号倒序",
    channel_asc: "通道号正序",
    ip_asc: "IP 正序",
    area_asc: "区域优先",
    binding_first: "待补优先",
    stream_failed_first: "待核验优先",
  };
  return cameraMap[sortMode.value] || "通道号倒序";
});
const batchActionTitle = computed(() => {
  if (filters.device_type === "switch") {
    return selectedSwitch.value
      ? `围绕 ${clean(selectedSwitch.value.hostname || selectedSwitch.value.display_name || selectedSwitch.value.management_ip || "-")} 做角色核实`
      : "先筛出待核实交换机，再进入单台批量核实";
  }
  return activeFollowupGroupLabel.value || "围绕取流、归属和现场回写做批量验收";
});
const batchActionHint = computed(() => {
  if (filters.device_type === "switch") {
    return "先把交换机分成接入、疑似汇聚和不可达，再对单台交换机做待归属链路核实。";
  }
  return "先筛待补归属或视频异常，再把现场补录表回导，资产与拓扑会一起更新。";
});
const currentSelectionTitle = computed(() => {
  if (filters.device_type === "switch") {
    return selectedSwitch.value ? clean(selectedSwitch.value.hostname || selectedSwitch.value.display_name || selectedSwitch.value.management_ip || "-") : "";
  }
  return selectedChannel.value ? cameraTitle(selectedChannel.value) : "";
});
const currentSelectionMeta = computed(() => {
  if (filters.device_type === "switch") {
    if (!selectedSwitch.value) {
      return visibleAssetCount.value > 0 ? `当前范围还有 ${visibleAssetCount.value} 台交换机待查看。` : "当前筛选结果为空。";
    }
    return `${selectedSwitch.value.management_ip || "-"} / ${clean(selectedSwitch.value.topology_role_label || selectedSwitch.value.area_display_name || selectedSwitch.value.area_name || "待确认")}`;
  }
  if (!selectedChannel.value) {
    return visibleAssetCount.value > 0 ? `当前范围还有 ${visibleAssetCount.value} 路摄像头待查看。` : "当前筛选结果为空。";
  }
  return `${selectedChannel.value.camera_ip || "-"} / ${platformLabel(selectedChannel.value)} / ${clean(selectedChannel.value.switch_ip || "待补归属")}`;
});
const currentSelectionGuide = computed(() => {
  if (filters.device_type === "switch") {
    return "先确认交换机角色和实采状态，再补它与楼层、摄像头和上联光口的关系。";
  }
  return "先看快照和取流，再核交换机归属；现场改口后直接从右侧修正链路。";
});
const lastUpdatedLabel = computed(() => {
  if (!lastUpdatedAt.value) return "等待首次加载";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(lastUpdatedAt.value);
});
const streamDiagnosticButtonLabel = computed(() => {
  if (streamDiagnosticStatus.value?.pending) return "同步最新取流验收";
  return "重载取流验收";
});
const streamFollowupPlan = computed(() => {
  if (streamAbnormalCount.value > 0) {
    return {
      state: "abnormal",
      title: "先处理当前取流未通过",
      description: `当前还有 ${streamAbnormalCount.value} 路摄像头取流未通过，这批才是最接近现状的验收问题。`,
      hint: "优先核 RTSP 地址、账号密码、交换机端口、供电和网络路径。",
      actionLabel: "先筛当前异常",
    };
  }
  if (streamHistoricalAbnormalCount.value > 0) {
    return {
      state: "stale_abnormal",
      title: "再复测历史异常",
      description: `有 ${streamHistoricalAbnormalCount.value} 路曾经失败，但结果已过期，不能直接当当前故障处理。`,
      hint: "建议重新扫 RTSP，或逐台点快照 / 直播窗口做复测。",
      actionLabel: "筛历史异常",
    };
  }
  if (streamHistoricalPassCount.value > 0) {
    return {
      state: "stale_ok",
      title: "补复测历史通过",
      description: `有 ${streamHistoricalPassCount.value} 路只剩“历史通过”证据，这类点位最容易让维护人员误以为当前没问题。`,
      hint: "历史通过不等于现在正常，适合做收尾复测或抽检。",
      actionLabel: "筛历史通过",
    };
  }
  if (streamUnknownCount.value > 0) {
    return {
      state: "unknown",
      title: "补齐未验收设备",
      description: `还有 ${streamUnknownCount.value} 路没有导入取流验收结果，当前只能靠快照和直播临时判断。`,
      hint: "建议先补一轮扫描，再决定是否进入异常处理。",
      actionLabel: "筛未验收",
    };
  }
  return {
    state: "",
    title: "当前验收闭环已清晰",
    description: "当前列表里没有待优先处理的取流验收缺口，可以继续做拓扑核实或现场补录。",
    hint: "如果你刚完成一轮整改，可以再重载一次取流验收作为复核。",
    actionLabel: "查看全部",
  };
});

onMounted(async () => {
  await loadBaseData();
  await loadFieldValidationProgress();
  await syncRouteContext();
});

onBeforeUnmount(() => {
  destroyFlvPlayer();
  if (feedbackTimer) clearTimeout(feedbackTimer);
});

watch(() => route.fullPath, syncRouteContext);
watch(page, (value) => {
  const normalizedPage = Math.min(totalPages.value, Math.max(1, Number(value) || 1));
  if (normalizedPage !== value) {
    page.value = normalizedPage;
    return;
  }
  pageJumpInput.value = String(normalizedPage);
});
watch(totalPages, (value) => {
  if (page.value > value) page.value = value;
  if (page.value < 1) page.value = 1;
});
watch(sortMode, () => {
  page.value = 1;
  if (filters.device_type === "switch") {
    if (selectedSwitch.value && !pagedSwitchDevices.value.some((item) => item.id === selectedSwitch.value.id)) {
      selectSwitch(pagedSwitchDevices.value[0] || sortedSwitchDevices.value[0] || null);
    }
    return;
  }
  if (selectedChannel.value && !pagedChannels.value.some((item) => item.id === selectedChannel.value.id)) {
    selectChannel(pagedChannels.value[0] || sortedChannels.value[0] || null);
  }
});
watch(switchSortMode, () => {
  if (filters.device_type !== "switch") return;
  page.value = 1;
  if (selectedSwitch.value && !pagedSwitchDevices.value.some((item) => item.id === selectedSwitch.value.id)) {
    selectSwitch(pagedSwitchDevices.value[0] || sortedSwitchDevices.value[0] || null);
  }
});
watch(() => filters.switch_role_state, () => {
  if (filters.device_type !== "switch") return;
  page.value = 1;
  if (selectedSwitch.value && !pagedSwitchDevices.value.some((item) => item.id === selectedSwitch.value.id)) {
    selectSwitch(pagedSwitchDevices.value[0] || sortedSwitchDevices.value[0] || null);
  }
});
watch(
  () => [filters.device_name, filters.device_ip, filters.q, selectedFloorScope.value.key],
  () => {
    page.value = 1;
    selectFirstVisible();
  },
);
watch(() => [previewDialog.visible, previewDialog.mode, previewDialog.channel?.id], async () => {
  if (!previewDialog.visible || previewDialog.mode !== "flv") {
    destroyFlvPlayer();
    return;
  }
  await initFlvPlayer();
});

function snapshotUrl(channel, seed = 0) {
  if (!channel?.snapshot_capture_enabled) return "";
  return buildChannelSnapshotUrl(channel.id, { refresh: seed > 0, cacheBust: true });
}

function flashMessage(message) {
  feedbackMessage.value = message;
  if (feedbackTimer) clearTimeout(feedbackTimer);
  feedbackTimer = setTimeout(() => { feedbackMessage.value = ""; }, 3500);
}

function formatProgressTime(value) {
  if (!value) return "尚无记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function markTopologyDirty(reason = "asset_changed") {
  try {
    localStorage.setItem("yongjia_topology_dirty_at", JSON.stringify({ reason, at: Date.now() }));
  } catch (error) {
    console.warn("Mark topology dirty failed", error);
  }
}

function quickPlatform(ip) { filters.source_management_ip = ip; page.value = 1; loadChannels(); }
function quickBinding(state) { filters.switch_binding_state = state; page.value = 1; loadChannels(); }
function focusSingleResultIfNeeded() {
  if (filters.device_type === "switch") {
    if (sortedSwitchDevices.value.length === 1) {
      selectSwitch(sortedSwitchDevices.value[0]);
      ensureSelectedPage();
    }
    return;
  }
  if (sortedChannels.value.length === 1) {
    selectChannel(sortedChannels.value[0]);
    ensureSelectedPage();
  }
}
async function applyAssetFilters() {
  page.value = 1;
  await loadChannels();
  focusSingleResultIfNeeded();
}
async function handleFloorNodeClick(node) {
  const scope = buildFloorScope(node);
  selectedFloorKey.value = scope.key;
  selectedFloorScope.value = scope;
  filters.area_id = scope.areaId ? String(scope.areaId) : "";
  activeFollowupGroup.value = null;
  topologyWorkbenchSwitch.value = null;
  page.value = 1;
  await loadChannels();
  selectFirstVisible();
  flashMessage(`已切换到：${scope.label} 楼层导航`);
}

function handleNodeClick(node) {
  handleFloorNodeClick(node);
}
function focusPendingBindings() {
  filters.device_type = "camera";
  filters.switch_binding_state = "pending";
  filters.stream_probe_state = "";
  activeFollowupGroup.value = null;
  topologyWorkbenchSwitch.value = null;
  page.value = 1;
  loadChannels();
  flashMessage("已切换到：待补归属摄像头");
}
async function focusStreamProbeState(state, { silent = false } = {}) {
  filters.device_type = "camera";
  filters.stream_probe_state = state || "";
  activeFollowupGroup.value = null;
  topologyWorkbenchSwitch.value = null;
  page.value = 1;
  await loadChannels();
  if (silent) return;
  const labelMap = {
    abnormal: "当前取流未通过",
    ok: "当前取流通过",
    stale_ok: "历史通过 / 待复测",
    stale_abnormal: "历史异常 / 待复测",
    unknown: "未验收",
    "": "全部验收状态",
  };
  flashMessage(`已切换到：${labelMap[state || ""] || "当前验收视图"}`);
}
function focusSwitchRoleState(state, label = "") {
  filters.device_type = "switch";
  filters.switch_role_state = state || "";
  page.value = 1;
  loadChannels();
  flashMessage(`已切换到：${label || "交换机角色视图"}`);
}
function resetFilters() {
  filters.q = "";
  filters.device_name = "";
  filters.device_ip = "";
  filters.area_id = "";
  filters.source_management_ip = "";
  filters.switch_binding_state = "";
  filters.stream_probe_state = "";
  filters.switch_role_state = "";
  filters.device_type = "camera";
  sortMode.value = "channel_desc";
  switchSortMode.value = "ip_asc";
  selectedFloorKey.value = "all";
  selectedFloorScope.value = { key: "all", label: "全场", terms: [], areaId: "" };
  activeFollowupGroup.value = null;
  topologyWorkbenchSwitch.value = null;
  page.value = 1;
  switchDevices.value = [];
  selectChannel(null);
  loadChannels();
}

function createFallbackFloorTree(label = "区域加载中") {
  return [
    {
      tree_key: "all",
      id: "all",
      label: "全场",
      terms: [],
      children: [
        {
          tree_key: "area-loading",
          id: "area-loading",
          label,
          terms: [],
          disabled: true,
        },
      ],
    },
  ];
}

function areaNodeLabel(area) {
  const baseLabel = clean(area?.menu_label || area?.display_name || area?.summary_label || area?.zone || "");
  const count = Number(area?.camera_count || 0);
  return count > 0 ? `${baseLabel || `区域 ${area?.id || ""}`} (${count})` : baseLabel || `区域 ${area?.id || ""}`;
}

function getOrCreateAreaGroup(map, list, key, label, terms = []) {
  if (map.has(key)) return map.get(key);
  const node = {
    tree_key: key,
    id: key,
    label: label || "未分组",
    terms: terms.map(clean).filter(Boolean),
    children: [],
    _childrenMap: new Map(),
  };
  map.set(key, node);
  list.push(node);
  return node;
}

function createAreaLeafNode(area) {
  const zone = clean(area.zone || area.menu_label || area.display_name || "");
  return {
    tree_key: `area:${area.id}`,
    id: `area:${area.id}`,
    area_id: area.id,
    label: areaNodeLabel(area),
    raw_label: clean(area.menu_label || area.display_name || area.summary_label || zone || ""),
    terms: [area.menu_label, area.display_name, area.summary_label, area.site, area.building, area.floor, area.zone]
      .map(clean)
      .filter(Boolean),
    camera_count: Number(area.camera_count || 0),
  };
}

function insertAreaTreeBranch(parent, segments, area, depth = 0) {
  if (depth >= segments.length) {
    parent.children.push(createAreaLeafNode(area));
    return;
  }
  const segment = segments[depth];
  const map = parent._childrenMap || (parent._childrenMap = new Map());
  const node = getOrCreateAreaGroup(
    map,
    parent.children,
    `${parent.tree_key}:${segment.kind}:${segment.label}`,
    segment.label,
    segment.terms,
  );
  insertAreaTreeBranch(node, segments, area, depth + 1);
}

function finalizeAreaTreeNode(node) {
  delete node._childrenMap;
  if (!Array.isArray(node.children) || !node.children.length) return node;
  node.children = node.children.map(finalizeAreaTreeNode);
  return node;
}

function buildAreaTree(rows = []) {
  const areaRows = Array.isArray(rows) ? rows.filter(Boolean) : [];
  if (!areaRows.length) return createFallbackFloorTree("暂无可用区域");

  const totalCameras = areaRows.reduce((sum, area) => sum + Number(area.camera_count || 0), 0);
  const root = {
    tree_key: "all",
    id: "all",
    label: totalCameras ? `全场 (${totalCameras})` : "全场",
    terms: [],
    children: [],
    _childrenMap: new Map(),
  };

  for (const area of areaRows) {
    const site = clean(area.site || "全场");
    const building = clean(area.building || "未分楼栋");
    const floor = clean(area.floor || "未分楼层");
    insertAreaTreeBranch(root, [
      { kind: "site", label: site, terms: [site] },
      { kind: "building", label: building, terms: [site, building] },
      { kind: "floor", label: floor, terms: [site, building, floor] },
    ], area);
  }

  return [finalizeAreaTreeNode(root)];
}

async function loadBaseData() {
  try {
    const areaRows = await fetchAreas({ only_with_channels: true });
    areas.value = Array.isArray(areaRows) ? areaRows : [];
    floorData.value = buildAreaTree(areas.value);
  } catch (error) {
    console.error("区域列表加载失败:", error);
    areas.value = [];
    floorData.value = createFallbackFloorTree("区域接口不可用");
    flashMessage("区域列表加载失败，已显示区域接口不可用提示。");
  }
  try {
    const [latestReportStatus, summary] = await Promise.all([
      fetchLatestStreamDiagnosticReportStatus(),
      fetchStreamDiagnosticSummary(),
    ]);
    streamDiagnosticStatus.value = latestReportStatus;
    streamDiagnosticSummary.value = summary;
    if (streamDiagnosticStatus.value?.pending) {
      flashMessage(`发现新取流诊断报告：${streamDiagnosticStatus.value.latest_report}，确认后可采用。`);
    }
  } catch (error) {
    console.error(error);
  }
}

async function loadFieldValidationProgress() {
  try {
    fieldValidationProgress.value = await fetchFieldValidationProgressSummary();
  } catch (error) {
    console.error(error);
  }
}

function normalizeAssetResponse(res) {
  if (Array.isArray(res?.data)) return res.data;
  if (Array.isArray(res?.rows)) return res.rows;
  if (Array.isArray(res)) return res;
  return [];
}

function logAssetFetchSuccess(scope, rows) {
  console.log("数据回传成功:", {
    scope,
    count: rows.length,
    data: rows,
    filters: { ...filters },
    floor: selectedFloorScope.value,
  });
}

function logAssetFetchFailure(scope, error) {
  console.error("资产数据请求失败:", {
    scope,
    message: error?.message || String(error),
    response: error?.response?.data || null,
    status: error?.response?.status || null,
  });
}

function createMockCameraRows(count = 10) {
  return Array.from({ length: count }, (_, index) => {
    const no = index + 1;
    return {
      id: `mock-camera-${no}`,
      channel_no: no,
      channel_name: `Mock 通道 ${no}`,
      camera_label: `Mock 摄像头 ${no}`,
      camera_ip: `10.255.0.${no}`,
      parent_label: "Mock 主平台 200",
      source_management_ip: "10.0.59.200",
      area_menu_label: no % 2 ? "1F 南楼 / 西侧监控" : "2F 北区",
      area_display_name: no % 2 ? "1F 南楼 / 西侧监控" : "2F 北区",
      direct_area: no % 2 ? "1F 南楼" : "2F 北区",
      switch_label: "Mock 接入交换机",
      switch_ip: "10.255.1.1",
      switch_port_name: `GE0/0/${no}`,
      switch_binding_state: "bound",
      stream_probe_status: no % 3 === 0 ? "unknown" : "ok",
      stream_probe_label: no % 3 === 0 ? "未检测" : "取流通过",
      channel_status: no % 4 === 0 ? "offline" : "online",
      rtsp_main: `rtsp://mock.local/camera/${no}`,
      snapshot_capture_enabled: false,
      __mock: true,
    };
  });
}

function createMockSwitchRows(count = 10) {
  return Array.from({ length: count }, (_, index) => {
    const no = index + 1;
    return {
      id: `mock-switch-${no}`,
      hostname: `Mock 交换机 ${no}`,
      display_name: `Mock 接入交换机 ${no}`,
      management_ip: `10.255.1.${no}`,
      vendor: "MockVendor",
      model: "Mock-SW",
      area_display_name: no % 2 ? "1F 南楼 / 西侧监控" : "2F 北区",
      area_name: no % 2 ? "1F 南楼" : "2F 北区",
      topology_role_guess: "camera_access",
      topology_role_label: "接入交换机",
      health_state: no % 4 === 0 ? "offline" : "online",
      device_status: "discovered",
      primary_source_type: "mock",
      live_probe_status: no % 4 === 0 ? "offline" : "online",
      live_probe_camera_match_count: no * 3,
      live_probe_l2_mac_count: no * 8,
      __mock: true,
    };
  });
}

function activateMockRows(scope, reason = "接口异常") {
  const rows = scope === "switch" ? createMockSwitchRows() : createMockCameraRows();
  console.warn("Mock 数据兜底已启用:", { scope, reason, count: rows.length, rows });
  if (scope === "switch") {
    switchDevices.value = rows;
    channels.value = [];
    selectSwitch(rows[0] || null);
  } else {
    channels.value = rows;
    switchDevices.value = [];
    selectChannel(rows[0] || null);
  }
  page.value = 1;
  lastUpdatedAt.value = new Date();
  flashMessage(`${reason}，已注入 10 条 Mock 资产用于验证表格渲染链路。`);
}

function effectiveAreaId() {
  return filters.area_id || selectedFloorScope.value?.areaId || "";
}

async function loadChannels(preferredChannelId = null) {
  const requestSeq = ++assetRequestSeq;
  assetLoading.value = true;
  assetLoadError.value = "";
  const areaId = effectiveAreaId();
  try {
    if (filters.device_type === "switch") {
      const rows = await fetchDevices({
        device_type: "switch",
        area_id: areaId || undefined,
        source_management_ip: filters.source_management_ip || undefined,
        limit: ASSET_FETCH_LIMIT,
      })
        .then((res) => {
          const payloadRows = normalizeAssetResponse(res);
          logAssetFetchSuccess("switch", payloadRows);
          return payloadRows;
        })
        .catch((error) => {
          logAssetFetchFailure("switch", error);
          throw error;
        });
      if (requestSeq !== assetRequestSeq) return;
      if (!rows.length) {
        activateMockRows("switch", "交换机接口返回空数组");
        return;
      }
      switchDevices.value = rows || [];
      channels.value = [];
      page.value = 1;
      if (!switchDevices.value.length) {
        selectSwitch(null);
        lastUpdatedAt.value = new Date();
        return;
      }
      const currentId = selectedSwitch.value?.id;
      const targetId = Number(preferredChannelId || 0);
      const targetSwitch =
        switchDevices.value.find((item) => item.id === targetId) ||
        switchDevices.value.find((item) => item.id === currentId) ||
        sortedSwitchDevices.value[0] ||
        switchDevices.value[0] ||
        null;
      selectSwitch(targetSwitch);
      ensureSelectedPage();
      console.log("资产表格绑定检查:", {
        boundVariable: "tableRows",
        rawCount: switchDevices.value.length,
        visibleCount: sortedSwitchDevices.value.length,
        pageCount: tableRows.value.length,
        selected: selectedSwitch.value,
      });
      lastUpdatedAt.value = new Date();
      return;
    }

    const rows = await fetchChannels({
      source_type: DEFAULT_SOURCE_TYPE,
      area_id: areaId || undefined,
      source_management_ip: filters.source_management_ip || undefined,
      switch_binding_state: filters.switch_binding_state || undefined,
      limit: ASSET_FETCH_LIMIT,
    })
      .then((res) => {
        const payloadRows = normalizeAssetResponse(res);
        logAssetFetchSuccess("camera", payloadRows);
        return payloadRows;
      })
      .catch((error) => {
        logAssetFetchFailure("camera", error);
        throw error;
      });
    if (requestSeq !== assetRequestSeq) return;
    if (!rows.length) {
      activateMockRows("camera", "摄像头接口返回空数组");
      return;
    }
    const streamFilteredRows = applyStreamProbeFilter(rows || []);
    channels.value = streamFilteredRows.length ? streamFilteredRows : rows;
    switchDevices.value = [];
    page.value = 1;
    if (!visibleChannels.value.length) {
      activateMockRows("camera", "前端筛选条件导致可见数据为 0");
      lastUpdatedAt.value = new Date();
      return;
    }
    const currentId = selectedChannel.value?.id;
    const targetId = Number(preferredChannelId || 0);
    const targetChannel =
      visibleChannels.value.find((item) => item.id === targetId) ||
      visibleChannels.value.find((item) => item.id === currentId) ||
      sortedChannels.value[0] ||
      visibleChannels.value[0] ||
      null;
    selectChannel(targetChannel);
    ensureSelectedPage();
    console.log("资产表格绑定检查:", {
      boundVariable: "tableRows",
      rawCount: rows.length,
      streamFilteredCount: streamFilteredRows.length,
      visibleCount: sortedChannels.value.length,
      pageCount: tableRows.value.length,
      selected: selectedChannel.value,
      filters: { ...filters },
      floor: selectedFloorScope.value,
    });
    lastUpdatedAt.value = new Date();
  } catch (error) {
    console.error("资产中心 loadChannels 总异常:", error);
    assetLoadError.value = "资产数据加载失败，请稍后重试。";
    if (requestSeq === assetRequestSeq) {
      activateMockRows(filters.device_type === "switch" ? "switch" : "camera", "接口请求失败");
    }
    flashMessage(assetLoadError.value);
  } finally {
    if (requestSeq === assetRequestSeq) {
      assetLoading.value = false;
    }
  }
}

async function refreshStreamDiagnostics() {
  try {
    if (streamDiagnosticStatus.value?.pending) {
      const shouldImport = window.confirm(`发现新取流诊断报告：${streamDiagnosticStatus.value.latest_report}\n是否采用这份最新报告覆盖当前视频验收结果？`);
      if (!shouldImport) return;
    }
    const result = await importLatestStreamDiagnostics();
    const [latestReportStatus, summary] = await Promise.all([
      fetchLatestStreamDiagnosticReportStatus(),
      fetchStreamDiagnosticSummary(),
    ]);
    streamDiagnosticStatus.value = latestReportStatus;
    streamDiagnosticSummary.value = summary;
    await loadChannels(selectedChannel.value?.id || null);
    await nextTick();
    if (streamFollowupPlan.value.state) {
      await focusStreamProbeState(streamFollowupPlan.value.state, { silent: true });
    }
    flashMessage(`取流验收已同步：${result.imported || 0} 路，报告 ${result.report || "-"}；下一步建议：${streamFollowupPlan.value.title}。`);
  } catch (error) {
    console.error(error);
    flashMessage("取流诊断导入失败，请先确认后台已有最新 RTSP 扫描报告。");
  }
}

function triggerFieldValidationImport() {
  if (fieldValidationImportBusy.value) return;
  fieldValidationInputRef.value?.click();
}

async function handleFieldValidationImport(event) {
  const input = event?.target;
  const file = input?.files?.[0];
  if (!file) return;
  fieldValidationImportBusy.value = true;
  try {
    const currentWorkbench = topologyWorkbenchSwitch.value
      ? {
          ip: topologyWorkbenchSwitch.value.ip,
          label: topologyWorkbenchSwitch.value.label || topologyWorkbenchSwitch.value.ip,
          count: Number(topologyWorkbenchSwitch.value.count || 0),
        }
      : null;
    const result = await importFieldValidationCameraSheet(file);
    fieldValidationResult.value = result;
    fieldValidationProgress.value = result.progress_summary || fieldValidationProgress.value;
    activeFollowupGroup.value = null;
    const unresolved = (result.unresolved_ips || []).slice(0, 5).join("、");
    const reduced = result.repair_delta?.area_missing_reduced || 0;
    const reducedGroups = result.repair_delta?.area_task_groups_reduced || 0;
    const nextGroup = result.repair_after?.next_priority_group;
    const nextHint = nextGroup
      ? `，下一批建议 ${nextGroup.segment || "-"} ${nextGroup.camera_ip_range || "-"}`
      : "";
    let workbenchHint = "";
    if (currentWorkbench?.ip) {
      const afterCount = await focusTopologySwitchWorkbench(currentWorkbench.ip, currentWorkbench.label, { silent: true });
      const reducedCount = Math.max(currentWorkbench.count - Number(afterCount || 0), 0);
      topologyWorkbenchFeedback.value = {
        switchIp: currentWorkbench.ip,
        switchLabel: currentWorkbench.label,
        beforeCount: currentWorkbench.count || 0,
        afterCount: Number(afterCount || 0),
        reducedCount,
        matched: result.matched || 0,
      };
      workbenchHint = `；交换机 ${currentWorkbench.label} 剩余 ${afterCount || 0} 条待核实`;
      if (reducedCount > 0) workbenchHint += `，本轮收口 ${reducedCount} 条`;
    } else {
      topologyWorkbenchFeedback.value = null;
    }
    flashMessage(
      `现场补录已回写：匹配 ${result.matched || 0}，补区域 ${result.area_updated || 0}，补 MAC ${result.mac_updated || 0}，修正链路 ${result.binding_updated || 0}，跳过 ${result.skipped || 0}` +
        `，区域缺口减少 ${reduced || 0}，任务包收口 ${reducedGroups || 0}` +
        nextHint +
        workbenchHint +
        (unresolved ? `，未命中示例 ${unresolved}` : "。"),
    );
    if ((result.binding_updated || 0) > 0 || (result.mac_updated || 0) > 0 || (result.area_updated || 0) > 0) markTopologyDirty("field_validation_import");
    await loadChannels(selectedChannel.value?.id || null);
    await loadFieldValidationProgress();
  } catch (error) {
    console.error(error);
    flashMessage("现场补录表导入失败，请确认 CSV 列名和交换机 IP/端口是否正确。");
  } finally {
    fieldValidationImportBusy.value = false;
    if (input) input.value = "";
  }
}

function parseHostRangeToken(token) {
  const raw = String(token || "").trim();
  if (!raw) return null;
  if (raw.includes("-")) {
    const [start, end] = raw.split("-", 2).map((item) => Number(item));
    if (Number.isInteger(start) && Number.isInteger(end)) {
      return { start: Math.min(start, end), end: Math.max(start, end) };
    }
    return null;
  }
  const single = Number(raw);
  if (Number.isInteger(single)) {
    return { start: single, end: single };
  }
  return null;
}

function cameraMatchesFollowupGroup(channel, group) {
  const ip = String(channel?.camera_ip || "").trim();
  if (!ip || !group) return false;
  const host = Number(ip.split(".").pop());
  if (!Number.isInteger(host)) return false;
  const segmentBuckets = Array.isArray(group.segments) && group.segments.length
    ? group.segments
    : [{ segment: group.segment, host_ranges: group.host_ranges || [] }];
  return segmentBuckets.some((bucket) => {
    if (!bucket?.segment || !ip.startsWith(`${bucket.segment}.`)) return false;
    const ranges = Array.isArray(bucket.host_ranges) ? bucket.host_ranges : [];
    if (!ranges.length) return true;
    return ranges.some((token) => {
      const parsed = parseHostRangeToken(token);
      return parsed ? host >= parsed.start && host <= parsed.end : false;
    });
  });
}

function compressHostRanges(hosts) {
  const sorted = [...new Set(hosts.filter((value) => Number.isInteger(value)).sort((a, b) => a - b))];
  if (!sorted.length) return [];
  const ranges = [];
  let start = sorted[0];
  let prev = sorted[0];
  for (let index = 1; index < sorted.length; index += 1) {
    const current = sorted[index];
    if (current === prev + 1) {
      prev = current;
      continue;
    }
    ranges.push(start === prev ? String(start) : `${start}-${prev}`);
    start = current;
    prev = current;
  }
  ranges.push(start === prev ? String(start) : `${start}-${prev}`);
  return ranges;
}

function buildSwitchPendingGroup(switchIp, switchLabel, rows) {
  const buckets = new Map();
  for (const row of rows || []) {
    const ip = String(row.camera_ip || "").trim();
    const parts = ip.split(".");
    if (parts.length !== 4) continue;
    const segment = parts.slice(0, 3).join(".");
    const host = Number(parts[3]);
    if (!Number.isInteger(host)) continue;
    if (!buckets.has(segment)) buckets.set(segment, []);
    buckets.get(segment).push(host);
  }
  const segments = [...buckets.entries()]
    .map(([segment, hosts]) => ({
      segment,
      host_ranges: compressHostRanges(hosts),
      count: hosts.length,
    }))
    .sort((a, b) => b.count - a.count || a.segment.localeCompare(b.segment, "zh-CN"));
  const displayRanges = segments.map((bucket) => `${bucket.segment}.${bucket.host_ranges.join(",")}`).join(" / ");
  return {
    bucket_label: `交换机 ${switchLabel || switchIp}`,
    suggested_area: "待核实链路批量作业",
    camera_ip_range: displayRanges || switchIp,
    switch_ip: switchIp,
    segment: segments[0]?.segment || "",
    host_ranges: segments[0]?.host_ranges || [],
    segments,
    display_label: [switchLabel || switchIp, displayRanges || "待核实摄像头"].filter(Boolean).join(" / "),
  };
}

function focusFollowupGroup(group, { silent = false } = {}) {
  activeFollowupGroup.value = group || null;
  filters.device_type = "camera";
  page.value = 1;
  const matched = visibleChannels.value;
  selectChannel(matched[0] || null);
  ensureSelectedPage();
  if (silent) return;
  flashMessage(`已聚焦剩余任务包：${activeFollowupGroupLabel.value || "当前分组"}`);
}

function clearFollowupGroupFocus() {
  activeFollowupGroup.value = null;
  topologyWorkbenchSwitch.value = null;
  page.value = 1;
  selectChannel(sortedChannels.value[0] || channels.value[0] || null);
  ensureSelectedPage();
}

async function focusTopologySwitchWorkbench(switchIp, switchLabel = "", { silent = false } = {}) {
  if (!switchIp) return;
  if (topologyWorkbenchFeedback.value?.switchIp && topologyWorkbenchFeedback.value.switchIp !== switchIp) {
    topologyWorkbenchFeedback.value = null;
  }
  const payload = await fetchTopologyUnattributedLinks(1000);
  const rows = (payload?.rows || []).filter((item) => String(item.switch_ip || "").trim() === String(switchIp).trim());
  topologyWorkbenchSwitch.value = { ip: switchIp, label: switchLabel || switchIp, count: rows.length, rows };
  if (!rows.length) {
    activeFollowupGroup.value = null;
    if (!silent) flashMessage(`交换机 ${switchLabel || switchIp} 当前没有待核实链路，已打开常规资产视图。`);
    return 0;
  }
  focusFollowupGroup(buildSwitchPendingGroup(switchIp, switchLabel, rows), { silent });
  return rows.length;
}

function exportTopologyWorkbenchSheet() {
  const workbench = topologyWorkbenchSwitch.value;
  if (!workbench?.ip) return;
  const rows = (workbench.rows || []).map((item) => ({
    camera_ip: item.camera_ip || "",
    camera_label: item.camera_label || "",
    current_area: item.zone || "",
    current_switch_ip: item.switch_ip || workbench.ip,
    current_port: item.port_name || "",
    current_vlan: item.vlan_id || "",
    current_zone: item.zone || "",
  }));
  if (!rows.length) {
    flashMessage(`交换机 ${workbench.label || workbench.ip} 当前没有可导出的待核实链路。`);
    return;
  }
  downloadFieldValidationTemplate({
    filename: `switch-field-validation-${(workbench.ip || "unknown").replace(/\./g, "-")}-${Date.now()}.csv`,
    switchLabel: workbench.label || workbench.ip,
    switchIp: workbench.ip,
    rows,
  });
  flashMessage(`已导出 ${workbench.label || workbench.ip} 的专属核实单，可现场填写后直接回导。`);
}

function clearTopologyWorkbench() {
  const nextQuery = { ...route.query };
  delete nextQuery.topology_switch_ip;
  delete nextQuery.topology_switch_label;
  if (!nextQuery.channel_id && nextQuery.switch_binding_state === "pending") {
    delete nextQuery.switch_binding_state;
  }
  topologyWorkbenchSwitch.value = null;
  topologyWorkbenchFeedback.value = null;
  clearFollowupGroupFocus();
  router.replace({ path: route.path, query: nextQuery });
  flashMessage("已退出交换机批量核实视图。");
}

function focusNextFollowupGroup() {
  const group = fieldValidationResult.value?.repair_after?.next_priority_group;
  if (!group) {
    flashMessage("当前没有可聚焦的下一批任务包。");
    return;
  }
  focusFollowupGroup(group);
}

function triggerSwitchGapImport() {
  if (switchGapImportBusy.value) return;
  switchGapInputRef.value?.click();
}

async function handleSwitchGapImport(event) {
  const input = event?.target;
  const file = input?.files?.[0];
  if (!file) return;
  switchGapImportBusy.value = true;
  try {
    const result = await importFieldValidationSwitchGapSheet(file);
    flashMessage(`交换机核实表已回写：匹配 ${result.matched || 0}，写入备注 ${result.noted || 0}，更新状态 ${result.status_updated || 0}。`);
    if ((result.status_updated || 0) > 0 || (result.noted || 0) > 0) markTopologyDirty("switch_gap_import");
    await loadChannels(filters.device_type === "switch" ? selectedSwitch.value?.id || null : selectedChannel.value?.id || null);
  } catch (error) {
    console.error(error);
    flashMessage("交换机核实表导入失败，请确认 CSV 列名和交换机 IP 是否正确。");
  } finally {
    switchGapImportBusy.value = false;
    if (input) input.value = "";
  }
}

async function probeSelectedSwitch() {
  if (!selectedSwitch.value?.management_ip || switchProbeBusy.value) return;
  const probeSeq = ++switchProbeSeq;
  const targetSwitch = { ...selectedSwitch.value };
  switchProbeBusy.value = true;
  try {
    const result = await runTopologySwitchLiveProbe({
      switch_ips: [targetSwitch.management_ip],
      limit: 1,
    });
    if (probeSeq !== switchProbeSeq) return;
    const current = result?.results?.[0];
    markTopologyDirty("switch_live_probe");
    if (current?.probe_status === "ok") {
      flashMessage(`交换机实采完成：${current.management_ip}，ARP ${current.arp_entry_count || 0}，命中摄像头 ${current.camera_match_count || 0}。`);
    } else {
      flashMessage(`交换机实采完成，但存在异常：${current?.error_message || current?.probe_status || "请检查 Telnet/网络"}`);
    }
    await loadChannels(targetSwitch.id);
  } catch (error) {
    if (probeSeq !== switchProbeSeq) return;
    console.error(error);
    flashMessage("交换机实采失败，请检查后台连通性、Telnet 口和密码。");
  } finally {
    if (probeSeq === switchProbeSeq) switchProbeBusy.value = false;
  }
}

async function syncRouteContext() {
  const query = route.query || {};
  const topologySwitchIp = typeof query.topology_switch_ip === "string" ? query.topology_switch_ip.trim() : "";
  const topologySwitchLabel = typeof query.topology_switch_label === "string" ? query.topology_switch_label.trim() : "";
  filters.q = topologySwitchIp ? "" : (typeof query.q === "string" ? query.q.trim() : "");
  filters.area_id = typeof query.area_id === "string" ? query.area_id : "";
  filters.source_management_ip = typeof query.source_management_ip === "string" ? query.source_management_ip : "";
  filters.switch_binding_state = typeof query.switch_binding_state === "string"
    ? query.switch_binding_state
    : (topologySwitchIp ? "pending" : "");
  filters.stream_probe_state = typeof query.stream_probe_state === "string" ? query.stream_probe_state : "";
  filters.device_type = query.device_type === "switch" ? "switch" : "camera";
  const targetChannelId = Number(query.channel_id || 0);
  const targetDeviceId = Number(query.device_id || query.switch_id || 0);
  await loadChannels(filters.device_type === "switch" ? targetDeviceId || null : targetChannelId || null);
  if (filters.device_type === "switch") return;
  if (topologySwitchIp) {
    await focusTopologySwitchWorkbench(topologySwitchIp, topologySwitchLabel);
  } else {
    topologyWorkbenchSwitch.value = null;
  }
  const target = targetChannelId
    ? channels.value.find((item) => item.id === targetChannelId)
    : channels.value.find((item) => item.camera_ip === filters.q || item.camera_label === filters.q) || selectedChannel.value;
  if (target) {
    selectChannel(target);
    ensureSelectedPage();
    if (query.action === "preview") openPreview(target);
    if (query.action === "snapshot") openSnapshot(target);
    if (query.action === "binding") openBindingDialog(target);
  }
}

function selectChannel(channel) {
  resetSelectionOperationState();
  selectedSwitch.value = null;
  selectedChannel.value = channel ? { ...channel } : null;
  snapshotSeed.value = Date.now();
}
function selectSwitch(device) {
  resetSelectionOperationState();
  selectedChannel.value = null;
  previewDialog.channel = null;
  selectedSwitch.value = device ? { ...device } : null;
}

function onAssetRowClick(row) {
  if (!row) return;
  if (filters.device_type === "switch") {
    selectSwitch(row);
    return;
  }
  selectChannel(row);
}

function selectFirstVisible() {
  if (filters.device_type === "switch") {
    selectSwitch(pagedSwitchDevices.value[0] || sortedSwitchDevices.value[0] || null);
    return;
  }
  selectChannel(pagedChannels.value[0] || sortedChannels.value[0] || null);
}

function goToPage() {
  const target = Number(pageJumpInput.value);
  if (!Number.isFinite(target)) {
    pageJumpInput.value = String(page.value);
    return;
  }
  page.value = Math.min(totalPages.value, Math.max(1, Math.floor(target)));
  pageJumpInput.value = String(page.value);
  selectFirstVisible();
}

function openSelectedSwitchWorkbench() {
  if (!selectedSwitch.value?.management_ip) {
    flashMessage("当前没有可进入批量核实的交换机。");
    return;
  }
  focusTopologySwitchWorkbench(
    selectedSwitch.value.management_ip,
    clean(selectedSwitch.value.hostname || selectedSwitch.value.display_name || selectedSwitch.value.management_ip || ""),
  );
}

function openSelectedSwitchTopology() {
  const switchIp = selectedSwitch.value?.management_ip || "";
  if (!switchIp) {
    flashMessage("当前交换机缺少管理 IP，无法跳转拓扑。");
    return;
  }
  router.push({
    path: "/topology",
    query: {
      switch_ip: switchIp,
      switch_label: clean(selectedSwitch.value?.hostname || selectedSwitch.value?.display_name || switchIp),
      from_module: "assets",
      return_device_type: "switch",
      return_q: switchIp,
    },
  });
}

function openBindingDialog(channel) {
  if (!channel?.id) return;
  bindingDialog.visible = true;
  bindingDialog.channelId = channel.id;
  bindingDialog.cameraLabel = cameraTitle(channel);
  bindingDialog.cameraIp = channel.camera_ip || "";
  bindingDialog.message = "请填写现场确认后的交换机端口。";
  Object.assign(bindingForm, {
    switch_ip: channel.switch_ip || "",
    port_name: channel.switch_port_name || "",
    vlan_id: channel.switch_port_vlan_id || "",
    evidence_note: "",
  });
}

function closeBindingDialog() {
  bindingDialog.visible = false;
  bindingDialog.channelId = null;
  bindingDialog.cameraLabel = "";
  bindingDialog.cameraIp = "";
  bindingDialog.message = "";
  Object.assign(bindingForm, { switch_ip: "", port_name: "", vlan_id: "", evidence_note: "" });
}

function openSelectedChannelTopology() {
  const switchIp = selectedChannel.value?.switch_ip || "";
  if (!switchIp) {
    flashMessage("当前摄像头还没有交换机归属，无法跳转拓扑。");
    return;
  }
  router.push({
    path: "/topology",
    query: {
      switch_ip: switchIp,
      switch_label: clean(selectedChannel.value?.switch_label || switchIp),
      from_module: "assets",
      return_device_type: "camera",
      return_q: selectedChannel.value?.camera_ip || "",
      focus_camera_ip: selectedChannel.value?.camera_ip || "",
      focus_camera_label: cameraTitle(selectedChannel.value),
    },
  });
}

async function submitBindingDialog() {
  if (!bindingDialog.channelId) return;
  if (!bindingForm.switch_ip || !bindingForm.port_name) {
    bindingDialog.message = "交换机 IP 和端口号必须填写。";
    return;
  }
  try {
    bindingDialog.message = "正在保存现场链路修正...";
    const result = await updateChannelTopologyBinding(bindingDialog.channelId, { ...bindingForm });
    const updatedChannel = result.channel || null;
    if (updatedChannel) {
      channels.value = channels.value.map((item) => (item.id === updatedChannel.id ? updatedChannel : item));
      selectChannel(updatedChannel);
    } else {
      await loadChannels(bindingDialog.channelId);
    }
    markTopologyDirty("manual_topology_binding");
    flashMessage(`链路已修正：${result.switch_ip || bindingForm.switch_ip} 端口 ${result.port_name || bindingForm.port_name}`);
    closeBindingDialog();
  } catch (error) {
    console.error(error);
    const detail = error?.response?.data?.detail;
    if (detail === "switch_not_found") {
      bindingDialog.message = "保存失败：系统里没有找到这台交换机，请先确认交换机 IP。";
    } else {
      bindingDialog.message = "保存失败，请检查交换机 IP、端口号或后台日志。";
    }
  }
}

function refreshSelectedSnapshot() { snapshotSeed.value = Date.now(); flashMessage("当前快照已刷新。"); }
function openSnapshot(channel) { previewDialog.channel = channel; previewDialog.mode = "snapshot"; previewDialog.visible = true; dialogSnapshotSeed.value = Date.now(); }
function openPreview(channel) { previewDialog.channel = channel; previewDialog.mode = "snapshot"; previewDialog.visible = true; dialogSnapshotSeed.value = Date.now(); }
function closePreviewDialog() { destroyFlvPlayer(); previewDialog.visible = false; previewDialog.mode = "snapshot"; previewDialog.channel = null; }
function refreshDialogSnapshot() { dialogSnapshotSeed.value = Date.now(); flashMessage("弹窗快照已刷新。"); }

function resetDeviceForm() {
  deviceDialog.editingId = null;
  deviceDialog.message = "";
  Object.assign(deviceForm, {
    device_type: "camera",
    vendor: "",
    model: "",
    serial_number: "",
    hostname: "",
    management_ip: "",
    service_ip: "",
    mac_address: "",
    area_id: null,
    parent_device_id: null,
    platform_source_id: null,
    health_state: "unknown",
    device_status: "manual",
    source_priority: 50,
    primary_source_type: "manual",
    notes: "",
  });
}

async function openDeviceForm(channel = null, seedChannel = null) {
  resetDeviceForm();
  const source = channel || seedChannel || null;
  deviceDialog.visible = true;
  if (channel?.camera_asset_id) {
    deviceDialog.message = "正在读取当前摄像头资产资料...";
    try {
      const detail = await fetchDeviceDetail(channel.camera_asset_id);
      fillDeviceForm(detail.device || {});
      deviceDialog.editingId = channel.camera_asset_id;
      deviceDialog.message = "已加载当前摄像头资产资料。";
      return;
    } catch (error) {
      console.error(error);
      deviceDialog.message = "资产详情读取失败，可手工补录。";
    }
  }
  if (source) {
    fillDeviceForm({
      device_type: "camera",
      hostname: cameraTitle(source),
      management_ip: source.camera_ip || "",
      area_id: source.area_id || null,
      primary_source_type: source.camera_source_type || source.source_type || "manual",
      health_state: source.channel_status === "offline" ? "offline" : "unknown",
      device_status: "manual",
      notes: [
        source.direct_area ? `平台区域：${clean(source.direct_area)}` : "",
        source.source_management_ip ? `来源平台：${source.source_management_ip}` : "",
        source.channel_no ? `来源通道：${source.channel_no}` : "",
      ].filter(Boolean).join("\n"),
    });
    deviceDialog.message = "已按当前通道预填，可现场核实后保存。";
  }
}

function fillDeviceForm(device) {
  Object.assign(deviceForm, {
    device_type: device.device_type || "camera",
    vendor: clean(device.vendor || ""),
    model: clean(device.model || ""),
    serial_number: clean(device.serial_number || ""),
    hostname: clean(device.hostname || device.display_name || ""),
    management_ip: device.management_ip || device.ip_address || "",
    service_ip: device.service_ip || "",
    mac_address: clean(device.mac_address || ""),
    area_id: device.area_id || null,
    parent_device_id: device.parent_device_id || null,
    platform_source_id: device.platform_source_id || null,
    health_state: device.health_state || "unknown",
    device_status: device.device_status || "manual",
    source_priority: device.source_priority || 50,
    primary_source_type: device.primary_source_type || device.source_type || "manual",
    notes: clean(device.notes || ""),
  });
}

function closeDeviceDialog() {
  deviceDialog.visible = false;
  resetDeviceForm();
}

async function submitDeviceForm() {
  const payload = {
    ...deviceForm,
    area_id: deviceForm.area_id ? Number(deviceForm.area_id) : null,
    parent_device_id: deviceForm.parent_device_id ? Number(deviceForm.parent_device_id) : null,
    platform_source_id: deviceForm.platform_source_id ? Number(deviceForm.platform_source_id) : null,
    source_priority: Number(deviceForm.source_priority || 50),
  };
  if (!payload.hostname && !payload.management_ip) {
    deviceDialog.message = "至少填写设备名称或管理 IP。";
    return;
  }
  try {
    if (deviceDialog.editingId) {
      await updateDevice(deviceDialog.editingId, payload);
      deviceDialog.message = "资产资料已保存。";
      flashMessage("资产资料已保存。");
    } else {
      await createDevice(payload);
      deviceDialog.message = "资产已添加。";
      flashMessage("资产已添加。");
    }
    markTopologyDirty(deviceDialog.editingId ? "asset_updated" : "asset_created");
    await loadBaseData();
    await loadChannels(selectedChannel.value?.id || null);
  } catch (error) {
    console.error(error);
    const detail = error?.response?.data?.detail;
    if (detail === "management_ip_exists") {
      deviceDialog.message = "保存失败：该管理 IP 已存在于资产台账。";
    } else {
      deviceDialog.message = "保存失败，请检查字段或后端日志。";
    }
  }
}

async function archiveSelectedDevice() {
  const deviceId = selectedChannel.value?.camera_asset_id;
  if (!deviceId) {
    flashMessage("当前通道没有绑定可归档的摄像头资产。");
    return;
  }
  const ok = window.confirm("确认归档当前摄像头资产？归档不会物理删除历史通道和拓扑记录，但资产会退出日常维护视图。");
  if (!ok) return;
  try {
    const result = await archiveDevice(deviceId);
    flashMessage(`资产已归档，关联通道 ${result.linked_channels || 0}，关联链路 ${result.linked_topology || 0}。`);
    markTopologyDirty("asset_archived");
    await loadChannels();
  } catch (error) {
    console.error(error);
    flashMessage("资产归档失败，请检查权限或后端日志。");
  }
}

async function copyRtsp(channel) {
  if (!channel?.rtsp_main) { flashMessage("当前通道没有可复制的 RTSP 地址。"); return; }
  try { await navigator.clipboard.writeText(channel.rtsp_main); flashMessage("RTSP 地址已复制。"); } catch (error) { console.error(error); flashMessage("复制 RTSP 失败，请检查浏览器权限。"); }
}

async function copyDiagnostic(channel) {
  const lines = [
    `平台：${platformLabel(channel)}`, `通道：${channel.channel_no || "-"}`, `摄像头：${cameraTitle(channel)}`, `IP：${channel.camera_ip || "-"}`,
    `区域：${clean(channel.area_display_name || channel.direct_area || "-")}`, `交换机：${clean(channel.switch_label || channel.switch_ip || "待补归属")}`,
    `端口：${channel.switch_port_name || "-"}`, `VLAN：${channel.switch_port_vlan_id || "-"}`, `视频验收：${streamProbeDisplayLabel(channel) || "未检测"}`,
    `诊断时间：${formatProbeTime(channel.stream_probe_checked_at)}`, `来源链路：${sourceLineageLabel(channel)}`, `RTSP：${channel.rtsp_main || "-"}`,
  ];
  try { await navigator.clipboard.writeText(lines.join("\n")); flashMessage("诊断摘要已复制。"); } catch (error) { console.error(error); flashMessage("复制诊断摘要失败。"); }
}

function destroyFlvPlayer() {
  if (flvStartTimer) { clearTimeout(flvStartTimer); flvStartTimer = null; }
  flvMessage.value = "";
  if (!flvPlayer) return;
  try { flvPlayer.pause?.(); flvPlayer.unload?.(); flvPlayer.detachMediaElement?.(); flvPlayer.destroy?.(); } catch (error) { console.warn("Destroy flv player failed", error); } finally { flvPlayer = null; }
}

async function initFlvPlayer() {
  await nextTick();
  destroyFlvPlayer();
  if (!previewDialog.channel?.rtsp_main && !previewDialog.channel?.rtsp_sub) { flvMessage.value = "当前通道没有可用 RTSP 地址。"; return; }
  if (!flvjs.isSupported() || !flvVideoRef.value) { flvMessage.value = "当前浏览器不支持 FLV 直播，请先用快照核验。"; return; }
  flvMessage.value = "正在连接 RTSP 直播，请稍候...";
  flvStartTimer = setTimeout(() => { flvMessage.value = "直播仍未出画面，请检查 RTSP 地址、网络和账号密码。"; }, 12000);
  flvPlayer = flvjs.createPlayer({ type: "flv", isLive: true, url: buildChannelFlvUrl(previewDialog.channel.id) }, { enableStashBuffer: false, autoCleanupSourceBuffer: true });
  flvPlayer.on(flvjs.Events.ERROR, (type, detail) => {
    console.warn("flv preview failed", type, detail);
    if (flvStartTimer) { clearTimeout(flvStartTimer); flvStartTimer = null; }
    flvMessage.value = "RTSP 直播加载失败，请改用快照核验并检查链路。";
  });
  flvPlayer.attachMediaElement(flvVideoRef.value);
  flvPlayer.load();
  try { await flvVideoRef.value.play(); } catch (error) { console.warn("flv autoplay blocked", error); }
}

function markFlvReady() { if (flvStartTimer) { clearTimeout(flvStartTimer); flvStartTimer = null; } flvMessage.value = ""; }

function resetSelectionOperationState() {
  switchProbeSeq += 1;
  switchProbeBusy.value = false;
  flvMessage.value = "";
  if (flvStartTimer) {
    clearTimeout(flvStartTimer);
    flvStartTimer = null;
  }
}

function prevPage() {
  page.value = Math.max(1, page.value - 1);
  if (filters.device_type === "switch") {
    selectSwitch(pagedSwitchDevices.value[0] || selectedSwitch.value);
    return;
  }
  selectChannel(pagedChannels.value[0] || selectedChannel.value);
}
function nextPage() {
  page.value = Math.min(totalPages.value, page.value + 1);
  if (filters.device_type === "switch") {
    selectSwitch(pagedSwitchDevices.value[0] || selectedSwitch.value);
    return;
  }
  selectChannel(pagedChannels.value[0] || selectedChannel.value);
}
function ensureSelectedPage() {
  if (filters.device_type === "switch") {
    if (!selectedSwitch.value) return;
    const index = sortedSwitchDevices.value.findIndex((item) => item.id === selectedSwitch.value.id);
    if (index >= 0) page.value = Math.floor(index / pageSize) + 1;
    return;
  }
  if (!selectedChannel.value) return;
  const index = sortedChannels.value.findIndex((item) => item.id === selectedChannel.value.id);
  if (index >= 0) page.value = Math.floor(index / pageSize) + 1;
}

function assetStatusTagType(row) {
  if (filters.device_type === "switch") {
    if (row.health_state === "online" || row.device_status === "verified") return "success";
    if (row.health_state === "offline" || row.health_state === "error") return "danger";
    return "warning";
  }
  if (row.stream_probe_status === "ok" && !row.stream_probe_is_stale) return "success";
  if (row.stream_probe_status && row.stream_probe_status !== "ok") return "danger";
  return "warning";
}

function assetStatusLabel(row) {
  if (filters.device_type === "switch") {
    if (row.health_state === "online") return "在线";
    if (row.health_state === "offline") return "离线";
    if (row.health_state === "warning" || row.health_state === "error") return "异常";
    if (row.device_status === "verified") return "已核实";
    return healthStateLabel(row.health_state);
  }
  if (row.stream_probe_status === "ok" && !row.stream_probe_is_stale) return "正常";
  if (row.stream_probe_status === "ok" && row.stream_probe_is_stale) return "历史通过";
  if (!row.stream_probe_status || row.stream_probe_status === "unknown") return "待核验";
  return "异常";
}

function csvValue(value) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

function exportCurrentAssets() {
  const rows = tableRows.value;
  if (!rows.length) {
    flashMessage("当前筛选范围没有可导出的资产。");
    return;
  }
  const headers =
    filters.device_type === "switch"
      ? ["名称", "管理IP", "厂商", "型号", "区域", "状态", "来源"]
      : ["名称", "摄像头IP", "通道号", "平台", "区域", "状态", "归属"];
  const lines = [
    headers.join(","),
    ...rows.map((row) => {
      const values =
        filters.device_type === "switch"
          ? [
              csvValue(row.hostname || row.display_name || row.management_ip || "-"),
              csvValue(row.management_ip || "-"),
              csvValue(row.vendor || "-"),
              csvValue(row.model || "-"),
              csvValue(row.area_display_name || row.area_name || "-"),
              csvValue(assetStatusLabel(row)),
              csvValue(clean(row.primary_source_type || "manual")),
            ]
          : [
              csvValue(cameraTitle(row) || row.camera_ip || "-"),
              csvValue(row.camera_ip || "-"),
              csvValue(row.channel_no || "-"),
              csvValue(platformLabel(row)),
              csvValue(row.area_display_name || row.direct_area || "-"),
              csvValue(assetStatusLabel(row)),
              csvValue(bindingLabel(row)),
            ];
      return values.join(",");
    }),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `资产中心-${filters.device_type}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
  link.click();
  URL.revokeObjectURL(url);
  flashMessage("当前资产列表已导出。");
}

async function openExistingDeviceForm(device) {
  if (!device?.id) return;
  resetDeviceForm();
  deviceDialog.visible = true;
  deviceDialog.message = "正在读取资产详情...";
  try {
    const detail = await fetchDeviceDetail(device.id);
    fillDeviceForm(detail.device || {});
    deviceDialog.editingId = device.id;
    deviceDialog.message = "资产详情已加载，可直接修改并保存。";
  } catch (error) {
    console.error(error);
    deviceDialog.message = "资产详情读取失败，请稍后重试。";
  }
}

function healthStateLabel(value) {
  if (value === "ok") return "正常";
  if (value === "online") return "在线";
  if (value === "offline") return "离线";
  if (value === "warning") return "异常";
  if (value === "error") return "失败";
  if (value === "archived") return "已归档";
  return "待确认";
}

function deviceStatusLabel(value) {
  if (value === "verified") return "现场已核实";
  if (value === "discovered") return "系统发现";
  if (value === "imported") return "导入资产";
  if (value === "archived") return "已归档";
  return "人工维护";
}

function applySwitchRoleFilter(rows) {
  if (!filters.switch_role_state) return rows;
  if (filters.switch_role_state === "auto_flagged") return rows.filter((item) => item.topology_auto_flagged);
  return rows.filter((item) => item.topology_role_guess === filters.switch_role_state);
}

function switchRoleOrder(item) {
  if (item.topology_role_guess === "camera_access") return 0;
  if (item.topology_role_guess === "suspected_aggregation") return 1;
  if (item.topology_role_guess === "unknown") return 2;
  if (item.topology_role_guess === "unreachable") return 3;
  return 9;
}

function sortSwitchDevices(a, b) {
  const ipDiff = ipToNumber(a.management_ip || "") - ipToNumber(b.management_ip || "");
  if (switchSortMode.value === "aggregation_first") {
    return Number(a.topology_role_guess !== "suspected_aggregation") - Number(b.topology_role_guess !== "suspected_aggregation")
      || Number(b.live_probe_l2_mac_count || 0) - Number(a.live_probe_l2_mac_count || 0)
      || ipDiff;
  }
  if (switchSortMode.value === "access_first") {
    return Number(a.topology_role_guess !== "camera_access") - Number(b.topology_role_guess !== "camera_access")
      || Number(b.live_probe_camera_match_count || 0) - Number(a.live_probe_camera_match_count || 0)
      || ipDiff;
  }
  if (switchSortMode.value === "camera_match_desc") {
    return Number(b.live_probe_camera_match_count || 0) - Number(a.live_probe_camera_match_count || 0)
      || switchRoleOrder(a) - switchRoleOrder(b)
      || ipDiff;
  }
  if (switchSortMode.value === "mac_desc") {
    return Number(b.live_probe_l2_mac_count || 0) - Number(a.live_probe_l2_mac_count || 0)
      || switchRoleOrder(a) - switchRoleOrder(b)
      || ipDiff;
  }
  return ipDiff;
}

function sortChannels(rows) {
  const items = [...rows];
  const channelNo = (item) => Number(item.channel_no || 0);
  const ipValue = (item) => ipToNumber(item.camera_ip || "");
  const areaValue = (item) => clean(item.area_display_name || item.direct_area || "");
  const streamPriority = (item) => {
    if (item.stream_probe_is_stale) return 1;
    if (item.stream_probe_status && item.stream_probe_status !== "ok") return 0;
    if (!item.stream_probe_status || item.stream_probe_status === "unknown") return 2;
    return 3;
  };
  if (sortMode.value === "channel_asc") return items.sort((a, b) => channelNo(a) - channelNo(b));
  if (sortMode.value === "ip_asc") return items.sort((a, b) => ipValue(a) - ipValue(b));
  if (sortMode.value === "area_asc") return items.sort((a, b) => areaValue(a).localeCompare(areaValue(b), "zh-CN") || ipValue(a) - ipValue(b));
  if (sortMode.value === "binding_first") return items.sort((a, b) => Number(a.switch_binding_state === "bound") - Number(b.switch_binding_state === "bound") || ipValue(a) - ipValue(b));
  if (sortMode.value === "stream_failed_first") return items.sort((a, b) => streamPriority(a) - streamPriority(b) || ipValue(a) - ipValue(b));
  return items.sort((a, b) => channelNo(b) - channelNo(a));
}

function applyStreamProbeFilter(rows) {
  if (filters.stream_probe_state === "ok") return rows.filter((item) => item.stream_probe_status === "ok" && !item.stream_probe_is_stale);
  if (filters.stream_probe_state === "abnormal") return rows.filter((item) => item.stream_probe_status && item.stream_probe_status !== "ok" && !item.stream_probe_is_stale);
  if (filters.stream_probe_state === "stale_ok") return rows.filter((item) => item.stream_probe_status === "ok" && item.stream_probe_is_stale);
  if (filters.stream_probe_state === "stale_abnormal") return rows.filter((item) => item.stream_probe_status && item.stream_probe_status !== "ok" && item.stream_probe_is_stale);
  if (filters.stream_probe_state === "unknown") return rows.filter((item) => !item.stream_probe_status || item.stream_probe_status === "unknown");
  return rows;
}

function normalizeKeyword(value) {
  return clean(value || "").trim().toLowerCase();
}

function composeAssetIndexText(item, fields, transformer = normalizeKeyword) {
  return fields.map((field) => transformer(item?.[field])).filter(Boolean).join(" ");
}

function buildAssetSearchIndex(item) {
  return {
    name: composeAssetIndexText(item, ASSET_NAME_FIELDS),
    ip: composeAssetIndexText(item, ASSET_IP_FIELDS),
    global: composeAssetIndexText(item, ASSET_GLOBAL_FIELDS),
    floor: composeAssetIndexText(item, ASSET_FLOOR_FIELDS, (value) => clean(value || "").toUpperCase()),
  };
}

function getAssetSearchIndex(item) {
  if (!item || typeof item !== "object") return { name: "", ip: "", global: "", floor: "" };
  const cached = assetSearchIndexCache.get(item);
  if (cached) return cached;
  const index = buildAssetSearchIndex(item);
  assetSearchIndexCache.set(item, index);
  return index;
}

function textIncludesKeyword(text, keyword) {
  return !keyword || text.includes(keyword);
}

function matchesAssetSearch(item) {
  const index = getAssetSearchIndex(item);
  const keywords = assetSearchKeywords.value;
  return textIncludesKeyword(index.name, keywords.name)
    && textIncludesKeyword(index.ip, keywords.ip)
    && textIncludesKeyword(index.global, keywords.global);
}

function buildFloorScope(node) {
  const rawLabel = clean(node?.raw_label || node?.label || "");
  const label = rawLabel || "全场";
  const rawKey = clean(node?.tree_key || node?.floor_id || node?.id || node?.value || "");
  const id = rawKey.toLowerCase();
  const areaId = clean(node?.area_id || (id.startsWith("area:") ? rawKey.slice(rawKey.indexOf(":") + 1) : ""));
  const nodeTerms = Array.isArray(node?.terms) ? node.terms.map(clean).filter(Boolean) : [];
  const labelWithoutCount = label.replace(/\s*\(\d+\)\s*$/, "");
  const terms = [...new Set([...nodeTerms, labelWithoutCount, label].map(clean).filter(Boolean))];
  const text = `${id} ${terms.join(" ")}`.toUpperCase();
  if (!label || id === "all" || label.startsWith("全场")) return { key: "all", label: "全场", terms: [], areaId: "" };
  if (areaId) return { key: `area:${areaId}`, label: labelWithoutCount || label, terms, areaId };
  if (id.includes("f1") || text.includes("F1") || text.includes("1F") || label.includes("南楼")) {
    return { key: id || "f1", label, terms: [...new Set([...terms, "F1", "1F", "南楼"])] , areaId: "" };
  }
  if (id.includes("f2") || text.includes("F2") || text.includes("2F") || label.includes("北区")) {
    return { key: id || "f2", label, terms: [...new Set([...terms, "F2", "2F", "北区"])] , areaId: "" };
  }
  if (id.includes("f3") || text.includes("F3") || text.includes("3F")) {
    return { key: id || "f3", label, terms: [...new Set([...terms, "F3", "3F"])] , areaId: "" };
  }
  return { key: id || label, label, terms: terms.length ? terms : [label], areaId: "" };
}

function ipToNumber(ip) {
  const parts = String(ip).split(".").map((part) => Number(part));
  if (parts.length !== 4 || parts.some((part) => !Number.isFinite(part))) return Number.MAX_SAFE_INTEGER;
  return parts.reduce((acc, part) => acc * 256 + part, 0);
}

function platformLabel(channelOrLabel) {
  const channel = typeof channelOrLabel === "object" && channelOrLabel ? channelOrLabel : null;
  const label = channel ? channel.parent_label : channelOrLabel;
  if (channel?.source_management_ip === "10.0.59.205" || clean(label).includes("205")) return "205 分平台";
  if (channel?.source_management_ip === "10.0.59.200" || clean(label).includes("富成")) return "主平台 200";
  return clean(label || "主平台 200");
}

function areaOptionLabel(area) {
  if (!area) return "";
  const menu = clean(area.menu_label || area.display_name || "-");
  const accuracy = clean(area.accuracy_label || "");
  return accuracy ? `${menu} [${accuracy}]` : menu;
}

function areaAccuracyLabel(channel) {
  if (!channel) return "";
  return clean(channel.area_accuracy_label || channel.direct_area_accuracy_label || "");
}

function areaScopeNote(channel) {
  const scope = clean(channel?.area_scope_kind || channel?.direct_area_scope_kind || "");
  if (scope === "precise") return "这是现场位置较明确的精准区域，可直接作为楼层/片区维护依据。";
  if (scope === "precise_project") return "这是明确项目区，目前口径稳定，可直接用于停车场或专项片区维护。";
  if (scope === "project_205") return "这是 205 项目区，位置判断基本可靠，但更偏项目分组，不等同于精确楼层点位。";
  if (scope === "addon_floor") return "这是后加点位组，适合按项目批次管理；若已确认具体楼层片区，建议继续细化回精准区域。";
  if (scope === "manual_review") return "这类区域仍需现场核定，暂时不要直接当精准楼层使用。";
  if (scope === "special_function") return "这类区域偏功能分组，适合专项设备管理，不等同于普通楼层片区。";
  return "当前区域为常规口径，如发现与现场楼层片区不一致，建议继续修正到更精准的区域。";
}

function matchesFloorScope(item) {
  const scope = selectedFloorScope.value || { key: selectedFloorKey.value || "all", terms: [], areaId: "" };
  const key = scope.key || "all";
  if (key === "all") return true;
  const scopeAreaId = clean(scope.areaId || "");
  if (scopeAreaId) {
    const itemAreaIds = [item?.area_id, item?.camera_area_id, item?.direct_area_id, item?.area?.id]
      .map((value) => clean(value || ""))
      .filter(Boolean);
    if (itemAreaIds.includes(scopeAreaId)) return true;
  }
  const text = getAssetSearchIndex(item).floor;
  const terms = Array.isArray(scope.terms) ? scope.terms : [];
  if (terms.length) return terms.some((term) => text.includes(clean(term).toUpperCase()));
  if (key === "f1") return text.includes("F1") || text.includes("1F");
  if (key === "f2") return text.includes("F2") || text.includes("2F");
  if (key === "f3") return text.includes("F3") || text.includes("3F");
  return text.includes(clean(scope.label || key).toUpperCase());
}

function cameraTitle(channel) { return channel ? clean(channel.camera_label || channel.channel_name || channel.camera_ip || "-") : ""; }
function shortArea(value) { const text = clean(value || "-"); return text.length <= 26 ? text : `${text.slice(0, 26)}...`; }
function bindingLabel(channel) { return channel?.switch_binding_state === "bound" ? "已归属" : "待补归属"; }
function topologyEvidenceLabel(channel) {
  const evidence = clean(channel?.topology_evidence_type || "");
  if (evidence === "manual_override") return "现场人工核实";
  if (evidence === "direct_switch_arp_probe") return "交换机实采(ARP)";
  if (evidence === "direct_switch_mac_probe") return "交换机实采(MAC表)";
  if (evidence === "platform_fact") return "平台导入参考";
  if (evidence === "platform_terminal_fact") return "平台终端推断";
  return evidence || "待确认";
}
function platformStatusLabel(value) {
  if (value === "1" || value === 1) return "平台标记正常";
  if (value === "0" || value === 0) return "平台标记异常";
  return "待确认";
}
function streamStatusClass(channel) {
  if (channel?.stream_probe_is_stale) return "stale";
  if (!channel?.stream_probe_status || channel.stream_probe_status === "unknown") return channel?.switch_binding_state === "bound" ? "ok" : "warn";
  if (channel.stream_probe_status === "ok") return "ok";
  if (["rtsp_rejected_4xx", "rtsp_rejected_permission"].includes(channel.stream_probe_error_class)) return "danger";
  return "warn";
}
function streamProbeDisplayLabel(channel) {
  if (!channel?.stream_probe_status || channel.stream_probe_status === "unknown") return "未检测";
  if (channel.stream_probe_is_stale) return channel.stream_probe_status === "ok" ? "历史通过/待复测" : "过期待复测";
  if (channel.stream_probe_status === "ok") return "取流通过";
  return channel.stream_probe_label || "取流未通过";
}
function formatProbeTime(value) {
  if (!value) return "未扫描";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}
function streamAdvice(channel) {
  if (!channel?.stream_probe_status || channel.stream_probe_status === "unknown") return "尚未导入取流扫描结果，可先以实时快照和直播按钮现场核验。";
  if (channel.stream_probe_is_stale) return `这条诊断已超过 ${channel.stream_probe_fresh_hours || 24} 小时有效期，不能再作为当前故障依据。建议重新执行 RTSP 扫描或手动刷新快照/直播复测。`;
  if (channel.stream_probe_status === "ok") return "RTSP 实测可取流，当前可作为视频验收通过证据。若浏览器直播失败，优先检查转码服务或浏览器播放链路。";
  if (channel.stream_probe_error_class === "rtsp_rejected_4xx") return "设备 IP 与 554 端口可达，但 RTSP 路径被拒绝，优先核对该摄像头真实取流路径和设备 RTSP 服务策略。";
  if (channel.stream_probe_error_class === "rtsp_rejected_permission") return "设备在线但取流被权限拒绝，优先核对账号密码、RTSP权限、通道号和码流配置。";
  if (["network_or_device_timeout", "timeout"].includes(channel.stream_probe_error_class)) return "取流超时，优先检查摄像头供电、交换机端口、VLAN链路和设备负载。";
  return "RTSP 实测异常，请结合错误详情、交换机归属和现场设备配置继续核验。";
}
function sourceLineageLabel(channel) {
  const items = Array.isArray(channel?.source_lineage) ? channel.source_lineage : [];
  return items.length ? items.map((item) => clean(item)).join(" / ") : clean(channel?.import_origin || "-");
}
function clean(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  if (!/[ÃÂåæçèéä¸]/.test(text)) return text;
  try {
    const bytes = Uint8Array.from(Array.from(text), (char) => char.charCodeAt(0) & 0xff);
    const decoded = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    const badOriginal = (text.match(/[ÃÂåæçèé]/g) || []).length;
    const badDecoded = (decoded.match(/[ÃÂåæçèé]/g) || []).length;
    return badDecoded < badOriginal ? decoded : text;
  } catch {
    return text;
  }
}
</script>

<style scoped>
.asset-page-wrapper {
  --asset-panel: rgba(255, 255, 255, 0.05);
  --asset-panel-strong: rgba(255, 255, 255, 0.08);
  --asset-card: rgba(255, 255, 255, 0.05);
  --asset-card-active: radial-gradient(circle at 100% 0%, rgba(111, 199, 255, 0.16), transparent 38%),
    rgba(255, 255, 255, 0.08);
  --asset-inner: rgba(255, 255, 255, 0.04);
  --asset-border: rgba(255, 255, 255, 0.1);
  --asset-glow: rgba(15, 60, 85, 0.12);
  --asset-muted-on-video: rgba(214, 222, 235, 0.82);
  --asset-input-bg: rgba(255, 255, 255, 0.08);
  --el-card-bg-color: rgba(255, 255, 255, 0.05);
  background:
    radial-gradient(circle at 8% 2%, rgba(111, 199, 255, 0.12), transparent 26%),
    radial-gradient(circle at 88% 12%, rgba(242, 216, 138, 0.08), transparent 28%),
    #0a0a0a;
  color: #f4fbff;
}

.asset-page-wrapper :deep(.el-card) {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: #f4fbff;
}

.title-block {
  display: grid;
  gap: 4px;
}

.title-block p {
  margin: 0;
  color: #76d0ef;
  font-size: 0.74rem;
  letter-spacing: 0.26em;
  text-transform: uppercase;
}

.title-block h2 {
  margin: 0;
  color: #f4fbff;
  font-size: 1.56rem;
}

.title-block span,
.filter-head span,
.side-head span,
.roadmap-card span,
.roadmap-card small,
.scope-row span,
.hint-row span {
  color: var(--muted);
}

.asset-content-shell,
.asset-main-shell,
.asset-layout-row,
.asset-primary-col,
.asset-primary-stack {
  min-width: 0;
  min-height: 0;
}

.asset-floor-aside {
  flex: 0 0 240px;
  width: 240px;
  min-width: 240px;
  max-width: 300px;
  flex-shrink: 0;
  padding: 16px;
  overflow: hidden;
}

.asset-floor-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(15px);
}

.asset-floor-head {
  flex: 0 0 auto;
  display: grid;
  gap: 4px;
}

.asset-floor-head h3 {
  margin: 0;
  color: #f4fbff;
  font-family: var(--font-head);
}

.asset-floor-head span {
  color: rgba(228, 235, 243, 0.72);
  font-size: 13px;
}

.asset-floor-tree {
  flex: 1 1 0;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  background: transparent;
  color: #409eff;
  scrollbar-width: thin;
  scrollbar-color: rgba(64, 158, 255, 0.5) transparent;
}

.asset-floor-tree :deep(.el-tree) {
  background: transparent;
  color: #409eff;
}

.asset-floor-tree :deep(.el-tree-node__content) {
  min-height: 42px;
  border-radius: 10px;
  color: #409eff;
  padding-right: 4px;
}

.asset-floor-tree :deep(.el-tree-node__label) {
  flex: 1 1 auto;
  min-width: 0;
  color: #409eff;
  font-weight: 600;
}

.asset-tree-label {
  display: block;
  max-width: 100%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-floor-tree :deep(.el-tree-node__expand-icon) {
  color: rgba(111, 199, 255, 0.92);
}

.asset-floor-tree :deep(.el-tree-node__content:hover) {
  background: rgba(64, 158, 255, 0.1);
}

.asset-floor-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: linear-gradient(90deg, rgba(64, 158, 255, 0.3), rgba(64, 158, 255, 0.08));
  color: #409eff;
  box-shadow:
    inset 3px 0 0 #409eff,
    0 0 18px rgba(64, 158, 255, 0.24);
}

.asset-floor-tree :deep(.el-tree-node.is-current > .el-tree-node__content .el-tree-node__label) {
  color: #8cc8ff;
  text-shadow: 0 0 10px rgba(64, 158, 255, 0.45);
}

.asset-content-shell {
  flex: 1 1 0;
  min-width: 0;
  width: 0;
  background: transparent;
}

.asset-main-shell {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow: hidden;
  background: transparent;
}

.asset-layout-row {
  display: flex;
  flex-wrap: nowrap;
  height: 100%;
  gap: 16px;
  min-width: 0;
}

.asset-primary-col {
  flex: 1 1 0;
  min-width: 0;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.asset-primary-stack {
  flex: 1 1 0;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}

.asset-slim-toolbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.04);
}

.asset-kpi-grid {
  flex: 0 0 auto;
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.asset-side-sticky {
  flex: 0 0 400px;
  min-height: 0;
  padding: 16px;
  border-left: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(25, 25, 25, 0.7);
  backdrop-filter: blur(15px);
}

.asset-side-panel {
  height: 100%;
  min-height: 0;
}

.asset-roadmap {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.roadmap-card,
.asset-scope-block {
  display: grid;
  gap: 6px;
  padding: 16px 18px;
  border-radius: 22px;
  border: 1px solid var(--line);
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(18px);
  background:
    radial-gradient(circle at 96% 6%, rgba(111, 199, 255, 0.12), transparent 28%),
    linear-gradient(180deg, rgba(10, 28, 46, 0.92), rgba(12, 49, 66, 0.88));
}

.roadmap-card strong,
.scope-row strong,
.hint-row strong {
  color: #f4fbff;
}

.roadmap-card.emphasis {
  background:
    radial-gradient(circle at 100% 0%, rgba(245, 165, 36, 0.14), transparent 32%),
    linear-gradient(135deg, rgba(55, 34, 10, 0.9), rgba(30, 22, 12, 0.86));
}

.side-head,
.filter-head {
  display: grid;
  gap: 4px;
}

.scope-list,
.hint-list {
  display: grid;
  gap: 10px;
}

.scope-row,
.hint-row {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(116, 180, 218, 0.18);
  background: rgba(255, 255, 255, 0.04);
  text-align: left;
}

.scope-row {
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease;
}

.scope-row:hover {
  transform: translateY(-1px);
  border-color: rgba(111, 199, 255, 0.42);
}

.asset-hero,
.asset-filter-panel,
.asset-list-panel,
.selected-overview,
.asset-toast,
.asset-followup-panel {
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(18px);
}

.asset-hero {
  position: relative;
  overflow: hidden;
  min-height: 190px;
  padding: 28px;
  border-radius: 28px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
  background:
    radial-gradient(circle at 78% 18%, rgba(111, 199, 255, 0.28), transparent 34%),
    radial-gradient(circle at 24% 0%, rgba(242, 216, 138, 0.22), transparent 30%),
    linear-gradient(135deg, rgba(10, 28, 46, 0.96), rgba(16, 65, 83, 0.88));
  color: #eef7fb;
}

.filter-actions,
.preview-actions,
.dialog-tabs,
.pager {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.asset-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
}

.metric-card {
  position: relative;
  overflow: hidden;
  height: 56px;
  padding: 4px 8px;
  border-radius: 12px;
  border: 1px solid var(--asset-border);
  background: rgba(255, 255, 255, 0.05);
  box-shadow: var(--shadow-soft);
}


.metric-card span,
.metric-card small,
.asset-toast span {
  display: block;
  color: var(--muted);
}

.metric-card strong {
  display: block;
  margin: 1px 0;
  font-size: 15px;
  font-family: var(--font-head);
  line-height: 1.1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-card span,
.metric-card small {
  font-size: 11px;
  line-height: 1.15;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-toast {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  margin-bottom: 10px;
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(18, 185, 129, 0.12), var(--asset-panel-strong));
}

.asset-topology-banner {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  padding: 16px 18px;
  border-radius: 22px;
  border: 1px solid rgba(245, 165, 36, 0.24);
  background:
    radial-gradient(circle at 100% 0%, rgba(245, 165, 36, 0.14), transparent 32%),
    linear-gradient(135deg, rgba(55, 34, 10, 0.9), rgba(30, 22, 12, 0.86));
}

.asset-topology-banner strong,
.asset-topology-banner span {
  display: block;
}

.asset-topology-banner span {
  color: var(--muted);
}

.topology-banner-flow,
.topology-banner-feedback {
  display: block;
  margin-top: 8px;
  color: rgba(229, 237, 252, 0.72);
  font-size: 12px;
  line-height: 1.5;
}

.topology-banner-feedback {
  color: rgba(255, 213, 150, 0.92);
}

.asset-followup-panel {
  display: grid;
  gap: 14px;
  padding: 16px 18px;
  border-radius: 22px;
  background:
    radial-gradient(circle at 96% 6%, rgba(111, 199, 255, 0.12), transparent 28%),
    linear-gradient(180deg, rgba(10, 28, 46, 0.92), rgba(12, 49, 66, 0.88));
}

.followup-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.followup-head h3 {
  margin: 4px 0 0;
  font-size: 22px;
}

.followup-head > span {
  color: var(--muted);
  font-size: 13px;
}

.followup-sequence {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.followup-sequence span,
.filter-tip {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}

.followup-sequence span {
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(111, 199, 255, 0.18);
  background: rgba(255, 255, 255, 0.04);
}

.followup-grid,
.followup-groups {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.followup-card,
.followup-group-card {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid var(--asset-border);
  background:
    radial-gradient(circle at top right, rgba(111, 199, 255, 0.08), transparent 30%),
    var(--asset-panel);
}

.followup-next-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid rgba(111, 199, 255, 0.24);
  background:
    radial-gradient(circle at 100% 0%, rgba(111, 199, 255, 0.16), transparent 34%),
    linear-gradient(135deg, rgba(12, 47, 67, 0.96), rgba(9, 29, 46, 0.9));
}

.followup-next-card span,
.followup-next-card small,
.followup-next-card p {
  display: block;
  margin: 0;
  color: var(--muted);
}

.followup-next-card strong {
  display: block;
  margin: 6px 0;
  font-size: 22px;
}

.followup-card span,
.followup-card small,
.followup-group-card span,
.followup-group-card small {
  display: block;
  color: var(--muted);
}

.followup-card strong,
.followup-group-card strong {
  display: block;
  margin: 6px 0;
}

.followup-inline-tip {
  display: block;
  margin-top: 6px;
  color: var(--muted);
}

.followup-group-card .action-row {
  margin-top: 10px;
}

.asset-filter-panel {
  flex: 0 0 auto;
  max-height: none;
  overflow: visible !important;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.05);
}

.asset-filter-panel :deep(.el-card__body) {
  padding: 6px 8px !important;
  max-height: none;
  overflow: visible !important;
}

.asset-filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 8px;
  align-items: center;
  width: 100%;
  overflow: visible !important;
}

.asset-filter-form :deep(.el-form-item) {
  flex: 0 1 176px;
  min-width: 168px;
  height: 28px;
  display: inline-flex !important;
  align-items: center;
  margin: 0 !important;
}

.asset-filter-form :deep(.el-form-item:last-child) {
  flex: 0 0 auto;
  min-width: 276px;
}

.asset-filter-form :deep(.el-form-item__label) {
  flex: 0 0 66px;
  width: 66px !important;
  height: 28px;
  margin: 0 6px 0 0 !important;
  padding: 0 !important;
  font-size: 11px;
  line-height: 28px;
  text-align: right;
  white-space: nowrap;
  color: rgba(228, 235, 243, 0.68);
}

.asset-filter-form :deep(.el-form-item__content) {
  flex: 1 1 auto;
  min-width: 0;
  height: 28px;
  line-height: 28px;
  display: flex;
  align-items: center;
}

.asset-filter-form :deep(.el-input),
.asset-filter-form :deep(.el-select) {
  width: 100%;
}

.asset-filter-form :deep(.el-input__wrapper),
.asset-filter-form :deep(.el-select__wrapper) {
  min-height: 28px;
  height: 28px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.06);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.filter-actions {
  width: auto;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
}

.filter-actions :deep(.el-button) {
  min-height: 28px;
  padding: 4px 8px;
  margin-left: 0 !important;
}

.filter-head {
  grid-column: 1 / -1;
}

.filter-field {
  display: grid;
  gap: 7px;
}

.filter-field label {
  font-size: 12px;
  color: var(--muted);
  letter-spacing: 0.08em;
}

.filter-tip {
  display: block;
}

.filter-input {
  width: 100%;
  background: var(--asset-input-bg);
  border-color: var(--asset-border);
}

.asset-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1.16fr) minmax(340px, 0.84fr);
  gap: 18px;
  align-items: start;
}

.asset-list-panel,
.selected-overview {
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(15px);
}

.asset-list-panel {
  flex: 1 1 0;
  height: 0;
  min-height: 300px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.asset-list-panel :deep(.el-card__body) {
  flex: 1 1 0;
  height: 0;
  min-height: 300px;
  display: flex;
  flex-direction: column;
  overflow: hidden !important;
  padding: 10px 12px !important;
}

.asset-list-panel,
.selected-overview {
  padding: 0;
  min-width: 0;
  overflow-x: visible;
}

.asset-table-scroll {
  flex: 1 1 0;
  height: 0;
  min-height: 300px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.02);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.04),
    inset 0 -28px 48px rgba(0, 0, 0, 0.16);
}

.asset-table {
  flex: 1 1 auto;
  width: 100%;
  height: 100% !important;
  min-width: 1200px;
  border: 0 !important;
  background: transparent;
}

.asset-table :deep(.el-table__inner-wrapper),
.asset-table :deep(.el-table__body-wrapper),
.asset-table :deep(.el-scrollbar),
.asset-table :deep(.el-scrollbar__wrap),
.asset-table :deep(.el-scrollbar__view) {
  height: 100% !important;
  min-height: 0 !important;
}

.asset-table :deep(.el-table__body-wrapper),
.asset-table :deep(.el-scrollbar__wrap) {
  overflow-y: auto !important;
  overflow-x: auto !important;
}

.asset-table :deep(.el-table__body) {
  min-width: 100%;
}

.asset-table :deep(.el-table__inner-wrapper::before),
.asset-table :deep(.el-table__border-left-patch) {
  display: none;
}

.asset-table :deep(.el-table__body-wrapper),
.asset-table :deep(.el-scrollbar__wrap),
.asset-table-scroll {
  scrollbar-width: thin;
  scrollbar-color: rgba(84, 92, 104, 0.78) rgba(255, 255, 255, 0.03);
}

.asset-table :deep(.el-scrollbar__wrap)::-webkit-scrollbar,
.asset-table :deep(.el-table__body-wrapper)::-webkit-scrollbar,
.asset-table-scroll::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.asset-table :deep(.el-scrollbar__wrap)::-webkit-scrollbar-track,
.asset-table :deep(.el-table__body-wrapper)::-webkit-scrollbar-track,
.asset-table-scroll::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.02);
}

.asset-table :deep(.el-scrollbar__wrap)::-webkit-scrollbar-thumb,
.asset-table :deep(.el-table__body-wrapper)::-webkit-scrollbar-thumb,
.asset-table-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(84, 92, 104, 0.78);
}

.asset-table :deep(.el-scrollbar__bar) {
  opacity: 0.44;
}

.asset-table :deep(.el-scrollbar__thumb) {
  background: rgba(84, 92, 104, 0.78);
}

.asset-side-sticky .asset-detail-panel {
  flex: 1;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.05) !important;
  backdrop-filter: blur(15px);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.18);
}

.asset-detail-panel :deep(.el-card__body) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px;
}

.asset-detail-scrollbar {
  flex: 1;
  min-height: 0;
}

.list-toolbar,
.selected-head,
.preview-head,
.section-mini-head,
.dialog-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
}

.list-toolbar {
  padding: 0;
  flex-wrap: wrap;
  align-items: flex-start;
}

.asset-list-panel :deep(.el-card__header) {
  flex: 0 0 auto;
  padding: 10px 12px !important;
  border-bottom-color: rgba(255, 255, 255, 0.08);
}

.asset-table-footer {
  flex: 0 0 auto;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  min-height: 34px;
  padding: 6px 2px 0;
  background: transparent;
}

.asset-table-footer :deep(.el-pagination) {
  --el-pagination-bg-color: transparent;
  --el-pagination-button-bg-color: transparent;
  --el-pagination-hover-color: #409eff;
  gap: 4px;
  justify-content: flex-end;
  color: rgba(228, 235, 243, 0.76);
}

.asset-table-footer :deep(.btn-prev),
.asset-table-footer :deep(.btn-next),
.asset-table-footer :deep(.el-pager li) {
  min-width: 28px;
  height: 28px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.04) !important;
  color: rgba(228, 235, 243, 0.82);
}

.asset-table-footer :deep(.btn-prev:disabled),
.asset-table-footer :deep(.btn-next:disabled) {
  background: transparent !important;
  color: rgba(228, 235, 243, 0.28);
}

.asset-table-footer :deep(.el-pager li.is-active) {
  background: rgba(64, 158, 255, 0.22) !important;
  color: #79bbff;
  box-shadow: 0 0 16px rgba(64, 158, 255, 0.22);
}

.asset-table-footer :deep(.el-pagination__jump),
.asset-table-footer :deep(.el-pagination__total) {
  margin-left: 8px;
  color: rgba(228, 235, 243, 0.64);
}

.asset-table-footer :deep(.el-input__wrapper) {
  min-height: 28px;
  background: rgba(255, 255, 255, 0.04);
  box-shadow: none;
}

.list-toolbar h3,
.selected-head h3 {
  margin: 4px 0;
  font-family: var(--font-head);
}

.list-toolbar span,
.selected-head span,
.preview-head span,
.section-mini-head span {
  color: var(--muted);
  font-size: 13px;
}

.selection-brief {
  min-width: min(100%, 240px);
  max-width: 100%;
  flex: 1 1 260px;
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(111, 199, 255, 0.14);
  background:
    radial-gradient(circle at 100% 0%, rgba(111, 199, 255, 0.07), transparent 34%),
    rgba(8, 20, 34, 0.72);
}

.selection-brief span,
.selection-brief small {
  color: var(--muted);
}

.selection-brief strong {
  color: var(--text);
  font-size: 15px;
  line-height: 1.35;
}

.selection-brief.muted {
  border-style: dashed;
}

.list-command-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.command-pill {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(111, 199, 255, 0.14);
  background:
    radial-gradient(circle at 100% 0%, rgba(111, 199, 255, 0.06), transparent 32%),
    rgba(8, 20, 34, 0.72);
}

.command-pill span,
.command-pill small {
  color: var(--muted);
}

.command-pill strong {
  color: var(--text);
  font-size: 15px;
  line-height: 1.35;
}

.inline-controls {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
  gap: 10px;
  align-items: end;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(111, 199, 255, 0.14);
  background:
    radial-gradient(circle at 100% 0%, rgba(111, 199, 255, 0.06), transparent 32%),
    rgba(8, 20, 34, 0.72);
}

.inline-field {
  display: grid;
  gap: 6px;
}

.inline-field span {
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.08em;
}

.compact-select,
.compact-input {
  min-height: 40px;
}

.page-jump-field {
  min-width: 0;
}

.inline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-start;
}

.batch-workbench-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.command-pill.emphasis {
  border-color: rgba(111, 199, 255, 0.2);
}

.batch-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(111, 199, 255, 0.14);
  background:
    radial-gradient(circle at 100% 0%, rgba(111, 199, 255, 0.06), transparent 32%),
    rgba(8, 20, 34, 0.72);
}

.channel-list {
  display: grid;
  gap: 10px;
  max-height: calc(100vh - 390px);
  min-height: 560px;
  overflow: auto;
  max-width: 100%;
  padding: 2px 4px 2px 2px;
}

.asset-grid-head {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(132px, 0.96fr) minmax(118px, 0.82fr) minmax(112px, 0.76fr);
  gap: 14px;
  padding: 0 18px 10px 24px;
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  align-items: end;
}

.channel-list::-webkit-scrollbar {
  width: 10px;
}

.channel-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(94, 117, 136, 0.26);
}

.channel-card {
  position: relative;
  width: 100%;
  min-height: 86px;
  display: grid;
  grid-template-columns: 6px minmax(0, 1.2fr) minmax(132px, 0.96fr) minmax(118px, 0.82fr) minmax(112px, 0.76fr);
  gap: 14px;
  align-items: center;
  padding: 12px 14px 12px 0;
  border: 1px solid var(--asset-border);
  border-radius: 20px;
  background: var(--asset-card);
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition: transform 150ms ease, border-color 150ms ease, box-shadow 150ms ease, background 150ms ease;
}

.channel-card:hover,
.channel-card.active {
  transform: translateY(-1px);
  border-color: rgba(111, 199, 255, 0.42);
  box-shadow: 0 18px 34px var(--asset-glow);
}

.channel-card.active {
  background: var(--asset-card-active);
}

.channel-card.active .channel-identity strong,
.channel-card.active .channel-side span {
  color: #f4fbff;
}

.channel-card.active .select-rail {
  box-shadow: 0 0 18px rgba(91, 206, 255, 0.42);
}

.channel-card.pending .select-rail {
  background: linear-gradient(180deg, #f5a524, #ef6c34);
}

.select-rail {
  border-radius: 999px;
  background: linear-gradient(180deg, #6fc7ff, #2aa876);
}

.channel-main {
  min-width: 0;
  display: grid;
  gap: 7px;
}

.channel-identity,
.channel-meta-stack,
.channel-area-cell,
.channel-side {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.channel-identity {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
}

.channel-identity strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
}

.channel-meta-stack,
.channel-area,
.channel-side small {
  color: var(--muted);
  font-size: 12px;
}

.channel-meta-stack span,
.channel-area-cell span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.channel-area {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.area-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgba(111, 199, 255, 0.2);
  background: rgba(255, 255, 255, 0.05);
  color: #bfe7ff;
  font-size: 11px;
  white-space: nowrap;
}

.channel-side {
  min-width: 0;
  justify-content: center;
  align-items: flex-end;
  text-align: right;
  color: var(--text);
}

.channel-side span {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 700;
}

.asset-list-panel.view-compact .asset-grid-head {
  grid-template-columns: minmax(0, 1.26fr) minmax(132px, 0.9fr) minmax(110px, 0.72fr) minmax(102px, 0.6fr);
}

.asset-list-panel.view-compact .channel-card {
  min-height: 76px;
  grid-template-columns: 6px minmax(0, 1.26fr) minmax(132px, 0.9fr) minmax(110px, 0.72fr) minmax(102px, 0.6fr);
}

.asset-list-panel.view-compact .channel-meta-stack span:last-child,
.asset-list-panel.view-compact .channel-side small,
.asset-list-panel.view-compact .channel-area-cell .area-badge {
  display: none;
}

.status-pill,
.status-ring {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 700;
}

.status-pill {
  padding: 5px 9px;
}

.status-pill.ok,
.status-ring.ok {
  color: #15724e;
  background: rgba(18, 185, 129, 0.14);
}

.status-pill.warn,
.status-ring.warn {
  color: #9b5812;
  background: rgba(245, 165, 36, 0.16);
}

.status-pill.stale,
.status-ring.stale {
  color: #475569;
  background: rgba(100, 116, 139, 0.14);
}

.status-pill.danger,
.status-ring.danger {
  color: #b42318;
  background: rgba(244, 63, 94, 0.14);
}

.asset-detail-rail {
  position: sticky;
  top: 18px;
  overflow-x: hidden;
}

.selected-head {
  margin-bottom: 16px;
}

.selected-head h3 {
  font-size: 22px;
}

.status-ring {
  min-width: 70px;
  height: 70px;
  padding: 0 12px;
  border: 1px solid currentColor;
}

.summary-kpis {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.summary-chip {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(111, 199, 255, 0.14);
  background:
    radial-gradient(circle at 100% 0%, rgba(111, 199, 255, 0.08), transparent 34%),
    rgba(8, 20, 34, 0.72);
}

.summary-chip span {
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.summary-chip strong {
  color: var(--text);
  font-size: 15px;
  line-height: 1.35;
}

.primary-ops {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.primary-ops :deep(.el-button) {
  width: 100%;
  min-height: 34px;
  margin-left: 0 !important;
  justify-content: center;
  border-radius: 10px;
}

.primary-ops :deep(.el-button:nth-child(2n + 1):last-child) {
  grid-column: 1 / -1;
}

.preview-card,
.detail-section {
  border: 1px solid var(--asset-border);
  border-radius: 22px;
  background:
    radial-gradient(circle at 100% 0%, rgba(111, 199, 255, 0.06), transparent 36%),
    var(--asset-panel-strong);
  padding: 12px;
  margin-top: 0;
  margin-bottom: 10px;
}

.preview-head {
  margin-bottom: 12px;
}

.preview-head strong,
.section-mini-head strong {
  display: block;
}

.snapshot-stage {
  min-height: 278px;
  border-radius: 18px;
  overflow: hidden;
  background:
    radial-gradient(circle at center, rgba(111, 199, 255, 0.08), transparent 52%),
    #050a14;
  display: flex;
  align-items: center;
  justify-content: center;
}

.snapshot-image {
  width: 100%;
  max-height: 420px;
  object-fit: contain;
  display: block;
}

.snapshot-placeholder,
.empty-state {
  color: rgba(214, 222, 235, 0.82);
  line-height: 1.7;
  padding: 28px;
  text-align: center;
}

.detail-empty-card {
  display: grid;
  gap: 8px;
  border: 1px dashed rgba(111, 199, 255, 0.22);
  border-radius: 22px;
  background:
    radial-gradient(circle at 100% 0%, rgba(111, 199, 255, 0.08), transparent 36%),
    rgba(7, 18, 31, 0.76);
}

.detail-empty-card strong {
  font-size: 18px;
  color: var(--text);
}

.detail-empty-card span {
  color: var(--muted);
}

.preview-actions {
  margin-top: 12px;
}

.maintenance-actions,
.dialog-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  align-items: center;
}

.switch-role-hint {
  display: inline-flex;
  align-items: center;
  margin-top: 0.35rem;
  padding: 0.22rem 0.6rem;
  border-radius: 999px;
  background: rgba(99, 179, 237, 0.12);
  color: rgba(168, 214, 255, 0.95);
  font-size: 0.76rem;
  letter-spacing: 0.02em;
}

.switch-judgement-banner {
  display: grid;
  gap: 0.35rem;
  padding: 0.9rem 1rem;
  margin-bottom: 1rem;
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(87, 167, 255, 0.14), rgba(64, 224, 208, 0.1));
  border: 1px solid rgba(113, 193, 255, 0.18);
}

.switch-judgement-banner.warning {
  background: linear-gradient(135deg, rgba(255, 196, 87, 0.16), rgba(255, 133, 102, 0.1));
  border-color: rgba(255, 191, 120, 0.22);
}

.switch-judgement-banner strong {
  color: rgba(240, 248, 255, 0.96);
  font-size: 0.92rem;
}

.switch-judgement-banner span {
  color: rgba(214, 233, 255, 0.82);
  font-size: 0.82rem;
  line-height: 1.65;
}

.danger-button {
  color: #b44949 !important;
  border-color: rgba(180, 73, 73, 0.3) !important;
}

.device-dialog-shell {
  width: min(920px, 100%);
  max-height: min(90vh, 920px);
  overflow: auto;
  padding: 18px;
  border-radius: 26px;
  border: 1px solid var(--line);
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.compact-dialog-shell {
  width: min(720px, 100%);
}

.device-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.device-form-grid label {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.device-form-grid label span {
  color: var(--muted);
  font-size: 12px;
}

.full-span {
  grid-column: 1 / -1;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.detail-grid div,
.link-card,
.rtsp-box {
  min-width: 0;
  padding: 12px;
  border-radius: 16px;
  background: var(--asset-inner);
}

.detail-grid label,
.link-card label,
.rtsp-box label {
  display: block;
  margin-bottom: 5px;
  color: var(--muted);
  font-size: 12px;
}

.detail-grid p,
.rtsp-box p {
  margin: 0;
  word-break: break-word;
}

.detail-area-stack {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-area-note {
  display: block;
  margin-top: 6px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.link-card {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.link-card p {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
}

.link-card.muted {
  border: 1px dashed rgba(245, 165, 36, 0.35);
}

.rtsp-box p {
  max-height: 98px;
  overflow: auto;
}

.stream-diagnostic-card {
  display: grid;
  gap: 8px;
  margin-top: 10px;
  padding: 12px;
  border-radius: 16px;
  border: 1px solid rgba(116, 180, 218, 0.16);
  background:
    radial-gradient(circle at 100% 0%, rgba(111, 199, 255, 0.08), transparent 36%),
    var(--asset-inner);
}

.stream-diagnostic-card > div {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.stream-diagnostic-card strong {
  font-size: 15px;
}

.stream-diagnostic-card span,
.stream-diagnostic-card small {
  color: var(--muted);
  font-size: 12px;
}

.stream-diagnostic-card p {
  margin: 0;
  line-height: 1.7;
}

.diagnostic-scope-note {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
}

.stream-diagnostic-card.ok {
  border-color: rgba(18, 185, 129, 0.26);
}

.stream-diagnostic-card.warn {
  border-color: rgba(245, 165, 36, 0.34);
}

.stream-diagnostic-card.stale {
  border-color: rgba(100, 116, 139, 0.28);
  background:
    radial-gradient(circle at 100% 0%, rgba(100, 116, 139, 0.09), transparent 36%),
    var(--asset-inner);
}

.stream-diagnostic-card.danger {
  border-color: rgba(244, 63, 94, 0.36);
  background:
    radial-gradient(circle at 100% 0%, rgba(244, 63, 94, 0.1), transparent 36%),
    var(--asset-inner);
}

.compact-button {
  padding: 7px 10px;
}

.mono {
  font-family: "Cascadia Mono", "Consolas", "SFMono-Regular", monospace;
}

.dialog-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(6, 12, 20, 0.72);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 80;
}

.video-dialog-shell {
  width: min(1120px, 100%);
  max-height: min(90vh, 900px);
  overflow: auto;
  padding: 18px;
  border-radius: 26px;
  border: 1px solid var(--line);
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.dialog-head strong {
  display: block;
  font-size: 20px;
}

.dialog-head span {
  color: var(--muted);
}

.dialog-tabs {
  margin-top: 14px;
}

.dialog-stage {
  margin-top: 16px;
  min-height: 420px;
  border-radius: 20px;
  background: #050a14;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
}

.dialog-stage-image,
.dialog-stage-video {
  width: 100%;
  max-height: 70vh;
  object-fit: contain;
  display: block;
  background: #050a14;
}

.dialog-hint {
  padding: 14px 18px 20px;
  color: rgba(214, 222, 235, 0.82);
}

.in-list {
  color: var(--muted);
}

@media (max-width: 1320px) {
  .followup-grid,
  .followup-groups {
    grid-template-columns: 1fr;
  }

  .asset-filter-panel {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .filter-field.wide,
  .filter-actions {
    grid-column: span 3;
  }

  .asset-workbench {
    grid-template-columns: 1fr;
  }

  .asset-detail-rail {
    position: static;
  }

  .channel-list {
    max-height: 720px;
  }

  .asset-grid-head {
    grid-template-columns: minmax(0, 1.16fr) minmax(122px, 0.9fr) minmax(108px, 0.76fr) minmax(102px, 0.68fr);
  }

  .channel-card {
    grid-template-columns: 6px minmax(0, 1.16fr) minmax(122px, 0.9fr) minmax(108px, 0.76fr) minmax(102px, 0.68fr);
  }
}

@media (max-width: 900px) {
  .asset-hero,
  .list-toolbar,
  .selected-head,
  .preview-head,
  .section-mini-head,
  .dialog-head,
  .asset-topology-banner {
    flex-direction: column;
    align-items: stretch;
  }

  .asset-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .asset-filter-panel {
    grid-template-columns: 1fr;
  }

  .asset-roadmap,
  .asset-metrics {
    grid-template-columns: 1fr;
  }

  .list-command-strip {
    grid-template-columns: 1fr;
  }

  .batch-workbench-strip {
    grid-template-columns: 1fr;
  }

  .inline-controls {
    grid-template-columns: 1fr;
  }

  .inline-actions {
    justify-content: flex-start;
  }

  .selection-brief {
    min-width: 0;
  }

  .summary-kpis {
    grid-template-columns: 1fr;
  }

  .filter-field.wide,
  .filter-actions {
    grid-column: auto;
  }

  .asset-grid-head {
    display: none;
  }

  .channel-card {
    grid-template-columns: 5px minmax(0, 1fr);
  }

  .channel-identity,
  .channel-meta-stack,
  .channel-area-cell,
  .channel-side {
    grid-column: 2;
    align-items: flex-start;
    text-align: left;
  }

  .channel-identity {
    grid-template-columns: 1fr;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .device-form-grid {
    grid-template-columns: 1fr;
  }

  .dialog-backdrop {
    padding: 12px;
  }
}

</style>

<style>
html[data-theme="dark"] .asset-command-page {
  --asset-panel: rgba(7, 18, 31, 0.86);
  --asset-panel-strong: rgba(10, 25, 42, 0.94);
  --asset-card: linear-gradient(135deg, rgba(13, 32, 52, 0.96), rgba(6, 18, 31, 0.9));
  --asset-card-active:
    radial-gradient(circle at 100% 0%, rgba(91, 206, 255, 0.24), transparent 42%),
    linear-gradient(135deg, rgba(15, 47, 76, 0.98), rgba(7, 22, 38, 0.94));
  --asset-inner: rgba(3, 12, 23, 0.42);
  --asset-border: rgba(116, 180, 218, 0.22);
  --asset-input-bg: rgba(5, 16, 29, 0.92);
  color: #e7f5ff;
}

html[data-theme="dark"] .asset-command-page .asset-filter-panel,
html[data-theme="dark"] .asset-command-page .asset-list-panel,
html[data-theme="dark"] .asset-command-page .selected-overview,
html[data-theme="dark"] .asset-command-page .metric-card,
html[data-theme="dark"] .asset-command-page .asset-followup-panel,
html[data-theme="dark"] .asset-command-page .asset-toast {
  border-color: rgba(116, 180, 218, 0.22);
  background:
    radial-gradient(circle at 92% 6%, rgba(91, 206, 255, 0.1), transparent 34%),
    linear-gradient(180deg, rgba(10, 25, 42, 0.94), rgba(6, 17, 30, 0.9)) !important;
  color: #e7f5ff;
}

html[data-theme="dark"] .asset-command-page .channel-card,
html[data-theme="dark"] .asset-command-page .preview-card,
html[data-theme="dark"] .asset-command-page .detail-section,
html[data-theme="dark"] .asset-command-page .detail-grid div,
html[data-theme="dark"] .asset-command-page .device-dialog-shell,
html[data-theme="dark"] .asset-command-page .link-card,
html[data-theme="dark"] .asset-command-page .rtsp-box,
html[data-theme="dark"] .asset-command-page .stream-diagnostic-card {
  border-color: rgba(116, 180, 218, 0.18);
  background:
    radial-gradient(circle at 100% 0%, rgba(91, 206, 255, 0.08), transparent 36%),
    linear-gradient(135deg, rgba(12, 29, 48, 0.96), rgba(5, 16, 29, 0.9)) !important;
  color: #e7f5ff;
}

html[data-theme="dark"] .asset-command-page .channel-card.active {
  border-color: rgba(91, 206, 255, 0.55);
  background: var(--asset-card-active) !important;
  box-shadow: 0 20px 46px rgba(56, 189, 248, 0.16);
}

html[data-theme="dark"] .asset-command-page .filter-input,
html[data-theme="dark"] .asset-command-page .text-input,
html[data-theme="dark"] .asset-command-page .text-area,
html[data-theme="dark"] .asset-command-page .ghost-button,
html[data-theme="dark"] .asset-command-page .action-btn.subtle {
  border-color: rgba(116, 180, 218, 0.24) !important;
  background: rgba(5, 16, 29, 0.88) !important;
  color: #e7f5ff !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

html[data-theme="dark"] .asset-command-page .ghost-button:hover,
html[data-theme="dark"] .asset-command-page .action-btn.subtle:hover {
  border-color: rgba(91, 206, 255, 0.48) !important;
  background: rgba(11, 34, 54, 0.94) !important;
}

html[data-theme="dark"] .asset-command-page .summary-chip {
  border-color: rgba(116, 180, 218, 0.18);
  background:
    radial-gradient(circle at 100% 0%, rgba(91, 206, 255, 0.08), transparent 36%),
    linear-gradient(135deg, rgba(11, 29, 47, 0.96), rgba(6, 18, 31, 0.9));
}

html[data-theme="dark"] .asset-command-page .summary-chip strong {
  color: #e7f5ff;
}

html[data-theme="dark"] .asset-command-page .selection-brief,
html[data-theme="dark"] .asset-command-page .detail-empty-card,
html[data-theme="dark"] .asset-command-page .command-pill,
html[data-theme="dark"] .asset-command-page .inline-controls,
html[data-theme="dark"] .asset-command-page .batch-actions {
  border-color: rgba(116, 180, 218, 0.18);
  background:
    radial-gradient(circle at 100% 0%, rgba(91, 206, 255, 0.08), transparent 36%),
    linear-gradient(135deg, rgba(11, 29, 47, 0.96), rgba(6, 18, 31, 0.9));
}

html[data-theme="dark"] .asset-command-page .selection-brief strong,
html[data-theme="dark"] .asset-command-page .detail-empty-card strong,
html[data-theme="dark"] .asset-command-page .command-pill strong {
  color: #e7f5ff;
}

html[data-theme="dark"] .asset-command-page .filter-input option {
  background: #071827;
  color: #e7f5ff;
}

html[data-theme="dark"] .asset-command-page .text-input option {
  background: #071827;
  color: #e7f5ff;
}

html[data-theme="dark"] .asset-command-page .metric-card span,
html[data-theme="dark"] .asset-command-page .metric-card small,
html[data-theme="dark"] .asset-command-page .list-toolbar span,
html[data-theme="dark"] .asset-command-page .selected-head span,
html[data-theme="dark"] .asset-command-page .preview-head span,
html[data-theme="dark"] .asset-command-page .section-mini-head span,
html[data-theme="dark"] .asset-command-page .channel-meta-row,
html[data-theme="dark"] .asset-command-page .channel-area,
html[data-theme="dark"] .asset-command-page .channel-side small,
html[data-theme="dark"] .asset-command-page .detail-grid label,
html[data-theme="dark"] .asset-command-page .link-card label,
html[data-theme="dark"] .asset-command-page .rtsp-box label,
html[data-theme="dark"] .asset-command-page .link-card p {
  color: #8fb0c6 !important;
}

html[data-theme="dark"] .asset-command-page .metric-card strong,
html[data-theme="dark"] .asset-command-page .channel-title-row strong,
html[data-theme="dark"] .asset-command-page .channel-side span,
html[data-theme="dark"] .asset-command-page .selected-head h3,
html[data-theme="dark"] .asset-command-page .detail-grid p,
html[data-theme="dark"] .asset-command-page .link-card strong,
html[data-theme="dark"] .asset-command-page .rtsp-box p {
  color: #f4fbff !important;
}

html[data-theme="dark"] .asset-command-page .status-pill.ok,
html[data-theme="dark"] .asset-command-page .status-ring.ok {
  color: #b7f7d8 !important;
  background: rgba(18, 185, 129, 0.18) !important;
  border-color: rgba(18, 185, 129, 0.32);
}

html[data-theme="dark"] .asset-command-page .status-pill.warn,
html[data-theme="dark"] .asset-command-page .status-ring.warn {
  color: #ffd59a !important;
  background: rgba(245, 165, 36, 0.18) !important;
  border-color: rgba(245, 165, 36, 0.34);
}

html[data-theme="dark"] .asset-command-page .status-pill.stale,
html[data-theme="dark"] .asset-command-page .status-ring.stale {
  color: #cbd5e1 !important;
  background: rgba(100, 116, 139, 0.2) !important;
  border-color: rgba(148, 163, 184, 0.28);
}

html[data-theme="dark"] .asset-command-page .status-pill.danger,
html[data-theme="dark"] .asset-command-page .status-ring.danger {
  color: #fecdd3 !important;
  background: rgba(244, 63, 94, 0.2) !important;
  border-color: rgba(244, 63, 94, 0.36);
}

html.dark .asset-page-wrapper,
html[data-theme="dark"] .asset-page-wrapper {
  --asset-panel: rgba(255, 255, 255, 0.05);
  --asset-panel-strong: rgba(255, 255, 255, 0.08);
  --asset-card: rgba(255, 255, 255, 0.05);
  --asset-card-active:
    radial-gradient(circle at 100% 0%, rgba(91, 206, 255, 0.24), transparent 42%),
    rgba(255, 255, 255, 0.08);
  --asset-inner: rgba(255, 255, 255, 0.04);
  --asset-border: rgba(255, 255, 255, 0.1);
  --asset-input-bg: rgba(255, 255, 255, 0.08);
  --el-card-bg-color: rgba(255, 255, 255, 0.05);
  color: #e7f5ff;
}

html.dark .asset-page-wrapper .asset-filter-panel,
html.dark .asset-page-wrapper .asset-list-panel,
html.dark .asset-page-wrapper .selected-overview,
html.dark .asset-page-wrapper .metric-card,
html.dark .asset-page-wrapper .asset-toast,
html[data-theme="dark"] .asset-page-wrapper .asset-filter-panel,
html[data-theme="dark"] .asset-page-wrapper .asset-list-panel,
html[data-theme="dark"] .asset-page-wrapper .selected-overview,
html[data-theme="dark"] .asset-page-wrapper .metric-card,
html[data-theme="dark"] .asset-page-wrapper .asset-toast {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05) !important;
  color: #e7f5ff;
}

html.dark .asset-page-wrapper .asset-floor-panel,
html[data-theme="dark"] .asset-page-wrapper .asset-floor-panel {
  background: rgba(255, 255, 255, 0.05);
}
</style>
