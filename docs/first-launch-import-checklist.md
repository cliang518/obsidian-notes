# 永嘉集团信息弱电视频运维系统 V2 首次上线导入清单

> 目标：让现场人员在“系统刚装好、数据还空”的情况下，按步骤完成首次导入并进入可用状态。

## 0. 先确认三件事

在开始导入前，先确认：

- 后端 `8011` 已启动
- 前端 `3011` 已启动
- 你已经能正常登录系统

如果这三项没通过，不要先导数据。

## 1. 准备导入文件

### 1.1 必备文件

先准备下面这些文件，建议按目录放好：

- `docs/switch-audit/10.0.68.250-audit/camera_switch_port_map_from_platform.csv`
- `docs/switch-audit/10.0.68.250-audit/camera_area_floor_zone_detail.csv`
- `docs/switch-audit/10.0.68.250-audit/telnet-show-bundle.txt`
- `docs/switch-audit/10.0.59.200-audit/extracted_channels.csv`
- `docs/switch-audit/10.0.59.205-audit/extracted_channels.csv`
- `docs/switch-audit/hikvision-audit-20260409/*`
- 旧告警库：`backend/cctv_maintenance.db`

### 1.2 可选文件

如果有这些，也建议一并准备：

- CAD 图纸导出的点位对照表
- 设备清单 Excel
- 维修工单导出表
- 风控/电控平台的只读审计结果

## 2. 建议导入顺序

### 第一步：导入控制平台占位信息

接口：

```http
POST /api/setup/import-source/control-platform-new
POST /api/setup/import-source/control-platform-legacy
```

目的：

- 先把风控/电控平台轨道挂上
- 后面再逐步补真实事实

检查点：

- 控制平台页能看到两条轨道
- 轨道状态正常显示

### 第二步：导入 TG/COS 核心事实

接口：

```http
POST /api/setup/import-source/tg-cos
POST /api/setup/import-source/tg-cos-area
POST /api/setup/import-source/tg-cos-vlan
```

目的：

- 建立摄像头-交换机-端口关系
- 建立楼层/区域关系
- 回填 VLAN 和 L2 MAC 结果

检查点：

- 设备管理里有交换机和摄像头
- 拓扑页能看到链路
- 端口 VLAN 有值
- 区域列表开始出现楼层信息

### 第三步：导入 JVSS 通道

接口：

```http
POST /api/setup/import-source/jvss-main
POST /api/setup/import-source/jvss-stream
```

目的：

- 把 10.0.59.200 和 10.0.59.205 的通道关系写进系统
- 让 RTSP、快照、通道名更完整

检查点：

- 视频中心能看到通道
- 通道名和摄像头 IP 对得上

### 第四步：导入海康设备

接口示例：

```http
POST /api/setup/import-source/hikvision-192.168.1.2
POST /api/setup/import-source/hikvision-192.168.1.3
POST /api/setup/import-source/hikvision-192.168.5.253
POST /api/setup/import-source/hikvision-192.168.5.254
POST /api/setup/import-source/hikvision-192.168.6.2
POST /api/setup/import-source/hikvision-192.168.6.3
```

目的：

- 把录像机、解码器和通道事实导入
- 让视频链路更完整

检查点：

- 视频中心出现海康通道
- 设备页能看到 NVR / 解码器

### 第五步：导入旧告警

接口：

```http
POST /api/setup/import-source/legacy-alerts
```

目的：

- 把旧系统的历史告警继承过来
- 让系统一启动就有历史上下文

检查点：

- 告警中心能看到历史告警
- 同一设备反复抖动的告警不会无限重复增长

## 3. 首次导入后的必查项

导入完成后，必须检查下面这些页面：

- 首页
- 设备管理
- 告警中心
- 视频中心
- 拓扑中心
- 控制平台
- 运行中心

如果其中任意一个页面显示异常，先停下来修数据，不要继续导入下一批。

## 4. 首次导入后的推荐顺序

### 4.1 先看设备数量

确认：

- 摄像头数量是否明显偏少
- 交换机数量是否合理
- NVR 数量是否合理

### 4.2 再看链路

确认：

- 摄像头有没有挂到正确交换机
- 端口 VLAN 是否合理
- 楼层区域是否对得上

### 4.3 再看告警

确认：

- 网络抖动设备有没有被归类
- 大面积异常有没有触发风暴防护
- 通知是否会被刷屏

### 4.4 再看视频

确认：

- RTSP 预览能不能打开
- 快照能不能抓
- 账号密码是否正确

## 5. 遇到重复导入怎么办

### 情况 A：设备重复

先检查 IP 是否相同。

- IP 相同，优先合并
- 名称不同但 IP 相同，通常是同一设备的不同来源

### 情况 B：告警重复

先看是否属于：

- 网络抖动观察
- 短时恢复又异常
- 同一设备同一标题重复进库

这类情况不建议直接手工删，优先用系统的清理/去重逻辑。

### 情况 C：平台轨道重复

如果风控/电控新旧平台都导了，先保留占位轨道，再逐步补真实资料，不要一次性把所有字段都覆盖掉。

## 6. 推荐的现场操作节奏

1. 先导控制平台占位
2. 再导 TG/COS
3. 再导 JVSS
4. 再导海康
5. 再导旧告警
6. 最后做视频预览和快照验证

## 7. 现场日志建议

导入时建议同步记录：

- 导入时间
- 使用了哪个接口
- 文件名
- 导入条数
- 失败条数
- 异常原因

这样后面一旦要回滚或复导，会非常省时间。

## 8. 最后确认

首次导入完成后，建议现场确认：

- 首页可用
- 告警可用
- 视频可用
- 托盘可用
- 备份可用
- 登录可用

只要这六项都通过，就可以认为系统已经具备上线测试基础。

