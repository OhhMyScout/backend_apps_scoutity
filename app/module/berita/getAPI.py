from flask import Blueprint, jsonify
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
import os

# =========================================
# LOAD ENV
# =========================================
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION")

# =========================================
# CONNECT MONGODB
# =========================================
client = MongoClient(MONGO_URI)

db = client[MONGO_DB]
collection = db[MONGO_COLLECTION]

# =========================================
# BLUEPRINT
# =========================================
get_api_bp = Blueprint("get_api", __name__)

# =========================================
# GET ALL DATA
# =========================================
@get_api_bp.route("/api/berita", methods=["GET"])
def get_berita():
    try:
        data = []

        for item in collection.find():
            item["_id"] = str(item["_id"])
            data.append(item)

        return jsonify({
            "success": True,
            "total": len(data),
            "data": data
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================
# GET BERITA BY ID
# =========================================
@get_api_bp.route("/api/berita/<id>", methods=["GET"])
def get_berita_by_id(id):
    try:
        berita = collection.find_one({"_id": ObjectId(id)})

        if not berita:
            return jsonify({
                "success": False,
                "message": "Data tidak ditemukan"
            }), 404

        berita["_id"] = str(berita["_id"])

        return jsonify({
            "success": True,
            "data": berita
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500