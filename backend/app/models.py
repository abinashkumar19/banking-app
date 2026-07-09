from pydantic import BaseModel, Field
from typing import Literal
from decimal import Decimal


class AccountCreate(BaseModel):
    owner_name: str
    account_type: Literal["savings", "current"] = "savings"
    opening_balance: Decimal = Decimal("0")


class Account(BaseModel):
    account_id: str
    owner_name: str
    account_type: str
    balance: Decimal


class TransactionCreate(BaseModel):
    account_id: str
    type: Literal["deposit", "withdrawal"]
    amount: Decimal = Field(gt=0)


class Transaction(BaseModel):
    account_id: str
    transaction_id: str
    type: str
    amount: Decimal
    balance_after: Decimal
    created_at: str
