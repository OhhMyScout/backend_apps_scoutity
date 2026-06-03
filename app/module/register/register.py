import os
import jwt
import datetime
from datetime import timezone
import random
import logging
from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt
from flask_mail import Message
from config.database import get_supabase_client
from dotenv import load_dotenv

load_dotenv()

supabase = get_supabase_client()
bcrypt = Bcrypt()
SECRET_KEY = os.getenv("SECRET_KEY")

# --- KONFIGURASI LOGGING UNTUK REGISTER LOKAL ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'log.txt')

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [REGISTER] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def generate_otp():
    return str(random.randint(1000, 9999))

def init_register_blueprint(mail):
    register_blueprint = Blueprint('register', __name__)

    @register_blueprint.route('/register', methods=['POST'])
    def register_user():
        data = request.json
        email = data.get('email')
        password = data.get('password')
        username = data.get('username')
        fullname = data.get('fullname')
        provinsi = data.get('provinsi')
        role = data.get('role', 'user')

        logging.info(f"Menerima request registrasi untuk email: {email}")

        try:
            # 1. Generate OTP & Atur Waktu Expired 10 Menit
            otp_code = generate_otp()
            waktu_sekarang = datetime.datetime.now(timezone.utc)
            waktu_expired = waktu_sekarang + datetime.timedelta(minutes=10)
            otp_expired_at = waktu_expired.isoformat()

            # 2. Kirim Email OTP via Flask-Mail
            logging.info(f"Mengirim kode OTP ke email: {email}")
            msg = Message(
                subject="Kode Verifikasi OTP Scoutify",
                recipients=[email]
            )
            msg.body = f"""Salam Pramuka, {fullname}!
            
Berikut adalah kode OTP untuk memverifikasi pendaftaran akun Scoutify kamu:

👉 {otp_code} 👈

Kode ini hanya berlaku selama 10 menit bray. Jangan berikan kode ini kepada siapa pun!

Salam,
Scoutify Team
"""
            mail.send(msg)
            logging.info(f"Email OTP sukses terkirim ke {email}")

            # 3. Hashing Password
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

            # 4. Registrasi ke Supabase Auth
            logging.info(f"Mencoba signup ke Supabase Auth untuk email: {email}")
            auth_response = supabase.auth.sign_up({
                "email": email,
                "password": password, 
            })

            if auth_response.user is not None:
                # 5. Generate JWT Token
                payload = {
                    'user_id': auth_response.user.id,
                    'email': email,
                    'exp': datetime.datetime.now(timezone.utc) + datetime.timedelta(days=7)
                }
                token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')

                # 6. Susun data user lengkap ke tabel 'users'
                user_data = {
                    "username": username,
                    "fullname": fullname,
                    "email": email,
                    "provinsi": provinsi,
                    "password": hashed_password, 
                    "token": token,             
                    "role": role,
                    "points": 0,
                    "images": data.get('images', 'default_profile.png'),
                    "otp": otp_code,          
                    "otp_expired_at": otp_expired_at,  
                    "is_verified": False             
                }
                
                logging.info(f"Memasukkan data user ke tabel 'users' untuk email: {email}")
                db_response = supabase.table("users").insert(user_data).execute()

                # --- AKTIVITAS AUDIT LOG KE DATABASE ---
                try:
                    new_user_id = db_response.data[0]['id'] if db_response.data else None
                    if new_user_id:
                        log_data = {
                            "user_id": new_user_id,
                            "activity": f"User {username} berhasil melakukan registrasi akun baru (Belum Verifikasi).",
                            "ip_address": request.remote_addr,
                            "user_agent": request.headers.get('User-Agent', 'Unknown Device')
                        }
                        supabase.table('activity_logs').insert(log_data).execute()
                except Exception as log_error:
                    print(f"⚠️ WARNING LOGGING REGISTER: Gagal simpan log. Detail: {str(log_error)}")

                logging.info(f"Registrasi Berhasil! Akun dibuat untuk email: {email}")
                return jsonify({
                    "status": "success",
                    "message": "User berhasil didaftarkan. Silakan cek email untuk verifikasi OTP.",
                    "token": token,
                    "data": db_response.data
                }), 201
                
            else:
                logging.error(f"Gagal registrasi: Auth response user bernilai None untuk email: {email}")
                return jsonify({"status": "error", "message": "User null, cek auth"}), 400
                
        except Exception as e:
            logging.error(f"Error pada proses registrasi email '{email}': {str(e)}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 400

    @register_blueprint.route('/verify-otp', methods=['POST'])
    def verify_otp():
        data = request.json
        email = data.get('email')
        otp_input = data.get('otp')

        logging.info(f"Menerima request verifikasi OTP untuk email: {email}")

        try:
            query = supabase.table("users").select("*").eq("email", email).execute()
            user_list = query.data

            if not user_list:
                logging.warning(f"Verifikasi OTP gagal: Email '{email}' tidak ditemukan")
                return jsonify({"status": "error", "message": "User tidak ditemukan"}), 404

            user = user_list[0]
            user_id = user.get('id')
            username = user.get('username')
            stored_otp = user.get('otp')
            stored_expired_str = user.get('otp_expired_at')

            if not stored_otp:
                logging.warning(f"Verifikasi OTP gagal: OTP sudah hangus/kosong di DB untuk email: {email}")
                return jsonify({"status": "error", "message": "Kode OTP sudah hangus atau tidak valid!"}), 400

            cleaned_time_str = stored_expired_str.replace('Z', '+00:00') if stored_expired_str else ""
            otp_expired_time = datetime.datetime.fromisoformat(cleaned_time_str)
            waktu_sekarang = datetime.datetime.now(timezone.utc)

            if waktu_sekarang > otp_expired_time:
                logging.warning(f"Verifikasi OTP gagal: OTP Kadaluarsa untuk email: {email}")
                supabase.table("users").update({"otp": None, "otp_expired_at": None}).eq("email", email).execute()
                return jsonify({"status": "error", "message": "Kode OTP sudah kadaluarsa (lebih dari 10 menit) bray!"}), 400

            if str(stored_otp) == str(otp_input):
                logging.info(f"OTP cocok! Memperbarui status 'is_verified' menjadi True untuk email: {email}")
                
                # --- 🔥 AMBIL DATA TOKEN LAMA ATAU GENERATE BARU BIAR FLUTTER TIDAK NULL 🔥 ---
                # Kita generate token baru yang fresh untuk login otomatis setelah OTP sukses
                payload = {
                    'user_id': user_id,
                    'email': email,
                    'exp': datetime.datetime.now(timezone.utc) + datetime.timedelta(days=7)
                }
                token_aktif = jwt.encode(payload, SECRET_KEY, algorithm='HS256')

                # Update status terverifikasi dan tempel token aktifnya di DB bray
                supabase.table("users").update({
                    "is_verified": True,
                    "token": token_aktif, # Update token terbaru ke DB
                    "otp": None,         
                    "otp_expired_at": None    
                }).eq("email", email).execute()

                # --- AKTIVITAS AUDIT LOG KE DATABASE ---
                try:
                    log_data = {
                        "user_id": user_id,
                        "activity": f"User {username} sukses memverifikasi kode OTP. Akun kini berstatus AKTIF bray.",
                        "ip_address": request.remote_addr,
                        "user_agent": request.headers.get('User-Agent', 'Unknown Device')
                    }
                    supabase.table('activity_logs').insert(log_data).execute()
                except Exception as log_error:
                    print(f"⚠️ WARNING LOGGING VERIFY: Gagal simpan log. Detail: {str(log_error)}")

                logging.info(f"Verifikasi sukses. Akun aktif untuk email: {email}")
                
                # --- SINKRONISASI DATANYA DI SINI BRAY! ---
                return jsonify({
                    "status": "success",
                    "message": "Verifikasi OTP Berhasil, akun kamu sudah aktif!",
                    "token": token_aktif, # Kunci penyelamat agar Flutter tidak membaca null
                    "data": [{
                        "id": user_id,
                        "email": email,
                        "username": username
                    }]
                }), 200
            else:
                logging.warning(f"Verifikasi OTP gagal: Input OTP salah untuk email: {email}")
                return jsonify({"status": "error", "message": "Kode OTP yang kamu masukkan salah bray!"}), 400

        except Exception as e:
            logging.error(f"Error pada verifikasi OTP email '{email}': {str(e)}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 400

    @register_blueprint.route('/resend-otp', methods=['POST'])
    def resend_otp():
        data = request.json
        email = data.get('email')

        if not email:
            return jsonify({"status": "error", "message": "Email tidak boleh kosong bray!"}), 400

        logging.info(f"Menerima request kirim ulang OTP untuk email: {email}")

        try:
            query = supabase.table("users").select("*").eq("email", email).execute()
            user_list = query.data

            if not user_list:
                logging.warning(f"Gagal resend OTP: Email '{email}' belum terdaftar")
                return jsonify({"status": "error", "message": "Email belum terdaftar di database bray!"}), 404

            user = user_list[0]
            user_id = user.get('id')
            username = user.get('username')

            if user.get('is_verified') == True:
                logging.warning(f"Gagal resend OTP: Akun email '{email}' terpantau sudah aktif")
                return jsonify({"status": "error", "message": "Akun ini sudah aktif bray, langsung login aja!"}), 400

            new_otp = generate_otp()
            waktu_expired = datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=10)
            otp_expired_at = waktu_expired.isoformat()

            msg = Message(subject="Kode OTP Baru Scoutify", recipients=[email])
            msg.body = f"Kamu telah meminta pengiriman ulang kode verifikasi. Berikut adalah kode OTP baru kamu:\n\n👉 {new_otp} 👈"
            mail.send(msg)
            logging.info(f"Email OTP baru berhasil dikirim ulang ke {email}")

            supabase.table("users").update({
                "otp": new_otp,
                "otp_expired_at": otp_expired_at
            }).eq("email", email).execute()

            # --- AKTIVITAS AUDIT LOG KE DATABASE ---
            try:
                log_data = {
                    "user_id": user_id,
                    "activity": f"User {username} meminta pengiriman ulang kode OTP registrasi.",
                    "ip_address": request.remote_addr,
                    "user_agent": request.headers.get('User-Agent', 'Unknown Device')
                }
                supabase.table('activity_logs').insert(log_data).execute()
            except Exception as log_error:
                print(f"⚠️ WARNING LOGGING RESEND: Gagal simpan log. Detail: {str(log_error)}")

            return jsonify({"status": "success", "message": "Kode OTP baru berhasil dikirim!"}), 200
        except Exception as e:
            logging.error(f"Error pada resend OTP email '{email}': {str(e)}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 400

    @register_blueprint.route('/resend-otp-reset', methods=['POST'])
    def resend_otp_reset():
        data = request.json
        email = data.get('email')

        if not email:
            return jsonify({"status": "error", "message": "Email tidak boleh kosong bray!"}), 400

        logging.info(f"Menerima request kirim ulang OTP (Reset Password) untuk email: {email}")

        try:
            query = supabase.table("users").select("*").eq("email", email).execute()
            user_list = query.data

            if not user_list:
                logging.warning(f"Gagal resend OTP reset: Email '{email}' tidak terdaftar")
                return jsonify({"status": "error", "message": "Email belum terdaftar bray!"}), 404

            user = user_list[0]
            user_id = user.get('id')
            username = user.get('username')

            new_otp = generate_otp()
            waktu_expired = datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=10)
            otp_expired_at = waktu_expired.isoformat()

            msg = Message(subject="Kode OTP Reset Password Scoutify", recipients=[email])
            msg.body = f"Berikut adalah kode OTP baru untuk mereset password akun Scoutify kamu bray:\n\n👉 {new_otp} 👈"
            mail.send(msg)
            logging.info(f"Email OTP Reset password berhasil dikirim ke {email}")

            supabase.table("users").update({
                "otp": new_otp,
                "otp_expired_at": otp_expired_at
            }).eq("email", email).execute()
            
            # --- AKTIVITAS AUDIT LOG KE DATABASE ---
            try:
                log_data = {
                    "user_id": user_id,
                    "activity": f"User {username} meminta kode OTP untuk keperluan reset password.",
                    "ip_address": request.remote_addr,
                    "user_agent": request.headers.get('User-Agent', 'Unknown Device')
                }
                supabase.table('activity_logs').insert(log_data).execute()
            except Exception as log_error:
                print(f"⚠️ WARNING LOGGING RESET: Gagal simpan log. Detail: {str(log_error)}")

            return jsonify({"status": "success", "message": "Kode OTP reset password berhasil dikirim ulang!"}), 200
        except Exception as e:
            logging.error(f"Error pada resend OTP reset email '{email}': {str(e)}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 400

    return register_blueprint