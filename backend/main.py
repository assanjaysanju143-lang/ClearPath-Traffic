from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import traffic, directions, incidents
from config import get_settings
import os
import uvicorn

settings = get_settings()

app = FastAPI(
    title="Traffic Route API",
    description="Smart traffic ratio detection and least-congestion route suggestion API",
    version="1.0.0"
)

# ALLOWED_ORIGINS env var: comma-separated list of frontend URLs allowed to call
# this API (e.g. "https://clearpath.vercel.app,http://localhost:3000").
# Defaults to "*" for easy local dev / demoing. No cookies/credentials are used,
# so a wildcard origin is safe here (and required — CORS forbids combining a
# wildcard origin with allow_credentials=True).
_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allowed_origins = ["*"] if _origins_env.strip() == "*" else [o.strip() for o in _origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(traffic.router, prefix="/api/traffic", tags=["Traffic"])
app.include_router(directions.router, prefix="/api/routes", tags=["Routes"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["Incidents"])

@app.get("/")
def root():
    return {"message": "Traffic Route API is running", "docs": "/docs"}

if __name__ == "__main__":
    # PORT is set by most hosts (Render, Railway) at deploy time; falls back to
    # 8000 for local dev. reload=True is dev-only — auto-reload has no place in
    # a production process and just wastes memory watching files that won't change.
    port = int(os.environ.get("PORT", 8000))
    is_prod = settings.APP_ENV == "production"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=not is_prod)
