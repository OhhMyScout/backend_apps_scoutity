import os
import jwt
import traceback

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv

from config.database import get_supabase_client
from app.services.activity_logger import ActivityLogger

load_dotenv()

# ==========================================================
# SETUP & CONFIGURATION
# ==========================================================
supabase = get_supabase_client()
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY tidak ditemukan di file .env")

# Inisialisasi HTTPBearer
security = HTTPBearer()


# ==========================================================
# PYDANTIC SCHEMA
# ==========================================================
class SaveScoreRequest(BaseModel):
    game_name: str
    score: int = 0


# ==========================================================
# DEPENDENCY: JWT VERIFICATION
# ==========================================================
def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Dependency untuk mengekstrak dan memvalidasi user_id dari token JWT.
    Jika token tidak valid, akan otomatis mengembalikan error 401.
    """
    token = credentials.credentials
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = decoded.get("user_id")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "error", "message": "Token tidak valid (user_id hilang)"}
            )
        return user_id
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Token sudah kedaluwarsa"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Token tidak valid"}
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Unauthorized"}
        )


# ==========================================================
# ROUTER INITIALIZER (Pengganti Blueprint)
# ==========================================================
def init_games_router():
    games_router = APIRouter()

    # =====================================================
    # 1. SAVE SCORE
    # =====================================================
    @games_router.post("/score")
    async def save_score(
        request_data: SaveScoreRequest,
        user_id: str = Depends(get_current_user_id) # Dependency injection di sini
    ):
        try:
            # Pydantic sudah memastikan game_name terisi, tapi pengecekan ekstra tidak ada salahnya
            if not request_data.game_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"status": "error", "message": "Nama game wajib diisi"}
                )

            # A. Simpan history skor ke tabel game_scores
            supabase.table("game_scores").insert({
                "user_id": user_id,
                "game_name": request_data.game_name,
                "score": request_data.score
            }).execute()

            # B. Update total points (Global Leaderboard) di tabel users
            if request_data.score > 0:
                # Ambil poin saat ini
                user_res = supabase.table("users").select("points, username").eq("id", user_id).execute()
                if user_res.data:
                    current_points = user_res.data[0].get("points", 0)
                    new_points = current_points + request_data.score
                    
                    # Update poin baru
                    supabase.table("users").update({"points": new_points}).eq("id", user_id).execute()

                    username = user_res.data[0].get("username", "User")
                    ActivityLogger.log(f"Skor {request_data.score} ditambahkan ke {username} dari {request_data.game_name}")

            return {
                "status": "success",
                "message": "Skor berhasil disimpan"
            }

        except HTTPException:
            raise
        except Exception as e:
            print(f"[SAVE SCORE ERROR] {str(e)}")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Gagal menyimpan skor"}
            )

    # =====================================================
    # 2. GLOBAL LEADERBOARD
    # =====================================================
    @games_router.get("/leaderboard")
    async def global_leaderboard():
        try:
            result = (
                supabase.table("users")
                .select("id,username,fullname,email,province,points,image,is_verified")
                .eq("is_verified", True)
                .order("points", desc=True)
                .execute()
            )

            users = result.data or []
            leaderboard_data = []

            for index, user in enumerate(users):
                leaderboard_data.append({
                    "rank": index + 1,
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "fullname": user.get("fullname"),
                    "email": user.get("email"),
                    "province": user.get("province"),
                    "points": user.get("points", 0),
                    "image": user.get("image")
                })

            return {
                "status": "success",
                "message": "Global Leaderboard berhasil diambil",
                "data": leaderboard_data
            }

        except Exception as e:
            print(f"[LEADERBOARD ERROR] {str(e)}")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Gagal mengambil leaderboard"}
            )

    # =====================================================
    # 3. SPECIFIC GAME LEADERBOARD
    # =====================================================
    # Di FastAPI, path parameter ditulis dengan kurung kurawal {}
    @games_router.get("/leaderboard/{game_name}")
    async def game_leaderboard(game_name: str):
        try:
            # Query ke tabel game_scores lalu join ke tabel users
            result = (
                supabase.table("game_scores")
                .select("score, users(id, username, fullname, province, image)")
                .eq("game_name", game_name)
                .order("score", desc=True)
                .execute()
            )

            scores = result.data or []
            
            # Ambil skor tertinggi unik per user
            seen_users = set()
            leaderboard_data = []
            
            for item in scores:
                user_info = item.get("users")
                if not user_info:
                    continue
                    
                user_id = user_info.get("id")
                if user_id not in seen_users:
                    seen_users.add(user_id)
                    leaderboard_data.append({
                        "rank": len(leaderboard_data) + 1,
                        "id": user_id,
                        "username": user_info.get("username"),
                        "fullname": user_info.get("fullname"),
                        "province": user_info.get("province"),
                        "points": item.get("score", 0),
                        "image": user_info.get("image")
                    })

            return {
                "status": "success",
                "message": f"Leaderboard {game_name} berhasil diambil",
                "data": leaderboard_data
            }

        except Exception as e:
            print(f"[GAME LEADERBOARD ERROR] {str(e)}")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": "Gagal mengambil leaderboard game"}
            )

    return games_router