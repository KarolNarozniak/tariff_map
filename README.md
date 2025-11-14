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
```
## 2) Clone repo on Linux server

On your Linux server (or in a cloud VM), clone the repository and enter the folder:

```bash
git clone https://github.com/KarolNarozniak/tariff_map.git
cd tariff_map
```

You should run the rest of the steps as a non-root deploy user.

---

## 3) Prepare the environment (Linux server, recommended)

Install system dependencies (example for Debian/Ubuntu):

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential curl
```

Recommended: use Poetry (optional) or a plain virtualenv.

Poetry (system-wide or per-user):

```bash
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
poetry install --no-interaction --no-ansi
```

Using virtualenv + pip (simple and portable):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Notes:
- `poetry install --with prod` will also install `gunicorn` if you want Poetry-managed production deps.

---

## 4) Configuration (Linux)

Create environment files. We ship a safe `.env.example` with defaults. Create a local secrets file `.env.local` (never commit this):

```bash
cp .env.example .env
nano .env.local
# paste strong SECRET_KEY, ADMIN_PASSWORD, and any API keys
```

Example entries to set in `.env.local`:

```
SECRET_KEY=your-very-strong-random-secret
ADMIN_USERNAME=admin
ADMIN_PASSWORD=VeryStr0ngP@ss!
WTO_API_KEY=...
WITS_API_KEY=...
SESSION_COOKIE_SECURE=1
```

The app loads `.env` then `.env.local` (without overriding existing environment variables). In production you should prefer setting real variables in systemd unit or container environment.

---

## 5) Run the app with Gunicorn on port 21982 (Linux)

Run with Poetry (recommended):

```bash
poetry run gunicorn "app:create_app()" -b 0.0.0.0:21982 -w 4 --threads 2 --timeout 120
```

Or with virtualenv + pip:

```bash
source .venv/bin/activate
gunicorn "app:create_app()" -b 0.0.0.0:21982 -w 4 --threads 2 --timeout 120
```

### Run as a systemd service (recommended for servers)

Create `/etc/systemd/system/tariff_map.service` (run as deploy user):

```
[Unit]
Description=Tariff Map (Gunicorn)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/tariff_map
EnvironmentFile=/path/to/tariff_map/.env
EnvironmentFile=-/path/to/tariff_map/.env.local
ExecStart=/path/to/venv/bin/gunicorn "app:create_app()" -b 0.0.0.0:21982 -w 4 --threads 2
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Reload and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tariff_map.service
sudo journalctl -u tariff_map -f
```

---

## 6) Optional: nginx reverse-proxy (TLS)

Install certbot / nginx and create a proxy config that forwards `/:` to `http://127.0.0.1:21982` and handles HTTPS termination. Example server block:

```
server {
  listen 80;
  server_name your.domain.example;
  location / {
    proxy_pass http://127.0.0.1:21982;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

Then secure with Certbot (Let's Encrypt) and reload nginx.

---

## 7) Post-deploy checklist

- Ensure `.env.local` is present and contains production secrets.
- Set `SESSION_COOKIE_SECURE=1` when running under HTTPS.
- Restrict firewall (allow 21982 only from your reverse proxy or internal network).

---

## 8) Troubleshooting

- If static assets (JS/CSS) do not update, clear browser cache or use hard refresh (Ctrl+F5).
- If Gunicorn fails to start, check `journalctl -u tariff_map` for logs.

---

If you want, I can generate a ready-to-use systemd unit and nginx config with your domain/path inserted.

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
