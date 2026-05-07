from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.floor_plan import FloorPlanDocument
from app.services.cad_import import (
    floor_plan_detail,
    list_floor_plan_documents,
    parse_floor_plan_document,
    upload_and_parse_floor_plan,
)
from app.services.text_normalize import normalize_text


router = APIRouter()


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    docs = list_floor_plan_documents(db)
    return {
        "document_count": len(docs),
        "parsed_count": sum(1 for row in docs if row.parse_status == "parsed"),
        "matched_count": sum(row.matched_anchor_count for row in docs),
        "formats": sorted({row.file_extension for row in docs if row.file_extension}),
        "recent_documents": [
            {
                "id": row.id,
                "title": normalize_text(row.title),
                "floor": normalize_text(row.floor),
                "zone": normalize_text(row.zone),
                "parse_status": row.parse_status,
                "matched_anchor_count": row.matched_anchor_count,
            }
            for row in docs[:8]
        ],
    }


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)) -> list[dict]:
    rows = list_floor_plan_documents(db)
    return [
        {
            "id": row.id,
            "title": normalize_text(row.title),
            "original_filename": row.original_filename,
            "file_extension": row.file_extension,
            "parse_status": row.parse_status,
            "site": normalize_text(row.site),
            "building": normalize_text(row.building),
            "floor": normalize_text(row.floor),
            "zone": normalize_text(row.zone),
            "parser_used": row.parser_used,
            "file_size": row.file_size,
            "extracted_text_count": row.extracted_text_count,
            "extracted_suffix_count": row.extracted_suffix_count,
            "matched_anchor_count": row.matched_anchor_count,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    site: str = Form(default=""),
    building: str = Form(default=""),
    floor: str = Form(default=""),
    zone: str = Form(default=""),
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
) -> dict:
    try:
        document = upload_and_parse_floor_plan(
            db,
            file,
            title=title,
            site=site,
            building=building,
            floor=floor,
            zone=zone,
            notes=notes,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return floor_plan_detail(db, document.id)


@router.post("/documents/{document_id}/reparse")
def reparse_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    if db.get(FloorPlanDocument, document_id) is None:
        raise HTTPException(status_code=404, detail="floor_plan_not_found")
    try:
        document = parse_floor_plan_document(db, document_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return floor_plan_detail(db, document.id)


@router.get("/documents/{document_id}")
def get_document_detail(document_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return floor_plan_detail(db, document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="floor_plan_not_found")
