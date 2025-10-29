from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from db import get_conn
from datetime import date

router = APIRouter(prefix="/rentals", tags=["rentals"])

class StartIn(BaseModel):
    reservation_id: str = Field(pattern=r"^RES-\d+$")  # e.g. RES-3

class CloseIn(BaseModel):
    reservation_id: str = Field(pattern=r"^RES-\d+$")
    damage_fee: float = 0
    refuel_fee: float = 0


@router.post("/start")
def start_rental(payload: StartIn):
    rid = payload.reservation_id
    with get_conn() as conn:
        row = conn.execute("""
            SELECT r.res_id, r.status, r.car_id, c.status AS car_status
            FROM public.reservations r
            JOIN public.cars c ON c.car_id = r.car_id
            WHERE r.res_id = %(rid)s
            FOR UPDATE
        """, {"rid": rid}).fetchone()

        if not row:
            raise HTTPException(404, "Reservation not found")
        if row["status"] != "Reserved":
            raise HTTPException(400, "Reservation is not in 'Reserved' state")
        if row["car_status"] not in ("Available","Reserved"):
            raise HTTPException(400, f"Car is not available (status={row['car_status']})")

        # flip reservation -> Active, car -> Rented
        conn.execute("UPDATE public.reservations SET status='Active' WHERE res_id=%(rid)s", {"rid": rid})
        conn.execute("UPDATE public.cars SET status='Rented' WHERE car_id=%(cid)s", {"cid": row["car_id"]})

        # ensure invoice exists for this reservation
        inv = conn.execute("SELECT inv_id FROM public.invoices WHERE reservation_id=%(rid)s", {"rid": rid}).fetchone()
        if not inv:
            conn.execute("""
                INSERT INTO public.invoices (reservation_id, issue_date, total_amount, payment_status)
                VALUES (%(rid)s, CURRENT_DATE, 0, 'unpaid')
            """, {"rid": rid})

    return {"ok": True, "message": "Rental started"}


@router.post("/close")
def close_rental(payload: CloseIn):
    rid = payload.reservation_id
    dmg = float(payload.damage_fee or 0)
    ref = float(payload.refuel_fee or 0)

    with get_conn() as conn:
        row = conn.execute("""
            SELECT r.res_id, r.status, r.car_id, r.start_date, r.end_date,
                   c.status AS car_status, c.price_per_day
            FROM public.reservations r
            JOIN public.cars c ON c.car_id = r.car_id
            WHERE r.res_id = %(rid)s
            FOR UPDATE
        """, {"rid": rid}).fetchone()

        if not row:
            raise HTTPException(404, "Reservation not found")
        if row["status"] != "Active":
            raise HTTPException(400, "Reservation is not in 'Active' state")

        # compute total
        start_d: date = row["start_date"]
        end_d: date   = row["end_date"]
        days = max((end_d - start_d).days, 1)
        base = float(row["price_per_day"] or 0) * days
        total = base + dmg + ref

        # flip reservation -> Completed, car -> Available
        conn.execute("UPDATE public.reservations SET status='Completed' WHERE res_id=%(rid)s", {"rid": rid})
        conn.execute("UPDATE public.cars SET status='Available' WHERE car_id=%(cid)s", {"cid": row["car_id"]})

        # update/create invoice
        inv = conn.execute("SELECT inv_id FROM public.invoices WHERE reservation_id=%(rid)s", {"rid": rid}).fetchone()
        if inv:
            conn.execute("""
              UPDATE public.invoices
                 SET total_amount = %(t)s,
                     payment_status = CASE
                       WHEN %(t)s <= COALESCE((SELECT SUM(amount) FROM public.payments WHERE invoice_id = %(iid)s), 0)
                         THEN 'paid'::payment_status
                       ELSE 'unpaid'::payment_status
                     END
               WHERE inv_id = %(iid)s
            """, {"t": total, "iid": inv["inv_id"]})
        else:
            conn.execute("""
              INSERT INTO public.invoices (reservation_id, issue_date, total_amount, payment_status)
              VALUES (%(rid)s, CURRENT_DATE, %(t)s, 'unpaid')
            """, {"rid": rid, "t": total})

    return {"ok": True, "message": "Rental closed", "total": total}
