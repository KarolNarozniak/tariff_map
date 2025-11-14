# app.py
from flask import Flask
from core.config import Config
from core.logging_config import configure_logging
from interface.api import api_bp
from interface.web import web_bp

# NEW: wczytanie .env (dev-friendly)
try:
    from dotenv import load_dotenv
    load_dotenv()  # wczyta zmienne z .env, jeśli istnieje
    # Dodatkowe lokalne zmienne (niecommitowalne) – .env.local nadpisuje tylko brakujące wartości
    load_dotenv(dotenv_path='.env.local', override=False)
except Exception:
    pass


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    configure_logging(app)

    # rejestracja blueprintów
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
