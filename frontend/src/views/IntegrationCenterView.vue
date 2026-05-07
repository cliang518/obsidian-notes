<template>
  <section class="page integration-workbench-page">
    <WorkbenchShell leftWidth="312px" rightWidth="380px" maxWidth="1880px">
      <template #title>
        <div class="title-block">
          <p>INTEGRATION WORKBENCH</p>
          <h2>接入中心工作台</h2>
          <span>左边先收事实源和导入动作，中间只保留质量体检与补齐作战区，右边固定承接来源详情、补采对象和链路落地状态。</span>
        </div>
      </template>

      <template #actions>
        <button class="tool-btn" @click="refreshAll">刷新接入状态</button>
        <button class="tool-btn" @click="runImport('jvss-main')">同步 200</button>
        <button class="tool-btn" @click="runImport('jvss-stream')">同步 205</button>
        <button class="tool-btn" @click="runSwitchLiveProbeBatch">交换机探测</button>
        <button class="tool-btn primary" @click="goTo('/topology')">打开拓扑中心</button>
      </template>

      <template #summary>
        <section class="integration-metrics">
          <article class="metric-card">
            <span>事实源总数</span>
            <strong>{{ summary.source_count || 0 }}</strong>
            <small>当前已登记的只读来源</small>
          </article>
          <article class="metric-card">
            <span>同步作业</span>
            <strong>{{ summary.job_count || 0 }}</strong>
            <small>当前可回看的接入作业</small>
          </article>
          <article class="metric-card">
            <span>快照记录</span>
            <strong>{{ summary.snapshot_count || 0 }}</strong>
            <small>接入过程留痕样本</small>
          </article>
          <article class="metric-card">
            <span>富成待补链路</span>
            <strong>{{ fuchengAlignment.switch_unbound_total || 0 }}</strong>
            <small>当前尚未落链的通道</small>
          </article>
          <article class="metric-card">
            <span>数据就绪度</span>
            <strong>{{ fuchengDataQuality.readiness_score || 0 }}%</strong>
            <small>视频主线可落地程度</small>
          </article>
          <article class="metric-card">
            <span>当前来源</span>
            <strong>{{ sourceDetail?.source?.name || "等待选择" }}</strong>
            <small>{{ actionMessage }}</small>
          </article>
        </section>
      </template>

      <template #roadmap>
        <section class="integration-roadmap">
          <article class="roadmap-step">
            <span>01</span>
            <strong>先收事实源</strong>
            <small>200、205、TG/COS、扫描结果都只读接入，先确认范围再动落地。</small>
          </article>
          <article class="roadmap-step">
            <span>02</span>
            <strong>再做质量体检</strong>
            <small>先盯 RTSP、区域、拓扑归属和重复脏数据，不直接回写第三方。</small>
          </article>
          <article class="roadmap-step">
            <span>03</span>
            <strong>集中补齐缺口</strong>
            <small>把区域纠偏、交换机补采、现场核验表都拉进同一个工作台闭环。</small>
          </article>
          <article class="roadmap-step">
            <span>04</span>
            <strong>回到资产与拓扑</strong>
            <small>接入中心只负责事实源对齐，最终结果要回到资产、拓扑和运维主线。</small>
          </article>
        </section>
      </template>

      <template #left>
        <aside class="integration-left-rail">
          <section class="scope-block">
            <div class="side-head">
              <strong>手动导入控制</strong>
              <span>只读接入，不改第三方</span>
            </div>
            <div class="scope-list">
              <button class="scope-row" @click="runImport('jvss-main')">
                <strong>同步富成主平台 200</strong>
                <span>把主线通道、区域、资产基础重新拉回 V2</span>
              </button>
              <button class="scope-row" @click="runImport('jvss-stream')">
                <strong>同步富成 B2 平台 205</strong>
                <span>把停车场 / 商场副线重新拉回 V2</span>
              </button>
              <button class="scope-row" @click="runImport('tg-cos')">
                <strong>同步 TG/COS 交换机关联</strong>
                <span>让交换机、终端、区域和候选链路重新对齐</span>
              </button>
              <button class="scope-row" @click="runImport('tg-cos-network-scan')">
                <strong>同步 TG 网络扫描</strong>
                <span>把新增网络设备和扫描事实只读落到资产层</span>
              </button>
              <button class="scope-row" @click="runImport('tg-cos-vlan')">
                <strong>回填交换机 VLAN</strong>
                <span>补齐交换机 VLAN 维度，便于后续楼层和域划分</span>
              </button>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>事实源卡片</strong>
              <span>{{ summary.source_cards?.length || 0 }} 个来源</span>
            </div>
            <div class="source-list">
              <button
                v-for="source in summary.source_cards || []"
                :key="source.id"
                class="source-row"
                :class="{ active: selectedSourceId === source.id }"
                @click="selectSource(source.id)"
              >
                <strong>{{ source.name }}</strong>
                <span>{{ formatSourceType(source.source_type) }} / {{ source.management_ip || "-" }}</span>
                <small>设备 {{ source.runtime_stats?.device_total || 0 }} / 通道 {{ source.runtime_stats?.channel_total || 0 }}</small>
              </button>
            </div>
          </section>

          <section class="scope-block">
            <div class="side-head">
              <strong>优先补采批次</strong>
              <span>{{ prioritySwitchBatches.length }} 组</span>
            </div>
            <div class="scope-list">
              <button
                v-for="item in prioritySwitchBatches.slice(0, 6)"
                :key="`priority-${item.switch_ip}`"
                class="scope-row"
                @click="openSwitchAsset(item.switch_ip)"
              >
                <strong>{{ item.switch_name || item.switch_ip }}</strong>
                <span>{{ item.switch_ip }} / 命中 {{ item.count }} 条待补链路</span>
                <small>{{ item.reason || "建议优先补采该交换机的登录、ARP、MAC 表和运行配置。" }}</small>
              </button>
              <p v-if="!prioritySwitchBatches.length" class="empty-note">当前没有优先补采批次。</p>
            </div>
          </section>
        </aside>
      </template>

      <template #default>
        <section class="integration-center">
          <article class="panel workbench-panel quality-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">QUALITY GATE</p>
                <h3>富成主线数据质量体检</h3>
                <span>只读核验 200 / 205 已落地到 V2 的数据，重点盯 RTSP、区域、拓扑归属和重复数据</span>
              </div>
              <div class="quality-score" :class="qualityScoreClass">
                <span>就绪度</span>
                <strong>{{ fuchengDataQuality.readiness_score || 0 }}%</strong>
              </div>
            </div>

            <div class="quality-metric-grid">
              <div
                v-for="metric in fuchengDataQuality.metrics || []"
                :key="metric.key"
                class="quality-metric"
                :class="`severity-${metric.severity || 'info'}`"
              >
                <span>{{ metric.label }}</span>
                <strong>{{ metric.count || 0 }}</strong>
              </div>
            </div>

            <div class="quality-platform-grid">
              <article
                v-for="platform in fuchengDataQuality.platforms || []"
                :key="`quality-platform-${platform.management_ip}`"
                class="quality-platform-card"
              >
                <div class="source-card-head">
                  <strong>{{ platform.platform_name }}</strong>
                  <span class="pill subtle">{{ platform.management_ip }}</span>
                </div>
                <div class="source-card-stats">
                  <div><label>通道</label><strong>{{ platform.channel_total || 0 }}</strong></div>
                  <div><label>RTSP</label><strong>{{ platform.rtsp_ready || 0 }}</strong></div>
                  <div><label>拓扑</label><strong>{{ platform.topology_bound || 0 }}</strong></div>
                </div>
                <div class="alignment-breakdown" v-if="platform.top_issues?.length">
                  <span v-for="issue in platform.top_issues" :key="`${platform.management_ip}-${issue.code}`" class="pill">
                    {{ issue.label }} {{ issue.count }}
                  </span>
                </div>
              </article>
            </div>

            <div v-if="fuchengDataQuality.sample_issues?.length" class="quality-samples">
              <div class="quality-samples-head">
                <strong>异常样本</strong>
                <span>先处理红色问题，再处理区域和拓扑补齐。</span>
              </div>
              <div class="stack-list compact-quality-list">
                <div
                  v-for="item in (fuchengDataQuality.sample_issues || []).slice(0, 8)"
                  :key="`${item.issue_code}-${item.channel_id}`"
                  class="stack-item"
                >
                  <strong>{{ item.issue_label }} / {{ item.camera_ip || item.channel_name || item.channel_id }}</strong>
                  <span>{{ item.platform_name }} {{ item.platform_ip }} / 通道 {{ item.channel_no || "-" }} / {{ item.channel_name || "-" }}</span>
                  <span v-if="item.direct_area">区域：{{ item.direct_area }}</span>
                  <span v-if="item.detail">{{ item.detail }}</span>
                  <div class="action-row wrap">
                    <button class="ghost-button" @click="openAssetByCamera(item.camera_ip)">定位资产</button>
                    <button class="ghost-button" @click="openVideoByCamera(item.camera_ip, item.channel_id)">看视频</button>
                  </div>
                </div>
              </div>
            </div>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">AREA NORMALIZATION</p>
                <h3>区域尾号纠偏与缺口补齐</h3>
                <span>按真实 camera_ip 重扫，把污染尾号从区域字段里拿掉，再把高置信区域建议应用回 V2</span>
              </div>
              <div class="list-actions">
                <button class="tool-btn" @click="refreshAreaNormalization">重新扫描尾号污染</button>
                <button class="tool-btn primary" @click="applyAreaNormalization">按真实 IP 纠偏</button>
              </div>
            </div>

            <div class="repair-summary-grid">
              <div><span>污染通道</span><strong>{{ fuchengAreaNormalization.polluted_channel_total || 0 }}</strong></div>
              <div><span>错尾号</span><strong>{{ fuchengAreaNormalization.tail_mismatch_total || 0 }}</strong></div>
              <div><span>通道待修正</span><strong>{{ fuchengAreaNormalization.channel_updates || 0 }}</strong></div>
              <div><span>摄像头区域回正</span><strong>{{ fuchengAreaNormalization.camera_area_updates || 0 }}</strong></div>
              <div><span>区域缺口</span><strong>{{ fuchengRepairPlan.area_missing_total || 0 }}</strong></div>
              <div><span>可自动补齐</span><strong>{{ fuchengRepairPlan.area_auto_applicable_total || 0 }}</strong></div>
            </div>

            <div class="action-row wrap">
              <button class="tool-btn" @click="previewApplyAreaSuggestions">预演区域补齐</button>
              <button class="tool-btn primary" @click="applyAreaSuggestions">应用高置信区域</button>
              <button class="tool-btn" @click="exportFieldValidationTemplate">导出现场核验表</button>
              <button class="tool-btn" @click="exportFuchengRepairPlan">导出补齐计划</button>
            </div>

            <section class="repair-columns top-gap">
              <div>
                <h4>污染通道样本</h4>
                <div class="stack-list compact-quality-list">
                  <div
                    v-for="item in (fuchengAreaNormalization.sample_channels || []).slice(0, 8)"
                    :key="`area-normalization-channel-${item.channel_id}`"
                    class="stack-item"
                  >
                    <strong>{{ item.camera_ip || "-" }} / {{ item.normalized_area || "待纠偏" }}</strong>
                    <span>{{ item.platform_name || "-" }} / {{ item.channel_name || "-" }}</span>
                    <span>原始：{{ item.direct_area_raw || "-" }}</span>
                    <span>旧尾号：{{ item.legacy_tail || "-" }} / 实际尾号：{{ item.actual_tail || "-" }}</span>
                  </div>
                </div>
              </div>
              <div>
                <h4>拓扑核验样本</h4>
                <div class="stack-list compact-quality-list">
                  <div
                    v-for="item in (fuchengRepairPlan.topology_suggestions || []).slice(0, 8)"
                    :key="`topology-suggest-${item.channel_id}`"
                    class="stack-item"
                  >
                    <strong>{{ item.camera_ip }} / {{ item.candidate_switch_ip || "待现场定位" }}</strong>
                    <span>{{ item.direct_area || item.channel_name || "-" }}</span>
                    <span>{{ item.evidence }}</span>
                    <div class="action-row wrap">
                      <button class="ghost-button" @click="openAssetByCamera(item.camera_ip)">定位摄像头</button>
                      <button v-if="item.candidate_switch_ip" class="ghost-button" @click="openSwitchAsset(item.candidate_switch_ip)">看候选交换机</button>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </article>

          <article class="panel workbench-panel">
            <div class="list-toolbar">
              <div>
                <p class="eyebrow">DISCOVERY WORKBENCH</p>
                <h3>设备发现作战台</h3>
                <span>把扫描、探测、导入收成一个闭环，让新增设备和补采结果能直接进入 V2 的拓扑和运维链路</span>
              </div>
              <div class="list-actions">
                <button class="tool-btn" @click="refreshSwitchLiveProbes">刷新探测结果</button>
                <button class="tool-btn primary" @click="runSwitchLiveProbeBatch">执行交换机探测</button>
              </div>
            </div>

            <div class="repair-summary-grid">
              <div><span>探测总数</span><strong>{{ switchLiveProbes.length || 0 }}</strong></div>
              <div><span>正常</span><strong>{{ switchLiveProbes.filter((item) => item.probe_status === 'ok').length }}</strong></div>
              <div><span>离线</span><strong>{{ switchLiveProbes.filter((item) => item.probe_status === 'offline').length }}</strong></div>
              <div><span>异常</span><strong>{{ switchLiveProbes.filter((item) => item.probe_status === 'error').length }}</strong></div>
              <div><span>待确认</span><strong>{{ switchLiveProbes.filter((item) => item.probe_status === 'unknown').length }}</strong></div>
            </div>

            <div class="action-row wrap">
              <button class="tool-btn" @click="runImport('tg-cos-network-scan')">导入 TG 网络扫描</button>
              <button class="tool-btn" @click="runImport('tg-cos')">同步 TG/COS 交换机关联</button>
              <button class="tool-btn" @click="runImport('tg-cos-vlan')">回填交换机 VLAN</button>
            </div>

            <section class="repair-columns top-gap">
              <div>
                <h4>最新交换机探测</h4>
                <div class="stack-list compact-quality-list">
                  <div
                    v-for="item in switchLiveProbes.slice(0, 10)"
                    :key="`switch-probe-${item.device_id}`"
                    class="stack-item"
                  >
                    <strong>{{ item.label || item.management_ip }}</strong>
                    <span>{{ item.management_ip }} / {{ formatProbeStatus(item.probe_status) }}</span>
                    <span>ARP {{ item.arp_entry_count || 0 }} / MAC {{ item.l2_mac_count || 0 }} / 摄像头命中 {{ item.camera_match_count || 0 }}</span>
                    <span>最近探测：{{ item.checked_at || "-" }}</span>
                    <div class="action-row wrap">
                      <button class="ghost-button" @click="openSwitchAsset(item.management_ip)">定位交换机</button>
                    </div>
                  </div>
                </div>
              </div>
              <div>
                <h4>发现流程说明</h4>
                <div class="stack-list compact-quality-list">
                  <div class="stack-item">
                    <strong>1. 先探测</strong>
                    <span>确认交换机是否在线、是否有 ARP/MAC 表、是否具备接入口特征。</span>
                  </div>
                  <div class="stack-item">
                    <strong>2. 再导入</strong>
                    <span>把 `tg-cos-network-scan` 的扫描结果只读导入资产库，生成设备和映射。</span>
                  </div>
                  <div class="stack-item">
                    <strong>3. 再回拓扑</strong>
                    <span>探测结果和导入结果一起回到拓扑中心，补交换机归属和链路证据。</span>
                  </div>
                </div>
              </div>
            </section>
          </article>
        </section>
      </template>

      <template #right>
        <aside class="integration-right-rail">
          <section class="detail-shell">
            <div class="side-head">
              <strong>来源详情</strong>
              <span>{{ sourceDetail?.source?.name || "选择左侧事实源" }}</span>
            </div>

            <template v-if="sourceDetail">
              <div class="detail-summary-grid">
                <article class="detail-chip">
                  <span>同步状态</span>
                  <strong>{{ formatSyncStatus(sourceDetail.source.sync_status) }}</strong>
                </article>
                <article class="detail-chip">
                  <span>最近同步</span>
                  <strong>{{ sourceDetail.source.last_sync_at || "-" }}</strong>
                </article>
                <article class="detail-chip">
                  <span>运行设备</span>
                  <strong>{{ sourceDetail.runtime_stats?.device_total || 0 }}</strong>
                </article>
                <article class="detail-chip">
                  <span>运行通道</span>
                  <strong>{{ sourceDetail.runtime_stats?.channel_total || 0 }}</strong>
                </article>
              </div>

              <div class="stack-list">
                <div class="stack-item"><strong>来源</strong><span>{{ formatSourceType(sourceDetail.source.source_type) }} / {{ sourceDetail.source.vendor || "-" }} / {{ sourceDetail.source.management_ip || "-" }}</span></div>
                <div class="stack-item"><strong>映射总数</strong><span>{{ sourceDetail.mapping_total || 0 }}</span></div>
                <div class="stack-item"><strong>可预览</strong><span>{{ sourceDetail.runtime_stats?.preview_ready || 0 }} / 预览异常 {{ sourceDetail.runtime_stats?.preview_failed || 0 }}</span></div>
                <div class="stack-item"><strong>已归属交换机</strong><span>{{ sourceDetail.runtime_stats?.switch_bound || 0 }}</span></div>
              </div>

              <div class="split-panel">
                <div>
                  <h4>映射类型</h4>
                  <ul class="plain-list compact-list">
                    <li v-for="item in sourceDetail.mapping_type_breakdown || []" :key="item.source_object_type">
                      {{ formatMappingType(item.source_object_type) }}：{{ item.count }}
                    </li>
                  </ul>
                </div>
                <div>
                  <h4>设备类型</h4>
                  <ul class="plain-list compact-list">
                    <li v-for="item in sourceDetail.device_type_breakdown || []" :key="item.device_type">
                      {{ formatDeviceType(item.device_type) }}：{{ item.count }}
                    </li>
                  </ul>
                </div>
              </div>
            </template>
            <p v-else class="empty-note">选择左侧事实源卡片后，这里会显示来源详情和最近样本。</p>
          </section>

          <section class="detail-shell">
            <div class="side-head">
              <strong>富成主线落地状态</strong>
              <span>{{ fuchengAlignment.cards?.length || 0 }} 个平台</span>
            </div>

            <div class="source-card-grid">
              <article
                v-for="card in fuchengAlignment.cards || []"
                :key="card.management_ip"
                class="source-card alignment-card"
              >
                <div class="source-card-head">
                  <strong>{{ card.platform_name }}</strong>
                  <span class="pill subtle">{{ card.management_ip }}</span>
                </div>
                <p class="source-card-meta">共 {{ card.channel_total || 0 }} 路，已归属 {{ card.switch_bound || 0 }} 路，待补 {{ card.switch_unbound || 0 }} 路</p>
                <div class="source-card-stats">
                  <div><label>可预览</label><strong>{{ card.preview_ready || 0 }}</strong></div>
                  <div><label>预览异常</label><strong>{{ card.preview_failed || 0 }}</strong></div>
                  <div><label>仅可达</label><strong>{{ card.reachable || 0 }}</strong></div>
                </div>
                <div v-if="card.switch_unbound_breakdown?.length" class="alignment-breakdown">
                  <span v-for="item in card.switch_unbound_breakdown" :key="`${card.management_ip}-${item.reason_code}`" class="pill">
                    {{ item.reason_label }} {{ item.count }}
                  </span>
                </div>
                <div class="action-row wrap">
                  <button class="ghost-button" @click="openAssetWorkbench(card.management_ip)">打开资产工作台</button>
                </div>
              </article>
            </div>
          </section>

          <section class="detail-shell">
            <div class="side-head">
              <strong>待补采交换机</strong>
              <span>{{ (tgSwitchAuditCoverage.pending_switches || []).length }} 台</span>
            </div>
            <div class="stack-list">
              <div
                v-for="item in (tgSwitchAuditCoverage.pending_switches || []).slice(0, 8)"
                :key="`pending-switch-${item.device_id}`"
                class="stack-item"
              >
                <strong>{{ item.hostname || item.management_ip }}</strong>
                <span>{{ item.management_ip }} / {{ item.model || "-" }}</span>
                <span>已采能力：{{ formatCapabilities(item.capabilities) }}</span>
                <div class="action-row wrap">
                  <button class="ghost-button" @click="openSwitchAsset(item.management_ip)">定位交换机</button>
                </div>
              </div>
            </div>
          </section>
        </aside>
      </template>
    </WorkbenchShell>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import WorkbenchShell from "../components/workbench/WorkbenchShell.vue";
import {
  applyFuchengAreaSuggestions,
  downloadFuchengDataQualityCsv,
  downloadFuchengAlignmentCsv,
  fetchFuchengAreaNormalizationPreview,
  downloadFuchengFieldValidationTemplateCsv,
  downloadFuchengRepairPlanCsv,
  downloadTgSwitchAuditCoverageCsv,
  applyFuchengAreaNormalization,
  fetchFuchengAlignment,
  fetchFuchengDataQuality,
  fetchFuchengRepairPlan,
  fetchIntegrationSourceDetail,
  fetchIntegrationSummary,
  fetchTopologySwitchLiveProbes,
  fetchTgSwitchAuditCoverage,
  importSingleSource,
  runTopologySwitchLiveProbe,
} from "../api/client";

const router = useRouter();

const summary = ref({
  latest_jobs: [],
  latest_snapshots: [],
  source_cards: [],
  source_type_breakdown: [],
  source_count: 0,
  job_count: 0,
  snapshot_count: 0,
});
const fuchengAlignment = ref({ cards: [], switch_unbound_total: 0 });
const fuchengDataQuality = ref({
  channel_total: 0,
  readiness_score: 0,
  issue_total: 0,
  metrics: [],
  platforms: [],
  sample_issues: [],
});
const fuchengAreaNormalization = ref({
  polluted_channel_total: 0,
  channel_updates: 0,
  camera_area_updates: 0,
  polluted_area_row_total: 0,
  area_row_updates: 0,
  area_rows_removed: 0,
  tail_mismatch_total: 0,
  sample_channels: [],
  sample_areas: [],
});
const fuchengRepairPlan = ref({
  area_missing_total: 0,
  area_auto_applicable_total: 0,
  area_manual_total: 0,
  topology_missing_total: 0,
  topology_with_candidate_total: 0,
  area_suggestions: [],
  area_task_groups: [],
  topology_suggestions: [],
  topology_task_groups: [],
});
const tgSwitchAuditCoverage = ref({
  switch_total: 0,
  valid_switch_total: 0,
  audited_switch_total: 0,
  partial_switch_total: 0,
  unaudited_switch_total: 0,
  invalid_switch_total: 0,
  recommendations: [],
  pending_switches: [],
  invalid_switches: [],
});
const switchLiveProbes = ref([]);
const sourceDetail = ref(null);
const selectedSourceId = ref(null);
const actionMessage = ref("可按来源手动触发只读导入。");

const prioritySwitchBatches = computed(() => {
  const bucket = new Map();
  for (const card of fuchengAlignment.value.cards || []) {
    for (const item of card.recommended_switches || []) {
      const switchIp = item.switch_ip || "";
      if (!switchIp) continue;
      const existing = bucket.get(switchIp) || {
        switch_ip: switchIp,
        switch_name: item.switch_name || switchIp,
        count: 0,
        platforms: [],
        primary_platform_ip: card.management_ip || "",
        reason: item.reason || "",
      };
      existing.count += Number(item.count || 0);
      if (card.platform_name && !existing.platforms.includes(card.platform_name)) {
        existing.platforms.push(card.platform_name);
      }
      if (!existing.reason && item.reason) {
        existing.reason = item.reason;
      }
      bucket.set(switchIp, existing);
    }
  }
  return Array.from(bucket.values()).sort((a, b) => b.count - a.count).slice(0, 10);
});

const qualityScoreClass = computed(() => {
  const score = Number(fuchengDataQuality.value.readiness_score || 0);
  if (score >= 90) return "is-good";
  if (score >= 70) return "is-warning";
  return "is-danger";
});

onMounted(async () => {
  await refreshAll();
});

async function refreshAll() {
  try {
    summary.value = await fetchIntegrationSummary();
    fuchengAlignment.value = await fetchFuchengAlignment();
    fuchengDataQuality.value = await fetchFuchengDataQuality();
    fuchengAreaNormalization.value = await fetchFuchengAreaNormalizationPreview();
    fuchengRepairPlan.value = await fetchFuchengRepairPlan();
    tgSwitchAuditCoverage.value = await fetchTgSwitchAuditCoverage();
    await refreshSwitchLiveProbes();
    if (summary.value.source_cards?.length) {
      const targetId = selectedSourceId.value || summary.value.source_cards[0].id;
      await selectSource(targetId);
    }
    actionMessage.value = "接入状态已刷新。";
  } catch (error) {
    console.error(error);
    actionMessage.value = "接入中心加载失败，请查看后端日志。";
  }
}

async function refreshSwitchLiveProbes() {
  try {
    const result = await fetchTopologySwitchLiveProbes(60);
    switchLiveProbes.value = Array.isArray(result?.items) ? result.items : [];
  } catch (error) {
    console.error(error);
    switchLiveProbes.value = [];
  }
}

async function runSwitchLiveProbeBatch() {
  try {
    const result = await runTopologySwitchLiveProbe({ limit: 12 });
    actionMessage.value = `交换机活体探测已执行：${result?.results?.length || 0} 台。`;
    await refreshSwitchLiveProbes();
  } catch (error) {
    console.error(error);
    actionMessage.value = "交换机活体探测执行失败，请查看后端日志。";
  }
}

async function selectSource(sourceId) {
  try {
    selectedSourceId.value = sourceId;
    sourceDetail.value = await fetchIntegrationSourceDetail(sourceId);
  } catch (error) {
    console.error(error);
  }
}

async function runImport(sourceKey) {
  try {
    const result = await importSingleSource(sourceKey);
    if (result?.error) {
      actionMessage.value = `导入失败：${result.error}`;
      return;
    }
    actionMessage.value = `已导入 ${result.source_name}，设备 ${result.devices || 0}，通道 ${result.channels || 0}，链路 ${result.links || 0}，区域 ${result.areas || 0}，告警 ${result.alerts || 0}`;
    await refreshAll();
  } catch (error) {
    console.error(error);
    actionMessage.value = "手动导入失败，请查看后端日志。";
  }
}

async function exportFuchengAlignment() {
  try {
    const blob = await downloadFuchengAlignmentCsv();
    downloadBlob(blob, "fucheng-alignment-gap.csv");
    actionMessage.value = "已导出富成缺口清单。";
  } catch (error) {
    console.error(error);
    actionMessage.value = "导出富成缺口清单失败，请查看后端日志。";
  }
}

async function exportFuchengDataQuality() {
  try {
    const blob = await downloadFuchengDataQualityCsv();
    downloadBlob(blob, "fucheng-data-quality-issues.csv");
    actionMessage.value = "已导出富成数据质量问题清单。";
  } catch (error) {
    console.error(error);
    actionMessage.value = "导出富成数据质量问题失败，请查看后端日志。";
  }
}

async function exportFuchengRepairPlan() {
  try {
    const blob = await downloadFuchengRepairPlanCsv();
    downloadBlob(blob, "fucheng-repair-plan.csv");
    actionMessage.value = "已导出富成缺口补齐计划。";
  } catch (error) {
    console.error(error);
    actionMessage.value = "导出富成缺口补齐计划失败，请查看后端日志。";
  }
}

async function refreshAreaNormalization() {
  try {
    fuchengAreaNormalization.value = await fetchFuchengAreaNormalizationPreview();
    actionMessage.value = `已重扫区域尾号污染：污染通道 ${fuchengAreaNormalization.value.polluted_channel_total || 0} 条，错尾号 ${fuchengAreaNormalization.value.tail_mismatch_total || 0} 条。`;
  } catch (error) {
    console.error(error);
    actionMessage.value = "重扫区域尾号污染失败，请查看后端日志。";
  }
}

async function applyAreaNormalization() {
  try {
    const result = await applyFuchengAreaNormalization();
    actionMessage.value = `已按真实 IP 纠偏：通道 ${result.channel_updates || 0} 条，摄像头区域 ${result.camera_area_updates || 0} 条，区域引用 ${result.area_row_updates || 0} 条。`;
    await refreshAll();
  } catch (error) {
    console.error(error);
    actionMessage.value = "应用区域尾号纠偏失败，请确认账号权限或查看后端日志。";
  }
}

async function exportFieldValidationTemplate() {
  try {
    const blob = await downloadFuchengFieldValidationTemplateCsv();
    downloadBlob(blob, "fucheng-field-validation-template.csv");
    actionMessage.value = "已导出现场核验表，现场只填写 collected_area / collected_switch_ip / collected_port 等回填列。";
  } catch (error) {
    console.error(error);
    actionMessage.value = "导出现场核验表失败，请查看后端日志。";
  }
}

async function previewApplyAreaSuggestions() {
  try {
    const result = await applyFuchengAreaSuggestions({ dry_run: true, min_confidence: 0.9 });
    actionMessage.value = `预演完成：可补 ${result.updated || 0} 条，跳过 ${result.skipped || 0} 条。`;
  } catch (error) {
    console.error(error);
    actionMessage.value = "预演区域补齐失败，请查看后端日志。";
  }
}

async function applyAreaSuggestions() {
  try {
    const result = await applyFuchengAreaSuggestions({ dry_run: false, min_confidence: 0.9 });
    actionMessage.value = `已应用高置信区域补齐：更新 ${result.updated || 0} 条，跳过 ${result.skipped || 0} 条。`;
    await refreshAll();
  } catch (error) {
    console.error(error);
    actionMessage.value = "应用区域补齐失败，请确认账号权限或查看后端日志。";
  }
}

async function exportTgSwitchAuditCoverage() {
  try {
    const blob = await downloadTgSwitchAuditCoverageCsv();
    downloadBlob(blob, "tg-switch-audit-coverage.csv");
    actionMessage.value = "已导出交换机补采清单。";
  } catch (error) {
    console.error(error);
    actionMessage.value = "导出交换机补采清单失败，请查看后端日志。";
  }
}

function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

function openAssetByCamera(cameraIp) {
  router.push({
    path: "/assets",
    query: {
      q: cameraIp || "",
      device_type: "camera",
      source_type: "jvss",
      from: "integration",
    },
  });
}

function goTo(path) {
  router.push(path);
}

function openAssetWorkbench(managementIp) {
  router.push({
    path: "/assets",
    query: {
      device_type: "camera",
      source_type: "jvss",
      source_management_ip: managementIp || "",
      from: "integration",
    },
  });
}

function openSwitchAsset(managementIp) {
  router.push({
    path: "/assets",
    query: {
      q: managementIp || "",
      device_type: "switch",
      source_type: "tg_cos",
      from: "integration",
    },
  });
}

function openVideoByCamera(cameraIp, channelId) {
  router.push({
    path: "/video",
    query: {
      q: cameraIp || "",
      channel_id: channelId ? String(channelId) : "",
    },
  });
}

function formatCapabilities(capabilities) {
  if (!Array.isArray(capabilities) || !capabilities.length) return "未采集";
  const labelMap = { login: "登录", arp: "ARP", mac_table: "MAC表", running_config: "运行配置", version: "版本" };
  return capabilities.map((item) => labelMap[item] || item).join(" / ");
}

function formatSourceType(sourceType) {
  const labelMap = {
    jvss: "富成/JVSS",
    tg_cos: "TG/COS",
    hikvision_nvr: "海康录像机",
    legacy_alerts: "旧告警",
    system: "系统内置",
  };
  return labelMap[sourceType] || sourceType || "未标记";
}

function formatProbeStatus(status) {
  const labelMap = { ok: "正常", offline: "离线", error: "异常", unknown: "待确认" };
  return labelMap[status] || status || "待确认";
}

function formatMappingType(mappingType) {
  const labelMap = {
    camera: "摄像头",
    channel: "视频通道",
    switch: "交换机",
    topology_link: "拓扑链路",
    terminal: "终端",
    area: "区域",
    alert: "告警",
  };
  return labelMap[mappingType] || mappingType || "未标记";
}

function formatDeviceType(deviceType) {
  const labelMap = {
    camera: "摄像头",
    switch: "交换机",
    nvr: "录像机",
    server: "服务器",
    workstation: "工作站",
    decoder: "解码器",
    gateway: "网关",
    unknown: "未标记",
  };
  return labelMap[deviceType] || deviceType || "未标记";
}

function formatSyncStatus(status) {
  const labelMap = { completed: "已完成", running: "进行中", failed: "失败", pending: "待执行", partial: "部分完成" };
  return labelMap[status] || status || "未执行";
}
</script>

<style scoped>
.integration-workbench-page {
  padding-bottom: 24px;
}

.integration-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.metric-card,
.scope-block,
.panel,
.detail-shell,
.ops-guide-card,
.detail-chip,
.quality-metric,
.quality-platform-card,
.source-row,
.source-card {
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
.ops-guide-card span,
.quality-metric span {
  font-size: 12px;
  color: rgba(207, 231, 255, 0.68);
}

.metric-card strong,
.detail-chip strong,
.ops-guide-card strong,
.quality-metric strong {
  font-size: 20px;
  color: #f4fbff;
}

.metric-card small,
.detail-chip small,
.ops-guide-card small,
.roadmap-step small,
.hint-row span,
.scope-row span,
.source-row span,
.status-line,
.empty-note,
.source-card-meta,
.stack-item span {
  color: rgba(207, 231, 255, 0.72);
}

.integration-roadmap {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
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

.integration-left-rail,
.integration-center,
.integration-right-rail {
  display: grid;
  gap: 12px;
  min-height: 0;
}

.scope-block,
.panel,
.detail-shell {
  border-radius: 20px;
  padding: 16px;
}

.side-head,
.list-toolbar,
.source-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.side-head strong,
.list-toolbar h3,
.source-card-head strong {
  color: #f4fbff;
}

.side-head span,
.list-toolbar span,
.eyebrow {
  color: rgba(207, 231, 255, 0.72);
}

.scope-list,
.hint-list,
.stack-list,
.source-list,
.source-card-grid {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.source-list,
.compact-quality-list {
  max-height: 520px;
  overflow: auto;
  padding-right: 4px;
}

.scope-row,
.hint-row,
.source-row,
.stack-item,
.source-card {
  width: 100%;
  text-align: left;
  border-radius: 16px;
  padding: 12px 14px;
  display: grid;
  gap: 4px;
  color: #f4fbff;
}

.scope-row,
.hint-row,
.stack-item,
.source-row {
  border: 1px solid rgba(111, 191, 255, 0.14);
  background: rgba(255, 255, 255, 0.03);
}

.source-row.active {
  border-color: rgba(111, 191, 255, 0.42);
  background: linear-gradient(180deg, rgba(24, 75, 115, 0.52), rgba(14, 43, 70, 0.4));
}

.ops-guide-strip,
.repair-summary-grid,
.quality-metric-grid,
.quality-platform-grid,
.repair-columns,
.detail-summary-grid,
.split-panel,
.source-card-stats {
  display: grid;
  gap: 12px;
}

.ops-guide-strip {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.repair-summary-grid {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  margin-top: 14px;
}

.repair-summary-grid div {
  border: 1px solid rgba(111, 191, 255, 0.14);
  border-radius: 18px;
  background: linear-gradient(160deg, rgba(20, 184, 166, 0.12), rgba(59, 130, 246, 0.06));
  padding: 16px;
}

.repair-summary-grid span {
  display: block;
  color: rgba(207, 231, 255, 0.68);
  font-size: 12px;
  margin-bottom: 6px;
}

.repair-summary-grid strong {
  color: #f4fbff;
  font-size: 24px;
}

.quality-metric-grid {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  margin-top: 14px;
}

.quality-platform-grid {
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  margin-top: 14px;
}

.quality-metric,
.quality-platform-card {
  border-radius: 18px;
  padding: 16px;
}

.quality-metric.severity-danger {
  border-color: rgba(248, 113, 113, 0.28);
}

.quality-metric.severity-warning {
  border-color: rgba(251, 191, 36, 0.28);
}

.quality-score {
  min-width: 128px;
  border: 1px solid rgba(111, 191, 255, 0.18);
  border-radius: 22px;
  padding: 14px 18px;
  background: linear-gradient(135deg, rgba(34, 211, 238, 0.16), rgba(59, 130, 246, 0.08));
  text-align: right;
}

.quality-score span {
  display: block;
  color: rgba(207, 231, 255, 0.68);
  font-size: 12px;
  margin-bottom: 4px;
}

.quality-score strong {
  color: #f4fbff;
  font-size: 28px;
}

.quality-score.is-good {
  box-shadow: 0 0 30px rgba(52, 211, 153, 0.18);
}

.quality-score.is-warning {
  box-shadow: 0 0 30px rgba(251, 191, 36, 0.18);
}

.quality-score.is-danger {
  box-shadow: 0 0 30px rgba(248, 113, 113, 0.18);
}

.quality-samples {
  margin-top: 16px;
}

.quality-samples-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  color: rgba(207, 231, 255, 0.68);
}

.repair-columns,
.detail-summary-grid,
.split-panel {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.action-row.wrap,
.list-actions,
.table-actions,
.alignment-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 58px;
  padding: 4px 9px;
  border-radius: 999px;
  border: 1px solid rgba(111, 191, 255, 0.2);
  background: rgba(255, 255, 255, 0.05);
  color: rgba(207, 231, 255, 0.8);
  font-size: 12px;
}

.source-card-stats {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.source-card-stats label {
  display: block;
  color: rgba(207, 231, 255, 0.62);
  font-size: 12px;
  margin-bottom: 4px;
}

.source-card-stats strong {
  color: #f4fbff;
}

.detail-chip {
  border-radius: 16px;
  padding: 12px 14px;
  display: grid;
  gap: 4px;
}

.ghost-button,
.tool-btn {
  cursor: pointer;
}

@media (max-width: 1380px) {
  .integration-metrics,
  .integration-roadmap {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .ops-guide-strip,
  .repair-columns,
  .detail-summary-grid,
  .split-panel,
  .source-card-stats {
    grid-template-columns: 1fr;
  }

  .quality-score {
    width: 100%;
    text-align: left;
  }
}

@media (max-width: 960px) {
  .integration-metrics,
  .integration-roadmap {
    grid-template-columns: 1fr;
  }
}
</style>
