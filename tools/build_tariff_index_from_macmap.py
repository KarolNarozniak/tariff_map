# tools/build_tobacco_index_from_excel.py
"""
Buduje indeks stawek celnych na tytoń (HS chapter 24)
na podstawie pliku Excel z MacMap (.xlsx).

Wejście:
    - MacMap_Data_354182.xlsx (arkusz "Data")

Wyjście:
    - data/tariffs/tobacco_index.json
      Struktura:
      {
        "24": {
          "USA": {
            "FRA": {"rate": 0.35, "year": 2024},
            "POL": {"rate": 0.12, "year": 2024}
          },
          "DEU": { ... }
        }
      }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

try:
    import pycountry
except ImportError:
    pycountry = None
    print(
        "[WARN] Brak biblioteki 'pycountry'. "
        "Zainstaluj ją: pip install pycountry"
    )

# === ŚCIEŻKI – dostosuj do swojego projektu ===

# plik z MacMap (ten, który pobrałeś z ITC)
INPUT_XLSX = Path(
    r"C:\Users\lives\Documents\MacMap_Data_354182.xlsx"
)

# gdzie zapiszemy indeks do użycia przez aplikację
OUTPUT_JSON = Path("data/tariffs/tobacco_index.json")

# opcjonalnie: logi z nierozpoznanymi nazwami krajów
UNMAPPED_REPORTERS = Path("data/tariffs/unmapped_reporters.txt")
UNMAPPED_PARTNERS = Path("data/tariffs/unmapped_partners.txt")

# interesuje nas tylko rozdział HS 24 (tytoń)
HS_CHAPTER = "24"


# --- Pomocnicza funkcja: nazwa kraju -> kod ISO3 ---


# Specjalne poprawki nazw, których pycountry może nie rozpoznać 1:1
ALIAS_FIXES = {
    # typowe "długie" nazwy z MacMap / ONZ
    "Bolivia (Plurinational State of)": "Bolivia, Plurinational State of",
    "Venezuela (Bolivarian Republic of)": "Venezuela, Bolivarian Republic of",
    "Iran (Islamic Republic of)": "Iran, Islamic Republic of",
    "Lao, People's Democratic Republic": "Lao People's Democratic Republic",
    "Cabo Verde": "Cabo Verde",  # pycountry zna tę nazwę
    "Eswatini": "Eswatini",
    "Congo, Democratic Republic of": "Congo, The Democratic Republic of the",
    "Micronesia (Federated States of)": "Micronesia, Federated States of",
    "Syrian Arab Republic": "Syrian Arab Republic",
    "Hong Kong, China Special Administrative Region": "Hong Kong",
    "Macao, China Special Administrative Region": "Macao",
    "Taipei, Chinese": "Taiwan, Province of China",
    "Tanzania, United Republic of": "Tanzania, United Republic of",
    "Korea, Republic of": "Korea, Republic of",
    "Korea, Democratic People's Republic of": "Korea, Democratic People's Republic of",
    "Moldova, Republic of": "Moldova, Republic of",
    "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
    # czasem drobne różnice w pisowni
    "Russian Federation": "Russian Federation",
    "Viet Nam": "Viet Nam",
    "Türkiye": "Türkiye",
}


def name_to_iso3(name: str) -> str | None:
    """
    Próbujemy zamienić nazwę kraju (taką jak w Excelu MacMap)
    na kod ISO3, używając pycountry + ALIAS_FIXES.

    Zwraca np. "USA", "DEU", "IND" albo None, jeśli się nie uda.
    """
    if not isinstance(name, str):
        return None

    raw = name.strip()
    if not raw:
        return None

    if not pycountry:
        # Jeśli pycountry nie jest dostępne – nie kombinujemy
        return None

    # krok 1: aliasy
    fixed = ALIAS_FIXES.get(raw, raw)

    # krok 2: lookup w pycountry
    try:
        country = pycountry.countries.lookup(fixed)
        return country.alpha_3.upper()
    except LookupError:
        # jako fallback – spróbujmy prostszej wersji nazwy
        # np. usunięcie rzeczy w nawiasach
        import re

        simplified = re.sub(r"\s*\(.*?\)", "", fixed).strip()
        if simplified != fixed:
            try:
                country = pycountry.countries.lookup(simplified)
                return country.alpha_3.upper()
            except LookupError:
                pass

        return None


# --- Główna logika budowy indeksu ---


def build_index() -> None:
    print(f"[INFO] Wczytuję plik Excel: {INPUT_XLSX}")

    if not INPUT_XLSX.exists():
        raise FileNotFoundError(
            f"Plik wejściowy {INPUT_XLSX} nie istnieje – popraw ścieżkę."
        )

    df = pd.read_excel(INPUT_XLSX, sheet_name="Data")

    # Upewniamy się, że mamy potrzebne kolumny
    required_cols = {
        "ReportingCountry",
        "PartnerCountry",
        "Year",
        "ProductCode",
        "AVE",
    }
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"Brakuje kolumn w Excelu: {missing}. "
            f"Kolumny dostępne: {list(df.columns)}"
        )

    # Filtrowanie tylko produktów z rozdziału 24
    print(f"[INFO] Filtrowanie rekordów dla HS chapter {HS_CHAPTER}...")
    df = df[df["ProductCode"].astype(str).str.startswith(HS_CHAPTER)]

    print(f"[INFO] Rekordów po filtrze HS {HS_CHAPTER}: {len(df)}")

    # Kontenery na "nierozpoznanych" reporterów i partnerów
    unmapped_reporters = set()
    unmapped_partners = set()

    # agregator: (chapter, reporter_iso3, partner_iso3) -> sum, n, year_max
    agg: Dict[Tuple[str, str, str], Dict[str, float]] = {}

    for _, row in df.iterrows():
        rep_name = str(row["ReportingCountry"])
        par_name = str(row["PartnerCountry"])

        rep_iso3 = name_to_iso3(rep_name)
        par_iso3 = name_to_iso3(par_name)

        if rep_iso3 is None:
            unmapped_reporters.add(rep_name)
            continue
        if par_iso3 is None:
            unmapped_partners.add(par_name)
            continue

        try:
            year = int(row["Year"])
        except Exception:
            year = None

        # AVE może być z przecinkiem jako separatorem dziesiętnym
        ave_raw = row["AVE"]
        if pd.isna(ave_raw):
            continue

        try:
            ave = float(str(ave_raw).replace(",", "."))
        except ValueError:
            continue

        key = (HS_CHAPTER, rep_iso3, par_iso3)
        acc = agg.setdefault(
            key, {"sum": 0.0, "count": 0, "year": year or 0}
        )
        acc["sum"] += ave
        acc["count"] += 1
        if year is not None:
            acc["year"] = max(acc["year"], year)

    print(f"[INFO] Rekordów po mapowaniu ISO3: {len(agg)}")

    # Budujemy strukturę docelową
    index: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}
    index[HS_CHAPTER] = {}

    for (chapter, rep_iso3, par_iso3), stats in agg.items():
        avg_rate = stats["sum"] / stats["count"] if stats["count"] else 0.0
        year = stats["year"] or 0

        rep_map = index[chapter].setdefault(rep_iso3, {})
        rep_map[par_iso3] = {
            "rate": float(avg_rate),
            "year": int(year),
        }

    # Prosty przegląd: ilu reporterów, ilu partnerów
    reporters = list(index[HS_CHAPTER].keys())
    print(
        f"[INFO] Reporterów w indeksie: {len(reporters)} "
        f"({', '.join(sorted(reporters)[:10])}{'...' if len(reporters) > 10 else ''})"
    )

    # Zapis indeksu
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"[INFO] Indeks zapisany do: {OUTPUT_JSON.resolve()}")

    # Zapis nierozpoznanych nazw (do debugowania)
    if unmapped_reporters:
        UNMAPPED_REPORTERS.parent.mkdir(parents=True, exist_ok=True)
        with UNMAPPED_REPORTERS.open("w", encoding="utf-8") as f:
            for name in sorted(unmapped_reporters):
                f.write(name + "\n")
        print(
            f"[INFO] Nierozpoznani reporterzy zapisani do: "
            f"{UNMAPPED_REPORTERS.resolve()}"
        )

    if unmapped_partners:
        UNMAPPED_PARTNERS.parent.mkdir(parents=True, exist_ok=True)
        with UNMAPPED_PARTNERS.open("w", encoding="utf-8") as f:
            for name in sorted(unmapped_partners):
                f.write(name + "\n")
        print(
            f"[INFO] Nierozpoznani partnerzy zapisani do: "
            f"{UNMAPPED_PARTNERS.resolve()}"
        )

    print("[INFO] Gotowe ✅")


if __name__ == "__main__":
    build_index()
