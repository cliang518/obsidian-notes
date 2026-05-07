from __future__ import annotations

from pathlib import Path

from app.core.settings import settings


def agent_gateway_summary() -> dict:
    return {
        "stage": "planned_foundation",
        "strategy": "rest_plus_mcp",
        "design_notes": [
            "主平台同时提供 REST API 和 MCP 适配层。",
            "OpenClaw、OpenCode 风格智能体优先走只读查询，再逐步开放工单和诊断建议写入。",
            "所有 Agent 动作都应具备审计日志和权限约束。",
        ],
        "planned_tools": [
            {"tool_name": "asset.search", "scope": "资产、区域、设备关系查询"},
            {"tool_name": "topology.query", "scope": "拓扑、链路、归属和热点查询"},
            {"tool_name": "alert.search", "scope": "告警检索、归因、状态汇总"},
            {"tool_name": "workorder.manage", "scope": "后续工单读写和状态更新"},
            {"tool_name": "resource.search", "scope": "资料、图片、文档、视频缓存检索"},
            {"tool_name": "video.snapshot", "scope": "抓图地址和预览入口获取"},
        ],
        "mcp_targets": [
            {"name": "OpenClaw", "status": "planned"},
            {"name": "OpenCode MCP", "status": "planned"},
            {"name": "Local MCP Hub", "status": "planned"},
        ],
    }


def mobile_workspace_summary() -> dict:
    return {
        "stage": "planned_foundation",
        "strategy": "responsive_plus_dedicated_mobile_views",
        "design_notes": [
            "PC 端保留全量平台工作台，移动端单独做轻量高频流程。",
            "移动端重点承载巡检、告警、工单、拍照上传、现场备注和扫码定位。",
            "未来支持企业微信、飞书、微信消息跳转移动工作台。",
        ],
        "planned_views": [
            {"name": "移动首页", "focus": "我的告警、我的工单、今日巡检"},
            {"name": "移动告警", "focus": "确认、转派、备注、拍照"},
            {"name": "移动工单", "focus": "处理进度、维修结果、现场照片"},
            {"name": "移动设备", "focus": "按区域和二维码定位设备"},
        ],
    }


def control_platform_summary() -> dict:
    return {
        "stage": "reserved_for_tomorrow_intake",
        "strategy": "triple_track_read_only_first_then_replaceable",
        "design_notes": [
            "电控系统、风控新系统、风控老系统按三条轨道并行审计接入。",
            "风控新/老系统支持同一实例下多入口路径（同主机不同目录）的建模方式。",
            "电控系统作为独立实例建模，并与风控实例分开治理。",
            "控制域网络与监控网络分 VLAN 运行，监控域已知为 VLAN2，风控/电控 VLAN 待交换机审计确认。",
            "先把第三方平台里的对象、点位、菜单、日志和场景吸进 V2，再逐步摆脱第三方运行依赖。",
            "风控新老系统需要先做事实比对，再决定哪一套字段作为未来主模型。",
            "由于控制平台更偏开关与控制逻辑，后续替代节奏可快于视频平台。",
            "新平台建立后，应能独立承接控制对象、场景、状态、日志与告警。",
        ],
        "platform_tracks": [
            {"key": "electrical_control_platform", "label": "电控系统", "mode": "只读预留", "status": "reserved"},
            {"key": "new_control_platform", "label": "风控新系统", "mode": "只读预留", "status": "reserved"},
            {"key": "legacy_control_platform", "label": "风控老系统", "mode": "只读预留", "status": "reserved"},
        ],
        "expected_capabilities": [
            {"name": "device_inventory", "value": "控制器、回路、场景、分组"},
            {"name": "control_points", "value": "开关点位、状态点、联动点"},
            {"name": "event_logs", "value": "操作日志、告警日志、历史记录"},
            {"name": "control_actions", "value": "后续可控替代接口"},
        ],
        "tomorrow_intake": [
            {"field": "electrical_base_url", "description": "电控系统地址"},
            {"field": "electrical_username", "description": "电控系统登录账号"},
            {"field": "electrical_password", "description": "电控系统登录密码"},
            {"field": "new_base_url", "description": "风控新平台地址"},
            {"field": "new_username", "description": "风控新平台登录账号"},
            {"field": "new_password", "description": "风控新平台登录密码"},
            {"field": "legacy_base_url", "description": "风控老平台地址"},
            {"field": "legacy_username", "description": "风控老平台登录账号"},
            {"field": "legacy_password", "description": "风控老平台登录密码"},
            {"field": "instance_host_relation", "description": "风控新老项目是否同主机多目录映射"},
            {"field": "control_vlan_ids", "description": "风控/电控所在 VLAN 编号与名称"},
            {"field": "switch_port_vlan_map", "description": "交换机端口与 VLAN 对应关系"},
            {"field": "menu_tree", "description": "菜单结构和功能入口"},
            {"field": "device_types", "description": "控制器、执行器、传感器类型"},
        ],
    }


def storage_resource_summary() -> dict:
    runtime_root = Path(settings.runtime_dir)
    return {
        "stage": "planned_foundation",
        "current_runtime_storage": {
            "runtime_dir": str(runtime_root),
            "database_path": str(settings.database_path),
        },
        "strategy": "provider_abstraction",
        "provider_targets": [
            {"name": "local_filesystem", "role": "开发期、本机临时缓存"},
            {"name": "s3_compatible", "role": "对象存储、视频缓存、临时文件"},
            {"name": "webdav", "role": "与协作文件系统互通"},
            {"name": "hikvision_storage", "role": "录像回放和海康存储入口"},
        ],
        "recommended_stack": [
            {"name": "SeaweedFS", "role": "对象存储与缓存层"},
            {"name": "Nextcloud", "role": "统一文件入口和 WebDAV"},
            {"name": "Paperless-ngx", "role": "文档归档和检索"},
            {"name": "Immich", "role": "移动端照片和视频资料"},
        ],
    }


def llm_provider_summary() -> dict:
    return {
        "stage": "planned_foundation",
        "strategy": "provider_layer",
        "design_notes": [
            "统一封装模型提供商，不将平台写死到某一家。",
            "支持 API Key、Base URL、模型名、超时、重试和审计日志。",
            "后续按能力分流：摘要、归因、报表、问答、知识检索。",
        ],
        "provider_types": [
            {"name": "openai_compatible", "status": "planned"},
            {"name": "anthropic_style", "status": "planned"},
            {"name": "local_gateway", "status": "planned"},
        ],
        "planned_use_cases": [
            {"name": "告警摘要", "mode": "轻模型"},
            {"name": "周报月报", "mode": "中模型"},
            {"name": "根因分析建议", "mode": "强模型"},
            {"name": "资料检索问答", "mode": "RAG + 模型"},
        ],
    }


def learning_center_summary() -> dict:
    return {
        "stage": "planned_foundation",
        "strategy": "human_approved_learning",
        "design_notes": [
            "系统先学习事实和经验，不直接自动改规则。",
            "阈值学习和归因建议默认走人工确认。",
            "学习结果沉淀到诊断建议、区域画像和疑难设备档案。",
        ],
        "data_sources": [
            {"name": "告警历史", "value": "识别抖动、重复异常和高发区域"},
            {"name": "工单结果", "value": "学习故障闭环和处理时长"},
            {"name": "拓扑快照", "value": "学习链路变化和归属关系"},
            {"name": "第三方平台同步", "value": "吸收设备事实与状态"},
            {"name": "人工备注", "value": "沉淀现场经验和排障手册"},
        ],
        "planned_outputs": [
            {"name": "疑难设备评分", "status": "running"},
            {"name": "阈值建议", "status": "planned"},
            {"name": "根因建议", "status": "planned"},
            {"name": "区域风险画像", "status": "planned"},
        ],
    }
