from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

# ==========================================================
# MONGODB CONFIG
# ==========================================================
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION")

client = MongoClient(MONGO_URI)

db = client[MONGO_DB]
collection = db[MONGO_COLLECTION]

# ==========================================================
# REMOVE FIELDS
# ==========================================================
result = collection.update_many(
    {},
    {
        "$unset": {
            "tanggal_publikasi": "",
            "tahun_publikasi": ""
        }
    }
)

print("=" * 50)
print("MongoDB Cleanup Success")
print(f"Matched Documents : {result.matched_count}")
print(f"Modified Documents: {result.modified_count}")
print("=" * 50)

# ==========================================================
# SAMPLE DATA
# ==========================================================
sample = collection.find_one()

if sample:
    sample["_id"] = str(sample["_id"])
    print(sample)