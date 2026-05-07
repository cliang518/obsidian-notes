# V2 当前接力状态

## 当前主线
- 工程根目录：`E:\cctv-maintenance`
- 新平台主线：`E:\cctv-maintenance\platform_v2`
- 旧系统只保留参考，不再作为继续堆功能的主线

## 当前运行入口
- V2 后端：`http://127.0.0.1:8011`
- V2 前端：`http://127.0.0.1:3011`
- 运行中心：`http://127.0.0.1:8011/api/system/runtime`
- 健康检查：`http://127.0.0.1:8011/api/system/health`

## 当前真实数据库
- 运行数据库：`E:\cctv-maintenance\platform_v2\runtime\platform_v2.db`

注意：
- 不要误用项目根目录下的旧空数据库文件
- 所有运行态数据以 `runtime` 目录为准

## 当前已完成

### 平台底座
- V2 独立目录和独立数据库已稳定运行
- 统一资产模型第一版已落地
- TG/COS、JVSS、海康 NVR、旧系统告警桥接已接入
- 控制平台、Agent/MCP、移动工作台、存储资源、模型接入、学习中心、授权中心均已挂上主线

### 登录与权限
- 登录、退出、当前用户恢复、Bearer 会话、路由保护已上线
- 自主注册已上线
- 管理员 / 主管审批开通、停用账号、重置临时口令已上线
- 人员管理中心已上线，支持角色分层、联系方式、部门、备注、角色矩阵

### 运维闭环
- 告警中心、资产中心、接入中心、拓扑中心、视频中心已上线
- 工单中心已上线
- 巡检中心已上线
- 已打通“告警 -> 工单 -> 巡检”的基础闭环
- 工单支持“转巡检”并生成复核任务
- 移动工作台已升级为值班入口，支持移动工作流台账和现场调度看板
- 移动工作台已补入调度类型分布、状态分布和调度状态流转
- 通知中心已上线，支持 Webhook、企业微信、飞书通道台账
- 通知中心已补上发送记录，`/api/notifications/deliveries` 可查看最近联调结果

### 移动调度
- 新增 `mobile_dispatch_item` 模型
- 已打通以下派发链路：
  - 告警 -> 移动调度
  - 工单 -> 移动调度
  - 巡检 -> 移动调度
- 告警中心、工单中心、巡检中心三页都已补上“一键转移动”
- 调度项支持完整状态流转：
  - `queued`
  - `acknowledged`
  - `in_progress`
  - `completed`
- 工单来源联动已生效：
  - 移动调度进入 `acknowledged / in_progress` 时，可把来源工单推进到 `in_progress`
- 巡检来源联动已生效：
  - 移动调度标记 `completed` 时，可把来源巡检推进到 `completed`

### 控制平台主线
- 已知入口：
  - 电控系统：`http://10.0.71.250/Web/`
  - 风控新平台：`http://10.0.69.100/Web/`
  - 风控老平台：`http://10.0.69.200/SmartEnergy/roomlist2.jsp`
- 这些地址当前尚未接入开发主机网络，只能先做承接和审计模板
- 双轨控制平台接入能力已上线：
  - 新平台
  - 老平台
- 控制域模型已上线：
  - `control_device`
  - `control_point`
  - `control_scenario`
  - `control_event`
  - `control_menu`
- 控制平台当前已支持：
  - 审计模板
  - 目录检查
  - 资料预览
  - 兼容性判断
  - 风险与建议
  - 资料包对比
  - 导入清单
  - 正式导入
  - 轨道活动
  - 轨道级对象摘要
  - 菜单树样本

### 第三方事实源
- `10.0.68.250`：上层弱电网络与控制事实源
- `10.0.59.200`：主视频平台事实源
- `10.0.59.205`：**B2 停车场视频平台**

当前原则：
- 第三方平台只负责“吐资料”
- V2 不以它们作为长期运行依赖
- V2 目标是逐步吸收其台账、拓扑、归属和控制信息后完成替代

### 授权
- 年授权规则已进系统：
  - 365 天授权
  - 3 天宽限
  - 换机重认
- V2 注册机：
  - `E:\cctv-maintenance\platform_v2\dist\YongjiaWeakCurrentV2LicenseGenerator.exe`
- V2 托盘：
  - `E:\cctv-maintenance\platform_v2\dist\YongjiaWeakCurrentV2Tray.exe`

### CAD / 图纸
- CAD 读取和洗图工具已建立
- 当前图纸读取能力保留，但本阶段暂停继续深挖
- 后续有更明确的监控点位标注规则时再回收这条线

## 当前环境说明
- 当前稳定后端运行链路优先使用：
  - `E:\cctv-maintenance\platform_v2\backend\venv\Scripts\python.exe`
- V2 托盘构建链路已切到这套专用运行时
- 后端启动脚本和托盘启动参数都已显式指定 `--app-dir`，避免 Windows 下同名 `app` 包串到旧路径
- 托盘已改成隐藏启动后端与静态前端，不再拉可见开发终端
- 前端静态服务已切到自定义 SPA 路由回退服务，根地址和 `/login` 均可直接访问

## 当前关于 VLAN 的结论
- 已确认：`VLAN 2` 是监控网主标识
- 已看到交换机中存在：`VLAN 3 / 4 / 5 / 6 / 7`
- 已补充事实：风控新/老项目具备“同实例多入口目录”形态，电控为独立实例
- 已在控制平台模型中落地字段：
  - `instance_name / instance_code`
  - `endpoint_name / endpoint_path`
  - `vlan_id / vlan_name / network_zone`
- 已在拓扑中心落地 VLAN 可视化摘要（含已知事实与登记态回填）
- 已新增 VLAN 归因诊断接口：`/api/topology/vlan-attribution`
- 已新增未归因导出与回写接口：
  - `GET /api/topology/vlan-attribution/unattributed`
  - `GET /api/topology/vlan-attribution/unattributed.csv`
  - `POST /api/topology/vlan-attribution/manual-apply`
- 已新增 TG VLAN 回填入口：`/api/setup/import-source/tg-cos-vlan`
- 当前一次回填结果（2026-04-11）：
  - `tg-cos-vlan` 更新端口 `44`
  - 归因链路 `600`，其中已归因 `501`，未归因 `99`
- 截至当前：
  - 还不能把某个 VLAN 明确认定为 BA / 风控 / 电控
  - 只能确认 `10.0.68.250` 平台里已经存在空调控制器和灯控控制器
  - 说明 BA / 电控终端已被总平台感知，但 `终端 -> VLAN -> 控制平台` 关系还未打透

## 当前重要边界
- `10.0.68.250`、`10.0.59.200`、`10.0.59.205` 仍然只作为只读事实源
- 海康 NVR 与解码器当前仍按只读接入
- 风控 / 电控 / BA 平台后续继续按只读审计接入，避免触碰生产控制逻辑
- 新平台目标是逐步替代第三方平台，不是当前立刻切断

## 当前重点资料
- `E:\cctv-maintenance\docs\2026-04-09-platform-rebuild-proposal-v2.md`
- `E:\cctv-maintenance\docs\2026-04-09-platform-architecture-blueprint-v1.md`
- `E:\cctv-maintenance\docs\2026-04-09-third-party-platform-exit-roadmap-v1.md`
- `E:\cctv-maintenance\docs\switch-audit`
- `E:\cctv-maintenance\platform_v2\docs\phase-1-execution-plan.md`
- `E:\cctv-maintenance\platform_v2\docs\dev-runbook.md`
- `E:\cctv-maintenance\platform_v2\docs\2026-04-09-platform-architecture-v2-expanded.md`
- `E:\cctv-maintenance\platform_v2\docs\tomorrow-control-platform-intake.md`
- `E:\cctv-maintenance\platform_v2\docs\2026-04-11-control-vlan-and-host-facts.md`

## 当前待继续
- 继续压平剩余边角页面和交互细节
- 把告警归因做成真正的原生闭环
- 把区域、交换机、端口、摄像头归属关系继续做深
- 在风控 / 电控平台接入后，把控制域彻底立起来
- 后续稳定阶段再规划从 SQLite 迁移到 PostgreSQL
- 功能稳定后再做一轮真正的 UI 重设计，提升平台感和科技感

## 特别提醒
- `开发进度中心` 仅作为开发期临时模块，正式交付前必须删除或彻底隐藏
