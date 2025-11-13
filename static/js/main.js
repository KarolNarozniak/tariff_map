// static/js/main.js

let map;
let countriesLayer;

// Dane stawek:
let tariffData = {};            // klucz: ISO3 → rate
let tariffDataByNum = {};       // klucz: ISO_numerical (np. "156") → rate
let globalFallbackRate = null;  // gdy backend zwraca partner: "ALL"
let currentReporter = null;     // ISO3 reportera wybranego na mapie

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
  // Natural Earth: ISO_N3 / iso_n3 / ADM0_A3_IS / numeric codes as strings with leading zeros
  const v = pickProp(props, ["ISO_N3", "iso_n3", "ADM0_A3_IS", "ISO3NUM", "ISO_NUM"]);
  if (v === undefined || v === null) return undefined;
  const s = String(v).trim();
  // znormalizuj do bez wiodących zer: WTO zwykle zwraca np. "156", NE bywa "156" albo "156"
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

// --------------- Mapa ----------------

function initMap() {
  map = L.map("map").setView([20, 0], 2);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 8,
    minZoom: 2,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  loadCountries();
}

function loadCountries() {
  fetch("/api/countries")
    .then((resp) => resp.json())
    .then((geojson) => {
      countriesLayer = L.geoJSON(geojson, {
        style: baseCountryStyle,
        onEachFeature: onEachCountryFeature,
      }).addTo(map);
    })
    .catch((err) => {
      console.error("Error loading countries:", err);
    });
}

function baseCountryStyle() {
  return {
    color: "#9ca3af",
    weight: 1,
    fillColor: "#e5e7eb",
    fillOpacity: 0.8,
  };
}

function styleWithTariff(feature) {
  const props = feature.properties || {};
  const iso3 = getISO3(props);
  const isoNum = getISONum(props);

  // 1) próbuj ISO3
  let rate = iso3 ? tariffData[iso3] : undefined;

  // 2) jak brak – a backend dał numery partnerów (WTO code ~ ISO numeric), próbuj po numerze
  if (rate === undefined && isoNum !== undefined) {
    rate = tariffDataByNum[isoNum];
  }

  // 3) fallback MFN "ALL": pokoloruj wszystkie poza samym reporterem
  if (rate === undefined && globalFallbackRate !== null) {
    if (!currentReporter || iso3 !== currentReporter) {
      rate = globalFallbackRate;
    }
  }

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

function getColorForRate(rate) {
  if (rate < 5) return "#22c55e";      // zielony
  if (rate < 10) return "#eab308";     // żółty
  if (rate < 20) return "#f97316";     // pomarańcz
  return "#ef4444";                    // czerwony
}

function onEachCountryFeature(feature, layer) {
  const props = feature.properties || {};
  const name = getName(props);
  const iso3 = getISO3(props);

  layer.on("mouseover", (e) => {
    e.target.setStyle({
      weight: 2,
      color: "#111827",
    });
  });

  layer.on("mouseout", (e) => {
    if (countriesLayer) {
      countriesLayer.resetStyle(e.target);
    }
  });

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
      // reset
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

          // Jeżeli partner wygląda na ISO-numeric (same cyfry), zapisujemy w osobnym słowniku:
          if (typeof partner === "string" && /^\d+$/.test(partner)) {
            tariffDataByNum[String(parseInt(partner, 10))] = rate; // normalizuj bez wiodących zer
          } else {
            // w przeciwnym razie traktujemy jako ISO3
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
         Tryb awaryjny: brak stawek per kraj w WTO (HS_P_0070). Pokazuję średnią MFN (HS_A_0010) dla rozdziału 24:
         <b>${Number(globalFallbackRate).toFixed(1)}%</b>.
       </div>`
    : "";

  legendDiv.innerHTML = `
    <h3>Legenda stawek celnych na tytoń</h3>
    <div><span class="legend-box" style="background:#22c55e;"></span> 0–5%</div>
    <div><span class="legend-box" style="background:#eab308;"></span> 5–10%</div>
    <div><span class="legend-box" style="background:#f97316;"></span> 10–20%</div>
    <div><span class="legend-box" style="background:#ef4444;"></span> &gt; 20%</div>
    <p class="legend-note">Źródło: WTO Timeseries (preferencje); fallback: MFN. Obsługuję ISO3 oraz kody numeryczne partnerów.</p>
    ${fallbackInfo}
  `;
}

document.addEventListener("DOMContentLoaded", initMap);
