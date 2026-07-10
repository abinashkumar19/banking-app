"""Payments microservice - generic CRUD against its own DynamoDB table."""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.aws_clients import table

SERVICE_NAME = "payments"
app = FastAPI(title="VeeraBank Payments Service", version="1.0.0")
router = APIRouter(prefix="/payments")
tbl = table(SERVICE_NAME)


class Item(BaseModel):
    class Config:
        extra = "allow"  # each service's shape can vary; keep this generic


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/")
def root():
    return {"service": "payments-service", "status": "running"}


@router.post("/items")
def create_item(item: Item):
    data: Dict[str, Any] = item.dict()
    data["id"] = str(uuid.uuid4())
    data["created_at"] = datetime.now(timezone.utc).isoformat()
    tbl.put_item(Item=data)
    return data


@router.get("/items", response_model=List[Dict[str, Any]])
def list_items():
    resp = tbl.scan()
    return resp.get("Items", [])


@router.get("/items/{item_id}")
def get_item(item_id: str):
    resp = tbl.get_item(Key={"id": item_id})
    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Payments item not found")
    return item


@router.delete("/items/{item_id}")
def delete_item(item_id: str):
    tbl.delete_item(Key={"id": item_id})
    return {"deleted": item_id}


app.include_router(router)
