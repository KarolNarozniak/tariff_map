# interface/api.py
import json
from pathlib import Path
from flask import Blueprint, jsonify, request
from access_control.auth import login_required
from application.tariff_map_service import TariffMapService

api_bp = Blueprint("api", __name__, url_prefix="/api")

_tariff_service = TariffMapService()


@api_bp.route("/countries")
@login_required
def get_countries():
    """
    Zwraca GeoJSON z krajami.
    Wczytujemy plik i NORMALIZUJEMY nazwy właściwości do:
      - ISO_A3 (kod kraju)
      - ADMIN  (nazwa kraju)
    żeby frontend działał niezależnie od wariantów źródła.
    """
    geojson_path = Path("data/world_countries.geojson")

    # fallback placeholder (gdy brak pliku)
    if not geojson_path.exists():
        sample_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"ADMIN": "Poland", "ISO_A3": "POL"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[19, 54], [24, 54], [24, 49], [19, 49], [19, 54]]],
                    },
                },
                {
                    "type": "Feature",
                    "properties": {"ADMIN": "Germany", "ISO_A3": "DEU"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[8, 55], [14, 55], [14, 48], [8, 48], [8, 55]]],
                    },
                },
            ],
        }
        return jsonify(sample_geojson)

    # wczytaj Twój geojson
    with geojson_path.open("r", encoding="utf-8") as f:
        gj = json.load(f)

    # normalizacja właściwości
    for feat in gj.get("features", []):
        props = feat.setdefault("properties", {})

        # ISO3
        if "ISO_A3" not in props:
            if "iso_a3" in props:
                props["ISO_A3"] = props["iso_a3"]
            elif "adm0_a3" in props:
                props["ISO_A3"] = props["adm0_a3"]
            elif "ISO3" in props:
                props["ISO_A3"] = props["ISO3"]

        # Nazwa
        if "ADMIN" not in props:
            if "name" in props:
                props["ADMIN"] = props["name"]
            elif "NAME" in props:
                props["ADMIN"] = props["NAME"]
            elif "ADMIN_NAME" in props:
                props["ADMIN"] = props["ADMIN_NAME"]
            elif "COUNTRY" in props:
                props["ADMIN"] = props["COUNTRY"]

    return jsonify(gj)


@api_bp.route("/tariffs")
@login_required
def get_tariffs():
    """
    Zwraca stawki celne na tytoń dla wybranego kraju (reporter).
    Parametr: ?from=POL (ISO3).
    """
    reporter = request.args.get("from")
    if not reporter:
        return jsonify({"error": "Missing 'from' parameter (ISO3)"}), 400

    payload = _tariff_service.as_api_payload(reporter_iso3=reporter)
    return jsonify(payload)
