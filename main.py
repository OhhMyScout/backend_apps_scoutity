import os
import sys
import time
import socket
import logging
import platform
from logging.handlers import RotatingFileHandler
from datetime import datetime
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from fastapi_mail import ConnectionConfig

# ==========================================================
# ROUTERS (Pastikan modul-modul ini sudah tersedia)
# ==========================================================
from app.module.login.login import init_login_router
from app.module.register.register import init_register_router
from app.module.logout.logout import init_logout_router
from app.module.profile.profile import init_profile_router
from app.module.games.games import init_games_router
from app.module.games.leaderboard import init_leaderboard_router
from app.module.forgot.forgot_password import init_forgot_router
from app.module.berita.berita import init_berita_router
from app.module.detection.detection import init_detection_router
from app.services.activity_logger import init_logs_router
from app.module.uji_sku.uji_sku import init_uji_sku_router


# ==========================================================
# INIT TIMER & ENV
# ==========================================================

START_TIME = time.time()
load_dotenv()

ENV = os.getenv("ENV", "development").lower()
IS_DEV = ENV == "development"

# ==========================================================
# ROTATING LOGGER CONFIGURATION
# ==========================================================
# Membuat folder logs otomatis jika belum ada
os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("scoutify")
logger.setLevel(logging.INFO)

log_formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

# File Handler: Max 5MB per file, simpan 5 backup file log (Rotating)
file_handler = RotatingFileHandler(
    "logs/scoutify_api.log", 
    maxBytes=5 * 1024 * 1024, 
    backupCount=5
)
file_handler.setFormatter(log_formatter)

# Console Handler untuk memunculkan log di terminal
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ==========================================================
# GET LOCAL IP (Untuk Development)
# ==========================================================
def get_local_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()

# ==========================================================
# LIFESPAN
# ==========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("Scoutify API Started")
    logger.info(f"Environment : {ENV.upper()}")
    logger.info("=" * 50)
    yield
    logger.info("Scoutify API Stopped")

# ==========================================================
# FASTAPI APP
# ==========================================================
app = FastAPI(
    title="Scoutify API",
    description="Production-Ready Backend API untuk Scoutify",
    version="1.0.0",
    lifespan=lifespan,
    # Keamanan: Matikan Docs di Production
    docs_url="/docs" if IS_DEV else None,
    redoc_url="/redoc" if IS_DEV else None,
    openapi_url="/openapi.json" if IS_DEV else None,
)

# ==========================================================
# MAX UPLOAD LIMIT MIDDLEWARE (30MB)
# ==========================================================
MAX_UPLOAD_SIZE = 30 * 1024 * 1024  # 30 MB

@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    if request.method in ["POST", "PUT", "PATCH"]:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_SIZE:
            logger.warning(f"Upload ditolak: Ukuran melebihi batas (IP: {request.client.host})")
            return JSONResponse(
                status_code=413,
                content={
                    "status": "error",
                    "message": "Payload Too Large. Maksimal ukuran upload adalah 30MB."
                }
            )
    return await call_next(request)

# ==========================================================
# TRUSTED HOST
# ==========================================================
allowed_hosts = [
    "haisen.my.id",
    "*.haisen.my.id",
    "trycenter.my.id",
    "*.trycenter.my.id"
]

# Development: Izinkan Localhost dan IP Publik lokal
if IS_DEV:
    allowed_hosts.extend(["localhost", "127.0.0.1", LOCAL_IP, "*"])

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=allowed_hosts
)

# ==========================================================
# CORS
# ==========================================================
allow_origins = [
    "https://trycenter.my.id",
    "https://www.trycenter.my.id",
    "https://api.trycenter.my.id",
    "https://dev.trycenter.my.id",
]

if IS_DEV:
    allow_origins.extend([
        "http://localhost:3000",
        "http://localhost:5000",
        "http://localhost:8080",
        "*"
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True, # Jika ada "*" di origins, hati-hati di production. Pastikan strict.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ==========================================================
# SECURITY HEADERS
# ==========================================================
@app.middleware("http")
async def security_headers(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = round(time.time() - start_time, 4)

    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    if not IS_DEV:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    response.headers["X-Process-Time"] = str(process_time)
    return response

# ==========================================================
# REQUEST LOGGER (CLOUDFLARE/NGINX READY)
# ==========================================================
@app.middleware("http")
async def request_logger(request: Request, call_next):
    # Dapatkan Real IP jika berada di balik proxy (Cloudflare/Nginx)
    ip = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for")
        or request.client.host
    )

    if ip and "," in str(ip):
        ip = ip.split(",")[0].strip()

    # Jangan spam log untuk route status/health check
    if request.url.path not in ["/", "/api/status"]:
        logger.info(f"{request.method} {request.url.path} | IP={ip}")
    
    response = await call_next(request)
    return response

# ==========================================================
# MAIL CONFIG
# ==========================================================
mail_conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
    MAIL_FROM=os.getenv("MAIL_DEFAULT_SENDER", "noreply@scoutify.id"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

# ==========================================================
# ROUTERS INJECTION
# ==========================================================

# -- 1. Auth & Security --
app.include_router(init_login_router(), prefix="/api", tags=["Auth & Security"])
app.include_router(init_register_router(mail_conf), prefix="/api", tags=["Auth & Security"])
app.include_router(init_logout_router(), prefix="/api", tags=["Auth & Security"])
app.include_router(init_forgot_router(mail_conf), prefix="/api", tags=["Auth & Security"])

# -- 2. Profile Management --
app.include_router(init_profile_router(mail_conf), prefix="/api", tags=["Profile Management"])

# -- 3. Kepramukaan & Fitur Utama --
app.include_router(init_uji_sku_router(), prefix="/api", tags=["Uji SKU"])
app.include_router(init_detection_router(), prefix="/api", tags=["Detection Services"])
app.include_router(init_games_router(), prefix="/api", tags=["Games"])
app.include_router(init_leaderboard_router(), prefix="/api", tags=["Games"])

# -- 4. Informasi & Berita --
# (Tag dihapus agar mengikuti setting bawaan file berita.py dan tidak duplikat)
app.include_router(init_berita_router(), prefix="/api")

# -- 5. System Logs --
# (Pemanggilan init_logs_router yang ganda sudah dihapus)
app.include_router(init_logs_router(), prefix="/api", tags=["User Activity Logs"])


# ==========================================================
# ROOT & HEALTH CHECKS
# ==========================================================

@app.get("/", tags=["System & Health"])
async def root():
    return {
        "status": "success",
        "message": "Scoutify Backend Running",
        "environment": ENV
    }



# ==========================================================
# API STATUS (HEALTH CHECK)
# ==========================================================
@app.get("/api/status", tags=["System & Health"])
async def api_status():
    # Hitung uptime server
    uptime_seconds = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_string = f"{hours}h {minutes}m {seconds}s"

    return {
        "status": "success",
        "message": "API is Online and Running",
        "info": {
            "environment": ENV.upper(),
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "uptime": uptime_string
        }
    }

# ==========================================================
# EXCEPTION HANDLERS (404 & 500)
# ==========================================================
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        logger.warning(f"404 Not Found: {request.url.path} (IP: {request.client.host})")
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "message": "Oops! Kamu keluar dari rute. Endpoint yang dicari tidak ada di peta kami"
            }
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": f"Misi dibatalkan: {exc.detail}"
        }
    )

# ==========================================================
# MAIN EXECUTION
# ==========================================================
if __name__ == "__main__":
    print("=" * 60)
    print("SCOUTIFY BACKEND RUNNING")
    print(f"ENVIRONMENT : {ENV.upper()}")
    print(f"LOCAL IP    : {LOCAL_IP}")
    print("HOST        : 0.0.0.0")
    print("PORT        : 5000")

    if IS_DEV:
        print(f"DOCS        : http://{LOCAL_IP}:5000/docs")

    print(f"STATUS      : http://{LOCAL_IP}:5000/api/status")
    print("=" * 60)

    # Configurasi uvicorn untuk Nginx/Cloudflare (proxy_headers & forwarded_allow_ips)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=IS_DEV,
        timeout_keep_alive=30,
        proxy_headers=True,
        forwarded_allow_ips="*"
    )