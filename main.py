from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
import models
from routes import auth as auth_routes, requests as request_routes, admin as admin_routes

# Create all tables (you may use alembic for migrations in production)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Request Management System")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins, you can specify domains instead of "*"
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

app.include_router(auth_routes.router)
app.include_router(request_routes.router)
app.include_router(admin_routes.router)

@app.get('/')
def server():
    return "Server is Active"

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    # Here you could log the error using your CRUD error log function.
    # For now, we simply return a generic error message.
    return {"detail": "Internal server error"}
