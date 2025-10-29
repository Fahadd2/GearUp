from fastapi import APIRouter
from db import get_conn
from datetime import date

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/kpis")
def get_kpis():
    """
    Returns KPI metrics for staff dashboard:
    - Today's pickups (reservations starting today)
    - Today's returns (reservations ending today)
    - Active rentals (currently ongoing)
    - Unpaid invoices count
    """
    today = date.today()
    
    with get_conn() as conn:
        # Today's pickups - reservations that start today and are Reserved
        pickups = conn.execute("""
            SELECT COUNT(*) as count
            FROM public.reservations
            WHERE start_date = %(today)s
              AND status = 'Reserved'
        """, {"today": today}).fetchone()["count"]
        
        # Today's returns - reservations that end today and are Active
        returns = conn.execute("""
            SELECT COUNT(*) as count
            FROM public.reservations
            WHERE end_date = %(today)s
              AND status = 'Active'
        """, {"today": today}).fetchone()["count"]
        
        # Active rentals - currently ongoing
        active = conn.execute("""
            SELECT COUNT(*) as count
            FROM public.reservations
            WHERE status = 'Active'
        """).fetchone()["count"]
        
        # Unpaid invoices
        unpaid = conn.execute("""
            SELECT COUNT(*) as count
            FROM public.invoices
            WHERE payment_status IN ('unpaid', 'partial')
        """).fetchone()["count"]
    
    return {
        "todays_pickups": pickups,
        "todays_returns": returns,
        "active_rentals": active,
        "unpaid_invoices": unpaid
    }

@router.get("/revenue")
def get_revenue_stats():
    """
    Revenue statistics:
    - Total revenue (all paid invoices)
    - Pending revenue (unpaid/partial)
    - This month's revenue
    """
    with get_conn() as conn:
        stats = conn.execute("""
            SELECT
                SUM(CASE WHEN payment_status = 'paid' THEN total_amount ELSE 0 END) as total_revenue,
                SUM(CASE WHEN payment_status IN ('unpaid', 'partial') THEN total_amount ELSE 0 END) as pending_revenue,
                SUM(CASE 
                    WHEN payment_status = 'paid' 
                    AND EXTRACT(MONTH FROM issue_date) = EXTRACT(MONTH FROM CURRENT_DATE)
                    AND EXTRACT(YEAR FROM issue_date) = EXTRACT(YEAR FROM CURRENT_DATE)
                    THEN total_amount 
                    ELSE 0 
                END) as this_month_revenue
            FROM public.invoices
        """).fetchone()
    
    return {
        "total_revenue": float(stats["total_revenue"] or 0),
        "pending_revenue": float(stats["pending_revenue"] or 0),
        "this_month_revenue": float(stats["this_month_revenue"] or 0)
    }