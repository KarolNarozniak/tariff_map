# application/tariff_map_service.py
from typing import List, Dict
from integration.wto_adapter import WTOTimeseriesAdapter
from domain.models import TariffRate
from core.config import Config


class TariffMapService:
    """Use-case: zbuduj mapę ceł na tytoń dla wybranego kraju."""

    def __init__(self, wto_adapter: WTOTimeseriesAdapter | None = None) -> None:
        self._wto = wto_adapter or WTOTimeseriesAdapter()

    def build_tobacco_tariff_map_for_reporter(self, reporter_iso3: str) -> List[TariffRate]:
        rows: List[Dict] = self._wto.get_tobacco_tariffs_for_reporter(reporter_iso3)

        rates: List[TariffRate] = []
        for row in rows:
            rates.append(
                TariffRate(
                    reporter_iso3=row["reporter"],
                    partner_iso3=row["partner"],
                    year=row["year"],
                    rate_percent=float(row["rate"]),
                    unit=row.get("unit", "%"),
                    flag=row.get("flag"),
                )
            )
        return rates

    def as_api_payload(self, reporter_iso3: str) -> Dict:
        """
        Opakowanie do użycia w API – zwraca JSON ready structure.
        """
        rates = self.build_tobacco_tariff_map_for_reporter(reporter_iso3)
        payload = {
            "reporter": reporter_iso3,
            "product": {
                "classification": Config.TOBACCO_CLASSIFICATION,
                "code": Config.TOBACCO_PRODUCT_CODE,
            },
            "year": Config.DEFAULT_YEAR,
            "tariffs": [
                {
                    "reporter": r.reporter_iso3,
                    "partner": r.partner_iso3,
                    "year": r.year,
                    "rate": r.rate_percent,
                    "unit": r.unit,
                    "flag": r.flag,
                }
                for r in rates
            ],
        }
        return payload
