#!/usr/bin/env python3
"""
telemetry_server.py

Simple HTTP service that receives JSON telemetry events from the SDL2 maze game
and inserts them into a MongoDB database.

- Listens on POST /events
- Accepts JSON payloads
- Stores each payload as a MongoDB document
"""

from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime

# ------------------------------------------------------------
# Flask application setup
# ------------------------------------------------------------

app = Flask(__name__)

# ------------------------------------------------------------
# MongoDB configuration
# ------------------------------------------------------------

MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "maze_telemetry"
MONGO_COLLECTION = "maze_input_data"

# Create MongoDB client and collection reference
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB_NAME]
mongo_collection = mongo_db[MONGO_COLLECTION]

# ------------------------------------------------------------
# HTTP endpoint to receive telemetry
# ------------------------------------------------------------

@app.route("/events", methods=["POST"])
def receive_event():
    """
    Receives a JSON telemetry event from the maze application
    and inserts it into MongoDB.
    """

    # Ensure request contains JSON
    if not request.is_json:
        return jsonify({"error": "Invalid JSON"}), 400

    # Parse JSON payload
    event_data = request.get_json()

    # Add server-side timestamp (useful for auditing/debugging)
    event_data["server_received_at"] = datetime.utcnow()

    # Insert into MongoDB
    try:
        mongo_collection.insert_one(event_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Return success response
    return jsonify({"status": "ok"}), 200

# ------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------

if __name__ == "__main__":
    """
    Start the HTTP server.

    The maze application expects:
    - Host: localhost
    - Port: 8080
    - Path: /events
    """

    app.run(
        host="0.0.0.0",
        port=8080,
        debug=True
    )
