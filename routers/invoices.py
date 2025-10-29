from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from db import get_conn

router = APIRouter(prefix="/invoices", tags=["invoices"])

@router.get("")
def list_invoices(limit: int = 100):
    lim = max(1, min(limit, 200))
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
              i.inv_id,
              i.reservation_id,
              i.issue_date,
              i.total_amount,
              i.payment_status,
              i.created_at,
              -- helpful join fields
              r.customer_license_no,
              r.car_id,
              r.start_date,
              r.end_date
            FROM public.invoices i
            JOIN public.reservations r
              ON r.res_id = i.reservation_id
            ORDER BY i.created_at DESC
            LIMIT %(lim)s
        """, {"lim": lim}).fetchall()

    # Safely convert Decimal/Date → JSON
    return JSONResponse(content=jsonable_encoder(rows))
