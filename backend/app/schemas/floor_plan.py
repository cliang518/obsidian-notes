from pydantic import BaseModel


class FloorPlanDocumentOut(BaseModel):
    id: int
    title: str
    original_filename: str
    file_extension: str
    parse_status: str
    site: str
    building: str
    floor: str
    zone: str
    parser_used: str
    file_size: int
    extracted_text_count: int
    extracted_suffix_count: int
    matched_anchor_count: int
    created_at: str
    updated_at: str


class FloorPlanCandidateOut(BaseModel):
    ip: str
    label: str
    source_type: str
    area_display_name: str
    score: int
    reasons: list[str]


class FloorPlanAnchorOut(BaseModel):
    id: int
    anchor_text: str
    normalized_text: str
    ip_suffix_hint: str
    layer_name: str
    entity_type: str
    pos_x: float | None = None
    pos_y: float | None = None
    matched_device_id: int | None = None
    confidence: float = 0.0
    match_note: str = ""
    candidates: list[FloorPlanCandidateOut] = []
