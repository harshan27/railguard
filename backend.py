"""
RailGuard ITMS Backend
----------------------
FastAPI backend for MongoDB Atlas integration.
Configured for local development and Render cloud hosting ($PORT binding).
"""

import os
from datetime import datetime, date
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson import ObjectId

# ============================================================
# CONFIGURATION
# ============================================================
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://tvkjeppiaar_db_user:AKFzxoFtV70bWTMW@itms-cluster.gjj7bgm.mongodb.net/?appName=ITMS-Cluster"
).strip()

DATABASE_NAME = "SIH25020"
COLLECTION_NAME = "sensor_data"

# ============================================================
# FASTAPI APP & CORS
# ============================================================
app = FastAPI(
    title="ITMS Railway Track Monitoring API",
    description="API for MongoDB sensor data used by RailGuard frontend.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# MONGODB CLIENT (Lazy connection with timeout)
# ============================================================
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]


def flatten_dict(data: dict, parent_key: str = "", separator: str = "_") -> dict:
    items = {}
    for key, value in data.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key
        if isinstance(value, dict):
            items.update(flatten_dict(value, new_key, separator))
        else:
            items[new_key] = value
    return items


def make_json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def get_flat_sensor_data(limit: int = 200) -> list[dict]:
    try:
        documents = list(collection.find().sort("timestamp", -1).limit(limit))
        return [make_json_safe(flatten_dict(doc)) for doc in documents]
    except Exception as exc:
        print(f"[MongoDB Error] {exc}")
        return []


# ============================================================
# API ENDPOINTS
# ============================================================
@app.get("/")
def root():
    return {
        "name": "ITMS Railway Track Monitoring API",
        "status": "running",
        "database": DATABASE_NAME,
        "collection": COLLECTION_NAME,
        "data_source": "MongoDB sensor_data",
    }


@app.get("/api/health")
def health():
    try:
        client.admin.command("ping")
        return {
            "status": "ok",
            "mongodb": "connected",
            "database": DATABASE_NAME,
            "collection": COLLECTION_NAME,
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "mongodb": "disconnected",
            "detail": str(exc),
        }


@app.get("/api/data")
def api_data(
    limit: int = Query(default=200, ge=1, le=1000)
):
    data = get_flat_sensor_data(limit)
    return {
        "count": len(data),
        "source": "MongoDB",
        "database": DATABASE_NAME,
        "collection": COLLECTION_NAME,
        "data": data,
    }


@app.get("/api/latest")
def api_latest():
    data = get_flat_sensor_data(1)
    if not data:
        return {"found": False, "data": None}
    return {"found": True, "data": data[0]}


@app.get("/api/count")
def api_count():
    try:
        total = collection.count_documents({})
        return {"total_records": total, "database": DATABASE_NAME, "collection": COLLECTION_NAME}
    except Exception as exc:
        return {"total_records": 0, "error": str(exc)}


# ============================================================
# SERVER ENTRYPOINT (Dynamic port for Render cloud)
# ============================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend:app", host="0.0.0.0", port=port, reload=False)