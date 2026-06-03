from flask import Blueprint, request, jsonify
from config.database import get_supabase_client 

logout_bp = Blueprint('logout', __name__)

@logout_bp.route('/logout', methods=['POST'])
def logout_user():
    try:
        # 1. Inisialisasi instance Supabase Client
        supabase = get_supabase_client()

        # 2. Ambil token JWT dari Header Authorization bray
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({
                "status": "error",
                "message": "Token tidak ditemukan bray!"
            }), 401
        
        # Ekstrak string token setelah teks "Bearer " dan bersihkan spasi gaib
        token = auth_header.split(" ")[1].strip()
        print(f"--- 🕵️‍♂️ DEBUG LOGOUT: Token diterima dari HP -> {token[:20]}... ---")

        # 3. Cari data user berdasarkan token yang aktif di DB
        print(f"--- DEBUG: MENCARI USER BERDASARKAN TOKEN DI DATABASE ---")
        user_check = supabase.table('users').select('id', 'username').eq('token', token).execute()
        
        print(f"--- 🕵️‍♂️ DEBUG LOGOUT: Hasil Query dari Supabase -> {user_check.data} ---")
        
        # Validasi ketat: Jika data kosong, berarti session sudah mati / sudah logout sebelumnya
        if not user_check.data or len(user_check.data) == 0:
            print("❌ ERROR LOGOUT: Token dari HP TIDAK COCOK dengan yang ada di database users bray!")
            return jsonify({
                "status": "error",
                "message": "Sesi login tidak valid atau Anda sudah logout bray!"
            }), 404
        
        user_id = user_check.data[0]['id']
        username = user_check.data[0]['username']
        print(f"✅ SUCCESS LOGOUT: Token cocok! User ID ditemukan -> {user_id} ({username})")

        # 4. FOKUS UTAMA: PROSES HAPUS TOKEN DI TABEL USERS (SET KE NULL)
        # Kita eksekusi ini duluan agar kepastian user keluar dari sistem terjamin 100% bray!
        print(f"--- DEBUG: MENCOBA MENEMBAK UPDATE TOKEN JADI NULL UNTUK USER ID {user_id} ---")
        db_update = supabase.table('users').update({"token": None}).eq('id', user_id).execute()
        print(f"--- 🕵️‍♂️ DEBUG LOGOUT: Respon database setelah update token -> {db_update.data} ---")

        # 5. PROSES PENCATATAN LOG ACTIVITY (Dibungkus try-except agar aman dari kegagalan tabel log)
        try:
            log_data = {
                "user_id": user_id,
                "activity": f"User {username} berhasil logout dari aplikasi Scoutify.",
                "ip_address": request.remote_addr, 
                "user_agent": request.headers.get('User-Agent', 'Unknown Device')
            }
            print(f"--- DEBUG: MENCATAT LOG LOGOUT UNTUK USER: {username} KE TABEL activity_logs ---")
            supabase.table('activity_logs').insert(log_data).execute()
            print(f"--- DEBUG: LOG LOGOUT BERHASIL TERSIMPAN DI CLOUD ---")
        except Exception as log_error:
            # Jika log gagal dimasukkan, aplikasi tidak akan crash dan proses logout tetap sukses bray!
            print(f"⚠️ WARNING LOGGING LOGOUT: Gagal menyimpan riwayat log aktivitas. Detail: {str(log_error)}")

        return jsonify({
            "status": "success",
            "message": "Logout berhasil dilakukan bray dan aktivitas telah dicatat!"
        }), 200

    except Exception as e:
        print(f"!!!!!!!! 🚨 DEBUG LOGOUT FATAL ERROR ASLI 🚨 !!!!!!!!: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Terjadi kesalahan sistem saat proses logout: {str(e)}"
        }), 500

# FUNGSI FACTORY UTAMA YANG DIPANGGIL DI MAIN.PY
def init_logout_blueprint():
    return logout_bp