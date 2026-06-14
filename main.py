import os
import time
import socket
import logging
import platform
import sys
from datetime import datetime



from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from fastapi_mail import ConnectionConfig

from fastapi.responses import JSONResponse, HTMLResponse

# ==========================================================
# ROUTERS
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

# Simpan waktu saat server pertama kali dijalankan
START_TIME = time.time()

# ==========================================================
# LOAD ENV
# ==========================================================
load_dotenv()

ENV = os.getenv("ENV", "development").lower()

# ==========================================================
# LOGGER
# ==========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("scoutify")

# ==========================================================
# GET LOCAL IP
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
    logger.info(f"Environment : {ENV}")
    logger.info("=" * 50)
    
    yield
    
    logger.info("Scoutify API Stopped")

# ==========================================================
# FASTAPI APP
# ==========================================================
app = FastAPI(
    title="Scoutify API",
    description="Backend API untuk Scoutify",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if ENV == "development" else None,
    redoc_url="/redoc" if ENV == "development" else None,
    openapi_url="/openapi.json" if ENV == "development" else None,
)

# ==========================================================
# TRUSTED HOST
# ==========================================================
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "localhost",
        "127.0.0.1",
        "haisen.my.id",
        "*.haisen.my.id",
        "trycenter.my.id",
        "*.trycenter.my.id"
    ]
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

if ENV == "development":
    allow_origins.extend([
        "http://localhost:3000",
        "http://localhost:5000",
        "http://localhost:8080",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
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

    if ENV == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    response.headers["X-Process-Time"] = str(process_time)
    return response

# ==========================================================
# REQUEST LOGGER
# ==========================================================
@app.middleware("http")
async def request_logger(request: Request, call_next):
    ip = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for")
        or request.client.host
    )

    if ip and "," in str(ip):
        ip = ip.split(",")[0].strip()

    logger.info(f"{request.method} {request.url.path} | IP={ip}")
    
    response = await call_next(request)
    return response

# ==========================================================
# MAIL CONFIG
# ==========================================================
mail_conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
    MAIL_FROM=os.getenv("MAIL_DEFAULT_SENDER", ""),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

# ==========================================================
# ROUTERS (DENGAN PENAMBAHAN TAGS)
# ==========================================================
# Dengan menambahkan tags di sini, dokumentasi di /docs akan 
# terpisah rapi sesuai dengan nama tag masing-masing.

app.include_router(init_login_router(), prefix="/api", tags=["Auth & Security"])
app.include_router(init_register_router(mail_conf), prefix="/api", tags=["Auth & Security"])
app.include_router(init_logout_router(), prefix="/api", tags=["Auth & Security"])
app.include_router(init_forgot_router(mail_conf), prefix="/api", tags=["Auth & Security"])

app.include_router(init_profile_router(mail_conf), prefix="/api", tags=["Profile Management"])

app.include_router(init_games_router(), prefix="/api", tags=["Games"])
app.include_router(init_leaderboard_router(), prefix="/api", tags=["Games"])

app.include_router(init_berita_router(), prefix="/api", tags=["News / Berita"])
app.include_router(init_detection_router(), prefix="/api", tags=["Detection Services"])

# ==========================================================
# ROOT
# ==========================================================
@app.get("/", tags=["System & Health"])
async def root():
    return {
        "status": "success",
        "message": "Scoutify Backend Running"
    }


# # ==========================================================
# # STATUS
# # ==========================================================
# @app.get("/api/status", tags=["System & Health"])
# async def api_status():
#     # Hitung uptime server
#     uptime_seconds = int(time.time() - START_TIME)
#     hours, remainder = divmod(uptime_seconds, 3600)
#     minutes, seconds = divmod(remainder, 60)
#     uptime_string = f"{hours}h {minutes}m {seconds}s"

#     return {
#         "status": "success",
#         "message": "Scoutify API is up and running! 🚀",
#         "core": {
#             "service": "Scoutify API",
#             "version": "1.0.0",
#             "environment": ENV.upper()
#         },
#         "server_metrics": {
#             "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#             "uptime": uptime_string,
#         },
#         "system_info": {
#             "os": platform.system(),
#             "python_version": sys.version.split(" ")[0]
#         }
#     }

# ==========================================================
# STATUS (FULLSCREEN TERMINAL UI DENGAN LIVE UPTIME & START TIME)
# ==========================================================
@app.get("/api/status", response_class=HTMLResponse, tags=["System & Health"])
async def api_status():
    # Ambil detik awal dari server saat halaman dimuat
    uptime_seconds = int(time.time() - START_TIME)
    
    # Format waktu server saat ini
    server_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Format waktu server pertama kali dinyalakan (Tanggal Bulan Tahun Jam)
    start_time_str = datetime.fromtimestamp(START_TIME).strftime("%d %B %Y %H:%M:%S")
    
    os_info = platform.system()
    python_version = sys.version.split(" ")[0]

    # Desain UI menggunakan HTML, CSS, & JS bergaya Terminal
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Scoutify Server Status</title>
        <style>
            * {{
                box-sizing: border-box;
            }}
            body {{
                background-color: #000000;
                color: #00ff00;
                font-family: 'Courier New', Courier, monospace;
                margin: 0;
                padding: 20px;
                min-height: 100vh;
                overflow-x: hidden;
            }}
            .terminal {{
                width: 100%;
                position: relative;
            }}
            .ascii-art {{
                white-space: pre;
                color: #00ff00;
                font-weight: bold;
                margin-bottom: 25px;
                font-size: 14px;
                line-height: 1.2;
            }}
            .prompt-line {{
                color: #ccc;
                margin-bottom: 20px;
                font-size: 16px;
            }}
            .user {{ color: #00ff00; font-weight: bold; }}
            .host {{ color: #00ff00; font-weight: bold; }}
            .path {{ color: #00aaff; font-weight: bold; }}
            .cmd {{ color: #ffffff; }}
            
            .output-row {{
                display: flex;
                margin-bottom: 10px;
                line-height: 1.5;
                font-size: 15px;
            }}
            .key {{
                width: 180px;
                color: #888;
            }}
            .val {{
                color: #00ff00;
                font-weight: bold;
            }}
            .val.env {{ color: #ff00ff; }}
            .val.sys {{ color: #ffff00; }}
            .val.ok {{ color: #00ff00; text-shadow: 0 0 5px #00ff00; }}
            .val.time {{ color: #00ffff; }}
            
            .blinking-cursor {{
                display: inline-block;
                width: 10px;
                height: 1.2em;
                background-color: #00ff00;
                vertical-align: middle;
                animation: blink 1s step-end infinite;
            }}
            @keyframes blink {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0; }}
            }}
            .scan-line {{
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 2px;
                background: rgba(0, 255, 0, 0.3);
                opacity: 0.4;
                animation: scan 6s linear infinite;
                pointer-events: none;
                z-index: 999;
            }}
            @keyframes scan {{
                0% {{ top: -10%; }}
                100% {{ top: 110%; }}
            }}
        </style>
    </head>
    <body>
        <div class="scan-line"></div>
        <div class="terminal">
            <div class="prompt-line">
                <span class="user">root</span>@<span class="host">scoutify-api</span>:<span class="path">~</span>$ <span class="cmd">./check_status.sh</span>
            </div>
            
            <div class="ascii-art">
   _____  _____ ____  _    _ _______ _____ ________     __
  / ____|/ ____/ __ \| |  | |__   __|_   _|  ____\ \   / /
 | (___ | |   | |  | | |  | |  | |    | | | |__   \ \_/ / 
  \___ \| |   | |  | | |  | |  | |    | | |  __|   \   /  
  ____) | |___| |__| | |__| |  | |   _| |_| |       | |   
 |_____/ \_____\____/ \____/   |_|  |_____|_|       |_|   
            </div>
            
            <div class="output-row">
                <div class="key">[+] SYSTEM_STATUS</div>
                <div class="val ok">ONLINE AND RUNNING</div>
            </div>
            <div class="output-row">
                <div class="key">[+] ENVIRONMENT</div>
                <div class="val env">{ENV.upper()}</div>
            </div>
            <div class="output-row">
                <div class="key">[+] SERVER_STARTED</div>
                <div class="val time">{start_time_str}</div>
            </div>
            <div class="output-row">
                <div class="key">[+] SERVER_TIME</div>
                <div class="val">{server_time}</div>
            </div>
            <div class="output-row">
                <div class="key">[+] UPTIME_METRIC</div>
                <div class="val" id="uptime-val"></div>
            </div>
            <div class="output-row">
                <div class="key">[+] HOST_OS</div>
                <div class="val sys">{os_info}</div>
            </div>
            <div class="output-row">
                <div class="key">[+] PYTHON_CORE</div>
                <div class="val sys">{python_version}</div>
            </div>
            <br>
            <div class="prompt-line">
                <span class="user">root</span>@<span class="host">scoutify-api</span>:<span class="path">~</span>$ <span class="blinking-cursor"></span>
            </div>
        </div>

        <script>
            // Menerima detik dari server FastAPI
            let uptimeSeconds = {uptime_seconds};
            
            function formatUptime(totalSec) {{
                let hours = Math.floor(totalSec / 3600);
                let minutes = Math.floor((totalSec % 3600) / 60);
                let seconds = totalSec % 60;
                return hours + "h " + minutes + "m " + seconds + "s";
            }}

            // Render pertama kali saat halaman dimuat
            document.getElementById("uptime-val").innerText = formatUptime(uptimeSeconds);

            // Tambahkan 1 detik setiap 1000ms dan update layar
            setInterval(function() {{
                uptimeSeconds++;
                document.getElementById("uptime-val").innerText = formatUptime(uptimeSeconds);
            }}, 1000);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content, status_code=200)

# ==========================================================
# MY IP
# ==========================================================
@app.get("/api/my-ip", tags=["System & Health"])
async def my_ip(request: Request):
    ip = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for")
        or request.client.host
    )

    if ip and "," in str(ip):
        ip = ip.split(",")[0].strip()

    return {
        "ip": ip
    }

# ==========================================================
# 404 HANDLER
# ==========================================================
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "message": "Endpoint Not Found"
            }
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": str(exc.detail)
        }
    )

# ==========================================================
# GLOBAL ERROR HANDLER
# ==========================================================
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception(exc)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal Server Error"
        }
    )

# ==========================================================
# MAIN
# ==========================================================
if __name__ == "__main__":
    print("=" * 60)
    print("SCOUTIFY BACKEND RUNNING")
    print(f"ENVIRONMENT : {ENV}")
    print(f"LOCAL IP    : {LOCAL_IP}")
    print("HOST        : 0.0.0.0")
    print("PORT        : 5000")

    if ENV == "development":
        print(f"DOCS        : http://{LOCAL_IP}:5000/docs")

    print(f"STATUS      : http://{LOCAL_IP}:5000/api/status")
    print("=" * 60)

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=(ENV == "development"),
        timeout_keep_alive=30
    )