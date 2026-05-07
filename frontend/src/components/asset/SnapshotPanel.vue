<template>
  <aside class="snapshot-panel-shell">
    <el-scrollbar class="snapshot-scrollbar">
      <article v-if="c.feedbackMessage" class="asset-toast">
        <strong>{{ c.feedbackMessage }}</strong>
        <span>最近刷新：{{ c.lastUpdatedLabel }}</span>
      </article>

      <template v-if="c.filters.device_type === 'camera' && c.selectedChannel">
        <div class="selected-head">
          <div>
            <p class="eyebrow">SELECTED CAMERA</p>
            <h3>{{ c.helpers.cameraTitle(c.selectedChannel) }}</h3>
            <span class="mono">{{ c.selectedChannel.camera_ip || "-" }}</span>
          </div>
          <el-tag :type="c.helpers.assetStatusTagType(c.selectedChannel)">{{ c.helpers.assetStatusLabel(c.selectedChannel) }}</el-tag>
        </div>

        <div class="summary-kpis">
          <article><span>视频验收</span><strong>{{ c.helpers.streamProbeDisplayLabel(c.selectedChannel) || "未扫描" }}</strong></article>
          <article><span>链路置信</span><strong>{{ c.selectedChannel.topology_confidence ? `${Math.round(c.selectedChannel.topology_confidence * 100)}%` : "待确认" }}</strong></article>
          <article><span>所属平台</span><strong>{{ c.helpers.platformLabel(c.selectedChannel) }}</strong></article>
          <article><span>区域精度</span><strong>{{ c.helpers.areaAccuracyLabel(c.selectedChannel) || "常规口径" }}</strong></article>
        </div>

        <div class="primary-ops">
          <el-button type="primary" @click="c.actions.openPreview(c.selectedChannel)">打开预览</el-button>
          <el-button @click="c.actions.refreshSelectedSnapshot()">刷新快照</el-button>
          <el-button @click="c.actions.openBindingDialog(c.selectedChannel)">链路归属</el-button>
          <el-button @click="c.actions.openDeviceForm(c.selectedChannel)">编辑资产</el-button>
          <el-button @click="c.actions.copyRtsp(c.selectedChannel)">复制 RTSP</el-button>
        </div>

        <section class="preview-card">
          <div class="panel-mini-head">
            <div>
              <strong>实时快照</strong>
              <span>{{ c.selectedChannel.snapshot_capture_enabled ? "来自 RTSP 当前帧" : "当前通道暂不可抓帧" }}</span>
            </div>
            <el-button size="small" @click="c.actions.refreshSelectedSnapshot()">刷新</el-button>
          </div>
          <div class="snapshot-stage">
            <img v-if="c.selectedSnapshotUrl" :src="c.selectedSnapshotUrl" :alt="c.selectedChannel.camera_ip || 'snapshot'" class="snapshot-image" />
            <div v-else class="snapshot-placeholder">NO SIGNAL / RTSP SNAPSHOT PENDING</div>
          </div>
          <div class="preview-actions">
            <el-button @click="c.actions.openSnapshot(c.selectedChannel)">放大快照</el-button>
            <el-button :disabled="!c.selectedChannel.switch_ip" @click="c.actions.openSelectedChannelTopology()">拓扑查看</el-button>
            <el-button type="danger" @click="c.actions.archiveSelectedDevice()">归档资产</el-button>
          </div>
        </section>

        <section class="detail-section">
          <div class="panel-mini-head">
            <strong>链路归属</strong>
            <span>{{ c.selectedChannel.topology_confidence ? `置信度 ${Math.round(c.selectedChannel.topology_confidence * 100)}%` : "待确认" }}</span>
          </div>
          <div class="link-card" :class="{ muted: c.selectedChannel.switch_binding_state !== 'bound' }">
            <div><label>交换机</label><strong>{{ c.helpers.clean(c.selectedChannel.switch_label || c.selectedChannel.switch_ip || "待补归属") }}</strong></div>
            <div><label>端口 / VLAN</label><strong>{{ c.selectedChannel.switch_port_name || "-" }}<template v-if="c.selectedChannel.switch_port_vlan_id"> / VLAN {{ c.selectedChannel.switch_port_vlan_id }}</template></strong></div>
            <div><label>归属来源</label><strong>{{ c.helpers.topologyEvidenceLabel(c.selectedChannel) }}</strong></div>
            <p>{{ c.helpers.clean(c.selectedChannel.topology_evidence_summary || "暂无链路证据，请通过拓扑补齐或现场核验。") }}</p>
          </div>
        </section>

        <section class="detail-section">
          <div class="panel-mini-head">
            <strong>视频验收证据</strong>
            <el-button size="small" @click="c.actions.copyDiagnostic(c.selectedChannel)">复制摘要</el-button>
          </div>
          <div class="rtsp-box">
            <label>主码流 RTSP</label>
            <p class="mono">{{ c.selectedChannel.rtsp_main || "当前通道没有主码流地址" }}</p>
          </div>
          <div class="stream-diagnostic-card" :class="c.helpers.streamStatusClass(c.selectedChannel)">
            <div>
              <strong>{{ c.helpers.streamProbeDisplayLabel(c.selectedChannel) || "未扫描" }}</strong>
              <span>最近扫描：{{ c.helpers.formatProbeTime(c.selectedChannel.stream_probe_checked_at) }}</span>
            </div>
            <p>{{ c.helpers.streamAdvice(c.selectedChannel) }}</p>
            <small v-if="c.selectedChannel.stream_probe_error">{{ c.helpers.clean(c.selectedChannel.stream_probe_error) }}</small>
          </div>
        </section>

        <section class="detail-section">
          <div class="panel-mini-head"><strong>基础资料</strong><span>{{ c.helpers.sourceLineageLabel(c.selectedChannel) }}</span></div>
          <div class="detail-grid">
            <div><label>所属平台</label><p>{{ c.helpers.platformLabel(c.selectedChannel) }}</p></div>
            <div><label>通道号</label><p>{{ c.selectedChannel.channel_no || "-" }}</p></div>
            <div><label>区域</label><p>{{ c.helpers.clean(c.selectedChannel.area_menu_label || c.selectedChannel.area_display_name || c.selectedChannel.direct_area || "-") }}</p><small>{{ c.helpers.areaScopeNote(c.selectedChannel) }}</small></div>
            <div><label>平台状态</label><p>{{ c.helpers.platformStatusLabel(c.selectedChannel.direct_platform_status) }}</p></div>
          </div>
          <div class="maintenance-actions">
            <el-button @click="c.actions.openDeviceForm(null, c.selectedChannel)">按当前通道补建资产</el-button>
          </div>
        </section>
      </template>

      <template v-else-if="c.filters.device_type === 'switch' && c.selectedSwitch">
        <div class="selected-head">
          <div>
            <p class="eyebrow">SELECTED SWITCH</p>
            <h3>{{ c.helpers.clean(c.selectedSwitch.hostname || c.selectedSwitch.display_name || "-") }}</h3>
            <span class="mono">{{ c.selectedSwitch.management_ip || "-" }}</span>
          </div>
          <el-tag :type="c.helpers.assetStatusTagType(c.selectedSwitch)">{{ c.helpers.assetStatusLabel(c.selectedSwitch) }}</el-tag>
        </div>

        <div class="summary-kpis">
          <article><span>实时探测</span><strong>{{ c.helpers.healthStateLabel(c.selectedSwitch.live_probe_status) }}</strong></article>
          <article><span>拓扑角色</span><strong>{{ c.helpers.clean(c.selectedSwitch.topology_role_label || c.selectedSwitch.topology_gap_label || "待确认") }}</strong></article>
          <article><span>命中摄像头</span><strong>{{ c.selectedSwitch.live_probe_camera_match_count || 0 }}</strong></article>
          <article><span>L2 MAC</span><strong>{{ c.selectedSwitch.live_probe_l2_mac_count || 0 }}</strong></article>
        </div>

        <div class="primary-ops">
          <el-button type="primary" :loading="c.switchProbeBusy" @click="c.actions.probeSelectedSwitch()">{{ c.switchProbeBusy ? "实采中..." : "实时探测" }}</el-button>
          <el-button :disabled="!c.selectedSwitch.management_ip" @click="c.actions.openSelectedSwitchTopology()">拓扑核实</el-button>
          <el-button @click="c.actions.openExistingDeviceForm(c.selectedSwitch)">编辑资产</el-button>
        </div>

        <section class="detail-section">
          <div class="panel-mini-head">
            <strong>实时探测</strong>
            <span>{{ c.selectedSwitch.live_probe_checked_at ? c.selectedSwitch.live_probe_checked_at.replace("T", " ") : "尚未实采" }}</span>
          </div>
          <div v-if="c.selectedSwitch.topology_role_label" class="switch-judgement-banner" :class="{ warning: c.selectedSwitch.topology_auto_flagged }">
            <strong>{{ c.selectedSwitch.topology_role_label }}</strong>
            <span>{{ c.helpers.clean(c.selectedSwitch.topology_judgement_summary || "系统已根据交换机实采结果自动标记。") }}</span>
          </div>
          <div class="detail-grid">
            <div><label>探测状态</label><p>{{ c.helpers.healthStateLabel(c.selectedSwitch.live_probe_status) }}</p></div>
            <div><label>版本</label><p>{{ c.helpers.clean(c.selectedSwitch.live_probe_version_text || "-") }}</p></div>
            <div><label>Telnet</label><p class="mono">{{ c.helpers.clean(c.selectedSwitch.live_probe_telnet_status || "-") }}</p></div>
            <div><label>HTTP / HTTPS</label><p class="mono">{{ c.helpers.clean(c.selectedSwitch.live_probe_http_status || "-") }} / {{ c.helpers.clean(c.selectedSwitch.live_probe_https_status || "-") }}</p></div>
            <div><label>ARP 条目</label><p>{{ c.selectedSwitch.live_probe_arp_entry_count || 0 }}</p></div>
            <div><label>自动判定</label><p>{{ c.helpers.clean(c.selectedSwitch.topology_gap_label || "-") }}</p></div>
          </div>
        </section>

        <section class="detail-section">
          <div class="panel-mini-head"><strong>基础资料</strong><span>{{ c.helpers.clean(c.selectedSwitch.primary_source_type || "manual") }}</span></div>
          <div class="detail-grid">
            <div><label>区域</label><p>{{ c.helpers.clean(c.selectedSwitch.area_display_name || c.selectedSwitch.area_name || "-") }}</p></div>
            <div><label>厂商</label><p>{{ c.helpers.clean(c.selectedSwitch.vendor || "-") }}</p></div>
            <div><label>型号</label><p>{{ c.helpers.clean(c.selectedSwitch.model || "-") }}</p></div>
            <div><label>资产状态</label><p>{{ c.helpers.deviceStatusLabel(c.selectedSwitch.device_status) }}</p></div>
            <div><label>管理 IP</label><p class="mono">{{ c.selectedSwitch.management_ip || "-" }}</p></div>
            <div><label>MAC</label><p class="mono">{{ c.helpers.clean(c.selectedSwitch.mac_address || "-") }}</p></div>
          </div>
        </section>
      </template>

      <template v-else>
        <article class="empty-state">
          <p class="eyebrow">{{ c.filters.device_type === "switch" ? "SELECT A SWITCH" : "SELECT A CAMERA" }}</p>
          <strong>{{ c.visibleAssetCount > 0 ? "右侧雷达已就绪，先从中间清单选中对象。" : "当前筛选范围里还没有可处理对象。" }}</strong>
          <span>{{ c.visibleAssetCount > 0 ? c.currentSelectionGuide : "可以先恢复默认筛选，或直接新增资产后再继续处理。" }}</span>
          <div class="primary-ops">
            <el-button v-if="c.visibleAssetCount > 0" type="primary" @click="c.actions.selectFirstVisible()">定位第一项</el-button>
            <el-button @click="c.actions.resetFilters()">恢复默认</el-button>
            <el-button @click="c.actions.openDeviceForm()">添加资产</el-button>
          </div>
        </article>
      </template>
    </el-scrollbar>
  </aside>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  context: {
    type: Object,
    required: true,
  },
});

const c = computed(() => props.context);
</script>

<style scoped>
.snapshot-panel-shell {
  flex: 0 0 400px;
  width: 400px;
  min-width: 400px;
  height: 100%;
  overflow: hidden;
  border-left: 1px solid rgba(56, 189, 248, 0.15);
  background: #05080f;
  color: #dbeafe;
}

.snapshot-scrollbar {
  height: 100%;
  padding: 10px;
}

.asset-toast,
.selected-head,
.summary-kpis article,
.preview-card,
.detail-section,
.empty-state {
  border: 1px solid rgba(56, 189, 248, 0.15);
  background: transparent;
}

.asset-toast,
.selected-head,
.preview-card,
.detail-section,
.empty-state {
  margin-bottom: 10px;
  padding: 10px;
}

.asset-toast,
.selected-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.asset-toast strong,
.selected-head h3 {
  margin: 0;
  color: #e2e8f0;
  font-size: 14px;
}

.asset-toast span,
.selected-head span,
.panel-mini-head span,
.empty-state span {
  color: rgba(148, 163, 184, 0.72);
  font-size: 11px;
}

.eyebrow {
  margin: 0 0 2px;
  color: #38bdf8;
  font-family: Consolas, monospace;
  font-size: 10px;
  letter-spacing: 0.16em;
}

.mono {
  font-family: Consolas, monospace;
}

.summary-kpis {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 10px;
}

.summary-kpis article {
  display: grid;
  gap: 3px;
  padding: 8px;
}

.summary-kpis span,
.detail-grid label,
.rtsp-box label,
.link-card label {
  color: rgba(148, 163, 184, 0.72);
  font-size: 10px;
  letter-spacing: 0.08em;
}

.summary-kpis strong,
.link-card strong {
  overflow: hidden;
  color: #e2e8f0;
  font-family: Consolas, monospace;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.primary-ops,
.preview-actions,
.maintenance-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 10px;
}

.snapshot-stage {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  overflow: hidden;
  border: 1px solid rgba(56, 189, 248, 0.16);
  background:
    linear-gradient(rgba(56, 189, 248, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.06) 1px, transparent 1px),
    #020617;
  background-size: 12px 12px;
}

.snapshot-stage::after {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: "";
  background: repeating-linear-gradient(180deg, transparent 0, transparent 7px, rgba(125, 211, 252, 0.08) 8px);
}

.snapshot-image {
  position: relative;
  z-index: 1;
  max-width: 100%;
  max-height: 240px;
  object-fit: contain;
}

.snapshot-placeholder {
  z-index: 1;
  color: rgba(125, 211, 252, 0.74);
  font-family: Consolas, monospace;
  font-size: 12px;
}

.panel-mini-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.panel-mini-head strong {
  color: #7dd3fc;
  font-size: 12px;
}

.link-card,
.rtsp-box,
.stream-diagnostic-card,
.switch-judgement-banner {
  display: grid;
  gap: 6px;
  padding: 8px;
  border-left: 2px solid rgba(56, 189, 248, 0.45);
  background: #080b14;
}

.link-card p,
.rtsp-box p,
.stream-diagnostic-card p,
.stream-diagnostic-card small,
.switch-judgement-banner span {
  margin: 0;
  color: rgba(219, 234, 254, 0.86);
  font-size: 12px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.detail-grid > div {
  min-width: 0;
  padding: 7px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.detail-grid p {
  overflow: hidden;
  margin: 2px 0 0;
  color: #e2e8f0;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-grid small {
  color: rgba(148, 163, 184, 0.68);
  font-size: 10px;
}

.empty-state {
  display: grid;
  gap: 8px;
}

.empty-state strong {
  color: #e2e8f0;
  font-size: 14px;
}
</style>
