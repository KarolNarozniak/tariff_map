# integration/wto_adapter.py
from typing import List, Dict
from core.config import Config


class WTOTimeseriesAdapter:
    """
    Adapter / stub do WTO.
    W przyszłości możesz tu użyć realnej biblioteki `wto` i Timeseries API.
    """

    def __init__(self) -> None:
        self.api_key = Config.WTO_API_KEY

    def get_tobacco_tariffs_for_reporter(self, reporter_iso3: str) -> List[Dict]:
        """
        Zwraca stawki celne na tytoń dla "kraju docelowego" (reporter),
        względem kilku przykładowych krajów eksportujących.
        W realnej wersji: pobierasz dane z WTO.
        """
        # Mockowane dane – dla PoC.
        # Wyobrażamy sobie: reporter = "POL" (Polska).
        # Stawki w % – czysto przykładowe.
        if reporter_iso3 == "POL":
            data = [
                {"reporter": "POL", "partner": "DEU", "year": Config.DEFAULT_YEAR, "rate": 5.0, "unit": "%"},
                {"reporter": "POL", "partner": "FRA", "year": Config.DEFAULT_YEAR, "rate": 7.5, "unit": "%"},
                {"reporter": "POL", "partner": "USA", "year": Config.DEFAULT_YEAR, "rate": 10.0, "unit": "%"},
                {"reporter": "POL", "partner": "ZAF", "year": Config.DEFAULT_YEAR, "rate": 12.0, "unit": "%"},
                {"reporter": "POL", "partner": "BRA", "year": Config.DEFAULT_YEAR, "rate": 20.0, "unit": "%"},
            ]
        else:
            # Dla innych krajów: po prostu inne przykładowe dane
            data = [
                {"reporter": reporter_iso3, "partner": "POL", "year": Config.DEFAULT_YEAR, "rate": 4.0, "unit": "%"},
                {"reporter": reporter_iso3, "partner": "USA", "year": Config.DEFAULT_YEAR, "rate": 8.0, "unit": "%"},
                {"reporter": reporter_iso3, "partner": "CHN", "year": Config.DEFAULT_YEAR, "rate": 15.0, "unit": "%"},
            ]
        return data
