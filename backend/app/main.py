from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .api.routes import router
from .auth import ensure_admin_exists


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    ensure_admin_exists()
    yield
    db.close()


app = FastAPI(title="Customers Platform", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json")
app.include_router(router)


@app.get("/api/health")
def health():
    return {"ok": True}


# ---- serve the built React app (frontend/dist) with SPA fallback ----
if (config.FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = (config.FRONTEND_DIST / path).resolve()
        if path and f.is_file() and config.FRONTEND_DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(config.FRONTEND_DIST / "index.html")
