# app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import cars, reservations, rentals, invoices, payments, auth, dashboard

app = FastAPI(title="GearUp API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "API is running"}

# Routers
app.include_router(auth.router)
app.include_router(cars.router)
app.include_router(reservations.router)
app.include_router(rentals.router)
app.include_router(invoices.router)
app.include_router(payments.router)
app.include_router(dashboard.router)