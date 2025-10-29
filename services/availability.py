def car_is_available(conn, car_id, start_date, end_date):
    """
    True if the car has no overlapping Reserved/Active reservations for the given range.
    Uses Postgres daterange overlap operator (&&).
    """
    sql = """
    select 1
    from reservations r
    where r.car_id = %(car_id)s
      and r.status in ('Reserved','Active')
      and daterange(r.start_date, r.end_date, '[]') && daterange(%(s)s, %(e)s, '[]')
    limit 1;
    """
    row = conn.execute(sql, {"car_id": car_id, "s": start_date, "e": end_date}).fetchone()
    return row is None
