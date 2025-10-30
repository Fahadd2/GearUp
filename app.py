# app.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from routers import cars, reservations, rentals, invoices, payments, auth, dashboard

app = FastAPI(title="GearUp API")

# CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "API is running"}

# API Routers
app.include_router(auth.router)
app.include_router(cars.router)
app.include_router(reservations.router)
app.include_router(rentals.router)
app.include_router(invoices.router)
app.include_router(payments.router)
app.include_router(dashboard.router)

# Serve static files (CSS, JS)
@app.get("/config.js")
def serve_config():
    return FileResponse("config.js")

@app.get("/styles.css")
def serve_styles():
    return FileResponse("styles.css")

@app.get("/staff.css")
def serve_staff_css():
    return FileResponse("staff.css")

# Serve HTML pages
@app.get("/")
def serve_index():
    return FileResponse("index.html")

@app.get("/login.html")
def serve_login():
    return FileResponse("login.html")

@app.get("/signup.html")
def serve_signup():
    return FileResponse("signup.html")

@app.get("/reset.html")
def serve_reset():
    return FileResponse("reset.html")

@app.get("/staff-login.html")
def serve_staff_login():
    return FileResponse("staff-login.html")

@app.get("/staff.html")
def serve_staff():
    return FileResponse("staff.html")