# interface/api.py
import json
from pathlib import Path
from flask import Blueprint, jsonify, request
from access_control.auth import login_required

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Ładujemy offline index z danych MacMap
INDEX_PATH = Path("data/tariffs/tobacco_index.json")
if INDEX_PATH.exists():
    with INDEX_PATH.open("r", encoding="utf-8") as f:
        TOBACCO_INDEX = json.load(f)
else:
    TOBACCO_INDEX = {}
    print("[WARN] brak pliku tobacco_index.json!")


@api_bp.route("/countries")
@login_required
def get_countries():
    geojson_path = Path("data/world_countries.geojson")
    if not geojson_path.exists():
        return jsonify({"type": "FeatureCollection", "features": []})

    with geojson_path.open("r", encoding="utf-8") as f:
        return jsonify(json.load(f))


@api_bp.route("/tariffs")
@login_required
def get_tariffs():
    """Zwraca stawki celne z offline tobacco_index.json"""
    reporter = request.args.get("from")
    if not reporter:
        return jsonify({"error": "Missing 'from' parameter (ISO3)"}), 400

    reporter = reporter.upper()

    # HS chapter 24 (tytoń)
    chapter = "24"

    chapter_data = TOBACCO_INDEX.get(chapter, {})
    reporter_data = chapter_data.get(reporter, {})

    tariffs = []
    for partner_iso3, entry in reporter_data.items():
        tariffs.append({
            "partner": partner_iso3,
            "rate": entry.get("rate"),
            "year": entry.get("year"),
        })

    return jsonify({
        "reporter": reporter,
        "product": {"classification": "HS", "code": chapter},
        "source": "Offline MacMap dataset",
        "tariffs": tariffs,
        "year": max([t["year"] for t in tariffs], default=None)
    })
