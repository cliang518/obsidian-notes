from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


router = APIRouter()

DOCS_ROOT = Path(__file__).resolve().parents[3] / "docs"
DOC_CATALOG = [
    {
        "slug": "system-user-guide",
        "title": "系统使用说明",
        "filename": "system-user-guide.md",
        "summary": "面向现场值班、维修和管理人员的完整使用说明。",
    },
    {
        "slug": "data-initialization-guide",
        "title": "数据初始化指南",
        "filename": "data-initialization-guide.md",
        "summary": "说明系统刚安装时如何初始化数据库和真实业务数据。",
    },
    {
        "slug": "first-launch-import-checklist",
        "title": "首次上线导入清单",
        "filename": "first-launch-import-checklist.md",
        "summary": "按顺序完成首次导入，适合现场按步骤执行。",
    },
    {
        "slug": "screenshot-collection-checklist",
        "title": "截图采集清单",
        "filename": "screenshot-collection-checklist.md",
        "summary": "帮助你补齐说明书截图素材。",
    },
    {
        "slug": "dev-runbook",
        "title": "运行手册",
        "filename": "dev-runbook.md",
        "summary": "开发、发布、安装、备份和冒烟测试入口说明。",
    },
]


@router.get("")
def list_docs() -> dict:
    items = []
    for item in DOC_CATALOG:
      path = DOCS_ROOT / item["filename"]
      items.append(
          {
              "slug": item["slug"],
              "title": item["title"],
              "summary": item["summary"],
              "filename": item["filename"],
              "exists": path.exists(),
              "url": f"/api/docs/{item['slug']}",
          }
      )
    return {"items": items}


@router.get("/{slug}")
def get_doc(slug: str):
    item = next((row for row in DOC_CATALOG if row["slug"] == slug), None)
    if not item:
        raise HTTPException(status_code=404, detail="doc_not_found")

    path = DOCS_ROOT / item["filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="doc_file_missing")

    return FileResponse(
        path=path,
        media_type="text/markdown; charset=utf-8",
        filename=item["filename"],
    )
