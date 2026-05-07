from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.asset import AssetArea, AssetDevice, VideoChannel
from app.models.floor_plan import FloorPlanAnchor, FloorPlanDocument
from app.services.text_normalize import normalize_text

try:
    import ezdxf
    from ezdxf import recover
    from ezdxf.addons import odafc
except ModuleNotFoundError:
    ezdxf = None
    recover = None
    odafc = None


IP_SUFFIX_PATTERN = re.compile(r"10\.0\.(\d{1,3})")


def floor_plan_storage_dir() -> Path:
    path = settings.runtime_dir / "floor_plans"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in name).strip("._") or "cad_file"


def _extract_text_and_point(entity) -> tuple[str, float | None, float | None]:
    entity_type = entity.dxftype()
    if entity_type == "TEXT":
        point = getattr(entity.dxf, "insert", None)
        return entity.dxf.text or "", getattr(point, "x", None), getattr(point, "y", None)
    if entity_type == "MTEXT":
        point = getattr(entity.dxf, "insert", None)
        text = entity.plain_text(split=False) if hasattr(entity, "plain_text") else entity.text
        return text or "", getattr(point, "x", None), getattr(point, "y", None)
    if entity_type in {"ATTRIB", "ATTDEF"}:
        point = getattr(entity.dxf, "insert", None)
        return entity.dxf.text or "", getattr(point, "x", None), getattr(point, "y", None)
    return "", None, None


def _iter_text_entities(doc) -> list[dict]:
    msp = doc.modelspace()
    items: list[dict] = []
    for entity in msp:
        entity_type = entity.dxftype()
        if entity_type in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
            text, pos_x, pos_y = _extract_text_and_point(entity)
            if text.strip():
                items.append(
                    {
                        "entity_type": entity_type,
                        "layer_name": getattr(entity.dxf, "layer", ""),
                        "text": text,
                        "x": pos_x,
                        "y": pos_y,
                    }
                )
            continue
        if entity_type == "INSERT":
            for attrib in getattr(entity, "attribs", []):
                text, pos_x, pos_y = _extract_text_and_point(attrib)
                if text.strip():
                    items.append(
                        {
                            "entity_type": "INSERT_ATTRIB",
                            "layer_name": getattr(attrib.dxf, "layer", getattr(entity.dxf, "layer", "")),
                            "text": text,
                            "x": pos_x,
                            "y": pos_y,
                        }
                    )
    return items


def _read_dxf_doc(path: Path):
    if ezdxf is None or recover is None:
        raise RuntimeError("ezdxf_not_installed")
    try:
        return ezdxf.readfile(path)
    except Exception:
        doc, _auditor = recover.readfile(path)
        return doc


def _last_octet(ip: str) -> str:
    parts = (ip or "").split(".")
    if len(parts) != 4:
        return ""
    return parts[-1]


def _score_candidate(document: FloorPlanDocument, area_name: str, source_type: str) -> tuple[int, list[str]]:
    score = 100
    reasons = ["IP 尾号匹配"]
    tokens = [normalize_text(document.site), normalize_text(document.building), normalize_text(document.floor), normalize_text(document.zone)]
    area_text = normalize_text(area_name)
    for token in tokens:
        token = token.strip()
        if token and token in area_text:
            score += 20
            reasons.append(f"区域命中:{token}")
    if normalize_text(document.floor).strip().upper() == "B2" and "205" in source_type:
        score += 30
        reasons.append("B2 停车场区域命中")
    return score, reasons


def _candidate_rows(db: Session) -> list[dict]:
    devices = db.scalars(select(AssetDevice)).all()
    areas = {row.id: row for row in db.scalars(select(AssetArea)).all()}
    channels = db.scalars(select(VideoChannel)).all()

    rows: list[dict] = []
    for device in devices:
        is_camera_like = (
            device.device_type in {"camera", "camera_direct", "camera_endpoint"}
            or device.primary_source_type in {"jvss", "jvss_205", "hikvision_nvr", "hikvision_nvr_legacy", "camera_direct"}
        )
        if not is_camera_like:
            continue
        for ip in {device.management_ip, device.service_ip}:
            if not (ip or "").startswith("10.0."):
                continue
            tail = _last_octet(ip)
            if not tail:
                continue
            area = areas.get(device.area_id)
            rows.append(
                {
                    "tail": tail,
                    "ip": ip,
                    "label": normalize_text(device.hostname) or ip,
                    "source_type": device.primary_source_type,
                    "area_display_name": normalize_text(area.display_name) if area else "",
                    "device_id": device.id,
                }
            )
    device_map = {row.id: row for row in devices}
    for channel in channels:
        if not (channel.camera_ip or "").startswith("10.0."):
            continue
        tail = _last_octet(channel.camera_ip)
        if not tail:
            continue
        camera = device_map.get(channel.camera_asset_id) if channel.camera_asset_id else None
        parent = device_map.get(channel.parent_device_id)
        area = areas.get((camera.area_id if camera else None) or (parent.area_id if parent else None))
        rows.append(
            {
                "tail": tail,
                "ip": channel.camera_ip,
                "label": normalize_text(channel.channel_name) or channel.camera_ip,
                "source_type": parent.primary_source_type if parent else "",
                "area_display_name": normalize_text(area.display_name) if area else "",
                "device_id": camera.id if camera else None,
            }
        )
    return rows


def _build_candidates(db: Session, document: FloorPlanDocument, suffix: str) -> list[dict]:
    dedup: dict[tuple[str, str], dict] = {}
    for row in _candidate_rows(db):
        if row["tail"] != suffix:
            continue
        score, reasons = _score_candidate(document, row["area_display_name"], row["source_type"])
        key = (row["ip"], row["label"])
        current = dedup.get(key)
        candidate = {
            "ip": row["ip"],
            "label": row["label"],
            "source_type": row["source_type"],
            "area_display_name": row["area_display_name"],
            "score": score,
            "reasons": reasons,
            "device_id": row["device_id"],
        }
        if current is None or candidate["score"] > current["score"]:
            dedup[key] = candidate
    return sorted(dedup.values(), key=lambda item: (-item["score"], item["ip"], item["label"]))[:10]


def _oda_converter_path() -> str:
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


def _configure_odafc() -> str:
    if ezdxf is None or odafc is None:
        raise RuntimeError("ezdxf_not_installed")
    oda_path = _oda_converter_path()
    if oda_path:
        ezdxf.options.set("odafc-addon", "win_exec_path", oda_path)
    return oda_path


def _load_dwg_as_dxf_text_entities(path: Path) -> list[dict]:
    oda_path = _configure_odafc()
    if not oda_path:
        raise RuntimeError("odafc_not_found")
    with TemporaryDirectory(prefix="v2_dwg_") as temp_dir:
        dxf_path = Path(temp_dir) / f"{path.stem}.dxf"
        odafc.convert(str(path), str(dxf_path), version="R2018", audit=False, replace=True)
        doc = _read_dxf_doc(dxf_path)
        return _iter_text_entities(doc)


def _stream_extract_script_path() -> Path:
    return settings.root_dir / "backend" / "scripts" / "extract_cad_text_topology.py"


def _run_stream_extract(path: Path) -> dict | None:
    script_path = _stream_extract_script_path()
    if not script_path.exists():
        return None
    command = [
        sys.executable,
        str(script_path),
        "--input",
        str(path),
        "--inventory-db",
        str(settings.database_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _candidate_device_map(db: Session) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for device in db.scalars(select(AssetDevice)).all():
        for ip in {device.management_ip, device.service_ip}:
            if ip and ip not in mapping:
                mapping[ip] = device.id
    for channel in db.scalars(select(VideoChannel)).all():
        if channel.camera_ip and channel.camera_asset_id and channel.camera_ip not in mapping:
            mapping[channel.camera_ip] = channel.camera_asset_id
    return mapping


def _parse_via_stream_extract(db: Session, document: FloorPlanDocument, path: Path) -> FloorPlanDocument | None:
    payload = _run_stream_extract(path)
    if not payload or not payload.get("summary_json"):
        return None
    summary_path = Path(str(payload["summary_json"]))
    if not summary_path.exists():
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    best_rows = summary.get("best_camera_candidates", [])
    device_map = _candidate_device_map(db)

    db.query(FloorPlanAnchor).filter(FloorPlanAnchor.document_id == document.id).delete()

    matched_count = 0
    for row in best_rows:
        camera_ip = normalize_text(str(row.get("camera_ip") or ""))
        device_id = device_map.get(camera_ip)
        if device_id:
            matched_count += 1
        note_parts = [
            f"match_kind={normalize_text(str(row.get('match_kind') or ''))}",
            f"confidence={row.get('confidence')}",
        ]
        if row.get("anchor_layer"):
            note_parts.append(f"anchor_layer={normalize_text(str(row.get('anchor_layer') or ''))}")
        if row.get("anchor_distance") is not None:
            note_parts.append(f"anchor_distance={row.get('anchor_distance')}")
        reasons = row.get("score_reasons") or []
        if isinstance(reasons, list) and reasons:
            note_parts.append("reasons=" + " | ".join(normalize_text(str(item)) for item in reasons))
        elif isinstance(reasons, str) and reasons.strip():
            note_parts.append("reasons=" + normalize_text(reasons))
        db.add(
            FloorPlanAnchor(
                document_id=document.id,
                anchor_text=normalize_text(str(row.get("label") or "")),
                normalized_text=camera_ip,
                ip_suffix_hint=camera_ip.replace("10.0.", ""),
                layer_name=normalize_text(str(row.get("layer") or row.get("anchor_layer") or "")),
                entity_type=normalize_text(str(row.get("entity_type") or row.get("match_kind") or "")),
                pos_x=row.get("x"),
                pos_y=row.get("y"),
                matched_device_id=device_id,
                confidence=float(row.get("confidence") or 0.0),
                match_note="; ".join(part for part in note_parts if part),
            )
        )

    document.parse_status = "parsed"
    document.parser_used = "stream_extract"
    document.extracted_text_count = int(summary.get("text_entity_count") or 0)
    document.extracted_suffix_count = int(summary.get("camera_candidate_count") or 0)
    document.matched_anchor_count = matched_count
    document.notes = normalize_text(document.notes)
    db.commit()
    db.refresh(document)
    return document


def upload_and_parse_floor_plan(
    db: Session,
    file: UploadFile,
    *,
    title: str = "",
    site: str = "",
    building: str = "",
    floor: str = "",
    zone: str = "",
    notes: str = "",
) -> FloorPlanDocument:
    if ezdxf is None:
        raise RuntimeError("ezdxf_not_installed")
    suffix = Path(file.filename or "").suffix.lower()
    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex}_{_safe_name(Path(file.filename or 'cad_file').name)}"
    storage_path = floor_plan_storage_dir() / stored_name
    content = file.file.read()
    storage_path.write_bytes(content)

    document = FloorPlanDocument(
        title=normalize_text(title) or normalize_text(Path(file.filename or "").stem),
        original_filename=file.filename or stored_name,
        file_extension=suffix,
        storage_path=str(storage_path),
        source_type="cad_upload",
        parse_status="uploaded",
        site=normalize_text(site),
        building=normalize_text(building),
        floor=normalize_text(floor),
        zone=normalize_text(zone),
        notes=normalize_text(notes),
        file_size=len(content),
    )
    db.add(document)
    db.flush()

    if suffix == ".dwg":
        return parse_floor_plan_document(db, document.id)

    if suffix == ".dxf":
        return parse_floor_plan_document(db, document.id)

    document.parse_status = "unsupported"
    document.parser_used = "unsupported"
    document.notes = (normalize_text(notes) + "\n" if notes else "") + "当前只直接支持 DXF，DWG 需先转换。"
    db.commit()
    db.refresh(document)
    return document


def parse_floor_plan_document(db: Session, document_id: int) -> FloorPlanDocument:
    if ezdxf is None:
        document = db.get(FloorPlanDocument, document_id)
        if document is None:
            raise ValueError("floor_plan_not_found")
        document.parse_status = "dependency_missing"
        document.parser_used = "ezdxf_missing"
        note = "当前主机未安装 ezdxf，图纸解析功能暂不可用。"
        document.notes = f"{normalize_text(document.notes)}\n{note}".strip()
        db.commit()
        db.refresh(document)
        return document
    document = db.get(FloorPlanDocument, document_id)
    if document is None:
        raise ValueError("floor_plan_not_found")
    path = Path(document.storage_path)
    if not path.exists():
        document.parse_status = "missing_file"
        document.parser_used = "missing"
        db.commit()
        db.refresh(document)
        return document

    stream_document = _parse_via_stream_extract(db, document, path)
    if stream_document is not None:
        return stream_document

    db.query(FloorPlanAnchor).filter(FloorPlanAnchor.document_id == document.id).delete()
    entities: list[dict]
    if document.file_extension.lower() == ".dxf":
        doc = _read_dxf_doc(path)
        entities = _iter_text_entities(doc)
        parser_used = "ezdxf"
    elif document.file_extension.lower() == ".dwg":
        try:
            entities = _load_dwg_as_dxf_text_entities(path)
            parser_used = "odafc+ezdxf"
        except RuntimeError:
            document.parse_status = "conversion_required"
            document.parser_used = "dwg_pending"
            document.notes = normalize_text(document.notes) + ("\n" if document.notes else "") + "DWG 解析需要 ODA File Converter。"
            db.commit()
            db.refresh(document)
            return document
    else:
        return document

    suffix_count = 0
    matched_count = 0
    for item in entities:
        raw_text = normalize_text(item["text"])
        match = IP_SUFFIX_PATTERN.search(raw_text)
        suffix = match.group(1) if match else ""
        candidates = _build_candidates(db, document, suffix) if suffix else []
        if suffix:
            suffix_count += 1
        if candidates:
            matched_count += 1
        best = candidates[0] if candidates else None
        db.add(
            FloorPlanAnchor(
                document_id=document.id,
                anchor_text=raw_text,
                normalized_text=raw_text,
                ip_suffix_hint=suffix,
                layer_name=normalize_text(item["layer_name"]),
                entity_type=item["entity_type"],
                pos_x=item["x"],
                pos_y=item["y"],
                matched_device_id=best["device_id"] if best else None,
                confidence=(best["score"] / 200.0) if best else 0.0,
                match_note="; ".join(best["reasons"]) if best else "",
            )
        )

    document.parse_status = "parsed"
    document.parser_used = parser_used
    document.extracted_text_count = len(entities)
    document.extracted_suffix_count = suffix_count
    document.matched_anchor_count = matched_count
    db.commit()
    db.refresh(document)
    return document


def list_floor_plan_documents(db: Session) -> list[FloorPlanDocument]:
    return db.scalars(select(FloorPlanDocument).order_by(FloorPlanDocument.id.desc())).all()


def floor_plan_detail(db: Session, document_id: int) -> dict:
    document = db.get(FloorPlanDocument, document_id)
    if document is None:
        raise ValueError("floor_plan_not_found")

    anchors = db.scalars(
        select(FloorPlanAnchor).where(FloorPlanAnchor.document_id == document.id).order_by(FloorPlanAnchor.id.asc())
    ).all()
    matched_ids = {anchor.matched_device_id for anchor in anchors if anchor.matched_device_id}
    matched_devices = (
        {
            row.id: row
            for row in db.scalars(select(AssetDevice).where(AssetDevice.id.in_(matched_ids))).all()
        }
        if matched_ids
        else {}
    )
    areas = {row.id: row for row in db.scalars(select(AssetArea)).all()}
    layer_summary = Counter(anchor.layer_name or "默认图层" for anchor in anchors)
    anchor_rows = []
    for anchor in anchors:
        matched_device = matched_devices.get(anchor.matched_device_id) if anchor.matched_device_id else None
        matched_area = areas.get(matched_device.area_id) if matched_device and matched_device.area_id else None
        if document.parser_used == "stream_extract":
            candidates = []
            if matched_device:
                candidates = [
                    {
                        "ip": normalize_text(matched_device.management_ip or matched_device.service_ip),
                        "label": normalize_text(matched_device.hostname) or normalize_text(anchor.normalized_text),
                        "source_type": normalize_text(matched_device.primary_source_type),
                        "area_display_name": normalize_text(matched_area.display_name) if matched_area else "",
                        "score": round(float(anchor.confidence or 0.0) * 100, 1),
                        "reasons": [normalize_text(anchor.match_note)] if anchor.match_note else [],
                    }
                ]
        else:
            candidates = _build_candidates(db, document, anchor.ip_suffix_hint) if anchor.ip_suffix_hint else []
        anchor_rows.append(
            {
                "id": anchor.id,
                "anchor_text": normalize_text(anchor.anchor_text),
                "normalized_text": normalize_text(anchor.normalized_text),
                "ip_suffix_hint": anchor.ip_suffix_hint,
                "layer_name": normalize_text(anchor.layer_name),
                "entity_type": anchor.entity_type,
                "pos_x": anchor.pos_x,
                "pos_y": anchor.pos_y,
                "matched_device_id": anchor.matched_device_id,
                "matched_device_ip": normalize_text(matched_device.management_ip or matched_device.service_ip) if matched_device else "",
                "matched_device_label": normalize_text(matched_device.hostname) if matched_device else "",
                "matched_device_type": normalize_text(matched_device.device_type) if matched_device else "",
                "matched_area_display_name": normalize_text(matched_area.display_name) if matched_area else "",
                "confidence": anchor.confidence,
                "match_note": normalize_text(anchor.match_note),
                "candidate_count": len(candidates),
                "candidates": [
                    {
                        "ip": item["ip"],
                        "label": item["label"],
                        "source_type": item["source_type"],
                        "area_display_name": item["area_display_name"],
                        "score": item["score"],
                        "reasons": item["reasons"],
                    }
                    for item in candidates
                ],
            }
        )

    return {
        "document": {
            "id": document.id,
            "title": normalize_text(document.title),
            "original_filename": document.original_filename,
            "file_extension": document.file_extension,
            "parse_status": document.parse_status,
            "site": normalize_text(document.site),
            "building": normalize_text(document.building),
            "floor": normalize_text(document.floor),
            "zone": normalize_text(document.zone),
            "notes": normalize_text(document.notes),
            "parser_used": document.parser_used,
            "file_size": document.file_size,
            "extracted_text_count": document.extracted_text_count,
            "extracted_suffix_count": document.extracted_suffix_count,
            "matched_anchor_count": document.matched_anchor_count,
            "unmatched_anchor_count": max(len(anchor_rows) - document.matched_anchor_count, 0),
            "high_confidence_anchor_count": sum(1 for row in anchor_rows if float(row["confidence"] or 0.0) >= 0.9),
            "created_at": document.created_at.isoformat(),
            "updated_at": document.updated_at.isoformat(),
        },
        "layers": [{"layer_name": name, "count": count} for name, count in layer_summary.most_common()],
        "anchors": anchor_rows,
    }
