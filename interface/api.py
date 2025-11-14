# interface/api.py
import json
from pathlib import Path
from flask import Blueprint, jsonify, request
from access_control.auth import login_required
import heapq
import math

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
    """
    Zwraca stawki celne dla HS 24 z offline tobacco_index.json.

    Parametry:
      ?from=USA (ISO3 reportera)
    """
    reporter = request.args.get("from")
    if not reporter:
        return jsonify({"error": "Missing 'from' parameter (ISO3)"}), 400

    reporter = reporter.upper()
    chapter = "24"  # HS chapter dla tytoniu

    chapter_data = TOBACCO_INDEX.get(chapter, {})
    reporter_data = chapter_data.get(reporter, {})

    tariffs = []
    for partner_iso3, entry in reporter_data.items():
        raw_rate = entry.get("rate")
        year = entry.get("year")
        if raw_rate is None:
            continue

        # MacMap: wartości są w ułamkach (np. 0.30 = 30%)
        rate_pct = float(raw_rate) * 100.0

        tariffs.append({
            "reporter": reporter,
            "partner": partner_iso3,
            "rate": rate_pct,
            "year": year,
            "unit": "percent",
        })

    return jsonify({
        "reporter": reporter,
        "product": {"classification": "HS", "code": chapter},
        "source": "Offline MacMap dataset (Effectively applied, min, HS6, aggregated bilaterally)",
        "tariffs": tariffs,
        "year": max((t["year"] for t in tariffs if t["year"]), default=None),
    })


@api_bp.route("/logistics_nodes")
@login_required
def get_logistics_nodes():
    """
    Zwraca punkty logistyczne (porty, lotniska itd.) jako GeoJSON.
    Dane trzymamy w data/logistics_nodes.json + opcjonalnie data/logistics_nodes_extra.json
    """
    def _read_features(p: Path):
        if not p.exists():
            return []
        with p.open("r", encoding="utf-8") as f:
            gj = json.load(f)
        feats = gj.get("features", [])
        return [feat for feat in feats if isinstance(feat, dict)]

    base_feats = _read_features(Path("data/logistics_nodes.json"))
    extra_feats = _read_features(Path("data/logistics_nodes_extra.json"))
    cities_feats = _read_features(Path("data/logistics_cities.json"))

    # dedupe by properties.id when present
    merged = []
    seen = set()
    for feat in base_feats + extra_feats + cities_feats:
        props = feat.get("properties", {}) if isinstance(feat, dict) else {}
        fid = props.get("id")
        if fid is None:
            merged.append(feat)
        else:
            if fid in seen:
                continue
            seen.add(fid)
            merged.append(feat)

    return jsonify({"type": "FeatureCollection", "features": merged})


# --------- Graf logistyczny: węzły (kraje + huby) i krawędzie ----------

def _haversine_km(lon1, lat1, lon2, lat2):
    R = 6371.0088  # km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _geometry_centroid_ll(geometry):
    """
    Prosty centroid w [lon, lat] dla Polygon/MultiPolygon – średnia po wszystkich wierzchołkach.
    Wystarczające do przybliżeń bez użycia zewnętrznych bibliotek.
    """
    if not geometry:
        return None
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    lons, lats = [], []

    def _collect(poly):
        # poly: lista pierścieni, pierwszy to obwiednia (ignorujemy otwory)
        if not poly:
            return
        ring = poly[0]
        for pt in ring:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                lons.append(float(pt[0]))
                lats.append(float(pt[1]))

    if gtype == "Polygon":
        _collect(coords)
    elif gtype == "MultiPolygon":
        for poly in coords or []:
            _collect(poly)
    elif gtype == "Point":
        if coords and len(coords) >= 2:
            return [float(coords[0]), float(coords[1])]

    if not lons:
        return None
    return [sum(lons) / len(lons), sum(lats) / len(lats)]


def _load_countries_nodes():
    path = Path("data/world_countries.geojson")
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    nodes = []
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        iso3 = None
        for key in ("ISO_A3", "iso_a3", "adm0_a3", "wb_a3", "gu_a3", "ISO3", "ADM0_A3"):
            v = props.get(key)
            if v and str(v).upper() not in ("-99", "UNK"):
                iso3 = str(v).upper()
                break
        if not iso3:
            continue
        name = (
            props.get("ADMIN")
            or props.get("NAME")
            or props.get("NAME_LONG")
            or props.get("name")
            or props.get("SOVEREIGNT")
            or props.get("COUNTRY")
            or iso3
        )
        centroid = _geometry_centroid_ll(feat.get("geometry"))
        if not centroid:
            continue
        lon, lat = centroid
        nodes.append({
            "id": f"COUNTRY_{iso3}",
            "name": name,
            "kind": "country",
            "country": name,
            "iso3": iso3,
            "coordinates": [lon, lat],
        })
    return nodes


def _load_hubs_nodes():
    def _read_file(p: Path):
        if not p.exists():
            return []
        with p.open("r", encoding="utf-8") as f:
            gj = json.load(f)
        out = []
        for feat in gj.get("features", []):
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            if (geom or {}).get("type") != "Point":
                continue
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            out.append({
                "id": str(props.get("id") or props.get("name")),
                "name": str(props.get("name") or props.get("id") or "hub"),
                "kind": str(props.get("kind") or "hub"),
                "country": props.get("country"),
                "iso3": props.get("iso3"),
                "coordinates": [float(coords[0]), float(coords[1])],
            })
        return out

    base_nodes = _read_file(Path("data/logistics_nodes.json"))
    extra_nodes = _read_file(Path("data/logistics_nodes_extra.json"))
    city_nodes = _read_file(Path("data/logistics_cities.json"))
    merged = {}
    for n in base_nodes + extra_nodes + city_nodes:
        merged[n["id"]] = n  # dedupe by id (extra can extend, but base wins if same id order-wise)
    return list(merged.values())


def _load_sea_waypoints():
    """
    Ładuje węzły morskie (waypointy) i ich sąsiedztwa (z właściwości 'neighbors').
    Zwraca (nodes, edge_pairs) gdzie edge_pairs to lista (id_a, id_b) – połączenia dwukierunkowe.
    """
    path = Path("data/sea_waypoints.json")
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    nodes = []
    pairs = set()
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        if (geom or {}).get("type") != "Point":
            continue
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        nid = str(props.get("id") or props.get("name"))
        nodes.append({
            "id": nid,
            "name": str(props.get("name") or nid),
            "kind": "sea_waypoint",
            "country": None,
            "iso3": None,
            "coordinates": [float(coords[0]), float(coords[1])],
        })
        for nb in (props.get("neighbors") or []):
            a, b = nid, str(nb)
            key = tuple(sorted((a, b)))
            pairs.add(key)
    return nodes, list(pairs)


def _load_countries_nodes_with_boundaries(quant_prec: int = 3):
    """
    Ładuje kraje jako węzły oraz zbiera zewnętrzne pierścienie granic (uprośc.
    jako zbiory zquantowanych punktów) w celu wykrywania sąsiedztwa lądowego.
    Zwraca (nodes, boundaries) gdzie boundaries to dict: node_id -> set(str_keys).
    """
    path = Path("data/world_countries.geojson")
    if not path.exists():
        return [], {}
    with path.open("r", encoding="utf-8") as f:
        gj = json.load(f)

    def qkey(lon, lat):
        return f"{round(float(lon), quant_prec)},{round(float(lat), quant_prec)}"

    nodes = []
    boundaries = {}
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        iso3 = None
        for key in ("ISO_A3", "iso_a3", "adm0_a3", "wb_a3", "gu_a3", "ISO3", "ADM0_A3"):
            v = props.get(key)
            if v and str(v).upper() not in ("-99", "UNK"):
                iso3 = str(v).upper()
                break
        if not iso3:
            continue

        name = (
            props.get("ADMIN")
            or props.get("NAME")
            or props.get("NAME_LONG")
            or props.get("name")
            or props.get("SOVEREIGNT")
            or props.get("COUNTRY")
            or iso3
        )
        centroid = _geometry_centroid_ll(feat.get("geometry"))
        if not centroid:
            continue
        lon, lat = centroid
        node_id = f"COUNTRY_{iso3}"
        nodes.append({
            "id": node_id,
            "name": name,
            "kind": "country",
            "country": name,
            "iso3": iso3,
            "coordinates": [lon, lat],
        })

        # Zbierz punkty z pierwszych pierścieni wszystkich poligonów
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        bset = set()
        if gtype == "Polygon":
            ring = (coords or [None])[0] or []
            for pt in ring:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    bset.add(qkey(pt[0], pt[1]))
        elif gtype == "MultiPolygon":
            for poly in coords or []:
                ring = (poly or [None])[0] or []
                for pt in ring:
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        bset.add(qkey(pt[0], pt[1]))
        boundaries[node_id] = bset

    return nodes, boundaries


def _build_graph(factor_road: float, factor_sea: float, factor_air: float, k_sea: int, k_air: int):
    # Kraje i granice lądowe
    countries, country_boundaries = _load_countries_nodes_with_boundaries()
    # Huby (porty, lotniska)
    hubs = _load_hubs_nodes()
    ports = [h for h in hubs if h.get("kind") == "seaport"]
    airports = [h for h in hubs if h.get("kind") == "air_cargo"]
    cities = [h for h in hubs if h.get("kind") == "city"]
    # Waypointy morskie i ich połączenia
    sea_nodes, sea_pairs = _load_sea_waypoints()
    # Indeks węzłów
    id_to_node = {n["id"]: n for n in (countries + hubs + sea_nodes)}

    edges = []

    # kraj <-> najbliższy port i lotnisko
    for c in countries:
        clon, clat = c["coordinates"]
        c_iso = c.get("iso3")
        # port – tylko w tym samym kraju (unikamy "drogi przez morze")
        ports_in_country = [p for p in ports if (p.get("iso3") or "").upper() == (c_iso or "").upper()]
        if ports_in_country:
            best_p = None
            best_d = 1e18
            for p in ports_in_country:
                plon, plat = p["coordinates"]
                d = _haversine_km(clon, clat, plon, plat)
                if d < best_d:
                    best_d, best_p = d, p
            if best_p is not None:
                w = best_d * factor_road
                edges.append({"source": c["id"], "target": best_p["id"], "transport": "road", "distance_km": best_d, "weight": w})
                edges.append({"source": best_p["id"], "target": c["id"], "transport": "road", "distance_km": best_d, "weight": w})
        # lotnisko – tylko w tym samym kraju
        airports_in_country = [a for a in airports if (a.get("iso3") or "").upper() == (c_iso or "").upper()]
        if airports_in_country:
            best_a = None
            best_d = 1e18
            for a in airports_in_country:
                alon, alat = a["coordinates"]
                d = _haversine_km(clon, clat, alon, alat)
                if d < best_d:
                    best_d, best_a = d, a
            if best_a is not None:
                w = best_d * factor_road
                edges.append({"source": c["id"], "target": best_a["id"], "transport": "road", "distance_km": best_d, "weight": w})
                edges.append({"source": best_a["id"], "target": c["id"], "transport": "road", "distance_km": best_d, "weight": w})

    # city <-> powiązania: do kraju, najbliższego portu i lotniska (w obrębie tego samego ISO3)
    # to pozwala startować/kończyć trasy na miastach
    if cities:
        # indeks krajów po ISO3
        country_by_iso = {}
        for cn in countries:
            iso = (cn.get("iso3") or "").upper()
            if iso and iso not in country_by_iso:
                country_by_iso[iso] = cn
        for city in cities:
            clon, clat = city["coordinates"]
            iso = (city.get("iso3") or "").upper()
            # powiązanie z krajem
            cnode = country_by_iso.get(iso)
            if cnode:
                d = _haversine_km(clon, clat, cnode["coordinates"][0], cnode["coordinates"][1])
                w = d * factor_road
                edges.append({"source": city["id"], "target": cnode["id"], "transport": "road", "distance_km": d, "weight": w})
                edges.append({"source": cnode["id"], "target": city["id"], "transport": "road", "distance_km": d, "weight": w})
            # najbliższy port w tym samym kraju
            ports_in = [p for p in ports if (p.get("iso3") or "").upper() == iso]
            if ports_in:
                bestp, bestd = None, 1e18
                for p in ports_in:
                    d = _haversine_km(clon, clat, p["coordinates"][0], p["coordinates"][1])
                    if d < bestd:
                        bestd, bestp = d, p
                if bestp:
                    w = bestd * factor_road
                    edges.append({"source": city["id"], "target": bestp["id"], "transport": "road", "distance_km": bestd, "weight": w})
                    edges.append({"source": bestp["id"], "target": city["id"], "transport": "road", "distance_km": bestd, "weight": w})
            # najbliższe lotnisko w tym samym kraju
            airports_in = [a for a in airports if (a.get("iso3") or "").upper() == iso]
            if airports_in:
                besta, bestd = None, 1e18
                for a in airports_in:
                    d = _haversine_km(clon, clat, a["coordinates"][0], a["coordinates"][1])
                    if d < bestd:
                        bestd, besta = d, a
                if besta:
                    w = bestd * factor_road
                    edges.append({"source": city["id"], "target": besta["id"], "transport": "road", "distance_km": bestd, "weight": w})
                    edges.append({"source": besta["id"], "target": city["id"], "transport": "road", "distance_km": bestd, "weight": w})

    # kraj <-> kraj (połączenia lądowe na podstawie styku granic – wspólne punkty pierścieni)
    n_c = len(countries)
    for i in range(n_c):
        ci = countries[i]
        bi = country_boundaries.get(ci["id"], set())
        if not bi:
            continue
        for j in range(i + 1, n_c):
            cj = countries[j]
            bj = country_boundaries.get(cj["id"], set())
            if not bj:
                continue
            # szybki test – czy mają jakikolwiek wspólny "kwantowany" punkt granicy
            if bi.isdisjoint(bj):
                continue
            # uznajemy, że graniczą lądem
            d = _haversine_km(ci["coordinates"][0], ci["coordinates"][1], cj["coordinates"][0], cj["coordinates"][1])
            w = d * factor_road
            edges.append({"source": ci["id"], "target": cj["id"], "transport": "road", "distance_km": d, "weight": w})
            edges.append({"source": cj["id"], "target": ci["id"], "transport": "road", "distance_km": d, "weight": w})

    # Morski graf: jeśli mamy waypointy morskie, użyj ich zamiast bezpośrednich port<->port
    if sea_nodes:
        # port <-> najbliższe waypointy morskie (bez sztywnego limitu odległości, aby zapewnić łączność)
        max_port_wp_km = 20000.0
        k_wp = max(1, min(3, k_sea or 2))
        for p in ports:
            plon, plat = p["coordinates"]
            dists = []
            for wpn in sea_nodes:
                wlon, wlat = wpn["coordinates"]
                d = _haversine_km(plon, plat, wlon, wlat)
                dists.append((d, wpn))
            dists.sort(key=lambda x: x[0])
            added = 0
            for d, wpn in dists:
                if d > max_port_wp_km:
                    break
                w = d * factor_sea
                edges.append({"source": p["id"], "target": wpn["id"], "transport": "sea", "distance_km": d, "weight": w})
                edges.append({"source": wpn["id"], "target": p["id"], "transport": "sea", "distance_km": d, "weight": w})
                added += 1
                if added >= k_wp:
                    break

        # waypoint <-> waypoint wg zadeklarowanych sąsiedztw
        for a_id, b_id in sea_pairs:
            a = id_to_node.get(a_id)
            b = id_to_node.get(b_id)
            if not a or not b:
                continue
            alon, alat = a["coordinates"]
            blon, blat = b["coordinates"]
            d = _haversine_km(alon, alat, blon, blat)
            w = d * factor_sea
            edges.append({"source": a_id, "target": b_id, "transport": "sea", "distance_km": d, "weight": w})
            edges.append({"source": b_id, "target": a_id, "transport": "sea", "distance_km": d, "weight": w})
    else:
        # fallback: port <-> K najbliższych portów
        sea_pairs_set = set()
        for i, p in enumerate(ports):
            plon, plat = p["coordinates"]
            dists = []
            for j, q in enumerate(ports):
                if i == j:
                    continue
                qlon, qlat = q["coordinates"]
                d = _haversine_km(plon, plat, qlon, qlat)
                dists.append((d, q))
            dists.sort(key=lambda x: x[0])
            for d, q in dists[:max(0, k_sea)]:
                a, b = p["id"], q["id"]
                key = tuple(sorted((a, b)))
                if key in sea_pairs_set:
                    continue
                sea_pairs_set.add(key)
                w = d * factor_sea
                edges.append({"source": a, "target": b, "transport": "sea", "distance_km": d, "weight": w})
                edges.append({"source": b, "target": a, "transport": "sea", "distance_km": d, "weight": w})

    # lotnisko <-> K najbliższych lotnisk
    air_pairs = set()
    for i, a in enumerate(airports):
        alon, alat = a["coordinates"]
        dists = []
        for j, b in enumerate(airports):
            if i == j:
                continue
            blon, blat = b["coordinates"]
            d = _haversine_km(alon, alat, blon, blat)
            dists.append((d, b))
        dists.sort(key=lambda x: x[0])
        for d, b in dists[:max(0, k_air)]:
            a_id, b_id = a["id"], b["id"]
            key = tuple(sorted((a_id, b_id)))
            if key in air_pairs:
                continue
            air_pairs.add(key)
            w = d * factor_air
            edges.append({"source": a_id, "target": b_id, "transport": "air", "distance_km": d, "weight": w})
            edges.append({"source": b_id, "target": a_id, "transport": "air", "distance_km": d, "weight": w})

    return {
        "countries": countries,
        "ports": ports,
        "airports": airports,
        "id_to_node": id_to_node,
        "edges": edges,
    }


@api_bp.route("/graph")
@login_required
def get_graph():
    """
    Buduje prosty graf (kraje + porty + lotniska) i podstawowe połączenia:
    - kraj <-> najbliższy port (road)
    - kraj <-> najbliższe lotnisko (road)
    - port <-> K najbliższych portów (sea)
    - lotnisko <-> K najbliższych lotnisk (air)

    Parametry (opcjonalne):
      factor_sea (float, domyślnie 0.5)
      factor_air (float, domyślnie 5.0)
      factor_road (float, domyślnie 1.0)
      k_sea_neighbors (int, domyślnie 3)
      k_air_neighbors (int, domyślnie 3)
    """
    try:
      factor_sea = float(request.args.get("factor_sea", 0.5))
    except Exception:
      factor_sea = 0.5
    try:
      factor_air = float(request.args.get("factor_air", 5.0))
    except Exception:
      factor_air = 5.0
    try:
      factor_road = float(request.args.get("factor_road", 1.0))
    except Exception:
      factor_road = 1.0
    try:
      k_sea = int(request.args.get("k_sea_neighbors", 3))
    except Exception:
      k_sea = 3
    try:
      k_air = int(request.args.get("k_air_neighbors", 3))
    except Exception:
      k_air = 3

    built = _build_graph(factor_road=factor_road, factor_sea=factor_sea, factor_air=factor_air, k_sea=k_sea, k_air=k_air)
    return jsonify({
        "meta": {
            "counts": {
                "countries": len(built["countries"]),
                "ports": len(built["ports"]),
                "airports": len(built["airports"]),
                "nodes_total": len(built["id_to_node"]),
                "edges_total": len(built["edges"]),
            },
            "factors": {"sea": factor_sea, "air": factor_air, "road": factor_road},
            "neighbors": {"k_sea": k_sea, "k_air": k_air},
        },
        "nodes": list(built["id_to_node"].values()),
        "edges": built["edges"],
    })


@api_bp.route("/route", methods=["POST"])
@login_required
def compute_route():
    """
    Liczy najkrótszą ścieżkę (Dijkstra) między dwoma krajami.

    Body JSON:
      - source_iso3 (np. "POL") [wymagane]
      - target_iso3 (np. "DEU") [wymagane]
      - factor_sea (opc.)
      - factor_air (opc.)
      - factor_road (opc.)
      - k_sea_neighbors (opc.)
      - k_air_neighbors (opc.)
    """
    payload = request.get_json(silent=True) or {}

    def _num(v, default):
        try:
            return float(v)
        except Exception:
            return default

    def _num_i(v, default):
        try:
            return int(v)
        except Exception:
            return default

    source_node = (payload.get("source_node") or "").strip() or None
    target_node = (payload.get("target_node") or "").strip() or None
    source_iso3 = (payload.get("source_iso3") or "").upper().strip()
    target_iso3 = (payload.get("target_iso3") or "").upper().strip()
    if not (source_node or source_iso3) or not (target_node or target_iso3):
        return jsonify({"error": "Provide either source_node/target_node or source_iso3/target_iso3"}), 400

    factor_sea = _num(payload.get("factor_sea"), 0.5)
    factor_air = _num(payload.get("factor_air"), 5.0)
    factor_road = _num(payload.get("factor_road"), 1.0)
    k_sea = _num_i(payload.get("k_sea_neighbors"), 3)
    k_air = _num_i(payload.get("k_air_neighbors"), 3)

    built = _build_graph(
        factor_road=factor_road, factor_sea=factor_sea, factor_air=factor_air, k_sea=k_sea, k_air=k_air
    )
    id_to_node = built["id_to_node"]
    edges = built["edges"]

    if source_node:
        source_id = source_node
    else:
        source_id = f"COUNTRY_{source_iso3}"
    if target_node:
        target_id = target_node
    else:
        target_id = f"COUNTRY_{target_iso3}"

    if source_id not in id_to_node:
        return jsonify({"error": f"Unknown source: {source_id}"}), 400
    if target_id not in id_to_node:
        return jsonify({"error": f"Unknown target: {target_id}"}), 400

    # adjacency: node_id -> list of (neighbor_id, weight, edge_index)
    adj = {}
    for idx, e in enumerate(edges):
        adj.setdefault(e["source"], []).append((e["target"], float(e["weight"]), idx))

    # Dijkstra
    INF = 1e300
    dist = {node_id: INF for node_id in id_to_node.keys()}
    prev = {node_id: None for node_id in id_to_node.keys()}  # (previous_node_id, via_edge_index)

    dist[source_id] = 0.0
    heap = [(0.0, source_id)]

    visited = set()

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        if u == target_id:
            break
        for v, w, eidx in adj.get(u, []):
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = (u, eidx)
                heapq.heappush(heap, (nd, v))

    if dist[target_id] >= INF/2:
        return jsonify({"error": "No path found"}), 404

    # reconstruct path
    path_nodes = []
    legs = []
    cur = target_id
    total_distance = 0.0
    while cur is not None:
        path_nodes.append(cur)
        ref = prev[cur]
        if ref is None:
            break
        u, eidx = ref
        e = edges[eidx]
        legs.append(e)
        total_distance += float(e.get("distance_km", 0.0))
        cur = u
    path_nodes.reverse()
    legs.reverse()

    return jsonify({
        "meta": {
            "factors": {"sea": factor_sea, "air": factor_air, "road": factor_road},
            "neighbors": {"k_sea": k_sea, "k_air": k_air},
        },
        "source": id_to_node[source_id],
        "target": id_to_node[target_id],
        "summary": {
            "total_weight": dist[target_id],
            "total_distance_km": total_distance,
            "hops": max(0, len(path_nodes) - 1),
        },
        "path": [id_to_node[nid] for nid in path_nodes],
        "legs": legs,
    })
