"""Cheques microservice - issue a cheque (no funds move yet, like a real
cheque), then clear it later (funds actually debit at that point - if
the balance isn't there, the cheque bounces instead of the request
failing)."""
import os
import sys
from decimal import Decimal
from typing import List

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, field_validator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.aws_clients import table
from common.service_base import adjust_balance, get_account_or_404, new_id, now_iso, write_audit_log

app = FastAPI(title="VeeraBank Cheques Service", version="2.0.0")
router = APIRouter(prefix="/cheques")
tbl = table("cheques")


class ChequeIssue(BaseModel):
    user_id: str
    account_id: str
    payee_name: str
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def _positive(cls, v):
        if v <= 0:
            raise ValueError("amount must be greater than zero")
        return v


def _cheque_number() -> str:
    import random
    return "".join(str(random.randint(0, 9)) for _ in range(6))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/")
def root():
    return {"service": "cheques-service", "status": "running"}


@router.post("/issue", status_code=201)
def issue(payload: ChequeIssue):
    account = get_account_or_404(payload.account_id)
    if account["user_id"] != payload.user_id:
        raise HTTPException(status_code=403, detail="You can only issue cheques from your own account")

    item = {
        "id": new_id(),
        "user_id": payload.user_id,
        "account_id": payload.account_id,
        "cheque_number": _cheque_number(),
        "payee_name": payload.payee_name,
        "amount": payload.amount,
        "status": "issued",
        "created_at": now_iso(),
    }
    tbl.put_item(Item=item)
    write_audit_log(payload.user_id, "cheque_issued", {"cheque_id": item["id"], "payee": payload.payee_name})
    return item


@router.get("/user/{user_id}", response_model=List[dict])
def list_for_user(user_id: str):
    resp = tbl.query(IndexName="user_id-index", KeyConditionExpression="user_id = :u", ExpressionAttributeValues={":u": user_id})
    return sorted(resp.get("Items", []), key=lambda i: i.get("created_at", ""), reverse=True)


@router.get("/{cheque_id}")
def get_cheque(cheque_id: str):
    resp = tbl.get_item(Key={"id": cheque_id})
    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Cheque not found")
    return item


@router.patch("/{cheque_id}/clear")
def clear(cheque_id: str):
    resp = tbl.get_item(Key={"id": cheque_id})
    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Cheque not found")
    if item["status"] != "issued":
        raise HTTPException(status_code=400, detail=f"Cheque is already {item['status']}")

    try:
        adjust_balance(item["account_id"], -Decimal(item["amount"]))
        new_status = "cleared"
    except HTTPException as e:
        if e.status_code != 402:
            raise
        new_status = "bounced"

    tbl.update_item(Key={"id": cheque_id}, UpdateExpression="SET #s = :s", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":s": new_status})
    write_audit_log(item["user_id"], "cheque_" + new_status, {"cheque_id": cheque_id})
    return {**item, "status": new_status}


app.include_router(router)
