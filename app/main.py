from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.db.session import Session
from app.llm.gateway import DbCache, build_default_gateway


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.sm = Session
    app.state.gw = build_default_gateway(DbCache(Session))
    yield


app = FastAPI(title="Agentic Dating", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if _dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        """Single-page app: any non-API path serves index.html (client-side routing)."""
        f = _dist / path
        return FileResponse(f if path and f.is_file() else _dist / "index.html")
