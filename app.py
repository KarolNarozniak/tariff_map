# app.py
from flask import Flask
from core.config import Config
from core.logging_config import configure_logging
from interface.api import api_bp
from interface.web import web_bp


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
