from fastapi import FastAPI
from app.routers import accounts, transactions

app = FastAPI(title="VeeraBank API", version="1.0.0")

app.include_router(accounts.router)
app.include_router(transactions.router)


@app.get("/healthz")
def healthz():
    """Used by the Kubernetes liveness/readiness probes."""
    return {"status": "ok"}


@app.get("/")
def root():
    return {"service": "veerabank-backend", "status": "running"}
