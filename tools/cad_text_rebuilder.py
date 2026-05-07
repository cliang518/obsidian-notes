from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import ezdxf
from ezdxf import recover
from ezdxf.addons import odafc


# 完整 IP：10.0.x.x
FULL_IP_PATTERN = re.compile(r"\b(10\.0\.(\d{1,3})\.(\d{1,3}))\b")
# 只写尾号的情况：独立的 1~3 位数字
SUFFIX_PATTERN = re.compile(r"^\s*(\d{1,3})\s*$")

OUTPUT_LAYER = "AI_提取_监控点位"
ORIGINAL_TEXT_LAYER = "AI_原始_监控文字"
CAMERA_BLOCK = "Standard_Camera"
CAMERA_ATTRIB_TAG = "CAMERA_IP"


@dataclass
class MarkerSummary:
    marker_type: str
    layer: str
    center_x: float
    center_y: float
    radius_hint: float


@dataclass
class CameraCandidate:
    source_text: str
    normalized_value: str
    match_type: str
    ip_suffix: str
    full_ip: str
    x: float
    y: float
    layer: str
    entity_type: str
    text_height: float
    color: int | None
    score: int
    has_nearby_marker: bool
    nearby_marker_type: str
    nearby_marker_layer: str
    marker_distance: float | None
    reasons: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从不规范监控平面图中挖掘摄像头 TEXT/MTEXT，并重构为标准监控块。",
    )
    parser.add_argument("input_file", help="输入 DXF 或 DWG 文件路径")
    parser.add_argument(
        "--output-dir",
        default="",
        help="输出目录。默认写到输入文件同目录下的 ai_extract 子目录。",
    )
    parser.add_argument(
        "--json-name",
        default="camera_topology.json",
        help="JSON 输出文件名",
    )
    parser.add_argument(
        "--clean-name",
        default="清洗后_监控图.dxf",
        help="洗图后 DXF 文件名",
    )
    parser.add_argument(
        "--min-suffix-height",
        type=float,
        default=1.0,
        help="尾号文本的最小字高阈值。用于过滤太小的尺寸文字。",
    )
    parser.add_argument(
        "--max-suffix-height",
        type=float,
        default=1200.0,
        help="尾号文本的最大字高阈值。用于过滤异常超大标题。",
    )
    parser.add_argument(
        "--nearby-radius",
        type=float,
        default=1500.0,
        help="判断文字附近是否存在圆形/闭合多段线符号的搜索半径。",
    )
    parser.add_argument(
        "--allowed-colors",
        default="",
        help="允许的颜色编号，逗号分隔，例如 1,2,3,7。为空表示不按颜色强过滤。",
    )
    parser.add_argument(
        "--blacklist-layers",
        default="尺寸,标注,面积,铺位,疏散,箱体,门窗,轴号,文字",
        help="黑名单图层关键字，命中后降低分数。",
    )
    parser.add_argument(
        "--wash-original-text",
        action="store_true",
        help="是否把命中的原始 TEXT/MTEXT 挪到 AI_原始_监控文字 图层，便于洗图。",
    )
    parser.add_argument(
        "--oda-path",
        default="",
        help="可选，手动指定 ODAFileConverter.exe 路径。",
    )
    return parser.parse_args()


def detect_oda_path(manual_path: str = "") -> str:
    if manual_path:
        path = Path(manual_path)
        if path.exists():
            return str(path)
    candidates = [
        Path(r"C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe"),
        Path(r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"),
        Path(r"C:\Program Files\ODA\ODAFileConverter 25.12.0\ODAFileConverter.exe"),
        Path(r"C:\Program Files\ODA\ODA File Converter\ODAFileConverter.exe"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


def read_dxf_document(path: Path):
    try:
        return ezdxf.readfile(path)
    except Exception:
        doc, _auditor = recover.readfile(path)
        return doc


def load_doc(input_path: Path, oda_path: str):
    suffix = input_path.suffix.lower()
    if suffix == ".dxf":
        return read_dxf_document(input_path)
    if suffix != ".dwg":
        raise ValueError(f"暂不支持的图纸格式: {suffix}")
    if not oda_path:
        raise RuntimeError("未找到 ODA File Converter，无法处理 DWG。")

    ezdxf.options.set("odafc-addon", "win_exec_path", oda_path)
    with TemporaryDirectory(prefix="camera_topology_") as temp_dir:
        dxf_path = Path(temp_dir) / f"{input_path.stem}.dxf"
        odafc.convert(str(input_path), str(dxf_path), version="R2018", audit=False, replace=True)
        doc = read_dxf_document(dxf_path)
    return doc


def extract_plain_text(entity) -> str:
    if entity.dxftype() == "TEXT":
        return entity.dxf.text or ""
    if entity.dxftype() == "MTEXT":
        if hasattr(entity, "plain_text"):
            return entity.plain_text(split=False)
        return entity.text or ""
    return ""


def entity_insert(entity) -> tuple[float, float]:
    insert = getattr(entity.dxf, "insert", None)
    return float(getattr(insert, "x", 0.0)), float(getattr(insert, "y", 0.0))


def entity_text_height(entity) -> float:
    if entity.dxftype() == "TEXT":
        return float(getattr(entity.dxf, "height", 0.0) or 0.0)
    if entity.dxftype() == "MTEXT":
        return float(getattr(entity.dxf, "char_height", 0.0) or 0.0)
    return 0.0


def entity_color(entity) -> int | None:
    value = getattr(entity.dxf, "color", None)
    if value in (0, 256):
        return None
    return int(value) if value is not None else None


def parse_allowed_colors(raw: str) -> set[int]:
    if not raw.strip():
        return set()
    result = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.add(int(part))
        except ValueError:
            continue
    return result


def collect_marker_summaries(doc) -> list[MarkerSummary]:
    markers: list[MarkerSummary] = []
    msp = doc.modelspace()
    for entity in msp:
        dxftype = entity.dxftype()
        layer = str(getattr(entity.dxf, "layer", "") or "")

        if dxftype == "CIRCLE":
            center = entity.dxf.center
            markers.append(
                MarkerSummary(
                    marker_type="circle",
                    layer=layer,
                    center_x=float(center.x),
                    center_y=float(center.y),
                    radius_hint=float(entity.dxf.radius or 0.0),
                )
            )
            continue

        if dxftype == "ARC":
            center = entity.dxf.center
            markers.append(
                MarkerSummary(
                    marker_type="arc",
                    layer=layer,
                    center_x=float(center.x),
                    center_y=float(center.y),
                    radius_hint=float(entity.dxf.radius or 0.0),
                )
            )
            continue

        if dxftype == "LWPOLYLINE":
            points = [(float(p[0]), float(p[1])) for p in entity.get_points("xy")]
            if points and entity.closed:
                cx = sum(p[0] for p in points) / len(points)
                cy = sum(p[1] for p in points) / len(points)
                radius_hint = max(math.dist((cx, cy), p) for p in points)
                markers.append(
                    MarkerSummary(
                        marker_type="closed_lwpolyline",
                        layer=layer,
                        center_x=cx,
                        center_y=cy,
                        radius_hint=radius_hint,
                    )
                )
            continue

        if dxftype == "POLYLINE":
            points = []
            try:
                for vertex in entity.vertices:
                    location = vertex.dxf.location
                    points.append((float(location.x), float(location.y)))
            except Exception:
                points = []
            if points and entity.is_closed:
                cx = sum(p[0] for p in points) / len(points)
                cy = sum(p[1] for p in points) / len(points)
                radius_hint = max(math.dist((cx, cy), p) for p in points)
                markers.append(
                    MarkerSummary(
                        marker_type="closed_polyline",
                        layer=layer,
                        center_x=cx,
                        center_y=cy,
                        radius_hint=radius_hint,
                    )
                )
    return markers


def find_nearby_marker(x: float, y: float, markers: list[MarkerSummary], radius_limit: float):
    best = None
    best_distance = None
    for marker in markers:
        distance = math.dist((x, y), (marker.center_x, marker.center_y))
        allowance = max(radius_limit, marker.radius_hint * 1.6)
        if distance <= allowance:
            if best_distance is None or distance < best_distance:
                best = marker
                best_distance = distance
    return best, best_distance


def score_text_candidate(
    raw_text: str,
    text_height: float,
    layer_name: str,
    color: int | None,
    nearby_marker,
    nearby_distance: float | None,
    args: argparse.Namespace,
) -> tuple[int, str, str, str, list[str]]:
    reasons: list[str] = []
    normalized_value = ""
    full_ip = ""
    ip_suffix = ""
    match_type = "ignored"
    score = 0

    full_match = FULL_IP_PATTERN.search(raw_text)
    if full_match:
        full_ip = full_match.group(1)
        ip_suffix = full_match.group(3)
        normalized_value = full_ip
        match_type = "full_ip"
        score = 100
        reasons.append("命中完整 IP 正则")
    else:
        suffix_match = SUFFIX_PATTERN.match(raw_text.strip())
        if suffix_match:
            ip_suffix = suffix_match.group(1)
            normalized_value = ip_suffix
            match_type = "suffix_only"
            number = int(ip_suffix)
            if number > 255:
                return 0, match_type, normalized_value, ip_suffix, ["尾号大于 255，已过滤"]
            score = 20
            reasons.append("命中独立尾号正则")
        else:
            return 0, match_type, normalized_value, ip_suffix, ["文本不符合 IP/尾号模式"]

    if text_height:
        if args.min_suffix_height <= text_height <= args.max_suffix_height:
            score += 15
            reasons.append("字高在候选区间内")
        else:
            score -= 10
            reasons.append("字高超出候选区间")

    blacklist_keywords = [item.strip() for item in args.blacklist_layers.split(",") if item.strip()]
    if any(keyword in layer_name for keyword in blacklist_keywords):
        score -= 25
        reasons.append("命中疑似建筑/尺寸类图层关键字")
    else:
        score += 8
        reasons.append("图层未命中黑名单")

    allowed_colors = parse_allowed_colors(args.allowed_colors)
    if allowed_colors:
        if color in allowed_colors:
            score += 10
            reasons.append("颜色命中白名单")
        else:
            score -= 8
            reasons.append("颜色未命中白名单")
    elif color is not None:
        reasons.append(f"颜色={color}")

    if nearby_marker is not None:
        score += 28
        reasons.append(f"附近存在 {nearby_marker.marker_type} 符号")
        if nearby_distance is not None:
            reasons.append(f"符号距离 {nearby_distance:.1f}")

    return score, match_type, normalized_value, ip_suffix, reasons


def ensure_layer(doc, layer_name: str, color: int = 1) -> None:
    if layer_name in doc.layers:
        return
    doc.layers.add(layer_name, dxfattribs={"color": color})


def ensure_camera_block(doc) -> None:
    if CAMERA_BLOCK in doc.blocks:
        return

    block = doc.blocks.new(name=CAMERA_BLOCK)
    # 标准块：圆形镜头 + 十字中心 + 右上角属性位。
    block.add_circle((0, 0), radius=150, dxfattribs={"layer": OUTPUT_LAYER, "color": 3})
    block.add_line((-170, 0), (170, 0), dxfattribs={"layer": OUTPUT_LAYER, "color": 3})
    block.add_line((0, -170), (0, 170), dxfattribs={"layer": OUTPUT_LAYER, "color": 3})
    block.add_line((110, 110), (250, 250), dxfattribs={"layer": OUTPUT_LAYER, "color": 3})
    block.add_attdef(
        CAMERA_ATTRIB_TAG,
        insert=(280, 140),
        height=90,
        rotation=0,
        dxfattribs={"layer": OUTPUT_LAYER, "color": 1},
    )


def insert_standard_camera_block(doc, candidate: CameraCandidate) -> None:
    msp = doc.modelspace()
    ref = msp.add_blockref(
        CAMERA_BLOCK,
        (candidate.x, candidate.y),
        dxfattribs={"layer": OUTPUT_LAYER, "xscale": 1.0, "yscale": 1.0},
    )
    ref.add_auto_attribs({CAMERA_ATTRIB_TAG: candidate.normalized_value})


def maybe_wash_original_text(candidate_map: dict[int, CameraCandidate], args: argparse.Namespace, text_entities: list) -> None:
    if not args.wash_original_text:
        return
    for index, entity in enumerate(text_entities):
        if index not in candidate_map:
            continue
        entity.dxf.layer = ORIGINAL_TEXT_LAYER
        try:
            entity.dxf.color = 8
        except Exception:
            pass


def extract_candidates(doc, args: argparse.Namespace) -> tuple[list[CameraCandidate], list]:
    markers = collect_marker_summaries(doc)
    text_entities = []
    candidates: list[CameraCandidate] = []
    msp = doc.modelspace()
    for entity in msp:
        if entity.dxftype() not in {"TEXT", "MTEXT"}:
            continue
        text_entities.append(entity)

    for entity in text_entities:
        raw_text = extract_plain_text(entity).replace("\\P", " ").strip()
        if not raw_text:
            continue
        x, y = entity_insert(entity)
        height = entity_text_height(entity)
        layer_name = str(getattr(entity.dxf, "layer", "") or "")
        color = entity_color(entity)
        nearby_marker, nearby_distance = find_nearby_marker(x, y, markers, args.nearby_radius)
        score, match_type, normalized_value, ip_suffix, reasons = score_text_candidate(
            raw_text=raw_text,
            text_height=height,
            layer_name=layer_name,
            color=color,
            nearby_marker=nearby_marker,
            nearby_distance=nearby_distance,
            args=args,
        )
        if match_type == "ignored":
            continue

        # 完整 IP 直接收；尾号则要求整体分数更高，以免和建筑尺寸混淆。
        threshold = 40 if match_type == "suffix_only" else 60
        if score < threshold:
            continue

        full_ip = normalized_value if match_type == "full_ip" else ""
        candidates.append(
            CameraCandidate(
                source_text=raw_text,
                normalized_value=normalized_value,
                match_type=match_type,
                ip_suffix=ip_suffix,
                full_ip=full_ip,
                x=x,
                y=y,
                layer=layer_name,
                entity_type=entity.dxftype(),
                text_height=height,
                color=color,
                score=score,
                has_nearby_marker=nearby_marker is not None,
                nearby_marker_type=nearby_marker.marker_type if nearby_marker else "",
                nearby_marker_layer=nearby_marker.layer if nearby_marker else "",
                marker_distance=nearby_distance,
                reasons=reasons,
            )
        )

    return candidates, text_entities


def write_json(output_path: Path, candidates: list[CameraCandidate], input_file: Path) -> None:
    payload = {
        "source_file": str(input_file),
        "camera_count": len(candidates),
        "cameras": [asdict(item) for item in candidates],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def rebuild_clean_dxf(doc, candidates: list[CameraCandidate], args: argparse.Namespace, text_entities: list, output_path: Path) -> None:
    ensure_layer(doc, OUTPUT_LAYER, color=1)
    ensure_layer(doc, ORIGINAL_TEXT_LAYER, color=8)
    ensure_camera_block(doc)

    entity_candidate_map: dict[int, CameraCandidate] = {}
    for candidate in candidates:
        insert_standard_camera_block(doc, candidate)

    if args.wash_original_text:
        matched_index = 0
        for entity in text_entities:
            raw_text = extract_plain_text(entity).replace("\\P", " ").strip()
            x, y = entity_insert(entity)
            for candidate in candidates:
                if (
                    candidate.source_text == raw_text
                    and abs(candidate.x - x) < 1e-6
                    and abs(candidate.y - y) < 1e-6
                ):
                    entity_candidate_map[matched_index] = candidate
                    break
            matched_index += 1
        maybe_wash_original_text(entity_candidate_map, args, text_entities)

    doc.saveas(output_path)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_file).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else input_path.parent / "ai_extract"
    output_dir.mkdir(parents=True, exist_ok=True)

    oda_path = detect_oda_path(args.oda_path)
    doc = load_doc(input_path, oda_path)
    candidates, text_entities = extract_candidates(doc, args)

    json_path = output_dir / args.json_name
    clean_dxf_path = output_dir / args.clean_name

    write_json(json_path, candidates, input_path)
    rebuild_clean_dxf(doc, candidates, args, text_entities, clean_dxf_path)

    print("=" * 72)
    print("摄像头文本提取完成")
    print(f"输入文件: {input_path}")
    print(f"ODA 路径: {oda_path or '未使用'}")
    print(f"识别数量: {len(candidates)}")
    print(f"JSON 输出: {json_path}")
    print(f"清洗 DXF: {clean_dxf_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()
