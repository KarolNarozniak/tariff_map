# domain/models.py
from dataclasses import dataclass
from typing import Optional


@dataclass
class TariffRate:
    reporter_iso3: str
    partner_iso3: str
    year: str
    rate_percent: float
    unit: str = "%"
    flag: Optional[str] = None
