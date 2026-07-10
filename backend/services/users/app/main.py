"""Users microservice - registration/login + first-time-registration
SNS notification. This is the entry point new customers hit first."""
import hashlib
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.aws_clients import table, sns_publish

app = FastAPI(title="VeeraBank Users Service", version="1.0.0")
router = APIRouter(prefix="/users")
users_table = table("users")

SNS_TOPIC_ENV = "USER_REGISTERED_TOPIC_ARN"


class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    password: str


def _hash_password(password: str) -> str:
    # Simple salted hash for demo purposes. Swap for bcrypt/argon2
    # before this ever handles real customer data.
    salt = os.getenv("PASSWORD_SALT", "veerabank-dev-salt")
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/")
def root():
    return {"service": "users-service", "status": "running"}


@router.post("/register")
def register(req: RegisterRequest):
    # Email is the natural unique key here.
    existing = users_table.get_item(Key={"email": req.email}).get("Item")
    if existing:
        raise HTTPException(status_code=409, detail="User already registered")

    user = {
        "email": req.email,
        "user_id": str(uuid.uuid4()),
        "full_name": req.full_name,
        "phone": req.phone,
        "password_hash": _hash_password(req.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    users_table.put_item(Item=user)

    # First-time registration -> notify via SNS (fans out to
    # email/SMS subscribers on the topic - see terraform/sns.tf).
    sns_publish(
        SNS_TOPIC_ENV,
        subject="Welcome to VeeraBank!",
        message=(
            f"New user registered: {req.full_name} ({req.email}, {req.phone}). "
            f"user_id={user['user_id']}"
        ),
    )

    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "full_name": user["full_name"],
    }


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
def login(req: LoginRequest):
    user = users_table.get_item(Key={"email": req.email}).get("Item")
    if not user or user["password_hash"] != _hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"user_id": user["user_id"], "email": user["email"], "full_name": user["full_name"]}


@router.get("/{user_id}")
def get_user(user_id: str):
    # user_id isn't the table key (email is), so scan+filter.
    # Fine at this scale; swap for a GSI on user_id if this table grows large.
    resp = users_table.scan(
        FilterExpression="user_id = :uid",
        ExpressionAttributeValues={":uid": user_id},
    )
    items = resp.get("Items", [])
    if not items:
        raise HTTPException(status_code=404, detail="User not found")
    user = items[0]
    return {"user_id": user["user_id"], "email": user["email"], "full_name": user["full_name"]}


app.include_router(router)
