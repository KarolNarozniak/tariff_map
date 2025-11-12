# core/logging_config.py
import logging
from flask import Flask


def configure_logging(app: Flask) -> None:
    """Prosta konfiguracja logowania."""
    log_level_name = app.config.get("LOG_LEVEL", "INFO")
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app.logger.setLevel(log_level)
    app.logger.info("Logging configured, level=%s", log_level_name)
