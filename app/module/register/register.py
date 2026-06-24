import os
import jwt
import traceback
import datetime
import random
import dns.resolver # <-- Tambahkan ini untuk cek domain email
from datetime import timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from supabase_auth.errors import AuthApiError 

from config.database import get_supabase_client
from dotenv import load_dotenv
from app.services.activity_logger import ActivityLogger

load_dotenv()

# ==========================================================
# CONFIGURATION
# ==========================================================

supabase = get_supabase_client()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY tidak ditemukan di file .env")

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================

def generate_otp():
    return str(random.randint(1000, 9999))

def is_domain_alive(email: str) -> bool:
    """
    Fungsi untuk mengecek apakah domain email memiliki MX record.
    Ini memblokir email dengan domain ngawur seperti user@asdfghjk.com
    """
    domain = email.split('@')[1]
    try:
        # Cek apakah domain memiliki server penerima email (Mail Exchange)
        records = dns.resolver.resolve(domain, 'MX')
        return len(records) > 0
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, Exception):
        return False

def get_email_html(fullname, otp_code):
    return f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 580px; margin: 40px auto; border-radius: 20px; overflow: hidden; background: #ffffff; box-shadow: 0 10px 25px rgba(0,0,0,0.08);">
        
        <div style="background: linear-gradient(135deg, #361F1A 0%, #5D4037 100%); padding: 40px 20px; text-align: center; color: white;">
            <div style="font-size: 40px; margin-bottom: 8px;"></div>
            <h1 style="margin: 0; font-size: 28px; letter-spacing: 0.5px;">Scoutify</h1>
            <p style="margin: 8px 0 0; font-size: 14px; opacity: 0.8; text-transform: uppercase; letter-spacing: 2px;">Verification Center</p>
        </div>

        <div style="padding: 40px 30px; color: #444;">
            <h2 style="margin-top: 0; font-size: 22px; color: #361F1A;">Halo, {fullname}! 👋</h2>
            <p style="font-size: 15px; color: #666; line-height: 1.7; margin-bottom: 30px;">
                Seseorang baru saja meminta kode verifikasi untuk akun Scoutify kamu. Jika ini bukan kamu, harap abaikan email ini.
            </p>

            <div style="text-align: center; margin: 30px 0;">
                <p style="font-size: 13px; color: #999; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px;">Kode OTP kamu</p>
                <div style="display: inline-block; padding: 18px 40px; font-size: 38px; font-weight: 800; letter-spacing: 12px; 
                            color: #7D562D; background: #F6F3EE; border-radius: 16px; border: 2px solid #EBE5DB;">
                    {otp_code}
                </div>
            </div>

            <div style="background: #FFFBF5; border-left: 4px solid #7D562D; padding: 16px; border-radius: 4px; font-size: 14px; color: #5D4037; margin-top: 30px;">
                <strong>Keamanan Akun:</strong> Kode ini hanya berlaku selama <strong>10 menit</strong>. Mohon untuk tidak membagikan kode ini kepada siapapun, termasuk pihak Scoutify.
            </div>
        </div>

        <div style="background: #FAFAFA; padding: 20px; text-align: center; font-size: 12px; color: #999;">
            <p style="margin: 0;">Pesan ini dikirim otomatis oleh sistem Scoutify.</p>
            <p style="margin: 5px 0 0;">&copy; 2026 Scoutify Indonesia. All rights reserved.</p>
        </div>
    </div>
    """

# ==========================================================
# PYDANTIC SCHEMAS
# ==========================================================

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    username: str
    fullname: str
    provinsi: Optional[str] = None
    role: str = "user"
    image: str = "default_profile.png"

class OtpRequest(BaseModel):
    email: EmailStr
    otp: str

class ResendOtpRequest(BaseModel):
    email: EmailStr

# ==========================================================
# ROUTER INITIALIZER
# ==========================================================
def init_register_router(mail_conf: ConnectionConfig):
    register_router = APIRouter()
    mail = FastMail(mail_conf)

    # ======================================================
    # 1. REGISTER
    # ======================================================
    @register_router.post("/register", status_code=status.HTTP_201_CREATED)
    async def register_user(request_data: RegisterRequest):
        try:
            email = str(request_data.email).strip().lower()
            password = str(request_data.password)
            username = request_data.username
            fullname = request_data.fullname
            province = request_data.provinsi
            role = request_data.role
            image = request_data.image

            # 1. Real-World Domain Check
            if not is_domain_alive(email):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "status": "error", 
                        "message": "Domain emailnya nggak ketemu di peta digital! Pakai email sungguhan ya, penjelajah."
                    }
                )

            # 2. Supabase Auth
            try:
                auth = supabase.auth.sign_up({"email": email, "password": password})
                if not auth.user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, 
                        detail={"status": "error", "message": "Kompas rusak! Gagal mendaftarkan akunmu di markas utama"}
                    )
            except AuthApiError as e:
                if "User already registered" in str(e):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, 
                        detail={"status": "error", "message": "Tenda ini sudah ada yang nempatin! Email kamu sudah terdaftar."}
                    )
                raise e 

            # 3. Data Prep
            otp_code = generate_otp()
            otp_expired_at = (datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=10)).isoformat()
            
            hashed_password = pwd_context.hash(password) # Menggunakan passlib untuk hash
            
            payload = {
                "user_id": auth.user.id,
                "email": email,
                "exp": datetime.datetime.now(timezone.utc) + datetime.timedelta(days=7)
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

            user_data = {
                "id": auth.user.id,
                "username": username,
                "fullname": fullname,
                "email": email,
                "province": province,
                "password": hashed_password,
                "otp": int(otp_code),
                "otp_expired_at": otp_expired_at,
                "token": token,
                "role": role,
                "points": 0,
                "image": image,
                "is_verified": False
            }

            # 4. Insert to Database
            supabase.table("users").insert(user_data).execute()
            ActivityLogger.log(f"Registrasi berhasil ({email})", auth.user.id)

            # 5. Send Email
            try:
                message = MessageSchema(
                    subject="Sandi Masuk Scoutify Kamu", 
                    recipients=[email],
                    body=get_email_html(fullname, otp_code),
                    subtype="html"
                )
                await mail.send_message(message)
            except Exception as e:
                print(f"[MAIL ERROR] {e}")

            return {
                "status": "success", 
                "message": "Pendaftaran sukses! Cek kotak suratmu untuk mengambil sandi rahasia (OTP)", 
                "token": token
            }

        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail={
                    "status": "error", 
                    "message": "Awan badai menutupi sinyal satelit. Server gagal merespons, coba lagi nanti ya!", 
                    "error": str(e)
                }
            )

    # ======================================================
    # 2. VERIFY OTP
    # ======================================================
    @register_router.post("/verify-otp")
    async def verify_otp(request_data: OtpRequest):
        try:
            email = str(request_data.email).strip().lower()
            otp_input = str(request_data.otp)

            res = supabase.table("users").select("*").eq("email", email).execute()
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail={"status": "error", "message": "Jejak tidak ditemukan! 🐾 Email ini belum terdaftar di posko kami."}
                )

            user = res.data[0]

            if str(user["otp"]) != otp_input:
                ActivityLogger.log("Verifikasi OTP gagal (kode salah)", user["id"])
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail={"status": "error", "message": "Sandi rahasia salah! Coba cek dan masukkan lagi kode OTP-nya."}
                )

            expired = datetime.datetime.fromisoformat(user["otp_expired_at"].replace("Z", "+00:00"))
            if datetime.datetime.now(timezone.utc) > expired:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail={"status": "error", "message": "Waduh, apinya keburu padam! Kode OTP kamu sudah kadaluarsa (lewat 10 menit)."}
                )

            supabase.table("users").update({
                "is_verified": True,
                "otp": None,
                "otp_expired_at": None
            }).eq("id", user["id"]).execute()

            safe_user_data = {
                "id": str(user["id"]),
                "username": user.get("username", ""),
                "fullname": user.get("fullname", ""),
                "email": user.get("email", ""),
                "role": user.get("role", "user"),
                "province": user.get("province", ""),
                "points": user.get("points", 0),
                "image": user.get("image", "default_profile.png")
            }

            return {
                "status": "success", 
                "message": "Verifikasi berhasil! Selamat bergabung di area perkemahan Scoutify",
                "token": user["token"],
                "user": safe_user_data
            }

        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail={"status": "error", "message": "Sistem sedang tersandung akar pohon. Gagal memverifikasi data."}
            )

    # ======================================================
    # 3. RESEND OTP
    # ======================================================
    @register_router.post("/resend-otp")
    async def resend_otp(request_data: ResendOtpRequest):
        try:
            email = str(request_data.email).strip().lower()
            
            res = supabase.table("users").select("id, fullname").eq("email", email).execute()
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail={"status": "error", "message": "Pramuka nyasar? Email tidak terdaftar untuk minta OTP baru."}
                )
            
            user = res.data[0]
            new_otp = generate_otp()
            new_expired = (datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=10)).isoformat()

            supabase.table("users").update({
                "otp": int(new_otp),
                "otp_expired_at": new_expired
            }).eq("id", user["id"]).execute()

            # Kirim Ulang Email
            message = MessageSchema(
                subject="Sandi Baru Scoutify Kamu", 
                recipients=[email],
                body=get_email_html(user["fullname"], new_otp),
                subtype="html"
            )
            await mail.send_message(message)

            return {"status": "success", "message": "Suar sinyal ditembakkan! OTP baru sudah terkirim ke emailmu."}
            
        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail={"status": "error", "message": "Gagal menembakkan suar sinyal. Coba lagi sebentar."}
            )

    return register_router

