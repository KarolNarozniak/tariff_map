# core/config.py
import os


class Config:
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # Admin – proste logowanie
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "password123")

    # WTO – w PoC nieużywane, ale zostawiamy hooki
    WTO_API_KEY = os.environ.get("WTO_API_KEY", "")
    WTO_DEFAULT_LANGUAGE = 1
    WTO_DEFAULT_FORMAT = "json"
    WTO_DEFAULT_OUTPUT_MODE = "full"

    # Produkt – tytoń (HS 24 – uproszczone)
    TOBACCO_CLASSIFICATION = "HS"
    TOBACCO_PRODUCT_CODE = "24"

    DEFAULT_YEAR = "2023"
