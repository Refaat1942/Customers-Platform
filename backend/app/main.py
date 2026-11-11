from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .api.pos import router as pos_router
from .api.routes import cleanup_stale_uploads, router
from .auth import ensure_admin_exists


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    ensure_admin_exists()
    cleanup_stale_uploads()
    # imports interrupted by a restart can never finish
    db.cursor().execute("UPDATE imports SET status='failed', message='Interrupted by a server "
                        "restart, please import the file again' WHERE status='running'")
    yield
    db.close()


app = FastAPI(title="Customers Platform", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json")
app.include_router(router)
app.include_router(pos_router)


@app.middleware("http")
async def gunzip_requests(request, call_next):
    """POS backfills may send gzip-compressed JSON (Content-Encoding: gzip) - 5-10x smaller."""
    if request.headers.get("content-encoding", "").lower() == "gzip" and \
            request.url.path.startswith("/api/v1/pos/"):
        import gzip
        body = gzip.decompress(await request.body())
        if len(body) > 200 * 1024 * 1024:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        request._body = body
        request.scope["headers"] = [(k, v) for k, v in request.scope["headers"]
                                    if k not in (b"content-encoding", b"content-length")] + \
            [(b"content-length", str(len(body)).encode())]
    return await call_next(request)


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
