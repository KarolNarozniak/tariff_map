// static/js/main.js

let map;
let countriesLayer;
let tariffData = {}; // { ISO3: rate }

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

// --- helpery do zgodności różnych geojsonów ---
function getISO3(props = {}) {
  return props.ISO_A3 || props.iso_a3 || props.ISO3 || props.adm0_a3 || "UNK";
}
function getName(props = {}) {
  return props.ADMIN || props.name || props.NAME || props.COUNTRY || "Unknown";
}

function styleWithTariff(feature) {
  const props = feature.properties || {};
  const iso3 = getISO3(props);
  const rate = tariffData[iso3];

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
    setSelectedCountry(name, iso3);
    loadTariffs(iso3);
  });

  layer.bindTooltip(`${name} (${iso3})`);
}

function setSelectedCountry(name, iso3) {
  const el = document.getElementById("selected-country");
  el.textContent = `Wybrany kraj docelowy: ${name} (${iso3})`;
}

function loadTariffs(reporterIso3) {
  fetch(`/api/tariffs?from=${encodeURIComponent(reporterIso3)}`)
    .then((resp) => resp.json())
    .then((data) => {
      tariffData = {};
      if (data.tariffs) {
        for (const row of data.tariffs) {
          tariffData[row.partner] = row.rate;
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
  legendDiv.innerHTML = `
    <h3>Legenda stawek celnych na tytoń</h3>
    <div><span class="legend-box" style="background:#22c55e;"></span> 0–5%</div>
    <div><span class="legend-box" style="background:#eab308;"></span> 5–10%</div>
    <div><span class="legend-box" style="background:#f97316;"></span> 10–20%</div>
    <div><span class="legend-box" style="background:#ef4444;"></span> &gt; 20%</div>
    <p class="legend-note">Dane mockowane (PoC). W przyszłości: WTO / oficjalne źródła.</p>
  `;
}

document.addEventListener("DOMContentLoaded", initMap);
