# db.py
import os
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("DATABASE_URL not set. Put it in .env (with ?sslmode=require).")

# Small client-side pool (works great with Supabase Session Pooler on port 6543)
pool = ConnectionPool(
    conninfo=DB_URL,
    min_size=1,
    max_size=5,
    max_idle=30,                    # seconds
    kwargs={"row_factory": dict_row}
)

def get_conn():
    """
    Usage:
        with get_conn() as conn:
            rows = conn.execute("select 1 as ok").fetchall()
    """
    return pool.connection()
