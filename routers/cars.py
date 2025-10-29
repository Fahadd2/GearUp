from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from db import get_conn

router = APIRouter(prefix="/cars", tags=["cars"])

class CarUpdate(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    category: Optional[str] = None
    transmission: Optional[str] = None
    price_per_day: Optional[float] = None
    status: Optional[str] = None

@router.get("")
def list_cars(
    category: str | None = None,
    seats: int | None = None,
    transmission: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
):
    sql = """
      SELECT
        car_id               AS id,
        plate_no,
        brand, model, year,
        category::text       AS category,
        fuel_type,
        color,
        seats,
        transmission::text   AS transmission,
        price_per_day::float AS price_per_day,
        status::text         AS status,
        COALESCE(photo_url,'') AS photo_url,
        created_at
      FROM public.cars
      WHERE 1=1
    """
    where, params = [], {}

    if category:
        where.append("AND category = %(cat)s::car_category")
        params["cat"] = category
    if seats:
        where.append("AND seats >= %(seats)s")
        params["seats"] = seats
    if transmission:
        where.append("AND transmission = %(tr)s::transmission_type")
        params["tr"] = transmission
    if min_price is not None:
        where.append("AND price_per_day >= %(pmin)s")
        params["pmin"] = min_price
    if max_price is not None:
        where.append("AND price_per_day <= %(pmax)s")
        params["pmax"] = max_price

    sql += " ".join(where) + " ORDER BY price_per_day, brand, model"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    return JSONResponse(content=jsonable_encoder(rows))


@router.put("/{car_id}")
def update_car(car_id: str, car: CarUpdate):
    """Update car details - staff only"""
    
    with get_conn() as conn:
        # Check if car exists
        existing = conn.execute(
            "SELECT car_id FROM public.cars WHERE car_id = %(id)s",
            {"id": car_id}
        ).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Car not found")
        
        # Build update query dynamically
        updates = []
        params = {"car_id": car_id}
        
        if car.brand is not None:
            updates.append("brand = %(brand)s")
            params["brand"] = car.brand
        if car.model is not None:
            updates.append("model = %(model)s")
            params["model"] = car.model
        if car.year is not None:
            updates.append("year = %(year)s")
            params["year"] = car.year
        if car.category is not None:
            updates.append("category = %(category)s::car_category")
            params["category"] = car.category
        if car.transmission is not None:
            updates.append("transmission = %(transmission)s::transmission_type")
            params["transmission"] = car.transmission
        if car.price_per_day is not None:
            updates.append("price_per_day = %(price_per_day)s")
            params["price_per_day"] = car.price_per_day
        if car.status is not None:
            updates.append("status = %(status)s::car_status")
            params["status"] = car.status
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        query = f"""
            UPDATE public.cars
            SET {', '.join(updates)}
            WHERE car_id = %(car_id)s
        """
        
        conn.execute(query, params)
    
    return {"message": "Car updated successfully", "car_id": car_id}