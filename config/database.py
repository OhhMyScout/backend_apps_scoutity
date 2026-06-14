# import os
# from dotenv import load_dotenv
# from supabase import create_client

# # Load file .env yang ada di folder root
# load_dotenv()

# # Ambil data dari .env menggunakan os.getenv
# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# def get_supabase_client():
#     # Pastikan variabel tidak None sebelum di-strip
#     url = SUPABASE_URL.strip().rstrip('/') if SUPABASE_URL else ""
#     key = SUPABASE_KEY.strip() if SUPABASE_KEY else ""
    
#     return create_client(url, key)


import os
from supabase import create_client, Client
from dotenv import load_dotenv

# load_dotenv() dipanggil di sini agar .env terbaca saat file ini di-import
load_dotenv()


def get_supabase_client() -> Client:
    """
    Mendapatkan Supabase client instance
    """
    # Pastikan nama variabel di bawah ini sama persis dengan yang di file .env
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")

    if not supabase_url or not supabase_key:
        # Ini akan mencetak variabel mana yang hilang untuk memudahkan debugging
        print(f"DEBUG URL: {supabase_url}")
        print(f"DEBUG KEY: {supabase_key}")
        raise ValueError(
            "SUPABASE_URL dan SUPABASE_ANON_KEY harus ada di file .env"
        )

    return create_client(supabase_url, supabase_key)


# Singleton instance
supabase_client = None


def get_supabase() -> Client:
    """
    Mendapatkan singleton Supabase client
    """
    global supabase_client
    if supabase_client is None:
        supabase_client = get_supabase_client()
    return supabase_client