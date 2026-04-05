from __future__ import annotations
import hashlib, uuid, secrets
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from api.db import supabase_query

router = APIRouter(prefix="/api/auth", tags=["auth"])

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token() -> str:
    return secrets.token_hex(32)

class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    student_id: str
    email: str
    name: str
    token: str

@router.post("/register", response_model=AuthResponse)
async def register(body: RegisterRequest):
    existing = await supabase_query("students", params={"email": f"eq.{body.email}", "select": "id"})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered. Please login instead.")
    student_id = str(uuid.uuid4())
    token = generate_token()
    await supabase_query("students", method="POST", json={
        "id": student_id, "email": body.email, "name": body.name,
        "password_hash": hash_password(body.password), "auth_token": token,
    })
    return AuthResponse(student_id=student_id, email=body.email, name=body.name, token=token)

@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    students = await supabase_query("students", params={"email": f"eq.{body.email}", "select": "id,email,name,password_hash"})
    if not students:
        raise HTTPException(status_code=401, detail="No account found with this email.")
    student = students[0]
    if student.get("password_hash") != hash_password(body.password):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    token = generate_token()
    await supabase_query(f"students?id=eq.{student['id']}", method="PATCH", json={"auth_token": token})
    return AuthResponse(student_id=student["id"], email=student["email"], name=student["name"], token=token)

@router.get("/me")
async def get_me(token: str):
    students = await supabase_query("students", params={"auth_token": f"eq.{token}", "select": "id,email,name"})
    if not students:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return students[0]
