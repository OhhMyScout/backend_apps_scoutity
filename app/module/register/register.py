import os
import jwt
import datetime
import traceback
from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt
from config.database import get_supabase_client
from dotenv import load_dotenv

# Muat file .env
load_dotenv()

register_blueprint = Blueprint('register', __name__)
supabase = get_supabase_client()
bcrypt = Bcrypt()

# Ambil SECRET_KEY dari .env (scoutify_pahri_husen_milik_allah)
SECRET_KEY = os.getenv("SECRET_KEY")

@register_blueprint.route('/register', methods=['POST'])
def register_user():
    data = request.json
    
    print("\n--- DEBUG: REQUEST DATA MASUK ---")
    print(f"Data: {data}")

    email = data.get('email')
    password = data.get('password')
    username = data.get('username')
    fullname = data.get('fullname')
    provinsi = data.get('provinsi')
    role = data.get('role', 'user')

    try:
        # 1. Hashing Password
        print("--- DEBUG: PROSES HASHING PASSWORD ---")
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # 2. Registrasi ke Supabase Auth
        print("--- DEBUG: MENCOBA SUPABASE AUTH SIGNUP ---")
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password,  # Auth internal butuh password asli
        })
        print(f"Auth Response User: {auth_response.user}")

        if auth_response.user is not None:
            # 3. Generate JWT Token
            print("--- DEBUG: GENERATING JWT TOKEN ---")
            payload = {
                'user_id': auth_response.user.id,
                'email': email,
                'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7) # Token aktif 7 hari
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')

            # 4. Simpan Data Lengkap ke Tabel users (termasuk hash password & token)
            print("--- DEBUG: MENYIAPKAN DATA TABEL ---")
            user_data = {
                "username": username,
                "fullname": fullname,
                "email": email,
                "provinsi": provinsi,
                "password": hashed_password, # Simpan versi hash
                "token": token,            # Simpan token agar tidak perlu login lagi
                "role": role,
                "points": 0,
                "images": data.get('images', 'default_profile.png')
            }
            
            print(f"Mencoba insert ke tabel 'users'...")
            db_response = supabase.table("users").insert(user_data).execute()
            print(f"Database Response: {db_response.data}")

            return jsonify({
                "status": "success",
                "message": "User berhasil didaftarkan",
                "token": token,
                "data": db_response.data
            }), 201
            
        else:
            return jsonify({"status": "error", "message": "User null, cek auth"}), 400
            
    except Exception as e:
        print("\n!!!!!!!! DEBUG: TERJADI ERROR !!!!!!!!")
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400