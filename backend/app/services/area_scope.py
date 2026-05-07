import re

from app.services.text_normalize import normalize_text


CHANNEL_TAIL_AREA_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}$")
CAMERA_DETAIL_SUFFIX_PATTERN = re.compile(r"^(?P<base>.+?)(?P<camera_no>\d+#)$")
PRECISE_AREA_PATTERN = re.compile(
    r"^(?:\d+F(?:[东南西北](?:楼|侧)?)?|B\d+\s*停车场|原市场)$",
    flags=re.IGNORECASE,
)


def split_area_channel_tail(display_name: str) -> tuple[str, str]:
    text = normalize_text(display_name or "").strip()
    if " / " not in text:
        return text, ""
    prefix, tail = text.rsplit(" / ", 1)
    tail = tail.strip()
    if CHANNEL_TAIL_AREA_PATTERN.fullmatch(tail):
        return prefix.strip(), tail
    return text, ""


def collapse_camera_detail_area(display_name: str) -> str:
    base_name, _ = split_area_channel_tail(display_name)
    matched = CAMERA_DETAIL_SUFFIX_PATTERN.match(base_name)
    if not matched:
        return base_name
    collapsed = matched.group("base").strip()
    if any(token in collapsed for token in ("F", "楼", "侧", "停车场", "市场")):
        return collapsed
    return base_name


def describe_area_scope(display_name: str) -> dict:
    original = normalize_text(display_name or "").strip()
    collapsed = collapse_camera_detail_area(original)
    channel_tail = ""
    if collapsed != original:
        _, channel_tail = split_area_channel_tail(original)
    else:
        collapsed, channel_tail = split_area_channel_tail(collapsed)

    if PRECISE_AREA_PATTERN.fullmatch(collapsed):
        return {
            "normalized_name": collapsed,
            "summary_label": collapsed,
            "menu_label": collapsed,
            "scope_kind": "precise",
            "sort_rank": 0,
            "accuracy_label": "精准区域",
            "channel_tail": channel_tail,
        }
    if collapsed == "中央大道 / B2 停车场":
        return {
            "normalized_name": collapsed,
            "summary_label": collapsed,
            "menu_label": collapsed,
            "scope_kind": "precise_project",
            "sort_rank": 4,
            "accuracy_label": "精准项目区",
            "channel_tail": channel_tail,
        }
    if collapsed == "中央大道 / 商场视频区":
        return {
            "normalized_name": collapsed,
            "summary_label": collapsed,
            "menu_label": f"{collapsed}（205项目）",
            "scope_kind": "project_205",
            "sort_rank": 12,
            "accuracy_label": "205项目区",
            "channel_tail": channel_tail,
        }
    if collapsed.startswith("中央大道 / 中央大道旅游购物中心-"):
        return {
            "normalized_name": collapsed,
            "summary_label": collapsed,
            "menu_label": f"{collapsed}（后加点位组）",
            "scope_kind": "addon_floor",
            "sort_rank": 20,
            "accuracy_label": "后加点位组",
            "channel_tail": channel_tail,
        }
    if collapsed in {"客流统计", "呼叫相机", "电梯"}:
        return {
            "normalized_name": collapsed,
            "summary_label": collapsed,
            "menu_label": f"{collapsed}（专项设备）",
            "scope_kind": "special_function",
            "sort_rank": 26,
            "accuracy_label": "专项设备",
            "channel_tail": channel_tail,
        }
    if collapsed in {"候补", "未命名"}:
        return {
            "normalized_name": collapsed,
            "summary_label": collapsed,
            "menu_label": f"{collapsed}（待现场核定）",
            "scope_kind": "manual_review",
            "sort_rank": 40,
            "accuracy_label": "待现场核定",
            "channel_tail": channel_tail,
        }
    return {
        "normalized_name": collapsed or original,
        "summary_label": collapsed or original,
        "menu_label": collapsed or original,
        "scope_kind": "general",
        "sort_rank": 30,
        "accuracy_label": "常规区域",
        "channel_tail": channel_tail,
    }


def area_scope_sort_key(item: dict) -> tuple[int, int, str]:
    sort_rank = item.get("sort_rank")
    camera_count = item.get("camera_count")
    count = item.get("count")
    return (
        int(sort_rank if sort_rank is not None else 99),
        -int(camera_count if camera_count is not None else (count if count is not None else 0)),
        str(item.get("menu_label") or item.get("summary_label") or item.get("display_name") or ""),
    )
