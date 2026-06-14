import traceback
import datetime
import random
from datetime import timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig

from config.database import get_supabase_client
from app.services.activity_logger import ActivityLogger

# ==========================================================
# CONFIGURATION
# ==========================================================
supabase = get_supabase_client()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================
def generate_otp():
    return str(random.randint(1000, 9999))

def get_forgot_email_html(fullname, otp_code):
    return f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 580px; margin: 40px auto; border-radius: 20px; overflow: hidden; background: #ffffff; box-shadow: 0 10px 25px rgba(0,0,0,0.08);">
        
        <div style="background: linear-gradient(135deg, #361F1A 0%, #5D4037 100%); padding: 40px 20px; text-align: center; color: white;">
            <div style="font-size: 40px; margin-bottom: 8px;">🔐</div>
            <h1 style="margin: 0; font-size: 28px; letter-spacing: 0.5px;">Scoutify</h1>
            <p style="margin: 8px 0 0; font-size: 14px; opacity: 0.8; text-transform: uppercase; letter-spacing: 2px;">Reset Password</p>
        </div>

        <div style="padding: 40px 30px; color: #444;">
            <h2 style="margin-top: 0; font-size: 22px; color: #361F1A;">Halo, {fullname}! 👋</h2>
            <p style="font-size: 15px; color: #666; line-height: 1.7; margin-bottom: 30px;">
                Kami menerima permintaan untuk mengatur ulang kata sandi akun Scoutify Anda. Jika ini bukan Anda, abaikan email ini dan akun Anda akan tetap aman.
            </p>

            <div style="text-align: center; margin: 30px 0;">
                <p style="font-size: 13px; color: #999; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px;">Kode OTP Reset Anda</p>
                <div style="display: inline-block; padding: 18px 40px; font-size: 38px; font-weight: 800; letter-spacing: 12px; 
                            color: #7D562D; background: #F6F3EE; border-radius: 16px; border: 2px solid #EBE5DB;">
                    {otp_code}
                </div>
            </div>

            <div style="background: #FFFBF5; border-left: 4px solid #7D562D; padding: 16px; border-radius: 4px; font-size: 14px; color: #5D4037; margin-top: 30px;">
                <strong>Perhatian:</strong> Kode ini hanya berlaku selama <strong>10 menit</strong>. Jangan pernah membagikan kode ini kepada siapa pun!
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
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyForgotOtpRequest(BaseModel):
    email: EmailStr
    otp: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str


# ==========================================================
# ROUTER INITIALIZER
# ==========================================================
def init_forgot_router(mail_conf: ConnectionConfig):
    forgot_router = APIRouter()
    mail = FastMail(mail_conf)

    # ======================================================
    # 1. REQUEST OTP FORGOT PASSWORD
    # ======================================================
    @forgot_router.post("/forgot-password", status_code=status.HTTP_200_OK)
    async def forgot_password(request_data: ForgotPasswordRequest):
        try:
            email = str(request_data.email).strip().lower()

            # Cari user di database
            res = supabase.table("users").select("id, fullname").eq("email", email).execute()
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"status": "error", "message": "Email tidak terdaftar"}
                )

            user = res.data[0]
            otp_code = generate_otp()
            otp_expired_at = (datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=10)).isoformat()

            # Update OTP di tabel users
            supabase.table("users").update({
                "otp": int(otp_code),
                "otp_expired_at": otp_expired_at
            }).eq("id", user["id"]).execute()

            ActivityLogger.log(f"Permintaan reset password", user["id"])

            # Kirim Email OTP
            try:
                message = MessageSchema(
                    subject="Kode Reset Password Scoutify",
                    recipients=[email],
                    body=get_forgot_email_html(user["fullname"], otp_code),
                    subtype="html"
                )
                await mail.send_message(message)
            except Exception as e:
                print(f"[MAIL ERROR] {e}")

            return {"status": "success", "message": "Kode OTP telah dikirim ke email Anda"}

        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Server error", "error": str(e)}
            )

    # ======================================================
    # 2. VERIFY FORGOT OTP
    # ======================================================
    @forgot_router.post("/verify-otp-reset", status_code=status.HTTP_200_OK)
    async def verify_forgot_otp(request_data: VerifyForgotOtpRequest):
        try:
            email = str(request_data.email).strip().lower()
            otp_input = str(request_data.otp)

            res = supabase.table("users").select("*").eq("email", email).execute()
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"status": "error", "message": "User tidak ditemukan"}
                )

            user = res.data[0]

            if str(user["otp"]) != otp_input:
                ActivityLogger.log("Verifikasi OTP Reset gagal (kode salah)", user["id"])
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"status": "error", "message": "OTP salah"}
                )

            if user.get("otp_expired_at"):
                expired = datetime.datetime.fromisoformat(user["otp_expired_at"].replace("Z", "+00:00"))
                if datetime.datetime.now(timezone.utc) > expired:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"status": "error", "message": "OTP sudah kedaluwarsa"}
                    )

            # Jangan hapus OTP dulu, kita butuh saat input password baru
            return {"status": "success", "message": "Verifikasi OTP berhasil, silakan buat password baru"}

        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Server error"}
            )

    # ======================================================
    # 3. RESEND FORGOT OTP
    # ======================================================
    @forgot_router.post("/resend-otp-reset", status_code=status.HTTP_200_OK)
    async def resend_forgot_otp(request_data: ForgotPasswordRequest): # Re-use schema ForgotPasswordRequest (only email)
        try:
            email = str(request_data.email).strip().lower()

            res = supabase.table("users").select("id, fullname").eq("email", email).execute()
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"status": "error", "message": "User tidak ditemukan"}
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
                subject="OTP Reset Baru Scoutify",
                recipients=[email],
                body=get_forgot_email_html(user["fullname"], new_otp),
                subtype="html"
            )
            await mail.send_message(message)

            return {"status": "success", "message": "OTP baru terkirim ke email Anda"}

        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Gagal resend OTP"}
            )

    # ======================================================
    # 4. RESET PASSWORD (Simpan Sandi Baru)
    # ======================================================
    @forgot_router.post("/reset-password", status_code=status.HTTP_200_OK)
    async def reset_password(request_data: ResetPasswordRequest):
        try:
            email = str(request_data.email).strip().lower()
            otp_input = str(request_data.otp)
            new_password = str(request_data.new_password)

            res = supabase.table("users").select("*").eq("email", email).execute()
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"status": "error", "message": "User tidak ditemukan"}
                )

            user = res.data[0]

            # Verifikasi ulang OTP untuk keamanan ganda sebelum ganti password
            if str(user["otp"]) != otp_input:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"status": "error", "message": "Sesi tidak valid, verifikasi ulang OTP Anda"}
                )

            # Hash password baru
            hashed_password = pwd_context.hash(new_password)

            # Simpan password baru & bersihkan kolom OTP
            supabase.table("users").update({
                "password": hashed_password,
                "otp": None,
                "otp_expired_at": None
            }).eq("id", user["id"]).execute()

            ActivityLogger.log("Password berhasil direset", user["id"])

            return {"status": "success", "message": "Kata sandi berhasil diubah! Silakan login."}

        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Server error gagal mereset password"}
            )

    return forgot_router