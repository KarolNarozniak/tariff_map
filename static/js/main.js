// static/js/main.js

let map;
let countriesLayer;

// Dane stawek:
let tariffData = {};            // klucz: ISO3 partnera → rate (w %)
let tariffDataByNum = {};       // klucz: ISO_numerical (np. "156") → rate (na przyszłość)
let globalFallbackRate = null;  // na razie praktycznie nieużywane przy offline
let currentReporter = null;     // ISO3 reportera (kraj docelowy wybrany na mapie)

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

// bardziej „gradientowa” skala
function getColorForRate(rate) {
  if (rate === null || rate === undefined || isNaN(rate)) {
    return "#f9fafb";
  }

  // rate jest już w % (np. 30.0 = 30%)
  if (rate < 2)  return "#16a34a"; // bardzo niska (0–2)
  if (rate < 5)  return "#22c55e"; // niska (2–5)
  if (rate < 10) return "#84cc16"; // umiarkowana (5–10)
  if (rate < 20) return "#eab308"; // podwyższona (10–20)
  if (rate < 30) return "#f97316"; // wysoka (20–30)
  if (rate < 40) return "#ea580c"; // bardzo wysoka (30–40)
  return "#ef4444";               // ekstremalna (>40)
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

  legendDiv.innerHTML = `
    <h3>Legenda stawek celnych na tytoń</h3>
    <div><span class="legend-box" style="background:#16a34a;"></span> 0–2%</div>
    <div><span class="legend-box" style="background:#22c55e;"></span> 2–5%</div>
    <div><span class="legend-box" style="background:#84cc16;"></span> 5–10%</div>
    <div><span class="legend-box" style="background:#eab308;"></span> 10–20%</div>
    <div><span class="legend-box" style="background:#f97316;"></span> 20–30%</div>
    <div><span class="legend-box" style="background:#ea580c;"></span> 30–40%</div>
    <div><span class="legend-box" style="background:#ef4444;"></span> >40%</div>
    <p class="legend-note">
      Źródło: offline MacMap (applied tariffs, min rate, HS6, agregacja wg importu).
      Najpierw wybierz kraj docelowy, potem najedź na inne kraje,
      aby zobaczyć konkretną stawkę importową.
    </p>
    ${fallbackInfo}
  `;
}

document.addEventListener("DOMContentLoaded", initMap);
