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
    status: Literal["Reserved", "Active", "Completed", "Cancelled"]


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

        # Update car status to Reserved
        conn.execute("""
            UPDATE public.cars
            SET status = 'Reserved'
            WHERE car_id = %(car)s
        """, {"car": payload.car_id})

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
                car.brand || ' ' || car.model as car_name,
                inv.inv_id,
                inv.total_amount,
                inv.payment_status
            FROM public.reservations r
            LEFT JOIN public.customers c ON r.customer_license_no = c.license_no
            LEFT JOIN public.cars car ON r.car_id = car.car_id
            LEFT JOIN public.invoices inv ON r.res_id = inv.reservation_id
            ORDER BY r.start_date DESC
        """).fetchall()

    return [dict(row) for row in rows]


@router.get("/my_reservations")
def my_reservations(authorization: Optional[str] = Header(None)):
    """Get reservations for the authenticated customer"""
    claims = verify_token(authorization)
    if not claims:
        raise HTTPException(status_code=401, detail="Not authenticated")

    license_no = claims["sub"]

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                r.res_id,
                r.car_id,
                r.start_date,
                r.end_date,
                r.status,
                car.brand || ' ' || car.model || ' ' || car.year as car_name,
                car.photo_url,
                inv.total_amount,
                inv.payment_status
            FROM public.reservations r
            LEFT JOIN public.cars car ON r.car_id = car.car_id
            LEFT JOIN public.invoices inv ON r.res_id = inv.reservation_id
            WHERE r.customer_license_no = %(license)s
            ORDER BY r.start_date DESC
        """, {"license": license_no}).fetchall()

    return [dict(row) for row in rows]


@router.put("/{reservation_id}")
def update_reservation_status(reservation_id: str, payload: ReservationStatusUpdate):
    """Update reservation status - staff only"""
    with get_conn() as conn:
        # Check if reservation exists
        row = conn.execute(
            "SELECT res_id, status, car_id FROM public.reservations WHERE res_id = %(rid)s",
            {"rid": reservation_id}
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Reservation not found")

        # Update status
        conn.execute(
            "UPDATE public.reservations SET status = %(status)s WHERE res_id = %(rid)s",
            {"status": payload.status, "rid": reservation_id}
        )

        # Update car status based on reservation status
        if payload.status == "Active":
            # Customer picked up the car
            conn.execute(
                "UPDATE public.cars SET status = 'Rented' WHERE car_id = %(car_id)s",
                {"car_id": row["car_id"]}
            )
        elif payload.status == "Completed" or payload.status == "Cancelled":
            # Customer returned the car or reservation cancelled, set back to Available
            conn.execute(
                "UPDATE public.cars SET status = 'Available' WHERE car_id = %(car_id)s",
                {"car_id": row["car_id"]}
            )
        elif payload.status == "Reserved":
            # Reservation created, mark car as Reserved
            conn.execute(
                "UPDATE public.cars SET status = 'Reserved' WHERE car_id = %(car_id)s",
                {"car_id": row["car_id"]}
            )

    return {"ok": True, "message": f"Reservation status updated to {payload.status}"}


@router.post("/auto_update_statuses")
def auto_update_expired_reservations():
    """Automatically update expired reservations based on payment status"""
    with get_conn() as conn:
        # Find all Active reservations where end_date < today with their payment status
        expired = conn.execute("""
            SELECT r.res_id, r.car_id, COALESCE(inv.payment_status, 'unpaid') as payment_status
            FROM public.reservations r
            LEFT JOIN public.invoices inv ON r.res_id = inv.reservation_id
            WHERE r.status = 'Active'
              AND r.end_date < CURRENT_DATE
        """).fetchall()

        updated_count = 0
        for reservation in expired:
            # Determine new status based on payment
            if reservation["payment_status"] == "paid":
                new_status = "Completed"
            else:
                new_status = "Cancelled"

            # Update reservation status
            conn.execute(
                "UPDATE public.reservations SET status = %(status)s WHERE res_id = %(rid)s",
                {"status": new_status, "rid": reservation["res_id"]}
            )
            # Set car back to Available
            conn.execute(
                "UPDATE public.cars SET status = 'Available' WHERE car_id = %(car_id)s",
                {"car_id": reservation["car_id"]}
            )
            updated_count += 1

    return {"ok": True, "updated": updated_count, "message": f"Updated {updated_count} expired reservation(s)"}
