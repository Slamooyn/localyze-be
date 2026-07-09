from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, RegisterRequest
from app.services import security

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_payload(user: User) -> dict:
    return {
        "token": security.create_token(user.id),
        "user": {"id": str(user.id), "name": user.name, "email": user.email},
    }


@router.post("/register", status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    email = req.email.lower()
    exists = db.scalar(select(User).where(User.email == email))
    if exists is not None:
        raise HTTPException(
            409, detail={"code": "EMAIL_TAKEN", "message": "Email sudah terdaftar"}
        )
    user = User(name=req.name, email=email, password_hash=security.hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _auth_payload(user)


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)) -> dict:
    email = req.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not security.verify_password(req.password, user.password_hash):
        raise HTTPException(
            401, detail={"code": "INVALID_CREDENTIALS", "message": "Email atau password salah"}
        )
    return _auth_payload(user)


@router.get("/me")
def me(user: User = Depends(security.get_current_user)) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "created_at": user.created_at.isoformat(),
    }
