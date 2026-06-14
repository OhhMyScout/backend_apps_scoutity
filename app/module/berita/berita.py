import os
import math
import re


from bson import ObjectId
from dotenv import load_dotenv
from fastapi import APIRouter
from pymongo import MongoClient

load_dotenv()

router = APIRouter(tags=["Berita"])

# ==========================================================
# MONGODB CONFIG
# ==========================================================
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION")

client = MongoClient(MONGO_URI)

db = client[MONGO_DB]
collection = db[MONGO_COLLECTION]




LIST_PROVINSI = [
    "Aceh",
    "Sumatera Utara",
    "Sumatera Barat",
    "Riau",
    "Kepulauan Riau",
    "Jambi",
    "Sumatera Selatan",
    "Bangka Belitung",
    "Bengkulu",
    "Lampung",
    "DKI Jakarta",
    "Jakarta",
    "Jawa Barat",
    "Banten",
    "Jawa Tengah",
    "DI Yogyakarta",
    "Yogyakarta",
    "Jawa Timur",
    "Bali",
    "Nusa Tenggara Barat",
    "NTB",
    "Nusa Tenggara Timur",
    "NTT",
    "Kalimantan Barat",
    "Kalimantan Tengah",
    "Kalimantan Selatan",
    "Kalimantan Timur",
    "Kalimantan Utara",
    "Sulawesi Utara",
    "Gorontalo",
    "Sulawesi Tengah",
    "Sulawesi Barat",
    "Sulawesi Selatan",
    "Sulawesi Tenggara",
    "Maluku",
    "Maluku Utara",
    "Papua",
    "Papua Barat",
]


def cari_provinsi(judul, ringkasan):

    teks = f"{judul} {ringkasan}".lower()

    for prov in LIST_PROVINSI:

        pola_regex = rf"\b{re.escape(prov.lower())}\b"

        if re.search(pola_regex, teks):

            if "jakarta" in prov.lower():
                return "DKI Jakarta"

            if "yogyakarta" in prov.lower():
                return "DI Yogyakarta"

            if prov.lower() == "ntb":
                return "Nusa Tenggara Barat"

            if prov.lower() == "ntt":
                return "Nusa Tenggara Timur"

            return prov

    return "Tidak Disebutkan"


# ==========================================================
# CLEAN DATA
# ==========================================================
def clean_data(obj):

    if isinstance(obj, dict):
        return {k: clean_data(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [clean_data(v) for v in obj]

    if isinstance(obj, float):
        if math.isnan(obj):
            return None

        if math.isinf(obj):
            return None

    return obj


# ==========================================================
# SERIALIZE DOCUMENT
# ==========================================================
def serialize_document(doc):

    doc["_id"] = str(doc["_id"])

    return clean_data(doc)


# ==========================================================
# GET ALL BERITA
# ==========================================================
@router.get("/berita")
async def get_berita():

    try:

        data = []

        cursor = collection.find()

        for item in cursor:
            data.append(
                serialize_document(item)
            )

        return {
            "success": True,
            "total": len(data),
            "data": data
        }

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }





# ==========================================================
# BERITA POPULER
# ==========================================================
@router.get("/berita/populer")
async def berita_populer():

    try:

        data = []

        cursor = collection.find().sort(
            "total_dilihat",
            -1
        ).limit(10)

        for item in cursor:
            data.append(
                serialize_document(item)
            )

        return {
            "success": True,
            "total": len(data),
            "data": data
        }

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }


# ==========================================================
# SEARCH BERITA
# ==========================================================
@router.get("/berita/search/{keyword}")
async def search_berita(keyword: str):

    try:

        data = []

        cursor = collection.find({
            "$or": [
                {
                    "judul": {
                        "$regex": keyword,
                        "$options": "i"
                    }
                },
                {
                    "ringkasan": {
                        "$regex": keyword,
                        "$options": "i"
                    }
                }
            ]
        })

        for item in cursor:
            data.append(
                serialize_document(item)
            )

        return {
            "success": True,
            "keyword": keyword,
            "total": len(data),
            "data": data
        }

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }


# ==========================================================
# SEBARAN PROVINSI
# ==========================================================
@router.get("/berita/provinsi")
async def sebaran_provinsi():

    try:

        hasil = {}

        for berita in collection.find():

            judul = berita.get("judul", "")
            ringkasan = berita.get("ringkasan", "")

            provinsi = cari_provinsi(
                judul,
                ringkasan
            )

            if provinsi == "Tidak Disebutkan":
                continue

            hasil[provinsi] = hasil.get(provinsi, 0) + 1

        data = []

        for provinsi, jumlah in hasil.items():

            data.append({
                "provinsi": provinsi,
                "jumlah_berita": jumlah
            })

        data.sort(
            key=lambda x: x["jumlah_berita"],
            reverse=True
        )

        return {
            "success": True,
            "total": len(data),
            "data": data
        }

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        } 


# ==========================================================
# TOP 10 PROVINSI
# ==========================================================
@router.get("/berita/provinsi/top10")
async def top_10_provinsi():

    try:

        hasil = {}

        for berita in collection.find():

            judul = berita.get("judul", "")
            ringkasan = berita.get("ringkasan", "")

            provinsi = cari_provinsi(
                judul,
                ringkasan
            )

            if provinsi == "Tidak Disebutkan":
                continue

            hasil[provinsi] = hasil.get(provinsi, 0) + 1

        data = []

        for provinsi, jumlah in hasil.items():

            data.append({
                "provinsi": provinsi,
                "jumlah_berita": jumlah
            })

        data.sort(
            key=lambda x: x["jumlah_berita"],
            reverse=True
        )

        return {
            "success": True,
            "total": min(10, len(data)),
            "data": data[:10]
        }

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }


# ==========================================================
# DETAIL BERITA
# ==========================================================
@router.get("/berita/detail/{berita_id}")
async def get_berita_by_id(berita_id: str):

    try:

        berita = collection.find_one({
            "_id": ObjectId(berita_id)
        })

        if not berita:
            return {
                "success": False,
                "message": "Berita tidak ditemukan"
            }

        return {
            "success": True,
            "data": serialize_document(berita)
        }

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }


# ==========================================================
# INIT ROUTER
# ==========================================================
def init_berita_router():
    return router