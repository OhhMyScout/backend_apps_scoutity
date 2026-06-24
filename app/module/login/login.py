import os
import jwt
import traceback
import datetime
from datetime import timezone

from fastapi import APIRouter, HTTPException, status, Depends, Header
from pydantic import BaseModel
from passlib.context import CryptContext
from dotenv import load_dotenv

from config.database import get_supabase_client
from app.services.activity_logger import ActivityLogger

load_dotenv()

# ==========================================================
# CONFIG
# ==========================================================
supabase = get_supabase_client()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY tidak ditemukan di file .env")


# ==========================================================
# PYDANTIC SCHEMAS
# ==========================================================
class LoginRequest(BaseModel):
    email: str
    password: str

class GoogleLoginRequest(BaseModel):
    email: str
    fullname: str
    supabase_uid: str
    image: str = ""

# Schema Baru untuk fitur Tautkan Akun Google
class LinkGoogleRequest(BaseModel):
    google_id: str
    google_email: str
    google_name: str = ""


# ==========================================================
# DEPENDENCY (JWT EXTRACTOR)
# ==========================================================
def get_current_user_id(authorization: str = Header(None)):
    """
    Fungsi ini mengambil Token JWT dari header Authorization,
    memverifikasinya, dan mengembalikan user_id jika valid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token tidak valid atau tidak ditemukan")
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        
        # Ekstrak ID (berdasarkan payload di fungsi login di bawah, key-nya adalah "user_id")
        user_id = payload.get("user_id") or payload.get("id") or payload.get("sub")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID tidak ditemukan di dalam token")
        return str(user_id)
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token sudah kedaluwarsa, silakan login ulang.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token tidak valid")


# ==========================================================
# ROUTER INITIALIZATION
# ==========================================================
def init_login_router():
    login_router = APIRouter()

    # ======================================================
    # 1. LOGIN MANUAL (EMAIL & PASSWORD) DENGAN INTEGRASI GOOGLE OTOMATIS
    # ======================================================
    @login_router.post("/login")
    async def login_user(request_data: LoginRequest):
        try:
            email = str(request_data.email).strip().lower()
            password = str(request_data.password)

            print(f"[LOGIN ATTEMPT] {email}")

            # Ambil Data User
            response = (
                supabase.table("users")
                .select("*")
                .eq("email", email)
                .limit(1)
                .execute()
            )

            users = response.data or []

            if len(users) == 0:
                ActivityLogger.log(f"Login gagal: email tidak ditemukan ({email})")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "status": "error",
                        "message": "Hmm, email ini kayaknya lagi nyasar di hutan. Gak ketemu di database kita! 🏕️"
                    }
                )

            user = users[0]
            user_id = user.get("id")
            username = user.get("username", "")
            fullname = user.get("fullname", "")
            role = user.get("role", "user")
            stored_hash = user.get("password")
            is_verified = user.get("is_verified", False)

            # Cek Password Kosong
            if not stored_hash:
                ActivityLogger.log(f"Login gagal: password kosong ({username})", user_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "status": "error",
                        "message": "Password-nya kok gaib? Ketik yang bener dong, jangan cuma di batin 🧘‍♂️"
                    }
                )

            # Verifikasi Password
            try:
                password_match = pwd_context.verify(password, stored_hash)
            except Exception:
                password_match = False

            if not password_match:
                ActivityLogger.log(f"Login gagal: password salah ({username})", user_id)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "status": "error",
                        "message": "Password salah, nih. Ayo diingat-ingat lagi, jangan sampai ketuker sama sandi morse pramuka! 🚩"
                    }
                )

            # Cek Status Verifikasi OTP
            if not is_verified:
                ActivityLogger.log(f"Login ditolak: akun belum verifikasi OTP ({username})", user_id)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "status": "error",
                        "message": "Halt! 🛑 Akun kamu belum verifikasi OTP. Cek email dulu gih, jangan di-ghosting terus pesannya 👻"
                    }
                )

            # Generate JWT Token
            payload = {
                "user_id": user_id,
                "email": email,
                "username": username,
                "role": role,
                "exp": (datetime.datetime.now(timezone.utc) + datetime.timedelta(days=7))
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

            # --- LOGIKA BARU: GENERATE GOOGLE ID DETERMINISTIK ---
            manual_google_id = f"manual-{email}"

            # --- LOGIKA BARU: UPDATE DATABASE YANG DIPERLUAS ---
            token_data_update = {
                "token": token,
                "google_email": email,
                "google_linked": True,
                "google_id": manual_google_id
            }

            # Update Token dan data Google di Database secara bersamaan
            supabase.table("users").update(token_data_update).eq("id", user_id).execute()

            # Catat Aktivitas
            ActivityLogger.log(f"Login berhasil ({username})", user_id)
            print(f"[LOGIN SUCCESS] {email}")

            return {
                "status": "success",
                "message": "Welcome back, Explorer! Siap berpetualang lagi? 🚀",
                "token": token,
                "user": {
                    "id": user_id,
                    "username": username,
                    "fullname": fullname,
                    "email": email,
                    "role": role,
                    "province": user.get("province", ""),
                    "image": user.get("image", ""),
                    "points": user.get("points", 0)
                }
            }

        except HTTPException:
            raise

        except Exception as e:
            print("\n========== LOGIN ERROR ==========")
            traceback.print_exc()
            print("=================================\n")
            
            try:
                ActivityLogger.log(f"Server error login: {str(e)}")
            except Exception:
                pass

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "error",
                    "message": "Waduh, server kita lagi kesandung akar pohon 🌳. Sabar ya, lagi diobatin dulu 🩹",
                    "error": str(e)
                }
            )


    # ======================================================
    # 2. GOOGLE LOGIN (OAUTH SYNC / DIRECT LOGIN)
    # ======================================================
    @login_router.post("/google-login")
    async def google_login_sync(request_data: GoogleLoginRequest):
        try:
            email = str(request_data.email).strip().lower()
            fullname = str(request_data.fullname)
            supabase_uid = str(request_data.supabase_uid)
            image = str(request_data.image)

            print(f"[GOOGLE LOGIN ATTEMPT] {email}")

            # Cek apakah user sudah ada di database
            response = (
                supabase.table("users")
                .select("*")
                .eq("email", email)
                .limit(1)
                .execute()
            )
            users = response.data or []

            # Auto-Register jika akun belum terdaftar
            if len(users) == 0:
                # Sesuai permintaan: username & nama mengikuti data Google,
                # password masih kosong, agar user wajib buat password baru.
                new_user_data = {
                    "email": email,
                    "fullname": fullname,
                    "username": email.split("@")[0],
                    "role": "user",
                    "image": image,
                    # Belum punya password (tetap kosong), sehingga user diminta buat password baru.
                    "password": None,
                    "is_verified": False,
                    "google_linked": True,
                    "google_email": email,
                    "google_id": supabase_uid,
                }

                import uuid

                # DB kemungkinan punya kolom id NOT NULL yang tidak auto-generate,
                # jadi kita generate UUID kalau kolom "id" ada.
                # (Dengan asumsi tipe id di tabel users adalah UUID/string.)
                new_user_data["id"] = str(uuid.uuid4())

                insert_resp = supabase.table("users").insert(new_user_data).execute()
                if not insert_resp.data:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Gagal membuat akun otomatis via Google."
                    )

                user = insert_resp.data[0]
                user_id = user.get("id")
                ActivityLogger.log(f"Register via Google (password kosong) berhasil ({user.get('username')})", user_id)

                # Notifikasi wajib buat password baru
                # (JWT tidak perlu dipakai; kembalikan response instruksi saja)
                return {
                    "status": "success",
                    "message": "Akun Google berhasil dibuat. Silakan buat password baru untuk menyelesaikan aktivasi.",
                    "requires_password_setup": True,
                    "user": {
                        "id": user_id,
                        "username": user.get("username", ""),
                        "fullname": user.get("fullname", fullname),
                        "email": email,
                        "role": user.get("role", "user"),
                        "image": user.get("image", ""),
                        "points": user.get("points", 0),
                        "province": user.get("province", "")
                    }
                }
            else:
                user = users[0]
                user_id = user.get("id")

            username = user.get("username", "")
            role = user.get("role", "user")

            # Generate JWT Token Kustom
            payload = {
                "user_id": user_id,
                "email": email,
                "username": username,
                "role": role,
                "exp": (datetime.datetime.now(timezone.utc) + datetime.timedelta(days=7))
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

            # Update Token dan pastikan status google terkait
            (
                supabase.table("users")
                .update({
                    "token": token,
                    "image": image,
                    "google_linked": True,
                    "google_id": supabase_uid,
                    "google_email": email
                })
                .eq("id", user_id)
                .execute()
            )

            ActivityLogger.log(f"Login Google berhasil ({username})", user_id)
            print(f"[GOOGLE LOGIN SUCCESS] {email}")

            return {
                "status": "success",
                "message": "Welcome, Scout! Autentikasi Google berhasil 🏕️",
                "token": token,
                "user": {
                    "id": user_id,
                    "username": username,
                    "fullname": user.get("fullname", fullname),
                    "email": email,
                    "role": role,
                    "image": image,
                    "points": user.get("points", 0),
                    "province": user.get("province", "")
                }
            }

        except HTTPException:
            raise

        except Exception as e:
            print("\n========== GOOGLE LOGIN ERROR ==========")
            traceback.print_exc()
            print("========================================\n")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "error", 
                    "message": "Gagal sinkronisasi data Google dengan server.", 
                    "error": str(e)
                }
            )

    # ======================================================
    # 3. TAUTKAN AKUN GOOGLE DARI HALAMAN PROFIL (BARU)
    # ======================================================
    @login_router.post("/link-google")
    async def link_google_account(
        request_data: LinkGoogleRequest,
        user_id: str = Depends(get_current_user_id)
    ):
        try:
            print(f"[LINK GOOGLE ATTEMPT] User ID: {user_id} | Email Google: {request_data.google_email}")

            google_id = str(request_data.google_id).strip()
            google_email = str(request_data.google_email).strip().lower()

            if not google_id or not google_email:
                raise HTTPException(
                    status_code=400,
                    detail={"status": "error", "message": "google_id dan google_email wajib diisi."}
                )

            # ======================================================
            # CHECK KONFLIK: Pastikan google_id / google_email hanya
            # bisa ditautkan ke 1 user saja.
            # ======================================================
            conflict_by_google_id = (
                supabase.table("users")
                .select("id")
                .eq("google_id", google_id)
                .neq("id", user_id)
                .limit(1)
                .execute()
            )

            if conflict_by_google_id.data:
                conflict_user_id = conflict_by_google_id.data[0].get("id")
                raise HTTPException(
                    status_code=409,
                    detail={
                        "status": "error",
                        "message": "google_id ini sudah terhubung ke akun user lain.",
                        "conflict_user_id": conflict_user_id,
                    }
                )

            conflict_by_google_email = (
                supabase.table("users")
                .select("id")
                .eq("google_email", google_email)
                .neq("id", user_id)
                .limit(1)
                .execute()
            )

            if conflict_by_google_email.data:
                conflict_user_id = conflict_by_google_email.data[0].get("id")
                raise HTTPException(
                    status_code=409,
                    detail={
                        "status": "error",
                        "message": "google_email ini sudah terhubung ke akun user lain.",
                        "conflict_user_id": conflict_user_id,
                    }
                )

            # Persiapkan data yang akan diupdate ke tabel users
            update_data = {
                "google_linked": True,
                "google_id": google_id,
                "google_email": google_email
            }

            # Update ke Supabase berdasarkan user yang sedang login
            response = supabase.table("users").update(update_data).eq("id", user_id).execute()

            if not response.data:
                raise HTTPException(
                    status_code=404, 
                    detail={"status": "error", "message": "Gagal menautkan. Pengguna tidak ditemukan."}
                )

            # Catat aktivitas di Log
            ActivityLogger.log(f"Menautkan akun Google ({request_data.google_email})", user_id)

            return {
                "status": "success",
                "message": "Akun Google berhasil ditautkan.",
                "data": update_data
            }

        except HTTPException:
            raise
        except Exception as e:
            print("\n========== LINK GOOGLE ERROR ==========")
            traceback.print_exc()
            print("=======================================\n")
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "error",
                    "message": "Gagal menyimpan integrasi Google ke database.",
                    "error": str(e)
                }
            )

    return login_router