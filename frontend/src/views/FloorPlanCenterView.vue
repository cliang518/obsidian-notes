<template>
  <section class="page floor-plan-page">
    <header class="hero-panel">
      <div>
        <p class="hero-eyebrow">FLOOR PLAN CENTER</p>
        <h2>楼层图与 CAD 解析中心</h2>
        <p class="hero-copy">
          这套模块现在已经支持 DWG / DXF 轻量解析、监控块识别、后两段 IP 抽取，以及和现有资产库做自动比对。
        </p>
      </div>
      <div class="hero-stats">
        <article class="stat-card">
          <span>图纸文档</span>
          <strong>{{ summary.document_count || 0 }}</strong>
        </article>
        <article class="stat-card">
          <span>已解析</span>
          <strong>{{ summary.parsed_count || 0 }}</strong>
        </article>
        <article class="stat-card">
          <span>已命中锚点</span>
          <strong>{{ summary.matched_count || 0 }}</strong>
        </article>
        <article class="stat-card">
          <span>支持格式</span>
          <strong>{{ (summary.formats || []).join(" / ") || "-" }}</strong>
        </article>
      </div>
    </header>

    <section class="panel-grid">
      <article class="panel glass-panel">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">UPLOAD</p>
            <h3>上传并解析图纸</h3>
          </div>
          <span class="panel-tip">建议填写楼栋、楼层、区域，方便后续做地图联动</span>
        </div>
        <div class="form-grid">
          <input v-model.trim="form.title" class="filter-input" placeholder="图纸标题，如 1F 北楼监控图" />
          <input v-model.trim="form.site" class="filter-input" placeholder="站点，如 永嘉集团信息弱电" />
          <input v-model.trim="form.building" class="filter-input" placeholder="楼栋，如 北楼 / 中央大道" />
          <input v-model.trim="form.floor" class="filter-input" placeholder="楼层，如 1F / B2" />
          <input v-model.trim="form.zone" class="filter-input" placeholder="区域，如 北楼东区 / 停车场" />
          <textarea v-model.trim="form.notes" class="filter-input textarea-input" placeholder="备注，如 数据来源、平面图版本、现场说明"></textarea>
          <input ref="fileInput" type="file" class="filter-input" accept=".dxf,.dwg" @change="handleFileChange" />
        </div>
        <div class="action-row">
          <button class="primary-button" :disabled="uploading || !selectedFile" @click="submitUpload">
            {{ uploading ? "解析中..." : "上传并解析" }}
          </button>
          <span class="muted">{{ selectedFile ? selectedFile.name : "请选择 DXF / DWG 图纸文件" }}</span>
        </div>
      </article>

      <article class="panel glass-panel">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">RECENT</p>
            <h3>最近图纸</h3>
          </div>
          <span class="panel-tip">点击任意图纸即可查看解析详情</span>
        </div>
        <div class="table-shell">
          <table class="mini-table">
            <thead>
              <tr>
                <th>图纸</th>
                <th>位置</th>
                <th>解析状态</th>
                <th>解析器</th>
                <th>候选</th>
                <th>命中</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="doc in documents"
                :key="doc.id"
                class="click-row"
                :class="{ active: selectedDetail?.document?.id === doc.id }"
                @click="loadDetail(doc.id)"
              >
                <td>
                  <div class="doc-title-cell">
                    <strong>{{ doc.title || doc.original_filename }}</strong>
                    <span>{{ doc.original_filename || "-" }}</span>
                  </div>
                </td>
                <td>{{ [doc.building, doc.floor, doc.zone].filter(Boolean).join(" / ") || "-" }}</td>
                <td>
                  <span class="status-pill" :class="statusClass(doc.parse_status)">
                    {{ parseStatusLabel(doc.parse_status) }}
                  </span>
                </td>
                <td>{{ parserLabel(doc.parser_used) }}</td>
                <td>{{ doc.extracted_suffix_count }}</td>
                <td>{{ doc.matched_anchor_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>

    <section v-if="selectedDetail?.document" class="detail-layout">
      <article class="panel detail-main">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">DETAIL</p>
            <h3>图纸解析结果</h3>
          </div>
          <div class="action-row compact">
            <button class="ghost-button" @click="reparseSelected">重新解析</button>
            <span class="muted">当前优先使用轻量流式解析，适合大型 DWG 图纸。</span>
          </div>
        </div>

        <div class="detail-grid">
          <div>
            <label>图纸名称</label>
            <p>{{ selectedDetail.document.title || selectedDetail.document.original_filename }}</p>
          </div>
          <div>
            <label>解析状态</label>
            <p>{{ parseStatusLabel(selectedDetail.document.parse_status) }}</p>
          </div>
          <div>
            <label>位置</label>
            <p>{{ [selectedDetail.document.building, selectedDetail.document.floor, selectedDetail.document.zone].filter(Boolean).join(" / ") || "-" }}</p>
          </div>
          <div>
            <label>解析器</label>
            <p>{{ parserLabel(selectedDetail.document.parser_used) }}</p>
          </div>
          <div>
            <label>文本实体</label>
            <p>{{ selectedDetail.document.extracted_text_count || 0 }}</p>
          </div>
          <div>
            <label>候选锚点</label>
            <p>{{ selectedDetail.document.extracted_suffix_count || 0 }}</p>
          </div>
          <div>
            <label>已命中设备</label>
            <p>{{ selectedDetail.document.matched_anchor_count || 0 }}</p>
          </div>
          <div>
            <label>高置信锚点</label>
            <p>{{ selectedDetail.document.high_confidence_anchor_count || 0 }}</p>
          </div>
        </div>

        <div class="insight-row">
          <article class="insight-card">
            <span>已命中</span>
            <strong>{{ selectedDetail.document.matched_anchor_count || 0 }}</strong>
            <small>已与现有资产库摄像头对上号</small>
          </article>
          <article class="insight-card warning">
            <span>待核实</span>
            <strong>{{ selectedDetail.document.unmatched_anchor_count || 0 }}</strong>
            <small>需要后续现场核实或继续调规则</small>
          </article>
          <article class="insight-card">
            <span>主要图层</span>
            <strong>{{ selectedDetail.layers?.[0]?.layer_name || "-" }}</strong>
            <small>当前图纸文本最密集的图层</small>
          </article>
        </div>

        <div class="chip-grid top-gap">
          <div v-for="layer in selectedDetail.layers.slice(0, 12)" :key="layer.layer_name" class="info-chip static-chip">
            <strong>{{ layer.layer_name || "默认图层" }}</strong>
            <span>{{ layer.count }} 条实体</span>
          </div>
        </div>
      </article>

      <article class="panel detail-side">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">ANCHORS</p>
            <h3>锚点与命中设备</h3>
          </div>
          <span class="panel-tip">优先展示高置信且已命中的结果</span>
        </div>

        <div class="anchor-list">
          <article v-for="anchor in rankedAnchors" :key="anchor.id" class="anchor-card">
            <div class="anchor-top">
              <div>
                <strong>{{ anchor.normalized_text || anchor.anchor_text || "-" }}</strong>
                <p>{{ anchor.layer_name || "默认图层" }} · {{ entityLabel(anchor.entity_type) }}</p>
              </div>
              <span class="confidence-pill" :class="confidenceClass(anchor.confidence)">
                {{ confidencePercent(anchor.confidence) }}
              </span>
            </div>

            <div class="anchor-meta">
              <span>锚点文本：{{ anchor.anchor_text || "-" }}</span>
              <span>坐标：{{ formatCoord(anchor.pos_x) }} / {{ formatCoord(anchor.pos_y) }}</span>
            </div>

            <div v-if="anchor.matched_device_id" class="match-panel is-hit">
              <div class="match-head">
                <strong>{{ anchor.matched_device_ip || anchor.normalized_text }}</strong>
                <span>已命中资产</span>
              </div>
              <p>{{ anchor.matched_device_label || "未命名设备" }}</p>
              <div class="match-meta">
                <span>{{ deviceTypeLabel(anchor.matched_device_type) }}</span>
                <span>{{ anchor.matched_area_display_name || "未绑定区域" }}</span>
              </div>
              <small>{{ anchor.match_note || "已通过当前解析链命中设备。" }}</small>
            </div>

            <div v-else class="match-panel is-miss">
              <div class="match-head">
                <strong>{{ anchor.normalized_text || "-" }}</strong>
                <span>待核实</span>
              </div>
              <p>当前资产库内尚未直接命中对应设备</p>
              <small>{{ anchor.match_note || "建议继续现场核对，或后续补充资产数据。" }}</small>
            </div>

            <div v-if="anchor.candidates?.length" class="candidate-stack">
              <div v-for="candidate in anchor.candidates.slice(0, 3)" :key="`${anchor.id}-${candidate.ip}`" class="candidate-line">
                <strong>{{ candidate.ip }}</strong>
                <span>{{ candidate.label || "-" }}</span>
                <span>{{ candidate.area_display_name || "-" }}</span>
              </div>
            </div>
          </article>
        </div>
      </article>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import {
  fetchFloorPlanDetail,
  fetchFloorPlanDocuments,
  fetchFloorPlanSummary,
  reparseFloorPlan,
  uploadFloorPlan,
} from "../api/client";

const summary = ref({});
const documents = ref([]);
const selectedDetail = ref(null);
const selectedFile = ref(null);
const fileInput = ref(null);
const uploading = ref(false);

const form = reactive({
  title: "",
  site: "永嘉集团信息弱电",
  building: "",
  floor: "",
  zone: "",
  notes: "",
});

const rankedAnchors = computed(() => {
  const anchors = selectedDetail.value?.anchors || [];
  return [...anchors]
    .sort((left, right) => {
      const hitDelta = Number(!!right.matched_device_id) - Number(!!left.matched_device_id);
      if (hitDelta !== 0) return hitDelta;
      return Number(right.confidence || 0) - Number(left.confidence || 0);
    })
    .slice(0, 120);
});

onMounted(async () => {
  await reload();
});

async function reload() {
  const [summaryData, documentRows] = await Promise.all([
    fetchFloorPlanSummary(),
    fetchFloorPlanDocuments(),
  ]);
  summary.value = summaryData;
  documents.value = documentRows;
  if (documents.value.length) {
    const currentId = selectedDetail.value?.document?.id;
    const fallbackId = currentId && documents.value.some((row) => row.id === currentId) ? currentId : documents.value[0].id;
    await loadDetail(fallbackId);
  } else {
    selectedDetail.value = null;
  }
}

function handleFileChange(event) {
  selectedFile.value = event.target.files?.[0] || null;
}

async function submitUpload() {
  if (!selectedFile.value) return;
  uploading.value = true;
  try {
    const payload = new FormData();
    payload.append("file", selectedFile.value);
    payload.append("title", form.title);
    payload.append("site", form.site);
    payload.append("building", form.building);
    payload.append("floor", form.floor);
    payload.append("zone", form.zone);
    payload.append("notes", form.notes);
    selectedDetail.value = await uploadFloorPlan(payload);
    selectedFile.value = null;
    if (fileInput.value) {
      fileInput.value.value = "";
    }
    await reload();
  } catch (error) {
    console.error(error);
  } finally {
    uploading.value = false;
  }
}

async function loadDetail(documentId) {
  try {
    selectedDetail.value = await fetchFloorPlanDetail(documentId);
  } catch (error) {
    console.error(error);
  }
}

async function reparseSelected() {
  if (!selectedDetail.value?.document?.id) return;
  try {
    selectedDetail.value = await reparseFloorPlan(selectedDetail.value.document.id);
    await reload();
  } catch (error) {
    console.error(error);
  }
}

function parseStatusLabel(status) {
  const mapping = {
    parsed: "已解析",
    uploaded: "已上传",
    pending: "待处理",
    dependency_missing: "缺少依赖",
    conversion_required: "等待转换",
    dwg_pending: "DWG 待转换",
    unsupported: "暂不支持",
    missing_file: "文件缺失",
  };
  return mapping[status] || status || "-";
}

function parserLabel(parser) {
  const mapping = {
    stream_extract: "轻量流式解析",
    "odafc+ezdxf": "ODA + ezdxf",
    ezdxf: "ezdxf 直读",
    dwg_pending: "DWG 待转换",
  };
  return mapping[parser] || parser || "-";
}

function statusClass(status) {
  return {
    "is-good": status === "parsed",
    "is-warn": ["uploaded", "pending", "conversion_required", "dwg_pending"].includes(status),
    "is-bad": ["dependency_missing", "unsupported", "missing_file"].includes(status),
  };
}

function confidencePercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function confidenceClass(value) {
  const numeric = Number(value || 0);
  if (numeric >= 0.9) return "is-high";
  if (numeric >= 0.7) return "is-medium";
  return "is-low";
}

function formatCoord(value) {
  if (value === null || value === undefined || value === "") return "-";
  return Number(value).toFixed(1);
}

function entityLabel(value) {
  const mapping = {
    TEXT: "文字",
    MTEXT: "多行文字",
    INSERT: "块参照",
    ATTRIB: "属性",
    anchor_partial_ip: "监控块配对",
    partial_ip_text: "部分 IP 文本",
  };
  return mapping[value] || value || "-";
}

function deviceTypeLabel(value) {
  const mapping = {
    camera: "摄像头",
    camera_direct: "直连摄像头",
    camera_endpoint: "摄像头端点",
    switch: "交换机",
  };
  return mapping[value] || value || "设备";
}
</script>

<style scoped>
.floor-plan-page {
  display: grid;
  gap: 20px;
}

.hero-panel {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.9fr);
  gap: 18px;
  padding: 24px;
  border-radius: 24px;
  border: 1px solid rgba(118, 155, 255, 0.18);
  background:
    radial-gradient(circle at top left, rgba(96, 166, 255, 0.18), transparent 36%),
    linear-gradient(135deg, rgba(9, 20, 43, 0.94), rgba(12, 36, 67, 0.9));
  box-shadow: 0 20px 60px rgba(5, 15, 40, 0.24);
}

.hero-eyebrow,
.panel-kicker {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.24em;
  color: rgba(167, 205, 255, 0.78);
}

.hero-panel h2,
.panel-header h3 {
  margin: 0;
  color: #f4f8ff;
}

.hero-copy,
.panel-tip,
.muted {
  color: rgba(225, 234, 255, 0.72);
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.stat-card,
.insight-card {
  padding: 16px 18px;
  border-radius: 18px;
  border: 1px solid rgba(154, 190, 255, 0.16);
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(12px);
}

.stat-card span,
.insight-card span {
  display: block;
  font-size: 12px;
  color: rgba(221, 232, 255, 0.72);
}

.stat-card strong,
.insight-card strong {
  display: block;
  margin-top: 8px;
  font-size: 30px;
  color: #ffffff;
}

.panel-grid,
.detail-layout {
  display: grid;
  gap: 18px;
}

.panel-grid {
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
}

.detail-layout {
  grid-template-columns: minmax(0, 1.05fr) minmax(360px, 0.95fr);
}

.glass-panel,
.detail-main,
.detail-side {
  border-radius: 22px;
  border: 1px solid rgba(131, 153, 209, 0.16);
  background: linear-gradient(180deg, rgba(10, 17, 33, 0.84), rgba(14, 27, 51, 0.76));
  box-shadow: 0 22px 60px rgba(3, 10, 25, 0.18);
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.textarea-input {
  min-height: 96px;
  resize: vertical;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.action-row.compact {
  margin-top: 0;
}

.doc-title-cell {
  display: grid;
  gap: 4px;
}

.doc-title-cell strong {
  color: #f5f8ff;
}

.doc-title-cell span {
  font-size: 12px;
  color: rgba(215, 225, 248, 0.62);
}

.status-pill,
.confidence-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 78px;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.status-pill.is-good,
.confidence-pill.is-high {
  background: rgba(70, 198, 130, 0.16);
  color: #7df1b0;
}

.status-pill.is-warn,
.confidence-pill.is-medium {
  background: rgba(255, 190, 92, 0.16);
  color: #ffd38d;
}

.status-pill.is-bad,
.confidence-pill.is-low {
  background: rgba(255, 111, 111, 0.14);
  color: #ff9999;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.detail-grid label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  color: rgba(210, 221, 246, 0.66);
}

.detail-grid p {
  margin: 0;
  color: #f4f8ff;
}

.insight-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.insight-card small {
  display: block;
  margin-top: 8px;
  color: rgba(214, 225, 248, 0.68);
}

.insight-card.warning {
  border-color: rgba(255, 184, 88, 0.2);
}

.top-gap {
  margin-top: 18px;
}

.chip-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.static-chip {
  min-width: 120px;
}

.anchor-list {
  display: grid;
  gap: 12px;
  max-height: 980px;
  overflow: auto;
  padding-right: 4px;
}

.anchor-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(136, 160, 219, 0.14);
  background: rgba(255, 255, 255, 0.04);
}

.anchor-top,
.match-head,
.anchor-meta,
.match-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.anchor-top strong,
.match-head strong {
  color: #f5f8ff;
}

.anchor-top p,
.match-panel p {
  margin: 6px 0 0;
  color: rgba(215, 226, 248, 0.74);
}

.anchor-meta,
.match-meta {
  margin-top: 10px;
  font-size: 12px;
  color: rgba(210, 221, 246, 0.66);
  flex-wrap: wrap;
}

.match-panel {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 16px;
}

.match-panel.is-hit {
  background: rgba(70, 198, 130, 0.1);
  border: 1px solid rgba(70, 198, 130, 0.18);
}

.match-panel.is-miss {
  background: rgba(255, 184, 88, 0.08);
  border: 1px solid rgba(255, 184, 88, 0.16);
}

.match-panel small {
  display: block;
  margin-top: 10px;
  color: rgba(221, 230, 249, 0.66);
  line-height: 1.5;
}

.candidate-stack {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.candidate-line {
  display: grid;
  grid-template-columns: 1.1fr 1fr 1fr;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  color: rgba(225, 234, 255, 0.78);
  font-size: 12px;
}

@media (max-width: 1200px) {
  .hero-panel,
  .panel-grid,
  .detail-layout,
  .detail-grid,
  .insight-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .hero-stats {
    grid-template-columns: 1fr;
  }

  .candidate-line {
    grid-template-columns: 1fr;
  }
}
</style>
