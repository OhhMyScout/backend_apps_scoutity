import os
import jwt
from fastapi import APIRouter, Depends, HTTPException, Header

# Pastikan import ini sesuai dengan lokasi file database Anda
from config.database import get_supabase_client

supabase = get_supabase_client()

# ==========================================
# 1. DATABASE HELPER CLASS
# ==========================================
class ActivityLogger:

    @staticmethod
    def log(activity: str, user_id: str = None, ip_address: str = None, user_agent: str = None):
        """
        Logger aman tanpa dependency Flask/FastAPI request context.
        Bisa dipakai di service / background job.
        """
        try:
            log_data = {
                "activity": activity,
                "ip_address": ip_address or "unknown",
                "user_agent": user_agent or "unknown",
            }

            # hanya simpan jika user_id ada
            if user_id:
                log_data["user_id"] = str(user_id)

            # insert ke Supabase
            supabase.table("activity_logs").insert(log_data).execute()

        except Exception as e:
            print("[ACTIVITY LOG ERROR]", str(e))

    @staticmethod
    def get_logs_by_user(user_id: str, limit: int = 50):
        """
        Mengambil riwayat aktivitas berdasarkan user_id.
        Mengembalikan list of dictionary dari data Supabase.
        """
        try:
            response = supabase.table("activity_logs") \
                .select("*") \
                .eq("user_id", str(user_id)) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
                
            return response.data
        except Exception as e:
            print("[ACTIVITY LOG FETCH ERROR]", str(e))
            return []


# ==========================================
# 2. ROUTER & ENDPOINT DEFINITION
# ==========================================
def init_logs_router():
    router = APIRouter()

    # Dependency untuk mengekstrak dan memvalidasi JWT Token
    def get_current_user_id(authorization: str = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            print("[AUTH ERROR] Header Authorization kosong atau tidak menggunakan format Bearer.")
            raise HTTPException(status_code=401, detail="Token tidak valid atau tidak ditemukan")
        
        token = authorization.split(" ")[1]
        try:
            # Ambil secret key dari .env. Pastikan namanya sama persis dengan yang dipakai saat login.
            # Kita coba ambil 'JWT_SECRET' dulu, kalau tidak ada coba 'SECRET_KEY'
            SECRET_KEY = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "secret-key-anda")) 
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            
            # Ekstrak ID. Coba berbagai macam key yang sering dipakai di payload
            user_id = payload.get("id") or payload.get("user_id") or payload.get("sub")
            
            if not user_id:
                print(f"[AUTH ERROR] ID tidak ditemukan di dalam payload. Isi Payload: {payload}")
                raise HTTPException(status_code=401, detail="User ID tidak ditemukan di dalam token")
            
            return str(user_id)
            
        except jwt.ExpiredSignatureError:
            print("[AUTH ERROR] Token sudah kedaluwarsa (Expired).")
            raise HTTPException(status_code=401, detail="Token sudah kedaluwarsa")
        except jwt.InvalidTokenError as e:
            print(f"[AUTH ERROR] Token tidak valid. Penyebab: {str(e)}")
            raise HTTPException(status_code=401, detail="Token tidak valid")

    # Endpoint Get Info Logs
    @router.get("/info-logs")
    async def get_info_logs(user_id: str = Depends(get_current_user_id)):
        """
        Mengambil maksimal 50 log aktivitas terakhir milik user yang sedang login.
        """
        try:
            logs_data = ActivityLogger.get_logs_by_user(user_id=user_id, limit=50)
            return {
                "status": "success",
                "data": logs_data
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gagal mengambil data log: {str(e)}")

    return router