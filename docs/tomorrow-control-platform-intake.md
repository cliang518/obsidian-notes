# 明日电控 / 风控三轨接入清单

## 目标

明天拿到控制平台地址和账号后，不临时硬接，而是按 V2 已定结构接入：
- 电控系统、风控新系统、风控老系统三轨并行只读深挖
- 统一纳入资产、控制点和区域模型
- 为后续替代原控制平台做准备

## 明日最需要的输入

### 电控系统
- 平台地址：`http://10.0.71.250/Web/`
- 登录账号：`xincheng`
- 登录密码：由现场持有，不在文档中明文落库
- 当前状态：由于前端交换机配置，尚未接入开发主机

### 风控新系统
- 平台地址
- 登录账号
- 登录密码
- 是否有客户端 / 网页双入口
- 是否要求证书、浏览器插件或控件

已知入口：
- `http://10.0.69.100/Web/`

### 风控老系统
- 平台地址
- 登录账号
- 登录密码
- 是否有客户端 / 网页双入口
- 是否要求证书、浏览器插件或控件

已知入口：
- `http://10.0.69.200/SmartEnergy/roomlist2.jsp`

## 审计资料建议落盘位置

每套平台单独建目录，建议放到：

- `E:\cctv-maintenance\docs\control-audit\electrical_control_platform`
- `E:\cctv-maintenance\docs\control-audit\risk_control_new_platform`
- `E:\cctv-maintenance\docs\control-audit\risk_control_legacy_platform`

推荐资料文件：
- `metadata.json`
- `devices.csv`
- `points.csv`
- `scenarios.csv`
- `menus.json`
- `events.csv`

说明：
- `metadata.json`：平台版本、厂商、入口、登录说明、备注
- `devices.csv`：设备、控制器、执行器、分组、区域
- `points.csv`：输入、输出、状态、测点、回路点位
- `scenarios.csv`：场景、联动、策略、时序或回路逻辑
- `menus.json`：菜单树、页面入口、功能块
- `events.csv`：事件、告警、操作日志、联动记录

## 进入平台后优先采集

### 1. 菜单树
- 首页
- 设备管理
- 场景管理
- 分组管理
- 告警中心
- 日志中心
- 联动策略
- 系统设置

### 2. 设备与控制对象
- 控制器
- 执行器
- 回路
- 继电器
- 传感器
- 场景
- 区域

### 3. 日志与状态
- 实时状态
- 历史状态
- 操作日志
- 告警日志
- 联动记录

### 4. 可替代性判断
重点观察：
- 是否只是开关控制
- 是否有复杂联动
- 是否有时间计划
- 是否有设备分组和区域逻辑
- 是否能导出或只读获取控制点位

## V2 接入目标

### 第一阶段
- 电控系统、风控新系统、风控老系统只读审计
- 菜单和接口采集
- 设备对象入库
- 区域和控制点位入库

### 第二阶段
- 告警桥接
- 控制对象拓扑关系
- 与视频、网络、区域做统一归因

### 第三阶段
- 视情况替代原控制平台
- 在 V2 中提供统一控制入口

## 当前已预埋的接口

- `GET /api/control-platform/audit-template`
- `GET /api/control-platform/audit-inspect`
- `POST /api/control-platform/import-audit-bundle/{registration_id}`

导入器当前已支持从资料目录中读取：
- `metadata.json`
- `devices.csv`
- `points.csv`
- `scenarios.csv`

## 结论

这类平台通常更像“开关控制平台”，比 `250 / 200 / 205` 更容易被 V2 替代。当前优先级应是：

1. 先把三条轨道都登记并打通资料目录
2. 先只读深挖，不写配置
3. 先吸收对象、点位、菜单、事件和场景
4. 再推进 V2 原生控制域替代
