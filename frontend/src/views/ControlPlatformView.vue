<template>
  <section class="page">
    <header class="hero">
      <div class="hero-copy">
        <p class="eyebrow">控制平台接入</p>
        <h2>风控 / 电控 / BA 平台接入中心</h2>
        <p class="lead">
          这里专门承接风控、电控、BA 新老平台的只读审计、资料预览、兼容性判断、导入计划和正式导入。
          当前原则是不依赖第三方平台运行，只把它们当作资料与关系事实源，后续逐步沉淀为 V2 自己的控制域底座。
        </p>
      </div>
      <div class="hero-side">
        <div class="hero-badge">
          <span>当前阶段</span>
          <strong>{{ platformStageLabel(summary.stage) }}</strong>
        </div>
        <div class="hero-metrics">
          <div>
            <label>接入策略</label>
            <strong>{{ platformStrategyLabel(summary.strategy) }}</strong>
          </div>
          <div>
            <label>已登记轨道</label>
            <strong>{{ summary.registration_count || 0 }}</strong>
          </div>
        </div>
      </div>
    </header>

    <section class="cards">
      <article class="card"><span>已登记轨道</span><strong>{{ summary.registration_count || 0 }}</strong></article>
      <article class="card"><span>实例数量</span><strong>{{ summary.instance_count || 0 }}</strong></article>
      <article class="card"><span>网络分域</span><strong>{{ summary.network_zone_count || 0 }}</strong></article>
      <article class="card"><span>可直接开审</span><strong>{{ summary.ready_count || 0 }}</strong></article>
      <article class="card"><span>已完成审计</span><strong>{{ summary.audited_count || 0 }}</strong></article>
      <article class="card"><span>控制设备</span><strong>{{ domainSummary.device_count || 0 }}</strong></article>
      <article class="card"><span>控制点位</span><strong>{{ domainSummary.point_count || 0 }}</strong></article>
      <article class="card"><span>控制场景</span><strong>{{ domainSummary.scenario_count || 0 }}</strong></article>
      <article class="card"><span>控制事件</span><strong>{{ domainSummary.event_count || 0 }}</strong></article>
      <article class="card"><span>菜单入口</span><strong>{{ domainSummary.menu_count || 0 }}</strong></article>
    </section>

    <section class="panel-grid">
      <article class="panel accent-panel">
        <h3>接入原则</h3>
        <ul class="plain-list compact-list">
          <li v-for="(item, index) in summary.design_notes || []" :key="index">{{ item }}</li>
        </ul>
      </article>
      <article class="panel">
        <h3>明日接入清单</h3>
        <div class="stack-list">
          <div v-for="item in summary.tomorrow_intake || []" :key="item.field" class="stack-item">
            <strong>{{ item.field }}</strong>
            <span>{{ item.description }}</span>
          </div>
        </div>
      </article>
    </section>

    <section class="panel-grid">
      <article class="panel">
        <h3>{{ editingId ? "编辑平台轨道" : "登记平台轨道" }}</h3>
        <div class="form-grid">
          <label>
            <span>轨道标识</span>
            <select v-model="form.track_key" class="text-input">
              <option value="electrical_control_platform">电控系统</option>
              <option value="new_control_platform">风控新平台</option>
              <option value="legacy_control_platform">风控老平台</option>
            </select>
          </label>
          <label>
            <span>实例名称</span>
            <input v-model="form.instance_name" class="text-input" placeholder="例如：风控新系统 A 栋实例" />
          </label>
          <label>
            <span>实例编码</span>
            <input v-model="form.instance_code" class="text-input" placeholder="例如：10.0.69.100" />
          </label>
          <label>
            <span>显示名称</span>
            <input v-model="form.display_name" class="text-input" placeholder="例如：风控新平台" />
          </label>
          <label>
            <span>平台类型</span>
            <input v-model="form.platform_family" class="text-input" placeholder="例如：风控 / 电控 / BA" />
          </label>
          <label>
            <span>厂商或来源</span>
            <input v-model="form.vendor" class="text-input" placeholder="例如：第三方控制平台" />
          </label>
          <label>
            <span>入口地址</span>
            <input v-model="form.base_url" class="text-input" placeholder="例如：http://10.0.69.100/Web/" />
          </label>
          <label>
            <span>入口名称</span>
            <input v-model="form.endpoint_name" class="text-input" placeholder="例如：Web 首页入口" />
          </label>
          <label>
            <span>入口路径</span>
            <input v-model="form.endpoint_path" class="text-input" placeholder="例如：/Web/ 或 /SmartEnergy/roomlist2.jsp" />
          </label>
          <label>
            <span>VLAN 编号</span>
            <input v-model="form.vlan_id" class="text-input" placeholder="例如：2 或 68-control" />
          </label>
          <label>
            <span>VLAN 名称</span>
            <input v-model="form.vlan_name" class="text-input" placeholder="例如：监控 VLAN2 / 风控电控 VLAN" />
          </label>
          <label>
            <span>网络分域</span>
            <input v-model="form.network_zone" class="text-input" placeholder="例如：视频监控域 / 风控电控域" />
          </label>
          <label>
            <span>管理 IP</span>
            <input v-model="form.management_ip" class="text-input" placeholder="可留空，系统会尝试提取" />
          </label>
          <label>
            <span>账号提示</span>
            <input v-model="form.username_hint" class="text-input" placeholder="只记录账号提示，不落库密码" />
          </label>
          <label>
            <span>访问模式</span>
            <select v-model="form.access_mode" class="text-input">
              <option value="web">网页</option>
              <option value="client">客户端</option>
              <option value="web_plus_client">网页 + 客户端</option>
              <option value="unknown">待确认</option>
            </select>
          </label>
          <label>
            <span>只读策略</span>
            <select v-model="form.read_only_strategy" class="text-input">
              <option value="web_audit">网页只读审计</option>
              <option value="api_audit">接口只读审计</option>
              <option value="client_capture">客户端抓取</option>
              <option value="hybrid_audit">混合审计</option>
            </select>
          </label>
          <label>
            <span>当前状态</span>
            <select v-model="form.status" class="text-input">
              <option value="reserved">已预留</option>
              <option value="ready">可开审</option>
              <option value="auditing">审计中</option>
              <option value="audited">已审计</option>
            </select>
          </label>
          <label class="form-switch"><input v-model="form.client_required" type="checkbox" /><span>需要客户端</span></label>
          <label class="form-switch"><input v-model="form.certificate_required" type="checkbox" /><span>需要证书</span></label>
          <label class="form-switch"><input v-model="form.plugin_required" type="checkbox" /><span>需要插件/控件</span></label>
          <label class="full-width">
            <span>下一步动作</span>
            <input v-model="form.next_action" class="text-input" placeholder="例如：拿到账号后先抓菜单树、设备、点位和日志" />
          </label>
          <label class="full-width">
            <span>备注</span>
            <textarea
              v-model="form.notes"
              class="text-area"
              rows="5"
              placeholder="记录账号获取方式、不能触碰的边界、浏览器/客户端要求、控件要求等。"
            />
          </label>
        </div>

        <div class="action-row">
          <button class="action-btn" @click="submitForm">{{ editingId ? "保存修改" : "登记轨道" }}</button>
          <button v-if="editingId" class="action-btn subtle" @click="resetForm">取消编辑</button>
        </div>
        <p class="action-note">{{ actionMessage }}</p>
      </article>

      <article class="panel">
        <h3>双平台轨道</h3>
        <div class="stack-list">
          <div v-for="item in summary.platform_tracks || []" :key="item.key" class="stack-item">
            <strong>{{ item.label }}</strong>
            <span>{{ accessModeLabel(item.mode) }} / {{ registrationStatusLabel(item.status) }}</span>
          </div>
        </div>

        <h3 style="margin-top: 1.5rem">VLAN 摘要</h3>
        <div class="stack-list">
          <div v-for="item in summary.vlan_breakdown || []" :key="`${item.vlan_id}-${item.vlan_name}`" class="stack-item">
            <strong>VLAN {{ item.vlan_id }}</strong>
            <span>{{ item.vlan_name || "-" }} / 轨道 {{ item.count || 0 }}</span>
          </div>
        </div>

        <h3 style="margin-top: 1.5rem">预留承接能力</h3>
        <div class="source-card-grid">
          <div v-for="item in summary.expected_capabilities || []" :key="item.name" class="source-card">
            <div class="source-card-head">
              <strong>{{ item.name }}</strong>
              <span class="pill subtle">预留</span>
            </div>
            <p class="source-card-meta">{{ item.value }}</p>
          </div>
        </div>
      </article>
    </section>

    <article class="panel">
      <div class="panel-head">
        <div>
          <h3>审计资料导入</h3>
          <p class="panel-subtitle">先检查目录，再预览、对比、生成导入清单，最后正式导入。</p>
        </div>
      </div>

      <div class="form-grid">
        <label>
          <span>审计轨道</span>
          <select v-model="auditTrackKey" class="text-input" @change="handleTrackChange">
            <option value="electrical_control_platform">电控系统</option>
            <option value="new_control_platform">风控新平台</option>
            <option value="legacy_control_platform">风控老平台</option>
          </select>
        </label>
        <label>
          <span>资料目录</span>
          <input v-model="auditBundleDir" class="text-input" :placeholder="auditTemplate.expected_root || defaultAuditDir(auditTrackKey)" />
        </label>
        <label>
          <span>对比目录</span>
          <input v-model="compareBundleDir" class="text-input" placeholder="可选，用于和另一套资料包对比" />
        </label>
      </div>

      <div class="action-row wrap">
        <button class="action-btn subtle" @click="checkBundle">检查目录</button>
        <button class="action-btn subtle" @click="previewBundle">资料预览</button>
        <button class="action-btn subtle" @click="compareBundles">对比资料包</button>
        <button class="action-btn subtle" :disabled="!selectedRegistrationId" @click="buildImportPlan">生成导入清单</button>
        <button class="action-btn" :disabled="!selectedRegistrationId" @click="runImport">正式导入</button>
        <button class="action-btn subtle" :disabled="!selectedRegistrationId" @click="exportSelectedRegistration">导出轨道</button>
        <button class="action-btn subtle danger" :disabled="!selectedRegistrationId" @click="clearSelectedAuditData">清空审计数据</button>
      </div>
      <p class="action-note">{{ auditMessage }}</p>

      <div class="stack-list top-gap" v-if="auditTemplate.expected_files?.length">
        <div v-for="item in auditTemplate.expected_files" :key="item.name" class="stack-item">
          <strong>{{ item.name }}</strong>
          <span>{{ item.description }}</span>
        </div>
      </div>

      <div v-if="auditInspection.files?.length" class="table-shell top-gap">
        <table class="mini-table">
          <thead>
            <tr>
              <th>文件</th>
              <th>说明</th>
              <th>状态</th>
              <th>路径</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in auditInspection.files" :key="item.name">
              <td>{{ item.name }}</td>
              <td>{{ item.description }}</td>
              <td>{{ item.exists ? "已找到" : "缺失" }}</td>
              <td>{{ item.path }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="cards compact-cards top-gap">
        <article class="card"><span>预览设备</span><strong>{{ auditPreview.counts?.devices || 0 }}</strong></article>
        <article class="card"><span>预览点位</span><strong>{{ auditPreview.counts?.points || 0 }}</strong></article>
        <article class="card"><span>预览场景</span><strong>{{ auditPreview.counts?.scenarios || 0 }}</strong></article>
        <article class="card"><span>预览事件</span><strong>{{ auditPreview.counts?.events || 0 }}</strong></article>
        <article class="card"><span>预览菜单</span><strong>{{ auditPreview.counts?.menus || 0 }}</strong></article>
      </div>

      <div class="panel-grid top-gap">
        <article class="panel nested-panel">
          <h3>资料元信息</h3>
          <div class="stack-list">
            <div class="stack-item"><strong>平台类型</strong><span>{{ auditPreview.metadata?.platform_family || "-" }}</span></div>
            <div class="stack-item"><strong>厂商</strong><span>{{ auditPreview.metadata?.vendor || "-" }}</span></div>
            <div class="stack-item"><strong>入口地址</strong><span>{{ auditPreview.metadata?.base_url || "-" }}</span></div>
            <div class="stack-item"><strong>版本</strong><span>{{ auditPreview.metadata?.version || "-" }}</span></div>
          </div>
        </article>

        <article class="panel nested-panel">
          <h3>导入就绪状态</h3>
          <div class="stack-list">
            <div class="stack-item"><strong>总体判断</strong><span>{{ auditPreview.readiness?.label || "-" }}</span></div>
            <div class="stack-item"><strong>已就绪对象</strong><span>{{ joinText(auditPreview.readiness?.ready_items) }}</span></div>
            <div class="stack-item"><strong>需补字段</strong><span>{{ joinText(auditPreview.readiness?.attention_items) }}</span></div>
            <div class="stack-item"><strong>阻塞对象</strong><span>{{ joinText(auditPreview.readiness?.blocked_items) }}</span></div>
            <div class="stack-item"><strong>待填充对象</strong><span>{{ joinText(auditPreview.readiness?.empty_items) }}</span></div>
          </div>
        </article>

        <article class="panel nested-panel">
          <h3>风险与建议</h3>
          <ul class="plain-list compact-list">
            <li v-for="(item, index) in auditPreview.warnings || []" :key="index">{{ item }}</li>
          </ul>
        </article>
      </div>

      <div class="panel-grid top-gap">
        <article class="panel nested-panel">
          <h3>字段映射判断</h3>
          <div class="stack-list">
            <div v-for="(value, key) in auditPreview.compatibility || {}" :key="key" class="stack-item">
              <strong>{{ fieldLabels[key] || key }}</strong>
              <span>{{ value.label }}；缺失：{{ joinText(value.missing_required_groups) }}</span>
            </div>
          </div>
        </article>

        <article class="panel nested-panel">
          <h3>字段结构预览</h3>
          <div class="stack-list">
            <div v-for="(value, key) in auditPreview.headers || {}" :key="key" class="stack-item">
              <strong>{{ fieldLabels[key] || key }}</strong>
              <span>{{ joinText(value) }}</span>
            </div>
          </div>
        </article>
      </div>

      <div class="panel-grid top-gap">
        <article class="panel nested-panel">
          <h3>设备样本</h3>
          <div class="stack-list">
            <div v-for="(item, index) in auditPreview.samples?.devices || []" :key="`device-${index}`" class="stack-item">
              <strong>{{ sampleMain(item) }}</strong>
              <span>{{ sampleMeta(item) }}</span>
            </div>
          </div>
        </article>

        <article class="panel nested-panel">
          <h3>点位样本</h3>
          <div class="stack-list">
            <div v-for="(item, index) in auditPreview.samples?.points || []" :key="`point-${index}`" class="stack-item">
              <strong>{{ sampleMain(item) }}</strong>
              <span>{{ sampleMeta(item) }}</span>
            </div>
          </div>
        </article>

        <article class="panel nested-panel">
          <h3>场景样本</h3>
          <div class="stack-list">
            <div v-for="(item, index) in auditPreview.samples?.scenarios || []" :key="`scenario-${index}`" class="stack-item">
              <strong>{{ sampleMain(item) }}</strong>
              <span>{{ sampleMeta(item) }}</span>
            </div>
          </div>
        </article>
      </div>

      <div class="panel-grid top-gap">
        <article class="panel nested-panel">
          <h3>事件样本</h3>
          <div class="stack-list">
            <div v-for="(item, index) in auditPreview.samples?.events || []" :key="`event-${index}`" class="stack-item">
              <strong>{{ sampleMain(item) }}</strong>
              <span>{{ sampleMeta(item) }}</span>
            </div>
          </div>
        </article>

        <article class="panel nested-panel">
          <h3>菜单样本</h3>
          <div class="stack-list">
            <div v-for="(item, index) in auditPreview.samples?.menus || []" :key="`menu-${index}`" class="stack-item">
              <strong>{{ sampleMain(item) }}</strong>
              <span>{{ sampleMeta(item) }}</span>
            </div>
          </div>
        </article>
      </div>

      <div class="panel-grid top-gap" v-if="auditCompare.left || auditCompare.right">
        <article class="panel nested-panel">
          <h3>资料包对比</h3>
          <div class="stack-list">
            <div class="stack-item"><strong>当前建议</strong><span>{{ auditCompare.decision?.label || "-" }}</span></div>
            <div class="stack-item"><strong>左侧评分</strong><span>{{ auditCompare.decision?.left_score ?? "-" }}</span></div>
            <div class="stack-item"><strong>右侧评分</strong><span>{{ auditCompare.decision?.right_score ?? "-" }}</span></div>
          </div>
          <ul class="plain-list compact-list top-gap">
            <li v-for="(item, index) in auditCompare.recommendations || []" :key="index">{{ item }}</li>
          </ul>
        </article>

        <article class="panel nested-panel">
          <h3>数量差异</h3>
          <div class="stack-list">
            <div v-for="(value, key) in auditCompare.count_diff || {}" :key="key" class="stack-item">
              <strong>{{ fieldLabels[key] || key }}</strong>
              <span>左 {{ value.left ?? 0 }} / 右 {{ value.right ?? 0 }} / 差值 {{ value.delta ?? 0 }}</span>
            </div>
          </div>
        </article>
      </div>

      <div v-if="importPlan.checklist?.length" class="panel nested-panel top-gap">
        <h3>导入清单</h3>
        <div class="stack-list">
          <div v-for="(item, index) in importPlan.checklist" :key="index" class="stack-item">
            <strong>{{ item.step }}</strong>
            <span>{{ item.status }} / {{ item.detail }}</span>
          </div>
        </div>
      </div>
    </article>

    <section class="panel-grid">
      <article class="panel">
        <h3>轨道活动</h3>
        <div class="stack-list">
          <div class="stack-item"><strong>最近作业数</strong><span>{{ activity.activity?.job_count || 0 }}</span></div>
          <div class="stack-item"><strong>最近快照数</strong><span>{{ activity.activity?.snapshot_count || 0 }}</span></div>
          <div class="stack-item"><strong>最新作业</strong><span>{{ activity.activity?.latest_job?.summary || "-" }}</span></div>
          <div class="stack-item"><strong>最新快照</strong><span>{{ activity.activity?.latest_snapshot?.snapshot_type || "-" }}</span></div>
        </div>
      </article>

      <article class="panel">
        <h3>轨道级对象摘要</h3>
        <div class="stack-list">
          <div class="stack-item"><strong>控制设备</strong><span>{{ registrationSummary.device_count || 0 }}</span></div>
          <div class="stack-item"><strong>控制点位</strong><span>{{ registrationSummary.point_count || 0 }}</span></div>
          <div class="stack-item"><strong>控制场景</strong><span>{{ registrationSummary.scenario_count || 0 }}</span></div>
          <div class="stack-item"><strong>控制事件</strong><span>{{ registrationSummary.event_count || 0 }}</span></div>
          <div class="stack-item"><strong>菜单入口</strong><span>{{ registrationSummary.menu_count || 0 }}</span></div>
        </div>
      </article>

      <article class="panel">
        <h3>菜单树样本</h3>
        <div class="stack-list">
          <div v-for="item in menuTree.nodes || []" :key="item.menu_key || item.id" class="stack-item">
            <strong>{{ item.display_name || item.menu_key || "-" }}</strong>
            <span>{{ item.route_path || item.page_type || "-" }}</span>
          </div>
        </div>
      </article>
    </section>

    <article class="panel">
      <div class="panel-head">
        <div>
          <h3>轨道实体对比</h3>
          <p class="panel-subtitle">对比风控新老平台或电控轨道的对象规模、区域分布和类型结构，方便判断未来主模型和资料优先级。</p>
        </div>
      </div>

      <div class="form-grid">
        <label>
          <span>左侧轨道</span>
          <select v-model="compareLeftRegistrationId" class="text-input">
            <option :value="null">请选择</option>
            <option v-for="item in registrations" :key="`left-${item.id}`" :value="item.id">
              {{ item.display_name }} / {{ trackLabel(item.track_key) }}
            </option>
          </select>
        </label>
        <label>
          <span>右侧轨道</span>
          <select v-model="compareRightRegistrationId" class="text-input">
            <option :value="null">请选择</option>
            <option v-for="item in registrations" :key="`right-${item.id}`" :value="item.id">
              {{ item.display_name }} / {{ trackLabel(item.track_key) }}
            </option>
          </select>
        </label>
      </div>

      <div class="action-row wrap">
        <button class="action-btn subtle" :disabled="!canCompareRegistrations" @click="runRegistrationCompare">执行轨道对比</button>
        <button class="action-btn subtle" :disabled="!registrationCompare.left" @click="exportRegistrationCompare">导出对比</button>
      </div>
      <p class="action-note">{{ compareMessage }}</p>

      <div v-if="registrationCompare.left && registrationCompare.right" class="panel-grid top-gap">
        <article class="panel nested-panel">
          <h3>基础对比</h3>
          <div class="stack-list">
            <div class="stack-item"><strong>左侧轨道</strong><span>{{ registrationCompare.left.display_name || "-" }}</span></div>
            <div class="stack-item"><strong>右侧轨道</strong><span>{{ registrationCompare.right.display_name || "-" }}</span></div>
            <div class="stack-item"><strong>左侧类型</strong><span>{{ trackLabel(registrationCompare.left.track_key) }}</span></div>
            <div class="stack-item"><strong>右侧类型</strong><span>{{ trackLabel(registrationCompare.right.track_key) }}</span></div>
          </div>
        </article>

        <article class="panel nested-panel">
          <h3>对象规模差异</h3>
          <div class="stack-list">
            <div v-for="(value, key) in registrationCompare.difference || {}" :key="key" class="stack-item">
              <strong>{{ compareMetricLabel(key) }}</strong>
              <span>左 {{ value.left ?? 0 }} / 右 {{ value.right ?? 0 }} / 差值 {{ value.delta ?? 0 }}</span>
            </div>
          </div>
        </article>
      </div>

      <div v-if="registrationCompare.left && registrationCompare.right" class="panel-grid top-gap">
        <article class="panel nested-panel">
          <h3>共同区域</h3>
          <div class="stack-list">
            <div v-for="item in registrationCompare.area_compare?.shared || []" :key="`area-shared-${item.name}`" class="stack-item">
              <strong>{{ item.name }}</strong>
              <span>左 {{ item.left }} / 右 {{ item.right }}</span>
            </div>
            <div v-if="!(registrationCompare.area_compare?.shared || []).length" class="stack-item">
              <strong>暂无</strong>
              <span>两侧还没有可对比的区域数据。</span>
            </div>
          </div>
        </article>

        <article class="panel nested-panel">
          <h3>左侧独有</h3>
          <div class="stack-list">
            <div v-for="item in registrationCompare.area_compare?.left_only || []" :key="`area-left-${item.name}`" class="stack-item">
              <strong>{{ item.name }}</strong>
              <span>{{ item.count }} 个对象</span>
            </div>
            <div v-if="!(registrationCompare.area_compare?.left_only || []).length" class="stack-item">
              <strong>暂无</strong>
              <span>左侧没有独有区域。</span>
            </div>
          </div>
        </article>

        <article class="panel nested-panel">
          <h3>右侧独有</h3>
          <div class="stack-list">
            <div v-for="item in registrationCompare.area_compare?.right_only || []" :key="`area-right-${item.name}`" class="stack-item">
              <strong>{{ item.name }}</strong>
              <span>{{ item.count }} 个对象</span>
            </div>
            <div v-if="!(registrationCompare.area_compare?.right_only || []).length" class="stack-item">
              <strong>暂无</strong>
              <span>右侧没有独有区域。</span>
            </div>
          </div>
        </article>
      </div>

      <div v-if="registrationCompare.left && registrationCompare.right" class="panel-grid top-gap">
        <article class="panel nested-panel">
          <h3>点位类型交集</h3>
          <div class="stack-list">
            <div v-for="item in registrationCompare.point_type_compare?.shared || []" :key="`point-shared-${item.name}`" class="stack-item">
              <strong>{{ item.name }}</strong>
              <span>左 {{ item.left }} / 右 {{ item.right }}</span>
            </div>
            <div v-if="!(registrationCompare.point_type_compare?.shared || []).length" class="stack-item">
              <strong>暂无</strong>
              <span>点位类型还没有形成交集。</span>
            </div>
          </div>
        </article>

        <article class="panel nested-panel">
          <h3>场景类型交集</h3>
          <div class="stack-list">
            <div v-for="item in registrationCompare.scenario_type_compare?.shared || []" :key="`scenario-shared-${item.name}`" class="stack-item">
              <strong>{{ item.name }}</strong>
              <span>左 {{ item.left }} / 右 {{ item.right }}</span>
            </div>
            <div v-if="!(registrationCompare.scenario_type_compare?.shared || []).length" class="stack-item">
              <strong>暂无</strong>
              <span>场景类型还没有形成交集。</span>
            </div>
          </div>
        </article>
      </div>
    </article>

    <article class="panel">
      <h3>已登记平台轨道</h3>
      <div class="table-shell">
        <table class="mini-table">
          <thead>
            <tr>
              <th>轨道</th>
              <th>实例编码</th>
              <th>显示名称</th>
              <th>类型</th>
              <th>VLAN</th>
              <th>入口路径</th>
              <th>入口地址</th>
              <th>状态</th>
              <th>最近审计</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in registrations" :key="item.id">
              <td>{{ trackLabel(item.track_key) }}</td>
              <td>{{ item.instance_code || "-" }}</td>
              <td>{{ item.display_name }}</td>
              <td>{{ item.platform_family || "-" }}</td>
              <td>{{ item.vlan_id || "-" }} / {{ item.network_zone || "-" }}</td>
              <td>{{ item.endpoint_path || "-" }}</td>
              <td>{{ item.base_url || "-" }}</td>
              <td>{{ registrationStatusLabel(item.status) }}</td>
              <td>{{ formatDate(item.last_audited_at) }}</td>
              <td>
                <div class="table-actions">
                  <button class="text-link" @click="selectRegistration(item)">查看</button>
                  <button class="text-link" @click="loadRegistration(item)">编辑</button>
                  <button class="text-link" @click="exportRegistration(item)">导出</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import {
  clearControlPlatformAuditData,
  compareControlAuditBundles,
  createControlPlatformRegistration,
  exportControlPlatformRegistration,
  fetchControlDomainCompare,
  fetchControlDomainMenuTree,
  fetchControlDomainRegistrationSummary,
  fetchControlDomainSummary,
  fetchControlPlatformAuditTemplate,
  fetchControlPlatformImportPlan,
  fetchControlPlatformRegistrationActivity,
  fetchControlPlatformRegistrations,
  fetchControlPlatformSummary,
  importControlAuditBundle,
  inspectControlAuditBundle,
  previewControlAuditBundle,
  updateControlPlatformRegistration,
} from "../api/client";

const fieldLabels = {
  devices: "设备",
  points: "点位",
  scenarios: "场景",
  events: "事件",
  menus: "菜单",
};

const defaultAuditDirs = {
  electrical_control_platform: "E:\\cctv-maintenance\\docs\\control-audit\\electrical_control_platform",
  new_control_platform: "E:\\cctv-maintenance\\docs\\control-audit\\new_control_platform",
  legacy_control_platform: "E:\\cctv-maintenance\\docs\\control-audit\\legacy_control_platform",
};

const summary = ref({});
const domainSummary = ref({});
const registrations = ref([]);
const editingId = ref(null);
const selectedRegistrationId = ref(null);
const actionMessage = ref("先把平台轨道登记进来，明天拿到资料后直接进入只读审计。");
const auditMessage = ref("先检查目录，再做预览、对比和导入。");
const compareMessage = ref("选择两条轨道后执行对比，先看对象规模，再看区域和类型差异。");

const form = reactive({
  track_key: "new_control_platform",
  instance_name: "",
  instance_code: "",
  endpoint_name: "",
  endpoint_path: "",
  vlan_id: "",
  vlan_name: "",
  network_zone: "",
  display_name: "",
  platform_family: "",
  vendor: "",
  base_url: "",
  management_ip: "",
  username_hint: "",
  access_mode: "web",
  client_required: false,
  certificate_required: false,
  plugin_required: false,
  read_only_strategy: "web_audit",
  status: "reserved",
  next_action: "",
  notes: "",
});

const auditTrackKey = ref("new_control_platform");
const auditBundleDir = ref(defaultAuditDirs.new_control_platform);
const compareBundleDir = ref(defaultAuditDirs.legacy_control_platform);
const auditTemplate = ref({ expected_root: "", expected_files: [] });
const auditInspection = ref({ bundle_dir: "", exists: false, files: [] });
const auditPreview = ref({
  counts: {},
  metadata: {},
  headers: {},
  samples: {},
  compatibility: {},
  readiness: {},
  warnings: [],
});
const auditCompare = ref({});
const importPlan = ref({});
const activity = ref({ activity: {} });
const registrationSummary = ref({});
const menuTree = ref({ nodes: [] });
const compareLeftRegistrationId = ref(null);
const compareRightRegistrationId = ref(null);
const registrationCompare = ref({});

onMounted(async () => {
  await reload();
});

watch(auditTrackKey, async () => {
  await handleTrackChange();
});

async function reload() {
  const [summaryData, domainData, registrationData] = await Promise.all([
    fetchControlPlatformSummary(),
    fetchControlDomainSummary(),
    fetchControlPlatformRegistrations(),
  ]);
  summary.value = summaryData;
  domainSummary.value = domainData;
  registrations.value = registrationData;

  if (!selectedRegistrationId.value && registrationData.length) {
    selectedRegistrationId.value = registrationData[0].id;
  }
  if (!compareLeftRegistrationId.value && registrationData.length) {
    compareLeftRegistrationId.value = registrationData[0].id;
  }
  if (
    (!compareRightRegistrationId.value || compareRightRegistrationId.value === compareLeftRegistrationId.value)
    && registrationData.length > 1
  ) {
    compareRightRegistrationId.value = registrationData.find((item) => item.id !== compareLeftRegistrationId.value)?.id || null;
  }

  await handleTrackChange();
  await loadRegistrationContext();
}

async function handleTrackChange() {
  auditBundleDir.value = defaultAuditDir(auditTrackKey.value);
  compareBundleDir.value =
    auditTrackKey.value === "new_control_platform"
      ? defaultAuditDir("legacy_control_platform")
      : auditTrackKey.value === "legacy_control_platform"
        ? defaultAuditDir("new_control_platform")
        : "";
  auditTemplate.value = await fetchControlPlatformAuditTemplate(auditTrackKey.value);
  const matched = registrations.value.find((item) => item.track_key === auditTrackKey.value);
  if (matched) {
    selectedRegistrationId.value = matched.id;
  }
  await loadRegistrationContext();
}

async function loadRegistrationContext() {
  if (!selectedRegistrationId.value) {
    activity.value = { activity: {} };
    registrationSummary.value = {};
    menuTree.value = { nodes: [] };
    return;
  }
  const [activityData, summaryData, menuData] = await Promise.all([
    fetchControlPlatformRegistrationActivity(selectedRegistrationId.value),
    fetchControlDomainRegistrationSummary(selectedRegistrationId.value),
    fetchControlDomainMenuTree(selectedRegistrationId.value),
  ]);
  activity.value = activityData;
  registrationSummary.value = summaryData;
  menuTree.value = {
    ...menuData,
    nodes: Array.isArray(menuData.roots) ? flattenMenuTree(menuData.roots).slice(0, 10) : [],
  };
}

function resetForm() {
  editingId.value = null;
  form.track_key = "new_control_platform";
  form.instance_name = "";
  form.instance_code = "";
  form.endpoint_name = "";
  form.endpoint_path = "";
  form.vlan_id = "";
  form.vlan_name = "";
  form.network_zone = "";
  form.display_name = "";
  form.platform_family = "";
  form.vendor = "";
  form.base_url = "";
  form.management_ip = "";
  form.username_hint = "";
  form.access_mode = "web";
  form.client_required = false;
  form.certificate_required = false;
  form.plugin_required = false;
  form.read_only_strategy = "web_audit";
  form.status = "reserved";
  form.next_action = "";
  form.notes = "";
}

function loadRegistration(item) {
  editingId.value = item.id;
  form.track_key = item.track_key;
  form.instance_name = item.instance_name || "";
  form.instance_code = item.instance_code || "";
  form.endpoint_name = item.endpoint_name || "";
  form.endpoint_path = item.endpoint_path || "";
  form.vlan_id = item.vlan_id || "";
  form.vlan_name = item.vlan_name || "";
  form.network_zone = item.network_zone || "";
  form.display_name = item.display_name || "";
  form.platform_family = item.platform_family || "";
  form.vendor = item.vendor || "";
  form.base_url = item.base_url || "";
  form.management_ip = item.management_ip || "";
  form.username_hint = item.username_hint || "";
  form.access_mode = item.access_mode || "web";
  form.client_required = !!item.client_required;
  form.certificate_required = !!item.certificate_required;
  form.plugin_required = !!item.plugin_required;
  form.read_only_strategy = item.read_only_strategy || "web_audit";
  form.status = item.status || "reserved";
  form.next_action = item.next_action || "";
  form.notes = item.notes || "";
  actionMessage.value = `正在编辑：${item.display_name}`;
}

async function submitForm() {
  try {
    const payload = { ...form };
    if (editingId.value) {
      await updateControlPlatformRegistration(editingId.value, payload);
      actionMessage.value = "平台轨道已更新。";
    } else {
      await createControlPlatformRegistration(payload);
      actionMessage.value = "平台轨道已登记。";
    }
    await reload();
    resetForm();
  } catch (error) {
    console.error(error);
    actionMessage.value = "保存失败，请检查轨道标识是否重复或查看后端日志。";
  }
}

async function selectRegistration(item) {
  selectedRegistrationId.value = item.id;
  auditTrackKey.value = item.track_key;
  await loadRegistrationContext();
}

async function checkBundle() {
  try {
    auditInspection.value = await inspectControlAuditBundle(auditBundleDir.value);
    auditMessage.value = "资料目录检查完成。";
  } catch (error) {
    console.error(error);
    auditMessage.value = "目录检查失败，请确认路径是否存在。";
  }
}

async function previewBundle() {
  try {
    auditPreview.value = await previewControlAuditBundle(auditBundleDir.value);
    auditMessage.value = "资料预览完成。";
  } catch (error) {
    console.error(error);
    auditMessage.value = "资料预览失败，请确认目录和文件格式。";
  }
}

async function compareBundles() {
  try {
    if (!compareBundleDir.value.trim()) {
      auditMessage.value = "请先填写对比目录。";
      return;
    }
    auditCompare.value = await compareControlAuditBundles(auditBundleDir.value, compareBundleDir.value);
    auditMessage.value = "资料包对比完成。";
  } catch (error) {
    console.error(error);
    auditMessage.value = "资料包对比失败，请检查目录。";
  }
}

async function buildImportPlan() {
  try {
    if (!selectedRegistrationId.value) {
      auditMessage.value = "请先选择要导入的轨道。";
      return;
    }
    importPlan.value = await fetchControlPlatformImportPlan(
      selectedRegistrationId.value,
      auditBundleDir.value,
      compareBundleDir.value || undefined,
    );
    auditMessage.value = "导入清单已生成。";
  } catch (error) {
    console.error(error);
    auditMessage.value = "生成导入清单失败，请检查目录或轨道配置。";
  }
}

async function runImport() {
  try {
    if (!selectedRegistrationId.value) {
      auditMessage.value = "请先选择要导入的轨道。";
      return;
    }
    const result = await importControlAuditBundle(selectedRegistrationId.value, auditBundleDir.value);
    auditMessage.value = `导入完成：设备 ${result.devices}，点位 ${result.points}，场景 ${result.scenarios}，事件 ${result.events}，菜单 ${result.menus}。`;
    await reload();
  } catch (error) {
    console.error(error);
    auditMessage.value = "正式导入失败，请先完成预览和兼容性检查。";
  }
}

async function exportSelectedRegistration() {
  const current = registrations.value.find((item) => item.id === selectedRegistrationId.value);
  if (!current) {
    auditMessage.value = "请先选择要导出的轨道。";
    return;
  }
  await exportRegistration(current);
}

async function exportRegistration(item) {
  try {
    const payload = await exportControlPlatformRegistration(item.id);
    downloadJson(
      `${item.track_key || "control-platform"}-${item.instance_code || item.id}-export.json`,
      payload,
    );
    auditMessage.value = `轨道资料已导出：${item.display_name}`;
  } catch (error) {
    console.error(error);
    auditMessage.value = "导出轨道资料失败，请查看后端日志。";
  }
}

async function clearSelectedAuditData() {
  const current = registrations.value.find((item) => item.id === selectedRegistrationId.value);
  if (!current) {
    auditMessage.value = "请先选择要清空的轨道。";
    return;
  }
  const confirmed = window.confirm(
    `确定清空“${current.display_name}”的审计导入数据吗？这会删除该轨道下的控制设备、点位、场景、事件、菜单以及同步记录，但不会删除轨道配置本身。`,
  );
  if (!confirmed) {
    return;
  }
  try {
    const result = await clearControlPlatformAuditData(current.id);
    auditMessage.value =
      `已清空 ${current.display_name}：设备 ${result.deleted.devices}，点位 ${result.deleted.points}，场景 ${result.deleted.scenarios}，事件 ${result.deleted.events}，菜单 ${result.deleted.menus}。`;
    await reload();
  } catch (error) {
    console.error(error);
    auditMessage.value = "清空审计数据失败，请查看后端日志。";
  }
}

async function runRegistrationCompare() {
  if (!canCompareRegistrations.value) {
    compareMessage.value = "请先选择两条不同的轨道。";
    return;
  }
  try {
    registrationCompare.value = await fetchControlDomainCompare(
      compareLeftRegistrationId.value,
      compareRightRegistrationId.value,
    );
    compareMessage.value = "轨道对比已生成。";
  } catch (error) {
    console.error(error);
    compareMessage.value = "轨道对比失败，请查看后端日志。";
  }
}

function exportRegistrationCompare() {
  if (!registrationCompare.value?.left || !registrationCompare.value?.right) {
    compareMessage.value = "请先生成轨道对比。";
    return;
  }
  const leftKey = registrationCompare.value.left?.track_key || "left";
  const rightKey = registrationCompare.value.right?.track_key || "right";
  downloadJson(`control-domain-compare-${leftKey}-vs-${rightKey}.json`, registrationCompare.value);
  compareMessage.value = "轨道对比已导出。";
}

function flattenMenuTree(nodes, level = 0, acc = []) {
  (nodes || []).forEach((node) => {
    acc.push({
      ...node,
      display_name: `${"· ".repeat(level)}${node.display_name || node.menu_key || "-"}`,
    });
    if (Array.isArray(node.children) && node.children.length) {
      flattenMenuTree(node.children, level + 1, acc);
    }
  });
  return acc;
}

function joinText(items) {
  return Array.isArray(items) && items.length ? items.join(" / ") : "-";
}

function sampleMain(item) {
  if (!item || typeof item !== "object") return "-";
  return item.display_name || item.title || item.name || item.point_code || item.event_code || item.menu_key || "-";
}

function sampleMeta(item) {
  if (!item || typeof item !== "object") return "-";
  const ignored = new Set(["display_name", "title", "name"]);
  const values = Object.entries(item)
    .filter(([key, value]) => value !== null && value !== "" && value !== undefined && !ignored.has(key))
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${value}`);
  return values.length ? values.join(" / ") : "-";
}

function formatDate(value) {
  if (!value) return "-";
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? value : dt.toLocaleString("zh-CN", { hour12: false });
}

function trackLabel(trackKey) {
  return (
    {
      electrical_control_platform: "电控系统",
      new_control_platform: "风控新平台",
      legacy_control_platform: "风控老平台",
    }[trackKey] || trackKey
  );
}

function platformStageLabel(value) {
  return (
    {
      reserved_for_tomorrow_intake: "待现场接入审计",
      planned_foundation: "基础能力规划中",
      foundation_ready: "基础能力已就绪",
    }[value] || value || "-"
  );
}

function platformStrategyLabel(value) {
  return (
    {
      triple_track_read_only_first_then_replaceable: "三轨并行，只读接入后逐步替代",
      provider_abstraction: "统一抽象，按能力解耦",
    rest_plus_mcp: "REST + 模型能力双接口",
    }[value] || value || "-"
  );
}

function registrationStatusLabel(value) {
  return (
    {
      reserved: "已预留",
      ready: "可开审",
      auditing: "审计中",
      audited: "已审计",
    }[value] || value || "-"
  );
}

function accessModeLabel(value) {
  return (
    {
      web: "网页",
      client: "客户端",
      web_plus_client: "网页 + 客户端",
      unknown: "待确认",
      web_audit: "网页只读审计",
      api_audit: "接口只读审计",
      client_capture: "客户端抓取",
      hybrid_audit: "混合审计",
    }[value] || value || "-"
  );
}

function compareMetricLabel(metricKey) {
  return (
    {
      device_count: "控制设备",
      point_count: "控制点位",
      scenario_count: "控制场景",
      event_count: "控制事件",
      menu_count: "菜单入口",
    }[metricKey] || metricKey
  );
}

function defaultAuditDir(trackKey) {
  return defaultAuditDirs[trackKey] || "";
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

const canCompareRegistrations = computed(
  () =>
    Number.isInteger(compareLeftRegistrationId.value)
    && Number.isInteger(compareRightRegistrationId.value)
    && compareLeftRegistrationId.value !== compareRightRegistrationId.value,
);
</script>

<style scoped>
.nested-panel {
  min-height: 100%;
}

.top-gap {
  margin-top: 1rem;
}

.wrap {
  flex-wrap: wrap;
}

.danger {
  color: #b42318;
  border-color: rgba(180, 35, 24, 0.22);
  background: rgba(255, 240, 240, 0.92);
}
</style>
