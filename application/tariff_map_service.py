# application/tariff_map_service.py
from __future__ import annotations
from typing import List, Dict, Optional
from domain.models import TariffRate
from core.config import Config
from integration.wto_adapter import WTOTimeseriesAdapter
# WITS pozostawiamy jako potencjalny fallback – na razie nie używamy:
# from integration.wits_adapter import WITSAdapter

class TariffMapService:
    """
    Primary: WTO Timeseries (HS_P_0070) – preferencyjne taryfy po partnerach (HS6, HS chapter 24).
    Zwracamy partner jako ISO3 (mapowany w adapterze).
    """

    def __init__(self,
                 wto: Optional[WTOTimeseriesAdapter] = None) -> None:
        self._wto = wto or WTOTimeseriesAdapter()

    # pozostawiamy podpis metody, gdybyś miał debugi gdzieś niżej:
    def _fetch_from_wto(self, reporter_iso3: str, indicator: Optional[str] = None, year: str = "latest") -> List[Dict]:
        return self._wto.get_tariffs_for_reporter_hs_chapter(
            reporter_iso3=reporter_iso3,
            hs_chapter=Config.TOBACCO_PRODUCT_CODE,  # "24"
            year=year,
            indicator=indicator or "HS_P_0070",
            include_subproducts=True,
        )

    def build_tobacco_tariff_map_for_reporter(
        self,
        reporter_iso3: str,
        indicator: Optional[str] = None,
        year: str = "latest",
        debug: bool = False,
    ) -> List[TariffRate]:
        rows = self._fetch_from_wto(reporter_iso3, indicator, year)
        rates: List[TariffRate] = []
        for row in rows:
            partner_iso3 = row.get("partner")
            if not partner_iso3 or partner_iso3.upper() in {"WLD", "ALL"}:
                continue
            rates.append(
                TariffRate(
                    reporter_iso3=row.get("reporter", reporter_iso3.upper()),
                    partner_iso3=partner_iso3.upper(),  # już ISO3
                    year=str(row.get("year")) if row.get("year") else Config.DEFAULT_YEAR,
                    rate_percent=float(row.get("rate")),
                    unit=row.get("unit", "%"),
                    flag=row.get("indicator", None),
                )
            )
        return rates

    def as_api_payload(
        self,
        reporter_iso3: str,
        indicator: Optional[str] = None,
        year: str = "latest",
        debug: bool = False,
    ) -> Dict:
        rates = self.build_tobacco_tariff_map_for_reporter(
            reporter_iso3=reporter_iso3,
            indicator=indicator,
            year=year,
            debug=debug,
        )
        payload: Dict = {
            "reporter": reporter_iso3.upper(),
            "product": {"classification": Config.TOBACCO_CLASSIFICATION, "code": Config.TOBACCO_PRODUCT_CODE},
            "year": year,
            "source": "WTO Timeseries (HS_P_0070, HS chapter 24)",
            "tariffs": [
                {
                    "reporter": r.reporter_iso3,
                    "partner": r.partner_iso3,   # ISO3 → frontend może kolorować
                    "year": r.year,
                    "rate": r.rate_percent,
                    "unit": r.unit,
                    "flag": r.flag,
                }
                for r in rates
            ],
        }
        if debug:
            last = self._wto.get_last_request_info()
            payload["debug_raw"] = {"wto_last_request": {"url": last[0], "params": last[1], "http_status": last[2]} if last else None}
        return payload
