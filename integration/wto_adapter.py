# integration/wto_adapter.py
from __future__ import annotations
from typing import List, Dict, Optional, Tuple, Any
import os
import requests
from core.config import Config

WTO_BASE = "https://api.wto.org/timeseries/v1"

# Minimalny, bezpieczny fallback dla reporterów (ISO3 -> kod WTO / ISO numeric as string)
ISO3_TO_WTO_FALLBACK = {
    "POL": "616",
    "DEU": "276",
    "FRA": "250",
    "ITA": "380",
    "ESP": "724",
    "PRT": "620",
    "NLD": "528",
    "BEL": "056",
    "CZE": "203",
    "SVK": "703",
    "HUN": "348",
    "LTU": "440",
    "LVA": "428",
    "EST": "233",
    "USA": "842",
    "CHN": "156",
    "GBR": "826",
    "RUS": "643",
    "UKR": "804",
}

# Członkowie UE (ISO3) → taryfa zewnętrzna raportowana pod reporterem "European Union" (WTO code 918)
EU_ISO3 = {
    "AUT","BEL","BGR","HRV","CYP","CZE","DNK","EST","FIN","FRA","DEU","GRC","HUN",
    "IRL","ITA","LVA","LTU","LUX","MLT","NLD","POL","PRT","ROU","SVK","SVN","ESP","SWE"
}
EU_WTO_REPORTER_CODE = "918"  # European Union


class WTOTimeseriesAdapter:
    """
    WTO Timeseries v1 – Preferential tariffs by HS (partner dimension).
      Priorytet: i=HS_P_0070 (Lowest preferential ad valorem tariff, HS6).
      Fallback: i=HS_A_0010 (MFN simple average by HS; bez wymiaru partnera).
    - Odporne rozwiązywanie endpointów słownikowych (reporters/partners).
    - Parser tolerujący różne kształty JSON.
    - Fallback ISO3->WTO code + retry, aby uniknąć 400 na r=POL.
    - Dla członków UE: reporter przerzucany na '918' (European Union).
    - Błędy nie podnoszą 500: dostępne przez get_last_error_json().
    """

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.s = session or requests.Session()
        self.key = os.environ.get("WTO_API_KEY")
        if not self.key:
            raise RuntimeError("WTO_API_KEY is not set in environment")

        # caches
        self._reporter_cache_iso3_to_code: Dict[str, str] = {}
        self._partner_cache_code_to_iso3: Dict[str, str] = {}
        self._economies_loaded = False
        self._partners_loaded = False

        # resolved dictionary endpoints (warianty)
        self._reporters_path: Optional[str] = None
        self._partners_path: Optional[str] = None

        # debug/diag
        self.last_request: Optional[Tuple[str, Dict]] = None
        self.last_status: Optional[int] = None
        self._last_error_json: Optional[Dict[str, Any]] = None

    # ---------------- HTTP ----------------

    def _headers(self) -> Dict[str, str]:
        return {"Ocp-Apim-Subscription-Key": self.key}

    def _get_raw(self, path: str, params: Dict) -> requests.Response:
        url = f"{WTO_BASE}/{path.lstrip('/')}"
        base = {"fmt": Config.WTO_DEFAULT_FORMAT, "lang": Config.WTO_DEFAULT_LANGUAGE}
        base.update(params)
        self.last_request = (url, base.copy())
        r = self.s.get(url, headers=self._headers(), params=base, timeout=60)
        self.last_status = r.status_code
        if r.status_code >= 400:
            try:
                self._last_error_json = r.json()
            except Exception:
                self._last_error_json = {"http_error": r.status_code, "text": r.text[:500]}
        else:
            self._last_error_json = None
        return r

    def _get(self, path: str, params: Dict) -> Dict:
        r = self._get_raw(path, params)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {}

    # -------------- Endpoint resolver -------------

    def _resolve_once(self, candidates: List[str]) -> Optional[str]:
        for c in candidates:
            try:
                resp = self._get_raw(c, params={})
                if resp.status_code < 400:
                    return c
            except requests.HTTPError as e:
                if getattr(e.response, "status_code", None) == 404:
                    continue
                raise
        return None

    def _ensure_reporters_path(self) -> str:
        if self._reporters_path:
            return self._reporters_path
        path = self._resolve_once(["reporters", "reporting_economies", "reportingEconomies"])
        if not path:
            self._reporters_path = ""  # brak endpointu słownika
            return ""
        self._reporters_path = path
        return path

    def _ensure_partners_path(self) -> str:
        if self._partners_path:
            return self._partners_path
        path = self._resolve_once(["partners", "partner_economies", "partnerEconomies"])
        if not path:
            self._partners_path = ""  # brak endpointu słownika
            return ""
        self._partners_path = path
        return path

    # -------------- Dictionaries -------------

    @staticmethod
    def _extract_list(payload: Any) -> List[Dict]:
        """Akceptuj listę lub obiekty z różnymi kluczami list."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "Dataset", "results", "reporters", "partners", "items"):
                v = payload.get(key)
                if isinstance(v, list):
                    return v
        return []

    def _load_reporting_economies(self) -> None:
        if self._economies_loaded:
            return
        path = self._ensure_reporters_path()
        if path:
            try:
                data = self._get(path, params={})
                rows = self._extract_list(data)
                for rec in rows:
                    iso3 = (rec.get("alpha3Code") or rec.get("alpha3") or "").upper()
                    code = str(rec.get("code") or "").strip()
                    if iso3 and code:
                        self._reporter_cache_iso3_to_code[iso3] = code
            except Exception:
                pass
        for iso3, code in ISO3_TO_WTO_FALLBACK.items():
            self._reporter_cache_iso3_to_code.setdefault(iso3, code)
        self._economies_loaded = True

    def _load_partner_economies(self) -> None:
        if self._partners_loaded:
            return
        path = self._ensure_partners_path()
        if path:
            try:
                data = self._get(path, params={})
                rows = self._extract_list(data)
                for rec in rows:
                    iso3 = (rec.get("alpha3Code") or rec.get("alpha3") or "").upper()
                    code = str(rec.get("code") or "").strip()
                    if iso3 and code:
                        self._partner_cache_code_to_iso3[code] = iso3
            except Exception:
                pass
        self._partners_loaded = True

    def _wto_code_for_reporter(self, reporter_iso3: str) -> str:
        """
        Zwraca kod WTO dla reportera. Dla członków UE zwraca kod EU (918),
        bo preferencyjne taryfy są publikowane pod "European Union".
        """
        self._load_reporting_economies()
        iso3 = reporter_iso3.upper().strip()
        if iso3 in EU_ISO3:
            return EU_WTO_REPORTER_CODE
        return self._reporter_cache_iso3_to_code.get(iso3, iso3)

    def _partner_iso3_from_code(self, partner_code: str) -> str:
        self._load_partner_economies()
        return self._partner_cache_code_to_iso3.get(str(partner_code), str(partner_code).upper())

    # -------------- Data --------------------

    def get_tariffs_for_reporter_hs_chapter(
        self,
        reporter_iso3: str,
        hs_chapter: str = "24",
        year: str | int = "latest",
        indicator: Optional[str] = None,
        include_subproducts: bool = True,
    ) -> List[Dict]:
        """
        Priorytet: Preferential tariffs by HS with partner dimension:
          i = HS_P_0070  (Lowest preferential ad valorem tariff, HS6)
          r = <WTO reporter code>  (dla UE → 918)
          p = all
          px= HS
          pc= <chapter> (24)
          spc=true (HS6)
          ps=all  (dla 'latest' wybieramy najnowszy rok per partner)
        Fallback: MFN by HS (bez partnera):
          i = HS_A_0010
          r = <WTO reporter code> (dla UE → 918)
          px= HS
          pc= <chapter>
          ps=all
        """
        i_code = (indicator or os.environ.get("WTO_INDICATOR_CODE") or "HS_P_0070").strip()
        ps = "all" if str(year).lower() == "latest" else str(year)
        r_code = self._wto_code_for_reporter(reporter_iso3)

        # --------- 1) Preferential HS_P_0070 (partner dimension) ----------
        params = {
            "i": i_code,
            "r": r_code,
            "p": "all",
            "px": "HS",
            "pc": hs_chapter,
            "ps": ps,
            "head": "M",
            "meta": "false",
        }
        if include_subproducts:
            params["spc"] = "true"

        rows: List[Dict] = []
        try:
            data = self._get("data", params=params)
            rows = data if isinstance(data, list) else data.get("Dataset") or data.get("data") or []
        except requests.HTTPError as e:
            # jeżeli poszło z literowym r (np. POL) – spróbuj fallback numeric
            if len(str(r_code)) == 3 and str(r_code).isalpha():
                fallback_code = ISO3_TO_WTO_FALLBACK.get(reporter_iso3.upper())
                if fallback_code:
                    params_retry = dict(params)
                    params_retry["r"] = fallback_code
                    try:
                        data = self._get("data", params=params_retry)
                        rows = data if isinstance(data, list) else data.get("Dataset") or data.get("data") or []
                    except Exception:
                        rows = []
            else:
                rows = []

        items: List[Dict] = []
        for row in rows:
            partner_code = (row.get("partnerEconomyCode") or row.get("p") or row.get("partner") or "")
            yr = row.get("year") or row.get("time")
            val = row.get("value") or row.get("Value")
            unit = row.get("unitCode") or "%"

            if not partner_code or val is None:
                continue
            try:
                v = float(val)
            except Exception:
                continue

            partner_iso3 = self._partner_iso3_from_code(str(partner_code))
            items.append({
                "reporter": reporter_iso3.upper(),  # zwracamy ISO3 reportera wejściowego
                "partner": partner_iso3,            # ISO3 partnera (o ile znany)
                "year": str(yr) if yr is not None else None,
                "rate": v,
                "unit": unit or "%",
                "indicator": i_code,
                "product": hs_chapter
            })

        # latest → najnowszy rok per partner
        if items and str(year).lower() == "latest":
            latest_by_partner: Dict[str, Dict] = {}
            for it in items:
                p = it["partner"]
                try:
                    yr_i = int(it["year"]) if it["year"] else -1
                except Exception:
                    yr_i = -1
                if p not in latest_by_partner or yr_i > int(latest_by_partner[p]["year"]):
                    latest_by_partner[p] = it
            items = list(latest_by_partner.values())

        if items:
            return items

        # --------- 2) Fallback: MFN HS_A_0010 (no partner dimension) ----------
        # Zwracamy 1 rekord "ALL" → frontend pokoloruje wszystkie kraje jednakowo
        mfni = "HS_A_0010"
        mf_params = {
            "i": mfni,
            "r": r_code,
            "px": "HS",
            "pc": hs_chapter,
            "ps": ps,
            "head": "M",
            "meta": "false",
        }
        try:
            data2 = self._get("data", params=mf_params)
            rows2 = data2 if isinstance(data2, list) else data2.get("Dataset") or data2.get("data") or []
        except Exception:
            rows2 = []

        # wybierz najnowszy rok dostępny
        best_row: Optional[Dict] = None
        best_year = -1
        for row in rows2:
            yr = row.get("year") or row.get("time")
            val = row.get("value") or row.get("Value")
            unit = row.get("unitCode") or "%"
            if val is None:
                continue
            try:
                yr_i = int(yr) if yr is not None else -1
                v = float(val)
            except Exception:
                continue
            if yr_i > best_year:
                best_year = yr_i
                best_row = {"year": str(yr) if yr is not None else None, "rate": v, "unit": unit or "%"}

        if best_row:
            return [{
                "reporter": reporter_iso3.upper(),
                "partner": "ALL",
                "year": best_row["year"],
                "rate": best_row["rate"],
                "unit": best_row["unit"],
                "indicator": mfni,
                "product": hs_chapter
            }]

        return []

    # --- debug/diag ---

    def get_last_request_info(self) -> Optional[Tuple[str, Dict, Optional[int]]]:
        if self.last_request is None:
            return None
        url, params = self.last_request
        return (url, params, self.last_status)

    def get_last_error_json(self) -> Optional[Dict[str, Any]]:
        return self._last_error_json
