// static/js/main.js

let map;
let countriesLayer;
let nodesLayer;  // warstwa z portami / lotniskami
let routeLayer;  // aktualnie narysowana trasa
let routeSegments = []; // segmenty trasy (polylines) dla interakcji

// Dane stawek:
let tariffData = {};            // klucz: ISO3 partnera → rate (w %)
let tariffDataByNum = {};       // klucz: ISO_numerical (np. "156") → rate (na przyszłość)
let globalFallbackRate = null;  // na razie praktycznie nieużywane przy offline
let currentReporter = null;     // ISO3 reportera (kraj docelowy wybrany na mapie)
let countriesIndex = [];        // lista krajów: {iso3, name, lon, lat}

// Stała skala kolorów: 0% = biały, następnie 20 równych przedziałów po 5 p.p. (0–5, 5–10, ..., 95–100).
const FIXED_COLOR_STEPS = 20; 
const FIXED_COLOR_BINS = Array.from({ length: FIXED_COLOR_STEPS }, (_, i) => (i + 1) * 5); // [5,10,...,100]
let FIXED_COLOR_PALETTE; // wypełniane przy starcie

// --------------- Helpers do GeoJSON ----------------

function pickProp(obj, keys) {
  for (const k of keys) {
    if (obj && obj[k] !== undefined && obj[k] !== null && obj[k] !== "" && obj[k] !== "-99") {
      return obj[k];
    }
  }
  return undefined;
}

function getISO3(props) {
  const val = pickProp(props, [
    "ISO_A3", "iso_a3", "adm0_a3", "wb_a3", "gu_a3", "ISO3", "ADM0_A3"
  ]);
  if (typeof val === "string") {
    const u = val.toUpperCase();
    if (u === "UNK" || u === "-99") return undefined;
    return u;
  }
  return val;
}

function getISONum(props) {
  const v = pickProp(props, ["ISO_N3", "iso_n3", "ADM0_A3_IS", "ISO3NUM", "ISO_NUM"]);
  if (v === undefined || v === null) return undefined;
  const s = String(v).trim();
  return String(parseInt(s, 10));
}

function getName(props) {
  return (
    pickProp(props, [
      "ADMIN",
      "NAME",
      "name",
      "name_long",
      "NAME_LONG",
      "NAME_EN",
      "SOVEREIGNT",
      "sovereignt",
      "COUNTRY",
      "country"
    ]) || "Nieznany kraj"
  );
}

// --------- Logika pobierania stawki dla kraju ----------

function getRateForCodes(iso3, isoNum) {
  // 1) ISO3
  if (iso3 && Object.prototype.hasOwnProperty.call(tariffData, iso3)) {
    return tariffData[iso3];
  }
  // 2) numeric (na przyszłość, gdybyśmy używali kodów WTO)
  if (isoNum && Object.prototype.hasOwnProperty.call(tariffDataByNum, isoNum)) {
    return tariffDataByNum[isoNum];
  }
  // 3) fallback "ALL"
  if (globalFallbackRate !== null) {
    if (!currentReporter || iso3 !== currentReporter) {
      return globalFallbackRate;
    }
  }
  return undefined;
}

// --------------- Mapa ----------------

function initMap() {
  map = L.map("map").setView([20, 0], 2);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 8,
    minZoom: 2,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  loadCountries();
  loadLogisticsNodes();
}

function loadCountries() {
  fetch("/api/countries")
    .then((resp) => resp.json())
    .then((geojson) => {
      countriesLayer = L.geoJSON(geojson, {
        // ważne: używamy styleWithTariff jako bazowego stylu
        style: styleWithTariff,
        onEachFeature: onEachCountryFeature,
      }).addTo(map);

      // Zbuduj indeks krajów (dla podpowiedzi i routingu)
      buildCountriesIndex(geojson);
      populateCountriesDatalist();
      initRoutingUI();
    })
    .catch((err) => {
      console.error("Error loading countries:", err);
    });
}

function styleWithTariff(feature) {
  const props = feature.properties || {};
  const iso3 = getISO3(props);
  const isoNum = getISONum(props);

  const rate = getRateForCodes(iso3, isoNum);

  if (rate === undefined) {
    return {
      color: "#9ca3af",
      weight: 1,
      fillColor: "#f9fafb",
      fillOpacity: 0.6,
    };
  }

  const color = getColorForRate(rate);

  return {
    color: "#4b5563",
    weight: 1,
    fillColor: color,
    fillOpacity: 0.9,
  };
}

// ---------------- Kolory: funkcje pomocnicze i skala ----------------

function hslToHex(h, s, l) {
  // h [0,360], s,l [0,100]
  s /= 100; l /= 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  let r = 0, g = 0, b = 0;
  if (0 <= h && h < 60) { r = c; g = x; b = 0; }
  else if (60 <= h && h < 120) { r = x; g = c; b = 0; }
  else if (120 <= h && h < 180) { r = 0; g = c; b = x; }
  else if (180 <= h && h < 240) { r = 0; g = x; b = c; }
  else if (240 <= h && h < 300) { r = x; g = 0; b = c; }
  else { r = c; g = 0; b = x; }
  const toHex = (v) => {
    const hv = Math.round((v + m) * 255).toString(16).padStart(2, "0");
    return hv;
  };
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function buildFixedPalette(steps) {
  // Paleta: gradient HSL od zieleni (h=120) do czerwieni (h=0) – stała, niezależna od danych
  const palette = [];
  for (let i = 0; i < steps; i++) {
    const ratio = i / (steps - 1);
    const h = 120 - 120 * ratio;   // 120 -> 0
    const s = 85;                  // nasycenie
    const l = 45;                  // jasność
    palette.push(hslToHex(h, s, l));
  }
  return palette;
}

// bardziej „gradientowa” skala (0% = białe)
function getColorForRate(rate) {
  if (rate === null || rate === undefined || isNaN(rate)) {
    return "#f9fafb"; // brak danych
  }
  if (Number(rate) === 0) {
    return "#ffffff"; // 0% biały
  }

  // Znajdź pierwszy stały próg >= rate
  for (let i = 0; i < FIXED_COLOR_BINS.length; i++) {
    if (rate <= FIXED_COLOR_BINS[i]) {
      return FIXED_COLOR_PALETTE[i];
    }
  }
  // Powyżej 100% – użyj ostatniego (najmocniejszego) czerwonego
  return FIXED_COLOR_PALETTE[FIXED_COLOR_PALETTE.length - 1];
}

function onEachCountryFeature(feature, layer) {
  const props = feature.properties || {};
  const name = getName(props);
  const iso3 = getISO3(props);
  const isoNum = getISONum(props);

  layer.on("mouseover", (e) => {
    const target = e.target;
    target.setStyle({
      weight: 2,
      color: "#111827",
    });

    // dynamiczny tooltip
    let tooltipHtml = `${name} (${iso3 || "—"})`;

    if (currentReporter && iso3 && iso3 !== currentReporter) {
      const rate = getRateForCodes(iso3, isoNum);
      if (rate !== undefined) {
        tooltipHtml += `<br/>Stawka importu do <b>${currentReporter}</b>: <b>${rate.toFixed(1)}%</b>`;
      } else {
        tooltipHtml += `<br/>Brak danych o stawce do <b>${currentReporter}</b>.`;
      }
    }

    target.bindTooltip(tooltipHtml, { sticky: true }).openTooltip();
  });

  layer.on("mouseout", (e) => {
    // resetStyle przywraca kolory z styleWithTariff
    if (countriesLayer) {
      countriesLayer.resetStyle(e.target);
    }
  });

  // Kliknięcie – wybór kraju docelowego (reportera)
  layer.on("click", () => {
    if (!iso3) {
      setSelectedCountry(name, "—");
      return;
    }
    setSelectedCountry(name, iso3);
    loadTariffs(iso3);
  });

  const tipIso = iso3 || "—";
  layer.bindTooltip(`${name} (${tipIso})`);
}

function setSelectedCountry(name, iso3) {
  currentReporter = (iso3 && iso3 !== "—") ? iso3 : null;
  const el = document.getElementById("selected-country");
  el.textContent = `Wybrany kraj docelowy: ${name} (${iso3 || "—"})`;
}

// --------------- Ładowanie stawek ----------------

function loadTariffs(reporterIso3) {
  fetch(`/api/tariffs?from=${encodeURIComponent(reporterIso3)}`)
    .then((resp) => resp.json())
    .then((data) => {
      tariffData = {};
      tariffDataByNum = {};
      globalFallbackRate = null;

      if (Array.isArray(data?.tariffs)) {
        for (const row of data.tariffs) {
          const partner = row.partner;
          const rate = row.rate;

          if (partner === "ALL") {
            globalFallbackRate = rate;
            continue;
          }

          if (typeof partner === "string" && /^\d+$/.test(partner)) {
            tariffDataByNum[String(parseInt(partner, 10))] = rate;
          } else {
            tariffData[String(partner).toUpperCase()] = rate;
          }
        }
      }

      if (countriesLayer) {
        countriesLayer.setStyle(styleWithTariff);
      }
      updateLegend();
    })
    .catch((err) => {
      console.error("Error loading tariffs:", err);
    });
}

function updateLegend() {
  const legendDiv = document.getElementById("legend");

  const fallbackInfo = globalFallbackRate !== null
    ? `<div style="margin-top:6px;padding:6px;border:1px dashed #9ca3af;border-radius:6px;">
         Tryb awaryjny: brak stawek per kraj, pokazuję średnią:
         <b>${Number(globalFallbackRate).toFixed(1)}%</b>.
       </div>`
    : "";

  // Legenda stała – 0% (biały) + 20 przedziałów po 5 p.p.
  let rows = '';
  // 0% osobno – biały
  rows += `<div><span class="legend-box" style="background:#ffffff;border:1px solid #e5e7eb;"></span> 0%</div>`;
  for (let i = 0; i < FIXED_COLOR_BINS.length; i++) {
    const from = i === 0 ? '>0' : `${FIXED_COLOR_BINS[i - 1]}`;
    const to = `${FIXED_COLOR_BINS[i]}`;
    const col = FIXED_COLOR_PALETTE[i];
    const label = i === 0 ? `>0–${to}%` : `${from}–${to}%`;
    rows += `<div><span class="legend-box" style="background:${col};"></span> ${label}</div>`;
  }

  legendDiv.innerHTML = `
    <h3>Legenda stawek celnych na tytoń</h3>
    ${rows}
    <p class="legend-note">
      Źródło: offline MacMap (applied tariffs, min rate, HS6, agregacja wg importu).
      Najpierw wybierz kraj docelowy, potem najedź na inne kraje,
      aby zobaczyć konkretną stawkę importową.
    </p>
    ${fallbackInfo}
  `;
}

function formatPercent(v, inclusiveUpper = false) {
  // Ładne formatowanie zakresów procentowych
  if (v <= 0) return inclusiveUpper ? "0%" : ">0%";
  if (v < 1) return `${v.toFixed(2)}%`;
  if (v < 10) return `${v.toFixed(1)}%`;
  return `${Math.round(v)}%`;
}

// Zainicjalizuj stałą paletę przy starcie skryptu
document.addEventListener("DOMContentLoaded", () => {
  FIXED_COLOR_PALETTE = buildFixedPalette(FIXED_COLOR_STEPS);
});

document.addEventListener("DOMContentLoaded", initMap);

function loadLogisticsNodes() {
  fetch("/api/logistics_nodes")
    .then((resp) => resp.json())
    .then((geojson) => {
      nodesLayer = L.geoJSON(geojson, {
        pointToLayer: (feature, latlng) => {
          const kind = feature.properties?.kind || "hub";
          // Kolory w zależności od typu
          let fill = "#0ea5e9"; // domyślny niebieski
          if (kind === "seaport") fill = "#3b82f6";
          if (kind === "air_cargo") fill = "#f97316";

          return L.circleMarker(latlng, {
            radius: 5,
            fillColor: fill,
            color: "#111827",
            weight: 1,
            opacity: 1,
            fillOpacity: 0.9,
          });
        },
        onEachFeature: (feature, layer) => {
          const p = feature.properties || {};
          const name = p.name || "Hub logistyczny";
          const kind = p.kind || "hub";
          const country = p.country || "";
          const id = p.id || "";

          layer.bindTooltip(
            `<b>${name}</b><br/>${country}<br/><i>${kind}</i><br/>ID: ${id}`,
            { sticky: true }
          );
        },
      }).addTo(map);
    })
    .catch((err) => {
      console.error("Error loading logistics nodes:", err);
    });
}

// ------------------- Routing UI i logika wyznaczania trasy -------------------

function buildCountriesIndex(geojson) {
  countriesIndex = [];
  for (const f of (geojson.features || [])) {
    const props = f.properties || {};
    const iso3 = getISO3(props);
    const name = getName(props);
    const centroid = centroidFromGeometry(f.geometry);
    if (!iso3 || !centroid) continue;
    countriesIndex.push({ iso3, name, lon: centroid[0], lat: centroid[1] });
  }
  // sort by name for nicer suggestions
  countriesIndex.sort((a, b) => a.name.localeCompare(b.name));
}

function centroidFromGeometry(geometry) {
  if (!geometry) return null;
  const type = geometry.type;
  const coords = geometry.coordinates;
  const lons = [], lats = [];
  function collect(poly) {
    if (!poly || !poly.length) return;
    const ring = poly[0];
    for (const pt of ring) {
      if (Array.isArray(pt) && pt.length >= 2) {
        lons.push(Number(pt[0]));
        lats.push(Number(pt[1]));
      }
    }
  }
  if (type === 'Polygon') {
    collect(coords);
  } else if (type === 'MultiPolygon') {
    for (const poly of coords || []) collect(poly);
  } else if (type === 'Point') {
    if (coords && coords.length >= 2) return [Number(coords[0]), Number(coords[1])];
  }
  if (!lons.length) return null;
  return [lons.reduce((a,b)=>a+b,0)/lons.length, lats.reduce((a,b)=>a+b,0)/lats.length];
}

function populateCountriesDatalist() {
  const dl = document.getElementById('countries-list');
  if (!dl) return;
  dl.innerHTML = '';
  for (const c of countriesIndex) {
    const opt = document.createElement('option');
    opt.value = `${c.name} (${c.iso3})`;
    dl.appendChild(opt);
  }
}

function initRoutingUI() {
  const btn = document.getElementById('route-go');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const fromVal = document.getElementById('route-from')?.value?.trim() || '';
    const toVal = document.getElementById('route-to')?.value?.trim() || '';
    const isoFrom = resolveCountryInputToISO3(fromVal);
    const isoTo = resolveCountryInputToISO3(toVal);
    const factorRoad = parseFloat(document.getElementById('factor-road')?.value || '1.0');
    const factorSea = parseFloat(document.getElementById('factor-sea')?.value || '0.5');
    const factorAir = parseFloat(document.getElementById('factor-air')?.value || '5.0');

    if (!isoFrom || !isoTo) {
      renderRouteSummary({ error: 'Podaj prawidłowe kraje w polach Skąd i Dokąd.' });
      return;
    }

    computeRouteRequest(isoFrom, isoTo, { factorRoad, factorSea, factorAir });
  });

  // Ułatwienia jak w Google Maps: Enter w polu "Skąd" fokusuje "Dokąd", Enter w "Dokąd" startuje trasę
  const fromInput = document.getElementById('route-from');
  const toInput = document.getElementById('route-to');
  fromInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      toInput?.focus();
    }
  });
  toInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      btn.click();
    }
  });

  // Presety wag
  document.getElementById('preset-cheap')?.addEventListener('click', () => applyPreset('cheap'));
  document.getElementById('preset-balanced')?.addEventListener('click', () => applyPreset('balanced'));
  document.getElementById('preset-fast')?.addEventListener('click', () => applyPreset('fast'));
}

function resolveCountryInputToISO3(value) {
  if (!value) return null;
  const v = value.trim();
  // Jeśli użytkownik wpisał bezpośrednio ISO3
  if (/^[A-Za-z]{3}$/.test(v)) {
    const iso = v.toUpperCase();
    if (countriesIndex.some(c => c.iso3 === iso)) return iso;
  }
  // Spróbuj sparsować "Nazwa (ISO)"
  const m = v.match(/\(([A-Za-z]{3})\)\s*$/);
  if (m) {
    const iso = m[1].toUpperCase();
    if (countriesIndex.some(c => c.iso3 === iso)) return iso;
  }
  // Spróbuj dopasować po nazwie (case-insensitive, startsWith)
  const low = v.toLowerCase();
  const exact = countriesIndex.find(c => c.name.toLowerCase() === low);
  if (exact) return exact.iso3;
  const starts = countriesIndex.find(c => c.name.toLowerCase().startsWith(low));
  if (starts) return starts.iso3;
  return null;
}

function computeRouteRequest(sourceIso3, targetIso3, { factorRoad, factorSea, factorAir }) {
  renderRouteSummary({ loading: true });
  // wyczyść poprzednią trasę
  if (routeLayer) {
    map.removeLayer(routeLayer);
    routeLayer = null;
  }
  if (routeSegments && routeSegments.length) {
    for (const seg of routeSegments) {
      try { map.removeLayer(seg); } catch {}
    }
    routeSegments = [];
  }
  fetch('/api/route', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_iso3: sourceIso3,
      target_iso3: targetIso3,
      factor_sea: factorSea,
      factor_air: factorAir,
      factor_road: factorRoad
    })
  })
    .then(r => r.json().then(data => ({ ok: r.ok, status: r.status, data })))
    .then(({ ok, status, data }) => {
      if (!ok) {
        const msg = data?.error || `Błąd ${status}`;
        renderRouteSummary({ error: msg });
        return;
      }
      renderRouteResult(data);
    })
    .catch(err => {
      console.error('Route error:', err);
      renderRouteSummary({ error: 'Nie udało się wyznaczyć trasy.' });
    });
}

function renderRouteSummary({ loading = false, error = null, summary = null } = {}) {
  const sumEl = document.getElementById('route-summary');
  const legsEl = document.getElementById('route-legs');
  if (!sumEl || !legsEl) return;
  if (loading) {
    sumEl.innerHTML = 'Wyznaczam trasę...';
    legsEl.innerHTML = '';
    return;
  }
  if (error) {
    sumEl.innerHTML = `<span style="color:#b91c1c;">${escapeHtml(error)}</span>`;
    legsEl.innerHTML = '';
    return;
  }
  if (summary) {
    const dist = Number(summary.total_distance_km || 0).toFixed(0);
    const weight = Number(summary.total_weight || 0).toFixed(1);
    sumEl.innerHTML = `Długość: <b>${dist} km</b><br/>Łączny koszt (waga): <b>${weight}</b>`;
  } else {
    sumEl.innerHTML = '';
    legsEl.innerHTML = '';
  }
}

function renderRouteResult(resp) {
  const path = resp?.path || [];
  const legs = resp?.legs || [];
  renderRouteSummary({ summary: resp?.summary });

  // Lista etapów z podpowiedziami
  const legsEl = document.getElementById('route-legs');
  let html = '';
  for (let i = 0; i < legs.length; i++) {
    const leg = legs[i];
    const s = leg.source;
    const t = leg.target;
    const sNode = findNodeInResponse(resp, s);
    const tNode = findNodeInResponse(resp, t);
    const nameS = sNode?.name || s;
    const nameT = tNode?.name || t;
    const transport = leg.transport || 'move';
    const dist = Number(leg.distance_km || 0).toFixed(0);
    const color = transportColor(transport);
    html += `<div data-leg-index="${i}" style="cursor:pointer;">
      <span style="display:inline-block;width:10px;height:10px;background:${color};border-radius:2px;margin-right:6px;vertical-align:middle;"></span>
      ${escapeHtml(nameS)} → ${escapeHtml(nameT)} <i>(${transport})</i> – ${dist} km
    </div>`;
  }
  legsEl.innerHTML = html || '<i>Brak danych etapów.</i>';

  // Rysowanie linii: segmentami wg transportu
  const group = L.layerGroup();
  const bounds = L.latLngBounds([]);
  routeSegments = [];
  for (let i = 0; i < legs.length; i++) {
    const leg = legs[i];
    const sNode = findNodeInResponse(resp, leg.source);
    const tNode = findNodeInResponse(resp, leg.target);
    if (!sNode || !tNode) continue;
    const s = sNode.coordinates, t = tNode.coordinates;
    if (!Array.isArray(s) || !Array.isArray(t) || s.length < 2 || t.length < 2) continue;
    const latlngs = [ [s[1], s[0]], [t[1], t[0]] ];
    const color = transportColor(leg.transport);
    const pl = L.polyline(latlngs, { color, weight: 4, opacity: 0.95 }).addTo(group);
    pl.bindTooltip(`${escapeHtml(sNode.name)} → ${escapeHtml(tNode.name)}<br/><i>${leg.transport}</i> • ${Number(leg.distance_km||0).toFixed(0)} km`);
    routeSegments.push(pl);
    latlngs.forEach(ll => bounds.extend(ll));
  }
  if (routeSegments.length) {
    routeLayer = group.addTo(map);
    try { map.fitBounds(bounds, { padding: [20, 20] }); } catch {}
  }

  // Klikalność listy etapów – powiększ do segmentu
  legsEl.querySelectorAll('[data-leg-index]')?.forEach((el) => {
    el.addEventListener('click', () => {
      const idx = Number(el.getAttribute('data-leg-index'));
      const seg = routeSegments[idx];
      if (seg) {
        try { map.fitBounds(seg.getBounds(), { padding: [30, 30] }); } catch {}
        seg.setStyle({ weight: 6 });
        setTimeout(() => { try { seg.setStyle({ weight: 4 }); } catch {} }, 800);
      }
    });
  });
}

function findNodeInResponse(resp, nodeId) {
  if (!resp || !Array.isArray(resp.path)) return null;
  for (const n of resp.path) if (n.id === nodeId) return n;
  return null;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function transportColor(kind) {
  if (!kind) return '#10b981';
  const k = String(kind).toLowerCase();
  if (k === 'sea') return '#3b82f6';      // niebieski
  if (k === 'air') return '#f97316';      // pomarańczowy
  return '#6b7280';                       // droga/kolej – szary
}

function applyPreset(name) {
  const road = document.getElementById('factor-road');
  const sea = document.getElementById('factor-sea');
  const air = document.getElementById('factor-air');
  if (!road || !sea || !air) return;
  if (name === 'cheap') {
    road.value = '1.0';
    sea.value = '0.4';
    air.value = '6.0';
  } else if (name === 'balanced') {
    road.value = '1.0';
    sea.value = '0.5';
    air.value = '5.0';
  } else if (name === 'fast') {
    road.value = '1.2';
    sea.value = '0.8';
    air.value = '2.0';
  }
}
