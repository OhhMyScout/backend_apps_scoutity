import os
import jwt
import datetime
from datetime import timezone  # <-- Ditambahkan untuk standarisasi waktu UTC modern
import logging
from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt
from config.database import get_supabase_client
from dotenv import load_dotenv

load_dotenv()

login_blueprint = Blueprint('login', __name__)
supabase = get_supabase_client()
bcrypt = Bcrypt()

SECRET_KEY = os.getenv("SECRET_KEY")

# --- KONFIGURASI LOGGING UNTUK LOGIN LOKAL ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'log.txt')

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [LOGIN] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

@login_blueprint.route('/login', methods=['POST'])
def login_user():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    logging.info(f"Mencoba login untuk email: {email}")

    try:
        # 1. Cari user di tabel berdasarkan email
        query = supabase.table("users").select("*").eq("email", email).execute()
        user_list = query.data

        if not user_list:
            logging.warning(f"Gagal login: Email '{email}' tidak terdaftar")
            return jsonify({"status": "error", "message": "Email tidak terdaftar"}), 404

        user = user_list[0]
        user_id = user.get('id')
        username = user.get('username')
        stored_hash = user.get('password')

        # 2. Cek apakah password cocok dengan Hash di DB
        if bcrypt.check_password_hash(stored_hash, password):
            
            # --- 🔥 SUNTIKAN VALIDASI: CEK STATUS VERIFIKASI OTP DISINI BRAY! 🔥 ---
            if not user.get('is_verified', False):
                logging.warning(f"Gagal login: Akun '{email}' belum diverifikasi OTP.")
                return jsonify({
                    "status": "error", 
                    "message": "Akun kamu belum aktif bray. Silakan verifikasi kode OTP terlebih dahulu!"
                }), 403  # HTTP 403 Forbidden (Akses ditolak karena belum verifikasi)

            logging.info(f"Login BERHASIL untuk email: {email}")
            
            # 3. GENERATE JWT TOKEN BARU (Menggunakan timezone.utc yang aman)
            payload = {
                'user_id': user_id,
                'email': email,
                'exp': datetime.datetime.now(timezone.utc) + datetime.timedelta(days=7)
            }
            new_token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')

            # --- UPDATE TOKEN BARU KE DATABASE SUPABASE ---
            print(f"--- DEBUG: MEMPERBARUI TOKEN BARU DI TABEL USERS UNTUK {username} ---")
            supabase.table("users").update({"token": new_token}).eq("id", user_id).execute()
            
            # --- SUNTIKAN KODE: LOG MASUK KE TABEL activity_logs ---
            try:
                log_data = {
                    "user_id": user_id,
                    "activity": f"User {username} berhasil login ke dalam aplikasi Scoutify.",
                    "ip_address": request.remote_addr, 
                    "user_agent": request.headers.get('User-Agent', 'Unknown Device')
                }
                print(f"--- DEBUG: MENCATAT LOG LOGIN UNTUK {username} ---")
                supabase.table('activity_logs').insert(log_data).execute()
                print(f"--- DEBUG: LOG LOGIN BERHASIL TERSIMPAN DI DATABASE ---")
            except Exception as log_error:
                print(f"⚠️ WARNING LOGGING LOGIN: Gagal menyimpan log ke DB bray. Detail: {str(log_error)}")
            
            # 4. Kembalikan token baru yang valid ke HP Flutter
            return jsonify({
                "status": "success",
                "message": "Login berhasil",
                "token": new_token,
                "user": {
                    "username": username,
                    "fullname": user.get('fullname'),
                    "role": user.get('role')
                }
            }), 200
        else:
            logging.warning(f"Gagal login: Password salah untuk email '{email}'")
            return jsonify({"status": "error", "message": "Password salah"}), 401

    except Exception as e:
        logging.error(f"Error pada proses login email '{email}': {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 400

# FUNGSI FACTORY UTAMA YANG DIPANGGIL DI MAIN.PY
def init_login_blueprint():
    return login_blueprint