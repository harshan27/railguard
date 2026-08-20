"""
ITMS Backend
-----------
FastAPI backend for the RailGuard frontend.

This backend uses the SAME MongoDB source and data structure as app.py:
    Database   : SIH25020
    Collection : sensor_data

It does not create sample/mock sensor data.

The MongoDB documents are flattened in the same way as app.py:
    imu -> imu_ax, imu_ay, ...
    movement -> movement_...
    geometry -> geometry_...
    rail_wear -> rail_wear_...
    crack_detection -> crack_detection_...
    location -> location_latitude, location_longitude, ...

Frontend endpoint:
    GET http://localhost:8000/api/data

Run:
    pip install fastapi uvicorn pymongo
    python backend.py
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

# Use the same MongoDB URI that you use in app.py.
# Recommended:
#   Windows CMD:
#       set MONGO_URI=mongodb+srv://tvkjeppiaar_db_user:AKFzxoFtV70bWTMW@itms-cluster.gjj7bgm.mongodb.net/?appName=ITMS-Cluster
#
#   PowerShell:
#       $env:MONGO_URI="mongodb+srv://tvkjeppiaar_db_user:AKFzxoFtV70bWTMW@itms-cluster.gjj7bgm.mongodb.net/?appName=ITMS-Cluster""
#
MONGO_URI = os.getenv("MONGO_URI", "").strip()

DATABASE_NAME = "SIH25020"
COLLECTION_NAME = "sensor_data"

if not MONGO_URI:
    raise RuntimeError(
        "MONGO_URI is not set. Set the same MongoDB Atlas connection "
        "string that you use in app.py."
    )


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="ITMS Railway Track Monitoring API",
    description="API for MongoDB sensor data used by the ITMS frontend.",
    version="1.0.0",
)

# Allows the HTML frontend to call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# MONGODB CONNECTION
# ============================================================

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)

    # Same database and collection as app.py
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    # Check the connection when the backend starts.
    client.admin.command("ping")

except Exception as exc:
    raise RuntimeError(
        f"MongoDB connection failed: {exc}"
    ) from exc


# ============================================================
# SAME FLATTENING LOGIC AS app.py
# ============================================================

def flatten_dict(data: dict, parent_key: str = "", separator: str = "_") -> dict:
    """
    Same concept as app.py.

    Example:
        {
            "imu": {
                "ax": 1,
                "ay": 2
            }
        }

    becomes:
        {
            "imu_ax": 1,
            "imu_ay": 2
        }
    """

    items = {}

    for key, value in data.items():

        new_key = (
            f"{parent_key}{separator}{key}"
            if parent_key
            else key
        )

        if isinstance(value, dict):
            items.update(
                flatten_dict(
                    value,
                    new_key,
                    separator
                )
            )
        else:
            items[new_key] = value

    return items


# ============================================================
# JSON SERIALIZATION
# ============================================================

def make_json_safe(value: Any) -> Any:
    """
    Convert MongoDB/Python values into values that can be returned
    safely as JSON.
    """

    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): make_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            make_json_safe(item)
            for item in value
        ]

    # Handle values such as numpy scalar values if they ever occur.
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return value


# ============================================================
# LOAD SENSOR DATA
# ============================================================

def get_sensor_documents(limit: int = 200) -> list[dict]:
    """
    Read the latest sensor records exactly like app.py:
        collection.find()
                 .sort("timestamp", -1)
                 .limit(200)

    No sample data is generated.
    """

    try:
        documents = list(
            collection
            .find()
            .sort("timestamp", -1)
            .limit(limit)
        )

        return documents

    except PyMongoError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read sensor_data: {exc}"
        )


def get_flat_sensor_data(limit: int = 200) -> list[dict]:
    """
    Flatten every MongoDB document using the same flattening approach
    as app.py.
    """

    documents = get_sensor_documents(limit)

    flat_data = [
        flatten_dict(document)
        for document in documents
    ]

    return [
        make_json_safe(document)
        for document in flat_data
    ]


# ============================================================
# API: HEALTH CHECK
# ============================================================

@app.get("/")
def root():
    return {
        "name": "ITMS Railway Track Monitoring API",
        "status": "running",
        "database": DATABASE_NAME,
        "collection": COLLECTION_NAME,
        "data_source": "MongoDB sensor_data",
        "sample_data": False,
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
            "sample_data": False,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MongoDB is not available: {exc}"
        )


# ============================================================
# API: ALL SENSOR DATA
# ============================================================

@app.get("/api/data")
def api_data(
    limit: int = Query(
        default=200,
        ge=1,
        le=1000,
        description="Number of latest MongoDB sensor records."
    )
):
    """
    Main endpoint for index.html.

    Returns only data actually present in MongoDB.

    Example response shape:

    {
        "count": 1,
        "source": "MongoDB",
        "database": "SIH25020",
        "collection": "sensor_data",
        "data": [
            {
                "device_id": "...",
                "temperature": 31.5,
                "overall_status": "...",
                "imu_ax": ...,
                "imu_ay": ...,
                "imu_az": ...,
                "movement_...": ...,
                "geometry_...": ...,
                "rail_wear_...": ...,
                "crack_detection_...": ...,
                "location_latitude": 12.34,
                "location_longitude": 78.90,
                "timestamp": "..."
            }
        ]
    }
    """

    data = get_flat_sensor_data(limit)

    return {
        "count": len(data),
        "source": "MongoDB",
        "database": DATABASE_NAME,
        "collection": COLLECTION_NAME,
        "sample_data": False,
        "data": data,
    }


# ============================================================
# API: LATEST SINGLE RECORD
# ============================================================

@app.get("/api/latest")
def api_latest():
    """
    Returns the newest sensor record from MongoDB.
    """

    data = get_flat_sensor_data(1)

    if not data:
        return {
            "found": False,
            "data": None,
        }

    return {
        "found": True,
        "data": data[0],
    }


# ============================================================
# API: AVAILABLE FIELDS
# ============================================================

@app.get("/api/fields")
def api_fields():
    """
    Returns the actual flattened field names present in the latest
    MongoDB sensor records.

    This lets the frontend know which geometry, IMU, movement,
    rail-wear and crack-detection parameters really exist.
    """

    data = get_flat_sensor_data(200)

    fields = set()

    for record in data:
        fields.update(record.keys())

    fields = sorted(fields)

    return {
        "count": len(fields),
        "fields": fields,
        "groups": {
            "imu": [
                field for field in fields
                if field.startswith("imu_")
            ],
            "movement": [
                field for field in fields
                if field.startswith("movement_")
            ],
            "geometry": [
                field for field in fields
                if field.startswith("geometry_")
            ],
            "rail_wear": [
                field for field in fields
                if field.startswith("rail_wear_")
            ],
            "crack_detection": [
                field for field in fields
                if field.startswith("crack_detection_")
            ],
            "location": [
                field for field in fields
                if field.startswith("location_")
            ],
        },
    }


# ============================================================
# API: DATABASE COUNT
# ============================================================

@app.get("/api/count")
def api_count():
    """
    Same source used by app.py's Total Records metric.
    """

    try:
        total = collection.count_documents({})

        return {
            "total_records": total,
            "database": DATABASE_NAME,
            "collection": COLLECTION_NAME,
        }

    except PyMongoError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not count sensor records: {exc}"
        )


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
