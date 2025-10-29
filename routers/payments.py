from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional
from db import get_conn

router = APIRouter(prefix="/payments", tags=["payments"])

class PayIn(BaseModel):
    invoice_id: str = Field(pattern=r"^INV-\d+$")
    method: str = Field(pattern=r"^(cash|card|transfer)$")
    amount: float = Field(gt=0)
    reference: Optional[str] = None  # Optional transaction reference

@router.post("/pay")
def record_payment(payload: PayIn, authorization: Optional[str] = Header(None)):
    iid = payload.invoice_id
    amt = float(payload.amount)
    method = payload.method
    reference = payload.reference

    with get_conn() as conn:
        # Lock the invoice row to avoid race conditions
        inv = conn.execute("""
            SELECT inv_id, total_amount, payment_status
            FROM public.invoices
            WHERE inv_id = %(iid)s
            FOR UPDATE
        """, {"iid": iid}).fetchone()

        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # Insert payment
        conn.execute("""
            INSERT INTO public.payments (invoice_id, method, amount, reference)
            VALUES (%(iid)s, %(m)s, %(a)s, %(ref)s)
        """, {"iid": iid, "m": method, "a": amt, "ref": reference})

        # Recalculate total paid
        paid = conn.execute("""
            SELECT COALESCE(SUM(amount), 0) AS paid
            FROM public.payments
            WHERE invoice_id = %(iid)s
        """, {"iid": iid}).fetchone()["paid"]

        # Decide new status
        if float(paid) >= float(inv["total_amount"]):
            new_status = "paid"
        elif float(paid) > 0:
            new_status = "partial"
        else:
            new_status = "unpaid"

        conn.execute("""
            UPDATE public.invoices
               SET payment_status = %(s)s::payment_status
             WHERE inv_id = %(iid)s
        """, {"s": new_status, "iid": iid})

    return {"ok": True, "invoice_id": iid, "status": new_status, "paid_total": float(paid)}