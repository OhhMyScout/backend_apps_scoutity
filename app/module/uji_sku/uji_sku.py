import traceback
import datetime
from datetime import timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel

from config.database import get_supabase_client
from app.services.activity_logger import ActivityLogger

# ==========================================================
# CONFIGURATION
# ==========================================================
supabase = get_supabase_client()
uji_sku_router = APIRouter(prefix="/uji-sku", tags=["Uji SKU"])

# ==========================================================
# PYDANTIC SCHEMAS (MASTER DATA)
# ==========================================================
class UjiSkuCreateRequest(BaseModel):
    admin_id: str # Ditambahkan untuk tracking di activity_logs
    level_id: str
    nomor_poin: int
    kategori_agama: str = "Umum"
    deskripsi: str

class UjiSkuUpdateRequest(BaseModel):
    admin_id: str # Ditambahkan untuk tracking di activity_logs
    nomor_poin: Optional[int] = None
    kategori_agama: Optional[str] = None
    deskripsi: Optional[str] = None

# ==========================================================
# PYDANTIC SCHEMAS (PROGRESS & TRANSAKSI)
# ==========================================================
class AjukanUjianRequest(BaseModel):
    user_id: str
    uji_sku_id: str
    bukti_url: Optional[str] = None

class ValidasiUjianRequest(BaseModel):
    pembina_id: str
    status: str # 'Selesai' atau 'Revisi'
    catatan: Optional[str] = None

class PelantikanRequest(BaseModel):
    user_id: str
    level_id: str
    location: str
    inaugurator_name: str
    inaugurator_role: Optional[str] = "Pembina Pramuka"
    shb_number: Optional[str] = None

# ==========================================================
# 1. CRUD MASTER DATA UJI SKU
# ==========================================================

@uji_sku_router.post("/master", status_code=status.HTTP_201_CREATED)
async def create_sku_item(request_data: UjiSkuCreateRequest):
    """Menambahkan butir soal SKU baru ke dalam database master."""
    try:
        data_insert = {
            "level_id": request_data.level_id,
            "nomor_poin": request_data.nomor_poin,
            "kategori": request_data.kategori,
            "deskripsi": request_data.deskripsi
        }
        
        res = supabase.table("uji_sku").insert(data_insert).execute()
        
        # Log Aktivitas
        ActivityLogger.log(f"Menambahkan materi SKU poin ke-{request_data.nomor_poin} ({request_data.kategori_agama})", request_data.admin_id)
        
        return {
            "status": "success",
            "message": "Mantap! Syarat kecakapan baru berhasil ditambahkan ke buku pedoman.",
            "data": res.data[0]
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": "Pena macet! Gagal mencatat SKU ke database.", "error": str(e)}
        )

@uji_sku_router.get("/master/{level_id}")
async def get_sku_by_level(level_id: str, agama: Optional[str] = None):
    """Mengambil daftar SKU berdasarkan tingkatan (Ramu/Rakit/Terap)."""
    try:
        query = supabase.table("uji_sku").select("*").eq("level_id", level_id)
        
        if agama:
            query = query.in_("kategori", ["Umum", agama])
            
        res = query.order("nomor_poin").execute()
        
        return {
            "status": "success",
            "message": "Peta materi SKU berhasil dibentangkan!",
            "data": res.data
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": "Kompas berputar tak karuan! Gagal memuat data SKU."}
        )

@uji_sku_router.put("/master/{id}")
async def update_sku_item(id: str, request_data: UjiSkuUpdateRequest):
    """Mengupdate butir soal SKU (misal ada revisi kalimat dari Kwartir)."""
    try:
        update_data = {k: v for k, v in request_data.dict(exclude={"admin_id"}).items() if v is not None}
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"status": "error", "message": "Tidak ada pesan sandi yang mau diubah!"}
            )
            
        res = supabase.table("uji_sku").update(update_data).eq("id", id).execute()
        
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"status": "error", "message": "Jejak SKU tidak ditemukan di titik koordinat ini."}
            )
            
        # Log Aktivitas
        ActivityLogger.log(f"Memperbarui data materi SKU (ID: {id})", request_data.admin_id)
            
        return {
            "status": "success",
            "message": "Pesan sandi di buku panduan berhasil diperbarui!",
            "data": res.data[0]
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": "Gagal merombak tenda data!"}
        )

@uji_sku_router.delete("/master/{id}")
async def delete_sku_item(id: str, admin_id: str = Query(..., description="ID Admin yang menghapus")):
    """Menghapus butir soal SKU."""
    try:
        res = supabase.table("uji_sku").delete().eq("id", id).execute()
        
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"status": "error", "message": "Data sudah menguap seperti asap api unggun, tidak ditemukan!"}
            )
            
        # Log Aktivitas
        ActivityLogger.log(f"Menghapus materi SKU dari database (ID: {id})", admin_id)
            
        return {
            "status": "success",
            "message": "Butir SKU berhasil dicabut dari pasaknya."
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": "Tali terlalu kencang, gagal menghapus data."}
        )

# ==========================================================
# 2. OPERASIONAL UJIAN SKU (PESERTA & PEMBINA)
# ==========================================================

@uji_sku_router.post("/ajukan")
async def ajukan_ujian(request_data: AjukanUjianRequest):
    """Peserta didik mengajukan poin SKU untuk dinilai Pembina."""
    try:
        cek_progress = supabase.table("user_sku_progress").select("*").eq("user_id", request_data.user_id).eq("uji_sku_id", request_data.uji_sku_id).execute()
        
        if cek_progress.data:
            progress = cek_progress.data[0]
            if progress['status'] == 'Selesai':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"status": "error", "message": "Poin ini sudah dapat Tanda Kecakapan, tidak perlu diuji lagi!"}
                )
            elif progress['status'] == 'Menunggu Validasi':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"status": "error", "message": "Tenang, laporanmu masih dalam antrean Kakak Pembina."}
                )
            
            update_data = {
                "status": "Menunggu Validasi",
                "bukti_url": request_data.bukti_url,
                "catatan": None 
            }
            res = supabase.table("user_sku_progress").update(update_data).eq("id", progress['id']).execute()
            ActivityLogger.log("Mengajukan ulang perbaikan ujian SKU", request_data.user_id)
            
        else:
            insert_data = {
                "user_id": request_data.user_id,
                "uji_sku_id": request_data.uji_sku_id,
                "status": "Menunggu Validasi",
                "bukti_url": request_data.bukti_url
            }
            res = supabase.table("user_sku_progress").insert(insert_data).execute()
            ActivityLogger.log("Mengajukan ujian SKU baru", request_data.user_id)

        return {
            "status": "success",
            "message": "Peluit ditiup! Ujianmu berhasil diajukan ke Kakak Pembina.",
            "data": res.data[0]
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": "Gagal mengirim pesan semaphore ke Pembina.", "error": str(e)}
        )

@uji_sku_router.put("/validasi/{progress_id}")
async def validasi_ujian(progress_id: str, request_data: ValidasiUjianRequest):
    """Kakak Pembina memberikan validasi (Lulus / Revisi) dan penambahan poin."""
    try:
        cek_prog = supabase.table("user_sku_progress").select("*").eq("id", progress_id).execute()
        if not cek_prog.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail={"status": "error", "message": "Data pengajuan tidak ditemukan di meja Pembina."}
            )
            
        peserta_id = cek_prog.data[0]["user_id"]

        update_data = {
            "status": request_data.status,
            "approved_by": request_data.pembina_id,
            "catatan": request_data.catatan
        }
        
        pesan = "Instruksi revisi berhasil dikirim ke peserta."

        if request_data.status == "Selesai":
            update_data["approved_at"] = datetime.datetime.now(timezone.utc).isoformat()
            pesan = "Paraf digital diberikan! Peserta mendapatkan poin tambahan."
            
            # Sistem Poin Reward
            user_data = supabase.table("users").select("points").eq("id", peserta_id).execute()
            current_points = user_data.data[0]["points"] if user_data.data and user_data.data[0].get("points") else 0
            
            supabase.table("users").update({"points": current_points + 10}).eq("id", peserta_id).execute()
            
            # Log untuk Peserta (Mendapatkan Poin)
            ActivityLogger.log("Lulus 1 poin ujian SKU (+10 Poin)", peserta_id)
            
        # Log untuk Pembina (Melakukan Validasi)
        ActivityLogger.log(f"Memvalidasi pengajuan SKU peserta (Status: {request_data.status})", request_data.pembina_id)

        res = supabase.table("user_sku_progress").update(update_data).eq("id", progress_id).execute()

        return {
            "status": "success",
            "message": pesan,
            "data": res.data[0]
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": "Tinta pena habis! Gagal memvalidasi ujian."}
        )

@uji_sku_router.get("/progress/{user_id}/{level_id}")
async def get_user_progress(user_id: str, level_id: str):
    """Mendapatkan rekapan progress seorang peserta di tingkatan tertentu."""
    try:
        res = supabase.table("user_sku_progress")\
            .select("*, uji_sku!inner(*)")\
            .eq("user_id", user_id)\
            .eq("uji_sku.level_id", level_id)\
            .execute()
            
        return {
            "status": "success",
            "message": "Buku saku berhasil dibuka!",
            "total_diselesaikan": len([item for item in res.data if item['status'] == 'Selesai']),
            "data": res.data
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": "Gagal membaca jejak rekam ujian."}
        )

@uji_sku_router.post("/pelantikan")
async def pelantikan_peserta(request_data: PelantikanRequest):
    """Mencatat sejarah pelantikan setelah peserta merampungkan 30 poin SKU."""
    try:
        insert_data = {
            "user_id": request_data.user_id,
            "level_id": request_data.level_id,
            "inauguration_date": datetime.datetime.now(timezone.utc).date().isoformat(),
            "location": request_data.location,
            "inaugurator_name": request_data.inaugurator_name,
            "inaugurator_role": request_data.inaugurator_role,
            "shb_number": request_data.shb_number
        }
        
        res = supabase.table("sku_inaugurations").insert(insert_data).execute()
        
        # Update level saat ini & berikan bonus poin pelantikan
        user_data = supabase.table("users").select("points").eq("id", request_data.user_id).execute()
        current_points = user_data.data[0]["points"] if user_data.data and user_data.data[0].get("points") else 0
        
        supabase.table("users").update({
            "current_sku_level_id": request_data.level_id,
            "points": current_points + 100
        }).eq("id", request_data.user_id).execute()

        # Log Aktivitas Pelantikan
        ActivityLogger.log(f"Resmi dilantik! Mendapat Tanda Kecakapan Umum (+100 Poin)", request_data.user_id)

        return {
            "status": "success",
            "message": "Selamat! Peserta berhasil dilantik dan mendapatkan Tanda Kecakapan Umum.",
            "data": res.data[0]
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail={"status": "error", "message": "Gagal mencatat sejarah pelantikan."}
        )
    
# ==========================================================
# ROUTER INITIALIZER
# ==========================================================
def init_uji_sku_router():
    return uji_sku_router