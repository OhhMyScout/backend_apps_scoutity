import os
import jwt
import random
import datetime
import traceback
from datetime import timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from dotenv import load_dotenv

from config.database import get_supabase_client

load_dotenv()

# ==========================================================
# SETUP & CONFIGURATION
# ==========================================================
supabase = get_supabase_client()
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY tidak ditemukan di file .env")

# Inisialisasi HTTPBearer untuk menangkap token
security = HTTPBearer()


# ==========================================================
# HELPER FUNCTIONS
# ==========================================================
def get_client_ip(request: Request) -> Optional[str]:
    """Mengambil IP address client (mendukung proxy)"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def save_activity_log(user_id=None, activity="", ip_address=None, user_agent=None):
    try:
        supabase.table("activity_logs").insert({
            "user_id": user_id,
            "activity": activity,
            "ip_address": ip_address,
            "user_agent": user_agent
        }).execute()
    except Exception as e:
        print(f"[ACTIVITY LOG ERROR] {str(e)}")


def generate_otp():
    return str(random.randint(1000, 9999))


def verify_jwt_token(token: str) -> dict:
    """Helper untuk decode dan validasi JWT"""
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return decoded
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Token sudah kedaluwarsa, silakan login kembali"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Token tidak valid"}
        )


# ==========================================================
# PYDANTIC SCHEMAS
# ==========================================================
class UpdateProfileRequest(BaseModel):
    fullname: Optional[str] = None
    username: Optional[str] = None
    gudep: Optional[str] = None
    province: Optional[str] = None
    email: Optional[EmailStr] = None  # Email hanya diupdate jika dikirim

class SendOtpRequest(BaseModel):
    email: EmailStr

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


# ==========================================================
# ROUTER INITIALIZER (Pengganti Blueprint)
# ==========================================================
def init_profile_router(mail_conf: ConnectionConfig):
    profile_router = APIRouter()
    
    # Inisialisasi FastMail
    mail = FastMail(mail_conf)

    # =====================================================
    # GET PROFILE
    # =====================================================
    @profile_router.get("/profile")
    async def get_profile(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ):
        try:
            token = credentials.credentials
            decoded = verify_jwt_token(token)
            user_id = decoded.get("user_id")
            
            user = supabase.table("users").select("*").eq("id", user_id).execute()

            if not user.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"status": "error", "message": "User tidak ditemukan"}
                )

            # Hilangkan data sensitif sebelum dikirim ke frontend
            user_data = user.data[0]
            user_data.pop("password", None)

            return {
                "status": "success",
                "user": user_data
            }

        except HTTPException:
            raise
        except Exception as e:
            print(f"[GET PROFILE ERROR] {str(e)}")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Terjadi kesalahan server"}
            )


    # =====================================================
    # UPDATE PROFILE
    # =====================================================
    @profile_router.put("/profile/update")
    async def update_profile(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        data: UpdateProfileRequest = None # Jika tidak ada body, akan None
    ):
        try:
            token = credentials.credentials
            decoded = verify_jwt_token(token)
            user_id = decoded.get("user_id")
            
            if not data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"status": "error", "message": "Request body tidak valid"}
                )

            # Pydantic: exclude_none=True akan secara otomatis menghapus field yang None
            # Sehingga tidak akan menimpa data lama dengan nilai kosong
            update_data = data.model_dump(exclude_none=True)

            if not update_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"status": "error", "message": "Tidak ada data yang diperbarui"}
                )

            result = supabase.table("users") \
                .update(update_data) \
                .eq("id", user_id) \
                .execute()

            # Logging pembaruan profil
            save_activity_log(
                user_id=user_id,
                activity="Pengguna memperbarui data profil",
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("User-Agent")
            )

            # Hilangkan password dari response
            response_user = result.data[0] if result.data else None
            if response_user:
                response_user.pop("password", None)

            return {
                "status": "success",
                "message": "Profile berhasil diupdate",
                "user": response_user
            }

        except HTTPException:
            raise
        except Exception as e:
            print(f"[UPDATE PROFILE ERROR] {str(e)}")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Terjadi kesalahan server saat memperbarui profil"}
            )


    # =====================================================
    # SEND OTP (DB + EMAIL)
    # =====================================================
    @profile_router.post("/otp/send")
    async def send_otp(request: Request, otp_data: SendOtpRequest):
        try:
            email = str(otp_data.email).strip().lower()

            # Verifikasi apakah email benar-benar ada di database sebelum kirim OTP
            user_check = supabase.table("users").select("id").eq("email", email).execute()
            if not user_check.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"status": "error", "message": "Email tidak terdaftar"}
                )

            user_id = user_check.data[0]["id"]
            otp_code = generate_otp()
            otp_expired_at = (
                datetime.datetime.now(timezone.utc)
                + datetime.timedelta(minutes=10)
            ).isoformat()

            # Save OTP to Database
            supabase.table("users") \
                .update({
                    "otp": otp_code,
                    "otp_expired_at": otp_expired_at
                }) \
                .eq("email", email) \
                .execute()

            # Send Email menggunakan FastAPI-Mail
            try:
                message = MessageSchema(
                    subject="OTP Verifikasi Perubahan Profil Scoutify",
                    recipients=[email],
                    body=f"""
Seseorang sedang meminta perubahan pengaturan pada akun profil kamu.
Kode OTP kamu: {otp_code}

Berlaku selama 10 menit.
Jangan bagikan kode ini ke siapa pun.
""",
                    subtype="plain" # Bisa diganti "html" jika ingin pakai template HTML
                )
                
                await mail.send_message(message)
                
                save_activity_log(
                    user_id=user_id,
                    activity=f"OTP pembaruan profil berhasil dikirim ke {email}",
                    ip_address=get_client_ip(request),
                    user_agent=request.headers.get("User-Agent")
                )

            except Exception as mail_error:
                print(f"[MAIL ERROR] {str(mail_error)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"status": "error", "message": "Gagal mengirimkan email OTP"}
                )

            return {
                "status": "success",
                "message": "OTP berhasil dikirim ke email"
            }

        except HTTPException:
            raise
        except Exception as e:
            print(f"[SEND OTP ERROR] {str(e)}")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Terjadi kesalahan server"}
            )


    # =====================================================
    # VERIFY OTP
    # =====================================================
    @profile_router.post("/otp/verify")
    async def verify_otp(request: Request, otp_data: VerifyOtpRequest):
        try:
            email = str(otp_data.email).strip().lower()
            otp_input = str(otp_data.otp)

            res = supabase.table("users") \
                .select("id", "otp", "otp_expired_at") \
                .eq("email", email) \
                .execute()

            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"status": "error", "message": "User tidak ditemukan"}
                )

            user = res.data[0]
            user_id = user["id"]

            # Check OTP match
            if str(user.get("otp")) != otp_input:
                save_activity_log(
                    user_id=user_id,
                    activity="Percobaan verifikasi OTP profil gagal (Kode salah)",
                    ip_address=get_client_ip(request),
                    user_agent=request.headers.get("User-Agent")
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"status": "error", "message": "OTP salah"}
                )

            # Check expiration
            expired_at = datetime.datetime.fromisoformat(
                user["otp_expired_at"].replace("Z", "+00:00")
            )

            if datetime.datetime.now(timezone.utc) > expired_at:
                save_activity_log(
                    user_id=user_id,
                    activity="Percobaan verifikasi OTP profil gagal (Expired)",
                    ip_address=get_client_ip(request),
                    user_agent=request.headers.get("User-Agent")
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"status": "error", "message": "OTP sudah kedaluwarsa"}
                )

            # Clear OTP upon successful verification
            supabase.table("users").update({
                "otp": None,
                "otp_expired_at": None
            }).eq("email", email).execute()

            save_activity_log(
                user_id=user_id,
                activity="Verifikasi OTP profil berhasil",
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("User-Agent")
            )

            return {
                "status": "success",
                "message": "OTP valid"
            }

        except HTTPException:
            raise
        except Exception as e:
            print(f"[VERIFY OTP ERROR] {str(e)}")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Terjadi kesalahan server saat verifikasi"}
            )

    return profile_router