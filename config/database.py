import os
from dotenv import load_dotenv
from supabase import create_client

# Load file .env yang ada di folder root
load_dotenv()

# Ambil data dari .env menggunakan os.getenv
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def get_supabase_client():
    # Pastikan variabel tidak None sebelum di-strip
    url = SUPABASE_URL.strip().rstrip('/') if SUPABASE_URL else ""
    key = SUPABASE_KEY.strip() if SUPABASE_KEY else ""
    
    return create_client(url, key)