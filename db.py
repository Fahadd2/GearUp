# db.py
import os
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()

# Railway automatically provides DATABASE_URL
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("DATABASE_URL not set. Add it in Railway environment variables.")

# Connection pool settings (optimized for Railway)
pool = ConnectionPool(
    conninfo=DB_URL,
    min_size=1,
    max_size=10,  # Increased for production traffic
    max_idle=60,  # Longer idle time for Railway
    kwargs={"row_factory": dict_row}
)

def get_conn():
    """
    Usage:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM cars").fetchall()
    """
    return pool.connection()