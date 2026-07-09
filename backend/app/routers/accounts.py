import uuid
from fastapi import APIRouter, HTTPException
from botocore.exceptions import ClientError

from app.db import accounts_table
from app.models import AccountCreate, Account

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=Account, status_code=201)
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


@router.get("/{account_id}", response_model=Account)
def get_account(account_id: str):
    resp = accounts_table.get_item(Key={"account_id": account_id})
    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Account not found")
    return item


@router.get("", response_model=list[Account])
def list_accounts():
    resp = accounts_table.scan()
    return resp.get("Items", [])


@router.delete("/{account_id}", status_code=204)
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
