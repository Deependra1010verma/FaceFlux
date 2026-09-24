"""
FaceFlux Backend — FastAPI entry point.

Local dev:  python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
Railway:    Procfile / railway.json handles this automatically
"""

import os
import uvicorn
from app.main import create_app

app = create_app()

if __name__ == "__main__":
    # Railway/Render inject PORT env var; local defaults to 8000
    # HOST: 127.0.0.1 for local-only, 0.0.0.0 for cloud deployment
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    reload = os.environ.get("RELOAD", "false").lower() == "true"

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
