from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes
from app.core.config import settings

app = FastAPI(
    title="ContractSense API",
    description="AI-powered contract analysis",
    version="0.1.0",
)

# CORS allows your Next.js frontend (running on localhost:3000)
# to talk to this API (running on localhost:8000)
# Without this, browsers block cross-origin requests.
# Configure other origins via the CORS_ORIGINS env var.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}