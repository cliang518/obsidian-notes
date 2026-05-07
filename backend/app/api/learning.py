from fastapi import APIRouter

from app.services.platform_capabilities import learning_center_summary


router = APIRouter()


@router.get("/summary")
def summary() -> dict:
    return learning_center_summary()
