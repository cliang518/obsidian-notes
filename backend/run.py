from pathlib import Path

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8011,
        reload=False,
        app_dir=str(Path(__file__).resolve().parent),
        access_log=False,
        use_colors=False,
    )
