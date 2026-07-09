import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from botocore.exceptions import ClientError

from app.db import accounts_table, transactions_table
from app.models import TransactionCreate, Transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=Transaction, status_code=201)
def create_transaction(payload: TransactionCreate):
    delta = payload.amount if payload.type == "deposit" else -payload.amount

    try:
        if payload.type == "withdrawal":
            # Conditional update prevents overdraft in a single atomic call -
            # no read-then-write race condition.
            update_resp = accounts_table.update_item(
                Key={"account_id": payload.account_id},
                UpdateExpression="SET balance = balance + :delta",
                ConditionExpression="attribute_exists(account_id) AND balance >= :amount",
                ExpressionAttributeValues={":delta": delta, ":amount": payload.amount},
                ReturnValues="UPDATED_NEW",
            )
        else:
            update_resp = accounts_table.update_item(
                Key={"account_id": payload.account_id},
                UpdateExpression="SET balance = balance + :delta",
                ConditionExpression="attribute_exists(account_id)",
                ExpressionAttributeValues={":delta": delta},
                ReturnValues="UPDATED_NEW",
            )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HTTPException(
                status_code=400,
                detail="Account not found or insufficient balance",
            )
        raise

    new_balance = update_resp["Attributes"]["balance"]

    txn_item = {
        "account_id": payload.account_id,
        "transaction_id": str(uuid.uuid4()),
        "type": payload.type,
        "amount": payload.amount,
        "balance_after": new_balance,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    transactions_table.put_item(Item=txn_item)
    return txn_item


@router.get("/{account_id}", response_model=list[Transaction])
def list_transactions(account_id: str):
    resp = transactions_table.query(
        KeyConditionExpression="account_id = :aid",
        ExpressionAttributeValues={":aid": account_id},
        ScanIndexForward=False,
    )
    return resp.get("Items", [])
