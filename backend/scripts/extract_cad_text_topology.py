from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.core.settings import settings


DEFAULT_ODA_PATH = Path(r"C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe")
FULL_IP_PATTERN = re.compile(r"10\.0\.\d{1,3}\.\d{1,3}")
PARTIAL_IP_PATTERN = re.compile(r"(?<![0-9A-Za-z])([1-9]\d{1,2}\.\d{1,3})(?![0-9A-Za-z])")
TAIL_PATTERN = re.compile(r"^\d{1,3}$")
EXCLUDED_LAYER_HINTS = ("DIM", "标注", "尺寸", "AXIS", "轴网")
EXCLUDED_LAYER_NAMES = {"WINDOW_TEXT", "WINDOW", "COLUMN", "AXIS", "MC", "DOOR_FIRE"}
PREFERRED_LAYER_HINTS = ("监控", "弱电", "LWIRE", "EQUIP")
PREFERRED_BLOCK_HINTS = ("TelecSys", "$equip", "A$C615F00DA", "A$C2D3553B4", "1a00a")
CAMERA_ANCHOR_RADIUS = 2600.0


@dataclass
class CadTextEntity:
    entity_type: str
    text: str
    layer: str
    color: str
    text_height: float
    x: float
    y: float
    handle: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract camera-like text entities from huge DWG/DXF files.")
    parser.add_argument("--input", required=True, help="Path to a DWG or DXF file.")
    parser.add_argument("--output-dir", default="", help="Optional output directory. Defaults to runtime/reports/cad_extract.")
    parser.add_argument("--oda-path", default=str(DEFAULT_ODA_PATH), help="ODA File Converter executable path.")
    parser.add_argument("--inventory-db", default=str(settings.database_path), help="Optional platform SQLite database used to validate extracted camera IPs.")
    parser.add_argument("--tail-min-height", type=float, default=1.0, help="Minimum text height for numeric tail candidates.")
    parser.add_argument("--tail-max-height", type=float, default=12.0, help="Maximum text height for numeric tail candidates.")
    parser.add_argument("--camera-prefix", default="10.0.", help="Prefix to prepend when a numeric tail is treated as camera IP suffix.")
    parser.add_argument("--keep-dxf", action="store_true", help="Keep converted DXF file when source is DWG.")
    return parser.parse_args()


def report_dir(custom: str) -> Path:
    if custom:
        path = Path(custom)
    else:
        path = settings.runtime_dir / "reports" / "cad_extract"
    path.mkdir(parents=True, exist_ok=True)
    return path


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def sanitize_mtext(text: str) -> str:
    value = (text or "").replace("\\P", " ").replace("\\~", " ")
    value = re.sub(r"{\\.*?;?", "", value)
    value = re.sub(r"\\[A-Za-z][^;]*;?", "", value)
    value = value.replace("{", "").replace("}", "")
    return " ".join(value.split())


def pair_stream(path: Path):
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        while True:
            code = handle.readline()
            if not code:
                break
            value = handle.readline()
            if not value:
                break
            yield code.strip(), value.rstrip("\r\n")


def parse_float(raw: str) -> float:
    try:
        return float(str(raw or "").strip())
    except ValueError:
        return 0.0


def _to_entity(entity_type: str, tags: dict[str, list[str]]) -> CadTextEntity | None:
    if entity_type not in {"TEXT", "MTEXT", "INSERT"}:
        return None
    text_values = tags.get("1", []) + tags.get("3", [])
    raw_text = " ".join(part for part in text_values if part.strip())
    if entity_type == "INSERT":
        raw_text = (tags.get("2", [""])[0] or "").strip()
    text = sanitize_mtext(raw_text if entity_type == "MTEXT" else raw_text.strip())
    if not text:
        return None
    return CadTextEntity(
        entity_type=entity_type,
        text=text,
        layer=(tags.get("8", [""])[0] or "").strip(),
        color=(tags.get("62", [""])[0] or "").strip(),
        text_height=parse_float((tags.get("40", ["0"])[0] or "0")),
        x=parse_float((tags.get("10", ["0"])[0] or "0")),
        y=parse_float((tags.get("20", ["0"])[0] or "0")),
        handle=(tags.get("5", [""])[0] or "").strip(),
    )


def iter_entities(path: Path):
    in_entities = False
    current_type = ""
    current_tags: dict[str, list[str]] = {}
    expect_section_name = False
    for code, value in pair_stream(path):
        if code == "0" and value == "SECTION":
            expect_section_name = True
            continue
        if expect_section_name and code == "2":
            in_entities = value == "ENTITIES"
            expect_section_name = False
            current_type = ""
            current_tags = {}
            continue
        if not in_entities:
            if code == "0" and value == "ENDSEC":
                in_entities = False
            continue
        if code == "0":
            if current_type:
                entity = _to_entity(current_type, current_tags)
                if entity is not None:
                    yield entity
            if value == "ENDSEC":
                in_entities = False
                current_type = ""
                current_tags = {}
                continue
            current_type = value
            current_tags = {}
            continue
        if current_type:
            current_tags.setdefault(code, []).append(value)
    if in_entities and current_type:
        entity = _to_entity(current_type, current_tags)
        if entity is not None:
            yield entity


def should_exclude_tail(entity: CadTextEntity, min_height: float, max_height: float) -> bool:
    if entity.text_height and entity.text_height < min_height:
        return True
    if entity.text_height and entity.text_height > max_height:
        return True
    layer_upper = entity.layer.upper()
    if entity.layer in EXCLUDED_LAYER_NAMES:
        return True
    return any(hint in layer_upper for hint in EXCLUDED_LAYER_HINTS)


def should_exclude_partial(entity: CadTextEntity) -> bool:
    if entity.layer in EXCLUDED_LAYER_NAMES:
        return True
    layer_upper = entity.layer.upper()
    return any(hint in layer_upper for hint in EXCLUDED_LAYER_HINTS)


def build_camera_ip_from_partial(partial: str, camera_prefix: str) -> str:
    left, right = partial.split(".", 1)
    prefix = camera_prefix.rstrip(".")
    return f"{prefix}.{int(left)}.{int(right)}"


def is_preferred_anchor(entity: CadTextEntity) -> bool:
    layer = entity.layer or ""
    text = entity.text or ""
    return any(hint in layer for hint in PREFERRED_LAYER_HINTS) or any(hint in text for hint in PREFERRED_BLOCK_HINTS)


def candidate_row(
    *,
    camera_ip: str,
    label: str,
    match_kind: str,
    confidence: float,
    entity: CadTextEntity,
    score_reasons: list[str],
    anchor: CadTextEntity | None = None,
    distance: float | None = None,
) -> dict:
    row = {
        "camera_ip": camera_ip,
        "label": label,
        "match_kind": match_kind,
        "confidence": round(confidence, 3),
        "x": round(entity.x, 3),
        "y": round(entity.y, 3),
        "text_height": entity.text_height,
        "layer": entity.layer,
        "color": entity.color,
        "entity_type": entity.entity_type,
        "handle": entity.handle,
        "score_reasons": score_reasons,
    }
    if anchor is not None:
        row.update(
            {
                "anchor_layer": anchor.layer,
                "anchor_text": anchor.text,
                "anchor_handle": anchor.handle,
            }
        )
    if distance is not None:
        row["anchor_distance"] = round(distance, 1)
    return row


def classify_camera_candidates(entities: list[CadTextEntity], camera_prefix: str, min_height: float, max_height: float) -> list[dict]:
    items: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for entity in entities:
        text = entity.text.strip()
        if FULL_IP_PATTERN.search(text):
            matched = FULL_IP_PATTERN.search(text)
            camera_ip = matched.group(0) if matched else text
            key = (entity.handle, "full_ip", camera_ip)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                candidate_row(
                    camera_ip=camera_ip,
                    label=text,
                    match_kind="full_ip",
                    confidence=0.99,
                    entity=entity,
                    score_reasons=["matched full 10.0.x.x text"],
                )
            )
            continue
        partial_match = PARTIAL_IP_PATTERN.search(text)
        if partial_match and not text.startswith("10.0."):
            if should_exclude_partial(entity):
                continue
            camera_ip = build_camera_ip_from_partial(partial_match.group(1), camera_prefix)
            confidence = 0.72
            reasons = ["matched partial x.x ip text"]
            if entity.layer == "0":
                confidence += 0.08
                reasons.append("base layer text often stores camera ip suffix")
            if entity.text_height >= 900:
                confidence += 0.05
                reasons.append("large annotation height resembles device label")
            if entity.layer != "0" and entity.text_height < 600:
                continue
            key = (entity.handle, "partial_ip_text", camera_ip)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                candidate_row(
                    camera_ip=camera_ip,
                    label=text,
                    match_kind="partial_ip_text",
                    confidence=min(confidence, 0.94),
                    entity=entity,
                    score_reasons=reasons,
                )
            )
            continue
        if TAIL_PATTERN.fullmatch(text):
            if should_exclude_tail(entity, min_height, max_height):
                continue
            suffix = text.zfill(1)
            camera_ip = f"{camera_prefix}{suffix}"
            key = (entity.handle, "tail_number", camera_ip)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                candidate_row(
                    camera_ip=camera_ip,
                    label=text,
                    match_kind="tail_number",
                    confidence=0.62,
                    entity=entity,
                    score_reasons=["matched numeric tail candidate"],
                )
            )

    anchors = [entity for entity in entities if entity.entity_type == "INSERT" and is_preferred_anchor(entity)]
    partial_text_entities = [
        entity
        for entity in entities
        if entity.entity_type in {"TEXT", "MTEXT"}
        and PARTIAL_IP_PATTERN.search(entity.text.strip())
        and not entity.text.strip().startswith("10.0.")
        and not should_exclude_partial(entity)
    ]
    for anchor in anchors:
        best_match: tuple[float, CadTextEntity] | None = None
        for text_entity in partial_text_entities:
            distance = math.hypot(text_entity.x - anchor.x, text_entity.y - anchor.y)
            if distance > CAMERA_ANCHOR_RADIUS:
                continue
            score = distance
            if text_entity.layer == "0":
                score -= 250.0
            if text_entity.text_height >= 900:
                score -= 120.0
            if best_match is None or score < best_match[0]:
                best_match = (score, text_entity)
        if best_match is None:
            continue
        _, text_entity = best_match
        distance = math.hypot(text_entity.x - anchor.x, text_entity.y - anchor.y)
        partial = PARTIAL_IP_PATTERN.search(text_entity.text.strip())
        if not partial:
            continue
        camera_ip = build_camera_ip_from_partial(partial.group(1), camera_prefix)
        confidence = 0.88
        reasons = ["paired nearby monitoring/electrical anchor block with partial x.x ip text"]
        if anchor.layer:
            reasons.append(f"anchor layer={anchor.layer}")
        if text_entity.layer == "0":
            confidence += 0.03
            reasons.append("nearby label is on base layer 0")
        if distance <= 1600:
            confidence += 0.03
            reasons.append("anchor and label are spatially close")
        key = (text_entity.handle, "anchor_partial_ip", camera_ip)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            candidate_row(
                camera_ip=camera_ip,
                label=text_entity.text.strip(),
                match_kind="anchor_partial_ip",
                confidence=min(confidence, 0.97),
                entity=text_entity,
                score_reasons=reasons,
                anchor=anchor,
                distance=distance,
            )
        )

    items.sort(key=lambda item: (-float(item.get("confidence", 0.0)), item.get("camera_ip", ""), item.get("handle", "")))
    return items


def convert_dwg_to_dxf(source: Path, output_root: Path, oda_path: Path) -> Path:
    if not oda_path.exists():
        raise FileNotFoundError(f"ODA converter not found: {oda_path}")
    work_dir = output_root / f"oda_job_{stamp()}"
    in_dir = work_dir / "in"
    out_dir = work_dir / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    copied = in_dir / source.name
    shutil.copy2(source, copied)
    command = [
        str(oda_path),
        str(in_dir),
        str(out_dir),
        "ACAD2018",
        "DXF",
        "0",
        "1",
        "*.dwg",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    dxf_files = list(out_dir.glob("*.dxf"))
    if result.returncode != 0 or not dxf_files:
        raise RuntimeError(
            f"ODA conversion failed (code={result.returncode}). stdout={result.stdout[:400]} stderr={result.stderr[:400]}"
        )
    return dxf_files[0]


def load_known_camera_ips(database_path: Path) -> set[str]:
    if not database_path.exists():
        return set()
    known: set[str] = set()
    conn = sqlite3.connect(str(database_path))
    try:
        cur = conn.cursor()
        for sql in (
            "SELECT camera_ip FROM video_channel WHERE camera_ip IS NOT NULL AND camera_ip <> ''",
            "SELECT management_ip FROM asset_device WHERE management_ip IS NOT NULL AND management_ip <> ''",
            "SELECT service_ip FROM asset_device WHERE service_ip IS NOT NULL AND service_ip <> ''",
        ):
            cur.execute(sql)
            known.update(str(row[0]).strip() for row in cur.fetchall() if row and row[0])
    finally:
        conn.close()
    return known


def write_outputs(output_dir: Path, source_name: str, entities: list[CadTextEntity], candidates: list[dict], known_camera_ips: set[str] | None = None) -> dict:
    file_stem = Path(source_name).stem
    out_json = output_dir / f"{file_stem}-camera-topology.json"
    out_csv = output_dir / f"{file_stem}-camera-topology.csv"
    out_best_csv = output_dir / f"{file_stem}-camera-topology-best.csv"
    out_known_csv = output_dir / f"{file_stem}-camera-topology-known.csv"
    out_text_json = output_dir / f"{file_stem}-text-entities.json"
    known_camera_ips = known_camera_ips or set()
    for item in candidates:
        ip = str(item.get("camera_ip") or "").strip()
        item["inventory_match"] = ip in known_camera_ips if ip else False
    match_kind_counts: dict[str, int] = {}
    for item in candidates:
        kind = str(item.get("match_kind") or "unknown")
        match_kind_counts[kind] = match_kind_counts.get(kind, 0) + 1
    best_by_ip: dict[str, dict] = {}
    for item in candidates:
        ip = str(item.get("camera_ip") or "").strip()
        if not ip:
            continue
        current = best_by_ip.get(ip)
        if current is None or float(item.get("confidence", 0.0)) > float(current.get("confidence", 0.0)):
            best_by_ip[ip] = item

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_name": source_name,
        "camera_candidate_count": len(candidates),
        "best_camera_candidate_count": len(best_by_ip),
        "inventory_match_count": sum(1 for item in candidates if item.get("inventory_match")),
        "best_inventory_match_count": sum(1 for item in best_by_ip.values() if item.get("inventory_match")),
        "text_entity_count": len(entities),
        "match_kind_counts": match_kind_counts,
        "best_camera_candidates": list(best_by_ip.values()),
        "camera_candidates": candidates,
    }
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    with out_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "camera_ip",
            "label",
            "match_kind",
            "confidence",
            "x",
            "y",
            "text_height",
            "layer",
            "color",
            "entity_type",
            "handle",
            "anchor_layer",
            "anchor_text",
            "anchor_handle",
            "anchor_distance",
            "inventory_match",
            "score_reasons",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in candidates:
            serializable = dict(row)
            if isinstance(serializable.get("score_reasons"), list):
                serializable["score_reasons"] = " | ".join(serializable["score_reasons"])
            writer.writerow(serializable)

    with out_best_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "camera_ip",
            "label",
            "match_kind",
            "confidence",
            "x",
            "y",
            "text_height",
            "layer",
            "color",
            "entity_type",
            "handle",
            "anchor_layer",
            "anchor_text",
            "anchor_handle",
            "anchor_distance",
            "inventory_match",
            "score_reasons",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(best_by_ip.values(), key=lambda item: item.get("camera_ip", "")):
            serializable = dict(row)
            if isinstance(serializable.get("score_reasons"), list):
                serializable["score_reasons"] = " | ".join(serializable["score_reasons"])
            writer.writerow(serializable)

    with out_known_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "camera_ip",
            "label",
            "match_kind",
            "confidence",
            "x",
            "y",
            "text_height",
            "layer",
            "color",
            "entity_type",
            "handle",
            "anchor_layer",
            "anchor_text",
            "anchor_handle",
            "anchor_distance",
            "inventory_match",
            "score_reasons",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted((item for item in best_by_ip.values() if item.get("inventory_match")), key=lambda item: item.get("camera_ip", "")):
            serializable = dict(row)
            if isinstance(serializable.get("score_reasons"), list):
                serializable["score_reasons"] = " | ".join(serializable["score_reasons"])
            writer.writerow(serializable)

    out_text_json.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "source_name": source_name,
                "entities": [asdict(item) for item in entities[:6000]],
                "truncated": len(entities) > 6000,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "summary_json": str(out_json),
        "camera_csv": str(out_csv),
        "camera_best_csv": str(out_best_csv),
        "camera_known_csv": str(out_known_csv),
        "text_entities_json": str(out_text_json),
    }


def main() -> int:
    args = parse_args()
    source = Path(args.input)
    if not source.exists():
        raise SystemExit(f"Input not found: {source}")

    output_dir = report_dir(args.output_dir)
    dxf_path = source
    converted = False
    if source.suffix.lower() == ".dwg":
        dxf_path = convert_dwg_to_dxf(source, output_dir, Path(args.oda_path))
        converted = True

    entities = list(iter_entities(dxf_path))
    known_camera_ips = load_known_camera_ips(Path(args.inventory_db))
    candidates = classify_camera_candidates(
        entities,
        camera_prefix=args.camera_prefix,
        min_height=args.tail_min_height,
        max_height=args.tail_max_height,
    )
    outputs = write_outputs(output_dir, source.name, entities, candidates, known_camera_ips=known_camera_ips)

    payload = {
        "ok": True,
        "source": str(source),
        "inventory_db": args.inventory_db,
        "known_camera_ip_count": len(known_camera_ips),
        "dxf_path": str(dxf_path),
        "converted_from_dwg": converted,
        "text_entity_count": len(entities),
        "camera_candidate_count": len(candidates),
        "full_ip_count": sum(1 for item in candidates if item["match_kind"] == "full_ip"),
        "tail_candidate_count": sum(1 for item in candidates if item["match_kind"] == "tail_number"),
        **outputs,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if converted and not args.keep_dxf:
        # Keep the DXF for downstream review; caller can clean manually if needed.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
