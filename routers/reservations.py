from datetime import date
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, field_validator
from db import get_conn
from routers.auth import verify_token  # your updated auth should put license_no in sub

router = APIRouter(prefix="/reservations", tags=["reservations"])

class ReserveAuthedIn(BaseModel):
    car_id: str                   # e.g. CAR-12
    start_date: date
    end_date: date

    @field_validator("start_date")
    @classmethod
    def start_not_in_past(cls, v: date):
        if v < date.today():
            raise ValueError("start_date cannot be in the past")
        return v

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info):
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date must be after start_date")
        return v


class ReservationStatusUpdate(BaseModel):
    status: Literal["Reserved", "Active", "Completed"]


def _calc_total(conn, car_id: str, start: date, end: date) -> float:
    days = (end - start).days
    if days < 1:
        raise HTTPException(status_code=400, detail="Minimum rental is 1 day")
    car = conn.execute(
        "SELECT price_per_day FROM public.cars WHERE car_id=%(id)s",
        {"id": car_id}
    ).fetchone()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    return days * float(car["price_per_day"])


@router.post("/create_auth")
def create_reservation_authed(payload: ReserveAuthedIn,
                              authorization: Optional[str] = Header(None)):
    # 1) who is the customer?  (JWT sub should be license_no now)
    claims = verify_token(authorization)
    if not claims:
        raise HTTPException(status_code=401, detail="Not authenticated")
    license_no = claims["sub"]

    # 2) Check availability & create reservation + invoice
    with get_conn() as conn:
        # overlap check on active/reserved
        clash = conn.execute("""
            SELECT 1
            FROM public.reservations
            WHERE car_id = %(car)s
              AND status IN ('Reserved','Active')
              AND NOT (%(end)s <= start_date OR %(start)s >= end_date)
            LIMIT 1
        """, {"car": payload.car_id, "start": payload.start_date, "end": payload.end_date}).fetchone()
        if clash:
            raise HTTPException(status_code=409, detail="Car not available for selected dates")

        total = _calc_total(conn, payload.car_id, payload.start_date, payload.end_date)

        res = conn.execute("""
            INSERT INTO public.reservations (
              customer_license_no, car_id, start_date, end_date, status
            ) VALUES (
              %(cust)s, %(car)s, %(start)s, %(end)s, 'Reserved'
            )
            RETURNING res_id
        """, {
            "cust": license_no,
            "car": payload.car_id,
            "start": payload.start_date,
            "end": payload.end_date
        }).fetchone()

        inv = conn.execute("""
            INSERT INTO public.invoices (reservation_id, total_amount, payment_status)
            VALUES (%(rid)s, %(total)s, 'unpaid')
            RETURNING inv_id, total_amount
        """, {"rid": res["res_id"], "total": total}).fetchone()

    return {"reservation_id": res["res_id"], "invoice_id": inv["inv_id"], "total_amount": float(inv["total_amount"])}


@router.get("")
def list_reservations():
    """List all reservations with customer and car details"""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                r.res_id,
                r.customer_license_no,
                r.car_id,
                r.start_date,
                r.end_date,
                r.status,
                c.first_name || ' ' || c.last_name as customer_name,
                c.email as customer_email,
                car.brand || ' ' || car.model as car_name
            FROM public.reservations r
            LEFT JOIN public.customers c ON r.customer_license_no = c.license_no
            LEFT JOIN public.cars car ON r.car_id = car.car_id
            ORDER BY r.start_date DESC
        """).fetchall()

    return [dict(row) for row in rows]


@router.put("/{reservation_id}")
def update_reservation_status(reservation_id: str, payload: ReservationStatusUpdate):
    """Update reservation status - staff only"""
    with get_conn() as conn:
        # Check if reservation exists
        row = conn.execute(
            "SELECT res_id, status FROM public.reservations WHERE res_id = %(rid)s",
            {"rid": reservation_id}
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Reservation not found")

        # Update status
        conn.execute(
            "UPDATE public.reservations SET status = %(status)s WHERE res_id = %(rid)s",
            {"status": payload.status, "rid": reservation_id}
        )

    return {"ok": True, "message": f"Reservation status updated to {payload.status}"}
