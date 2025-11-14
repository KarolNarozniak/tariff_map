# Tariff Map — build & run guide

This repository contains a Flask-based interactive map for tariff visualization and basic logistics routing.
This README explains how to build and run the app locally and in production with Gunicorn bound to port `21982`.

---

## Quick overview

- Python 3.10+ required
- Two ways to manage dependencies:
  - Poetry (recommended)
  - pip + requirements.txt
- Configuration is read from environment variables (see `.env.example`).
  - Put secret values into `.env.local` (this file is ignored by git).

---

## 1) Prepare the environment (Poetry)

Install Poetry (if you don't have it):

- Windows (PowerShell):
  ```powershell
  (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
  ```
- Linux / macOS:
  ```bash
  curl -sSL https://install.python-poetry.org | python3 -
  ```

Open a new shell (so `poetry` is on PATH) and then in the project root run:

```bash
poetry install
```

To include the optional production extras (gunicorn):

```bash
poetry install --with prod
```

---

## 2) (Alternative) Prepare the environment with pip

If you prefer pip, create a virtual environment and install packages:

Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Linux/macOS:
```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

If you need `gunicorn` on Windows, use WSL or run the app with a Windows-compatible WSGI server (e.g. waitress). The README below shows gunicorn usage (Linux/WSL/production).

---

## 3) Configuration

- Copy `.env.example` to `.env` for safe defaults (committed). Then create `.env.local` for secrets (never commit that file).

Windows PowerShell example:
```powershell
copy .env.example .env
# Edit .env.local manually in a secure editor, or create with:
notepad .env.local
```

Recommended values to set in `.env.local` (example):
```
SECRET_KEY=your-very-strong-random-secret
ADMIN_USERNAME=admin
ADMIN_PASSWORD=VeryStr0ngP@ss!
WTO_API_KEY=...
WITS_API_KEY=...
SESSION_COOKIE_SECURE=1
```

The app loads `.env` then attempts to load `.env.local` (without overriding existing environment variables). On production, prefer setting real env vars in the system or container.

---

## 4) Run development server (Flask)

Using Poetry:

```bash
poetry run python app.py
```

Using pip / venv:

```powershell
python app.py
```

Open http://localhost:5000 in the browser.

---

## 5) Run production server with Gunicorn on port 21982

> Note: Gunicorn does not run natively on Windows. Use Linux, macOS or WSL for production. Below commands are for Linux/WSL or server environment.

Using Poetry (recommended):

```bash
# ensure prod extras are installed
poetry install --with prod
# run gunicorn with 4 workers, listening on port 21982
poetry run gunicorn "app:create_app()" -b 0.0.0.0:21982 -w 4 --threads 2 --timeout 120
```

Using pip (virtualenv):

```bash
# inside activated venv
pip install gunicorn
gunicorn "app:create_app()" -b 0.0.0.0:21982 -w 4 --threads 2 --timeout 120
```

If you deploy behind a reverse proxy (nginx), bind Gunicorn to a local port (21982 or a socket) and proxy from nginx.

---

## 6) Windows / production alternative

On Windows, use Waitress instead of Gunicorn (pure-Python WSGI server). Install and run:

```powershell
pip install waitress
# run on port 21982
python -m waitress --listen=*:21982 "app:create_app()"
```

Waitress is a solid choice for Windows hosts.

---

## 7) Useful commands and tips

- Export current env from Poetry: `poetry run python -c "import os, json; print(json.dumps(dict(os.environ), indent=2))"`
- Regenerate `requirements.txt` (from Poetry):
  ```bash
  poetry export -f requirements.txt --output requirements.lock.txt --without-hashes --with dev
  ```

- Hard-refresh browser to pick up new JS/CSS: Ctrl+F5 (Windows) or Cmd+Shift+R (macOS).

---

## 8) Security checklist

- Do NOT commit `.env.local` or real secrets to the repository.
- Use strong `SECRET_KEY` and `ADMIN_PASSWORD` in production.
- When running production on HTTPS, set `SESSION_COOKIE_SECURE=1`.
- If exposing the app publicly, run behind a reverse proxy with TLS and enable firewall rules.

---

If you want, I can also add a systemd unit, Dockerfile, and example nginx config to make production deployment smoother.
