import uuid
from decimal import Decimal
from typing import Literal, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from botocore.exceptions import ClientError

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.aws_clients import table

app = FastAPI(title="VeeraBank Accounts Service", version="1.0.0")
accounts_table = table("accounts")


class AccountCreate(BaseModel):
    owner_name: str
    account_type: Literal["savings", "current"] = "savings"
    opening_balance: Decimal = Decimal("0")


class Account(BaseModel):
    account_id: str
    owner_name: str
    account_type: str
    balance: Decimal


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"service": "accounts-service", "status": "running"}


@app.post("/accounts", response_model=Account, status_code=201)
def create_account(payload: AccountCreate):
    account_id = str(uuid.uuid4())
    item = {
        "account_id": account_id,
        "owner_name": payload.owner_name,
        "account_type": payload.account_type,
        "balance": payload.opening_balance,
    }
    accounts_table.put_item(Item=item)
    return item


@app.get("/accounts/{account_id}", response_model=Account)
def get_account(account_id: str):
    resp = accounts_table.get_item(Key={"account_id": account_id})
    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Account not found")
    return item


@app.get("/accounts", response_model=List[Account])
def list_accounts():
    resp = accounts_table.scan()
    return resp.get("Items", [])


@app.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: str):
    try:
        accounts_table.delete_item(
            Key={"account_id": account_id},
            ConditionExpression="attribute_exists(account_id)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HTTPException(status_code=404, detail="Account not found")
        raise
