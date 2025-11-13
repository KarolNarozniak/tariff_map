# integration/wits_adapter.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import os
import requests
import xml.etree.ElementTree as ET


class WITSAdapter:
    """
    Adapter do WITS:
      (A) TradeStats-Tariff (agregaty UNCTAD TRAINS) – główne źródło do mapowania partnerów:
          /API/V1/wits/WITSApiService.svc/datasource/tradestats-tariff/indicator/{indicator}/year/{year}/country/{reporter}/partner/{partner}/product/{product}/?format=JSON

      (B) TRN (linie taryfowe; SDMX) – fallback:
          SDMX JSON:
            /API/V1/SDMX/V21/datasource/TRN/reporter/{reporter}/partner/{partner}/product/{product}/year/{year}/datatype/{reported|aveestimated}?format=JSON
          META XML (kraje i availability):
            /API/V1/wits/datasource/trn/country/ALL
            /API/V1/wits/datasource/trn/dataavailability/country/{code}/year/{yearSel}
    """

    BASE = "https://wits.worldbank.org"

    # -------- TradeStats-Tariff (JSON) --------
    # Uwaga: wymagany segment WITSApiService.svc + trailing slash + ?format=JSON
    TST_BASE = BASE + "/API/V1/wits/WITSApiService.svc"

    # -------- TRN meta (XML) --------
    META_COUNTRY_URL = BASE + "/API/V1/wits/datasource/trn/country/ALL"
    DATA_AVAIL_URL = BASE + "/API/V1/wits/datasource/trn/dataavailability/country/{code}/year/{yearSel}"

    # -------- TRN data (SDMX JSON) --------
    TRN_DATA_URL = (
        BASE
        + "/API/V1/SDMX/V21/datasource/TRN/reporter/{reporter}/partner/{partner}/product/{product}/year/{year}/datatype/{datatype}"
    )

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.s = session or requests.Session()
        # WITS zwykle nie wymaga klucza, ale zostawiam hook:
        self.api_key = os.environ.get("WITS_API_KEY", "")
        # cache TRN meta
        self._iso3_by_code: Optional[Dict[str, str]] = None
        self._code_by_iso3: Optional[Dict[str, str]] = None

    # ----------------- HTTP helpers -----------------

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get_json(self, url: str, params: Optional[Dict] = None) -> Dict:
        r = self.s.get(url, headers=self._headers(), params=params or {}, timeout=60)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {}

    def _get_xml_root(self, url: str) -> ET.Element:
        r = self.s.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        try:
            return ET.fromstring(r.content)
        except ET.ParseError as e:
            raise RuntimeError(f"XML parse error at {url}: {e}")

    # =====================================================================
    # (A) TRADESTATS-TARIFF – główne źródło
    # =====================================================================

    def _tst_request(self, path: str) -> List[Dict]:
        # Składamy pełny URL + TRAILING SLASH i format=JSON w parametrach
        url = f"{self.TST_BASE}/datasource/tradestats-tariff/{path.lstrip('/')}/"
        data = self._get_json(url, params={"format": "JSON"})
        return data if isinstance(data, list) else (data.get("data") or data.get("Data") or [])

    def _tst_latest_year(self, reporter_iso3: str, indicator: str, chapter: str) -> str:
        # najprościej: pobierz year=all i wybierz max rok z wyników
        path = f"indicator/{indicator}/year/all/country/{reporter_iso3}/partner/all/product/{chapter}"
        rows = self._tst_request(path)
        years: List[int] = []
        for r in rows:
            yr = r.get("Year") or r.get("year")
            try:
                if yr is not None:
                    years.append(int(yr))
            except Exception:
                pass
        return str(max(years)) if years else os.environ.get("WITS_FALLBACK_YEAR", "2021")

    def get_tradestats_tariff_chapter(
        self,
        reporter_iso3: str,
        hs_chapter: str = "24",
        indicator: str = "AHS-WGHTD-AVRG",  # Applied, trade-weighted avg; alternatywa: MFN-WGHTD-AVRG
        year: str | int = "latest",
    ) -> List[Dict]:
        y = self._tst_latest_year(reporter_iso3, indicator, hs_chapter) if str(year).lower() == "latest" else str(year)
        path = f"indicator/{indicator}/year/{y}/country/{reporter_iso3}/partner/all/product/{hs_chapter}"
        rows = self._tst_request(path)

        items: List[Dict] = []
        for row in rows:
            rep = row.get("ReporterISO3") or row.get("reporteriso3") or reporter_iso3.upper()
            partner = row.get("PartnerISO3") or row.get("partneriso3") or row.get("Partner")
            val = row.get("Value") or row.get("value")
            yr = row.get("Year") or row.get("year")
            if not partner or val is None:
                continue
            try:
                v = float(val)
            except Exception:
                continue
            items.append({
                "reporter": str(rep).upper(),
                "partner": str(partner).upper(),  # ISO3 dla frontu
                "year": str(yr) if yr is not None else y,
                "rate": v,
                "unit": "%",
                "indicator": indicator,
                "product": hs_chapter,
            })
        return items

    # =====================================================================
    # (B) TRN – fallback (linie taryfowe; wolniejsze)
    # =====================================================================

    def _load_country_meta(self) -> None:
        if self._iso3_by_code is not None:
            return
        root = self._get_xml_root(self.META_COUNTRY_URL)
        iso3_by_code: Dict[str, str] = {}
        code_by_iso3: Dict[str, str] = {}
        for node in root.iter():
            if node.tag.lower().endswith("country"):
                code = (node.attrib.get("countrycode") or "").strip()
                if not code:
                    continue
                iso3 = None
                for child in node:
                    if child.tag.lower().endswith("iso3code"):
                        iso3 = (child.text or "").strip().upper()
                        break
                if iso3:
                    iso3_by_code[code] = iso3
                    code_by_iso3[iso3] = code
        if not iso3_by_code:
            raise RuntimeError("Failed to build WITS country map.")
        self._iso3_by_code = iso3_by_code
        self._code_by_iso3 = code_by_iso3

    def _iso3_to_trn_code(self, iso3: str) -> str:
        self._load_country_meta()
        code = self._code_by_iso3.get(iso3.upper()) if self._code_by_iso3 else None
        if not code:
            raise ValueError(f"WITS/TRN: unknown ISO3 '{iso3}'.")
        return code

    def _trn_code_to_iso3(self, code: str) -> Optional[str]:
        self._load_country_meta()
        return self._iso3_by_code.get(str(code)) if self._iso3_by_code else None

    def _latest_year_and_partners_TRN(self, reporter_code: str) -> Tuple[str, List[str]]:
        # 1) lata
        url_all_years = self.DATA_AVAIL_URL.format(code=reporter_code, yearSel="all")
        root = self._get_xml_root(url_all_years)
        years: List[int] = []
        for node in root.iter():
            yr = node.attrib.get("year")
            if yr is None:
                for ch in node:
                    if ch.tag.lower().endswith("year"):
                        yr = (ch.text or "").strip()
                        break
            if yr:
                try:
                    years.append(int(yr))
                except Exception:
                    pass
        latest = str(max(years)) if years else os.environ.get("WITS_FALLBACK_YEAR", "2021")

        # 2) partnerzy dla latest
        url_latest = self.DATA_AVAIL_URL.format(code=reporter_code, yearSel=latest)
        root2 = self._get_xml_root(url_latest)
        partners: List[str] = []
        for node in root2.iter():
            if node.tag.lower().endswith("partner"):
                code = node.attrib.get("code") or (node.text or "").strip()
                if code:
                    partners.append(code.strip())
            if node.tag.lower().endswith("partnerlist"):
                txt = (node.text or "").strip()
                if txt:
                    for part in txt.replace(",", ";").split(";"):
                        part = part.strip()
                        if part:
                            partners.append(part)
        partners = list(dict.fromkeys(partners))
        return latest, partners

    def get_trn_chapter_avg_fallback(
        self,
        reporter_iso3: str,
        hs_chapter_prefix: str = "24",
        datatype: str = "aveestimated",
    ) -> List[Dict]:
        reporter_code = self._iso3_to_trn_code(reporter_iso3)
        year, partners = self._latest_year_and_partners_TRN(reporter_code)

        items: List[Dict] = []
        for partner_code in partners:
            partner_iso3 = self._trn_code_to_iso3(partner_code)
            if not partner_iso3:
                continue
            url = self.TRN_DATA_URL.format(
                reporter=reporter_code, partner=partner_code, product="All", year=year, datatype=datatype
            )
            data = self._get_json(url, params={"format": "JSON"})
            rows = data if isinstance(data, list) else (
                data.get("data") or data.get("Data") or data.get("Dataset") or data.get("Series") or []
            )
            vals: List[float] = []
            for row in rows:
                prod = str(row.get("ProductCode") or row.get("productcode") or row.get("Product") or "").strip()
                if not prod.startswith(hs_chapter_prefix):
                    continue
                val = row.get("OBS_VALUE") or row.get("ObsValue") or row.get("Value") or row.get("value")
                if val is None:
                    continue
                try:
                    vals.append(float(val))
                except Exception:
                    pass
            if not vals:
                continue
            rate = sum(vals) / len(vals)
            items.append({
                "reporter": reporter_iso3.upper(),
                "partner": partner_iso3,
                "year": year,
                "rate": float(rate),
                "unit": "%",
                "indicator": f"TRN-{datatype}",
                "product": hs_chapter_prefix,
            })

        return items
