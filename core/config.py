# core/config.py
import os


class Config:
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # Admin – proste logowanie
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "password123")

    # WTO – Timeseries API
    WTO_API_KEY = os.environ.get("WTO_API_KEY", "")
    WTO_DEFAULT_LANGUAGE = int(os.environ.get("WTO_DEFAULT_LANGUAGE", "1"))  # 1=en
    WTO_DEFAULT_FORMAT = os.environ.get("WTO_DEFAULT_FORMAT", "json")

    # WITS – opcjonalny klucz (często zbędny)
    WITS_API_KEY = os.environ.get("WITS_API_KEY", "")

    # Produkt – tytoń (HS 24 – uproszczone)
    TOBACCO_CLASSIFICATION = os.environ.get("TOBACCO_CLASSIFICATION", "HS")
    TOBACCO_PRODUCT_CODE = os.environ.get("TOBACCO_PRODUCT_CODE", "24")

    DEFAULT_YEAR = os.environ.get("DEFAULT_YEAR", "2023")
