# routers/auth.py
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, EmailStr, Field
from passlib.hash import bcrypt_sha256, bcrypt
import jwt
import os

from db import get_conn

router = APIRouter(prefix="/auth", tags=["auth"])

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRES_MIN = int(os.getenv("JWT_EXPIRES_MIN", "120"))

# ----------------- helpers -----------------
def verify_any(plain: str, stored: str) -> bool:
    if not stored:
        return False
    if bcrypt_sha256.identify(stored):
        return bcrypt_sha256.verify(plain, stored)
    if bcrypt.identify(stored):
        return bcrypt.verify(plain, stored)
    return False

def make_token(sub: str, email: str) -> str:
    """sub = customers.license_no OR employees.emp_id"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXPIRES_MIN)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_token(auth_header: Optional[str]) -> Optional[dict]:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None

def _norm_license(s: str) -> str:
    # remove spaces/dashes and uppercase
    return "".join(ch for ch in str(s).strip() if ch.isalnum()).upper()

# ----------------- models -----------------
class StaffLoginIn(BaseModel):
    email: EmailStr
    password: str
    role: Literal["employee", "admin"]

class SignUpIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name:  str = Field(min_length=1, max_length=100)
    email:      EmailStr
    phone:      Optional[str] = None
    license_no: str
    license_expiry: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_of_birth:  str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    password:   str = Field(min_length=6, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ResetByLicenseIn(BaseModel):
    email: EmailStr
    license_no: str
    new_password: str = Field(min_length=6, max_length=128)

# ----------------- staff auth -----------------
@router.post("/staff_login")
def staff_login(payload: StaffLoginIn):
    email = payload.email.strip().lower()
    role  = payload.role.strip().lower()

    with get_conn() as conn:
        row = conn.execute("""
            select emp_id, email, lower(role) as role,
                   coalesce(password_hash,'') as password_hash,
                   first_name, last_name
            from public.employees
            where lower(email) = %(e)s
              and lower(role)  = %(r)s
            limit 1
        """, {"e": email, "r": role}).fetchone()

    if (not row) or (not verify_any(payload.password, row["password_hash"])):
        raise HTTPException(status_code=401, detail="Invalid credentials or role")

    token = make_token(row["emp_id"], row["email"])  # sub = EMP-#
    return {
        "token": token,
        "employee": {
            "id": row["emp_id"],
            "email": row["email"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "role": row["role"],
        },
    }

# ----------------- customer auth -----------------
@router.post("/signup")
def signup(payload: SignUpIn):
    # parse/validate dates
    try:
        dob = date.fromisoformat(payload.date_of_birth)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date_of_birth format (YYYY-MM-DD).")

    try:
        lic_exp = date.fromisoformat(payload.license_expiry)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid license_expiry format (YYYY-MM-DD).")

    today = date.today()
    # age >= 17
    age = (today.year - dob.year) - ( (today.month, today.day) < (dob.month, dob.day) )
    if age < 17:
        raise HTTPException(status_code=400, detail="You must be at least 17 years old to sign up.")
    # license must be future
    if lic_exp <= today:
        raise HTTPException(status_code=400, detail="License expiry must be a future date.")

    with get_conn() as conn:
        # unique email
        exists = conn.execute("select 1 from public.customers where lower(email)=%(e)s",
                              {"e": payload.email.lower()}).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="Email already registered")

        # optional: unique license_no too (DB has PK, this just gives friendlier error)
        lic_exists = conn.execute("select 1 from public.customers where license_no=%(l)s",
                                  {"l": payload.license_no}).fetchone()
        if lic_exists:
            raise HTTPException(status_code=409, detail="License number already registered")

        pwd_hash = bcrypt_sha256.hash(payload.password)
        row = conn.execute("""
          insert into public.customers (
            license_no, first_name, last_name, email, phone,
            license_expiry, date_of_birth, address_street, address_city, password_hash
          ) values (
            %(lic)s, %(fn)s, %(ln)s, %(em)s, %(ph)s,
            %(lex)s, %(dob)s, null, null, %(phash)s
          )
          returning license_no, first_name, last_name, email
        """, {
          "lic": payload.license_no,
          "fn":  payload.first_name,
          "ln":  payload.last_name,
          "em":  payload.email,
          "ph":  payload.phone,
          "lex": payload.license_expiry,
          "dob": payload.date_of_birth,
          "phash": pwd_hash
        }).fetchone()

    token = make_token(row["license_no"], row["email"])  # sub = license_no
    return {"token": token, "customer": row}

@router.post("/login")
def login(payload: LoginIn):
    with get_conn() as conn:
        user = conn.execute("""
            select license_no, email, coalesce(password_hash,'') as password_hash,
                   first_name, last_name
            from public.customers
            where lower(email) = %(e)s
            limit 1
        """, {"e": payload.email.lower()}).fetchone()

    if (not user) or (not user["password_hash"]) or (not bcrypt_sha256.verify(payload.password, user["password_hash"])):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = make_token(user["license_no"], user["email"])  # sub = license_no
    return {
        "token": token,
        "customer": {
            "license_no": user["license_no"],
            "email": user["email"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
        },
    }

@router.post("/reset_by_license")
def reset_by_license(payload: ResetByLicenseIn):
    email = payload.email.strip().lower()
    lic_in = _norm_license(payload.license_no)

    with get_conn() as conn:
        row = conn.execute("""
            select license_no, email
            from public.customers
            where lower(email) = %(e)s
            limit 1
        """, {"e": email}).fetchone()

        if not row or _norm_license(row["license_no"]) != lic_in:
            raise HTTPException(status_code=401, detail="Invalid email or license number")

        new_hash = bcrypt_sha256.hash(payload.new_password)
        conn.execute("""
            update public.customers
               set password_hash = %(h)s
             where license_no = %(lic)s
        """, {"h": new_hash, "lic": row["license_no"]})

    return {"ok": True, "message": "Password has been reset"}

@router.get("/me")
def me(authorization: Optional[str] = Header(None)):
    claims = verify_token(authorization)
    if not claims:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"sub": claims["sub"], "email": claims["email"]}

@router.post("/logout")
def logout():
    # stateless JWT: frontend just deletes its token
    return {"ok": True}
