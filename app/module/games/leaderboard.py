import traceback

from fastapi import APIRouter, HTTPException, status, Query
from config.database import get_supabase_client

supabase = get_supabase_client()


# ==========================================================
# ROUTER INITIALIZER (Pengganti Blueprint)
# ==========================================================
def init_leaderboard_router():
    leaderboard_router = APIRouter()

    # ==============================================================
    # 1. ENDPOINT: LEADERBOARD GLOBAL (Akumulasi Poin di tabel Users)
    # ==============================================================
    @leaderboard_router.get("/leaderboard")
    async def get_global_leaderboard():
        try:
            # Ambil data langsung dari tabel users
            res = supabase.table("users") \
                .select("id, fullname, email, province, points, image") \
                .order("points", desc=True) \
                .execute()
            
            return {
                "status": "success",
                "data": res.data
            }
            
        except Exception as e:
            print("[GLOBAL LEADERBOARD ERROR]")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": str(e)}
            )

    # ==============================================================
    # 2. ENDPOINT: LEADERBOARD SPESIFIK GAME (/game-scores)
    # ==============================================================
    @leaderboard_router.get("/game-scores")
    async def get_game_scores(
        # FastAPI Query: otomatis menangkap ?game_name=xxx dari URL
        # Jika tidak dikirim, akan langsung error 400 sesuai pesan di bawah
        game_name: str = Query(..., description="Nama game yang ingin dicari leaderboard-nya")
    ):
        try:
            # Lakukan Query JOIN di Supabase
            # Mengambil data dari 'game_scores' sekaligus data dari 'users'
            res = supabase.table("game_scores") \
                .select("score, users(fullname, email, province, image)") \
                .eq("game_name", game_name) \
                .order("score", desc=True) \
                .execute()

            # FILTER LOGIC: Hanya ambil skor tertinggi untuk setiap user
            # (Berguna jika satu user bermain berkali-kali dan datanya menumpuk)
            user_best_scores = {}
            for row in res.data:
                user_info = row.get("users")
                if not user_info:
                    continue
                
                email = user_info.get("email")
                current_score = int(row.get("score", 0))

                # Jika email belum ada di dictionary, atau skor saat ini lebih tinggi dari yang tersimpan
                if email not in user_best_scores or current_score > int(user_best_scores[email].get("score", 0)):
                    user_best_scores[email] = row

            # Ubah dictionary kembali menjadi list
            final_data = list(user_best_scores.values())
            
            # Urutkan kembali list final berdasarkan skor tertinggi
            final_data.sort(key=lambda x: int(x["score"]), reverse=True)

            return {
                "status": "success",
                "data": final_data
            }

        except Exception as e:
            print(f"[GAME SCORES ERROR - {game_name}]")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "message": str(e)}
            )

    return leaderboard_router