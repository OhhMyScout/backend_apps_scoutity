import os
import jwt
import traceback
from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt
from config.database import get_supabase_client
from dotenv import load_dotenv

load_dotenv()

login_blueprint = Blueprint('login', __name__)
supabase = get_supabase_client()
bcrypt = Bcrypt()

SECRET_KEY = os.getenv("SECRET_KEY")

@login_blueprint.route('/login', methods=['POST'])
def login_user():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    print(f"\n--- DEBUG: PROSES LOGIN {email} ---")

    try:
        # 1. Cari user di tabel berdasarkan email
        query = supabase.table("users").select("*").eq("email", email).execute()
        user_list = query.data

        if not user_list:
            return jsonify({"status": "error", "message": "Email tidak terdaftar"}), 404

        user = user_list[0]
        stored_hash = user.get('password')

        # 2. Cek apakah password cocok dengan Hash di DB
        if bcrypt.check_password_hash(stored_hash, password):
            print("--- DEBUG: PASSWORD COCOK ---")
            
            # 3. Kembalikan token yang sudah ada atau buat baru jika perlu
            return jsonify({
                "status": "success",
                "message": "Login berhasil",
                "token": user.get('token'),
                "user": {
                    "username": user.get('username'),
                    "fullname": user.get('fullname'),
                    "role": user.get('role')
                }
            }), 200
        else:
            print("--- DEBUG: PASSWORD SALAH ---")
            return jsonify({"status": "error", "message": "Password salah"}), 401

    except Exception as e:
        print("\n!!!!!!!! DEBUG: ERROR LOGIN !!!!!!!!")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 400