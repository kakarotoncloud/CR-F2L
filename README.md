# Telegram File Link Bot

Production-ready Telegram bot that converts uploaded files into secure, expiring:

- Direct download links
- Streaming links
- Browser player links (video/audio)

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Async-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pyrogram](https://img.shields.io/badge/Telegram-Pyrogram-2CA5E0?logo=telegram&logoColor=white)](https://docs.pyrogram.org/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Deploy](https://img.shields.io/badge/Deploy-Heroku%20%7C%20VPS%20%7C%20Colab-6f42c1)](#deployment-guides)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/kakarotoncloud/CR-F2L/blob/main/colab_setup.ipynb)

---

## Table of contents

- [What this bot does](#what-this-bot-does)
- [Features](#features)
- [Quick start options](#quick-start-options)
- [Safe GitHub Actions test mode (1-2 hours)](#safe-github-actions-test-mode-1-2-hours)
- [One-click Google Colab (easiest)](#one-click-google-colab-easiest)
- [Local run](#local-run)
- [Bot commands](#bot-commands)
- [Environment variables](#environment-variables)
- [Deployment guides](#deployment-guides)
  - [Heroku](#heroku)
  - [VPS Ubuntu](#vps-ubuntu)
  - [Google Colab](#google-colab)
- [How links work](#how-links-work)
- [Troubleshooting](#troubleshooting)
- [Security checklist](#security-checklist)
- [Project structure](#project-structure)

---

## What this bot does

When a user sends a file to your bot:

1. Bot receives the file in Telegram.
2. Bot saves and indexes it in SQLite.
3. Bot generates a signed expiring token.
4. Bot sends links back:
   - Download URL
   - Stream URL
   - Player page URL

Supported Telegram media:

- Document
- Video
- Audio
- Photo
- Voice
- Animation

---

## Features

- Fully async architecture (Pyrogram + FastAPI + aiosqlite)
- Signed token links with expiration
- Byte-range streaming support
- Optional HLS generation with FFmpeg
- File deduplication by Telegram unique file ID
- Admin features:
  - `/stats`
  - `/users`
  - `/broadcast <message>`
- User expiry control:
  - `/expire <minutes|default>`
- Basic anti-spam rate limiting
- Structured logging for production

---

## Quick start options

Choose the path that matches your experience:

| You are... | Best option | Time |
|---|---|---|
| Non-technical / beginner | Google Colab | 5-10 min |
| Want simple cloud deployment | Heroku | 10-20 min |
| Want full control + domain + nginx | VPS Ubuntu | 20-40 min |

---

## Safe GitHub Actions test mode (1-2 hours)

This repository includes a safe test workflow:

- `.github/workflows/safe-bot-test.yml`

Use it for temporary checks, not 24/7 hosting.

### Why this is safer

- Manual start only (`Run workflow`)
- Duration is clamped to 15-180 minutes
- Job auto-timeout
- Auto-stop at the end
- Test logs are uploaded as an artifact
- If `PUBLIC_BASE_URL` secret is missing, workflow creates a temporary public Cloudflare tunnel URL

### One-time setup (simple steps)

1. Open your GitHub repository.
2. Go to **Settings -> Secrets and variables -> Actions**.
3. Add these repository secrets:
   - `BOT_TOKEN` (required)
   - `API_ID` (required)
   - `API_HASH` (required)
   - `PUBLIC_BASE_URL` (optional)
   - `ADMIN_IDS` (optional)
   - `LINK_SIGNING_SECRET` (optional but recommended)

### How to run

1. Go to **Actions** tab in your repository.
2. Open workflow: **Safe Bot Test Run**.
3. Click **Run workflow**.
4. Enter:
   - `duration_minutes` (for example `60` or `120`)
   - `max_file_size_mb` (for example `2048`)
5. Click **Run workflow** button.
6. Open run logs and verify `health` checks are passing.
7. If you did not set `PUBLIC_BASE_URL`, copy the printed line:
   - `Temporary public URL: https://...trycloudflare.com`
   Links sent by bot will use this URL while workflow is running.

### Important note

This is intended for temporary testing (like daily 1-2 hours), not permanent hosting.

---

## Before you run (Telegram credentials)

You need these values:

- `BOT_TOKEN` (from **@BotFather**)
- `API_ID` (from https://my.telegram.org)
- `API_HASH` (from https://my.telegram.org)

How to get them quickly:

1. Open Telegram and chat with **@BotFather**
2. Run `/newbot` and create your bot
3. Copy the bot token
4. Open https://my.telegram.org -> API Development Tools
5. Create app and copy API ID + API HASH

---

## One-click Google Colab (easiest)

Click:

- https://colab.research.google.com/github/kakarotoncloud/CR-F2L/blob/main/colab_setup.ipynb

Then:

1. Run cells top-to-bottom.
2. Enter `BOT_TOKEN`, `API_ID`, `API_HASH`.
3. (Optional) Enter public URL and port.
4. Notebook installs dependencies, writes `.env`, starts bot.
5. You get running status + URL.

Note: For public links in Colab, use a tunnel (Cloudflare Tunnel / ngrok) and set that as `PUBLIC_BASE_URL`.

---

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
python -m bot.main
```

Health check:

```bash
curl http://127.0.0.1:8080/health
```

Expected:

```json
{"status":"ok"}
```

---

## Bot commands

### User commands

| Command | Description |
|---|---|
| `/start` | Welcome message and usage |
| `/help` | Show all commands |
| `/expire <minutes>` | Set personal link expiry |
| `/expire default` | Reset to default expiry |

### Admin commands

| Command | Description |
|---|---|
| `/stats` | Show users/files/links/storage stats |
| `/users` | Show recent users |
| `/broadcast <message>` | Send message to all users |

---

## Environment variables

Copy `.env.example` to `.env` and set values.

### Required

| Variable | Example | Purpose |
|---|---|---|
| `BOT_TOKEN` | `123456:ABC...` | Bot token from BotFather |
| `API_ID` | `123456` | Telegram API ID |
| `API_HASH` | `xxxxxxxx` | Telegram API hash |
| `PUBLIC_BASE_URL` | `https://files.example.com` | URL used in generated links |

### Common optional

| Variable | Default | Purpose |
|---|---|---|
| `ADMIN_IDS` | empty | Comma-separated Telegram numeric user IDs |
| `LINK_SIGNING_SECRET` | derived fallback | Secret for secure token signing |
| `LINK_EXPIRY_SECONDS` | `86400` | Default link expiration (24h) |
| `RATE_LIMIT_REQUESTS` | `8` | Requests allowed per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window seconds |
| `MAX_FILE_SIZE_MB` | `2048` | Max accepted upload size |
| `FFMPEG_ENABLED` | `true` | Enable HLS endpoints |
| `PORT` | `8080` | HTTP server port |
| `SERVER_HOST` | `0.0.0.0` | HTTP bind host |

---

## Deployment guides

### Heroku

Already included:

- `Procfile`
- `runtime.txt`
- `requirements.txt`

Steps:

1. Create Heroku app.
2. Connect your GitHub repository.
3. Deploy your branch.
4. Add Config Vars in Heroku settings:
   - `BOT_TOKEN`
   - `API_ID`
   - `API_HASH`
   - `PUBLIC_BASE_URL`
   - `LINK_SIGNING_SECRET`
5. Open `/health` endpoint to verify.

Important: Heroku file system is ephemeral. For large/long-term storage, use external storage.

---

### VPS Ubuntu

### 1) Install packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg nginx git
```

### 2) Setup project

```bash
sudo mkdir -p /opt/telegram-file-link-bot
sudo chown -R $USER:$USER /opt/telegram-file-link-bot
cd /opt/telegram-file-link-bot
git clone <YOUR_REPO_URL> .
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
```

### 3) Setup systemd service

```bash
sudo cp deploy/telegram-file-link-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-file-link-bot
sudo systemctl start telegram-file-link-bot
sudo systemctl status telegram-file-link-bot
```

### 4) Setup nginx reverse proxy

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/telegram-file-link-bot
sudo ln -s /etc/nginx/sites-available/telegram-file-link-bot /etc/nginx/sites-enabled/telegram-file-link-bot
sudo nginx -t
sudo systemctl reload nginx
```

Then add TLS using Certbot (recommended).

---

### Google Colab

Use `colab_setup.ipynb`:

1. Prompts for required credentials.
2. Clones project and installs dependencies.
3. Creates `.env`.
4. Starts bot + API.
5. Prints status and URL.

Direct link:

- https://colab.research.google.com/github/kakarotoncloud/CR-F2L/blob/main/colab_setup.ipynb

---

## How links work

- Download: `/d/<token>`
- Stream: `/s/<token>`
- Player: `/player/<token>`
- HLS playlist (optional): `/hls/<token>/index.m3u8`

Tokens are signed and auto-expire.

---

## Troubleshooting

### Bot does not start

- Verify `BOT_TOKEN`, `API_ID`, `API_HASH`
- Ensure Python 3.11+ is installed
- Reinstall dependencies: `pip install -r requirements.txt`

### Links not opening publicly

- Check `PUBLIC_BASE_URL`
- Check domain DNS
- Check nginx/reverse proxy

### Streaming problems

- Verify FFmpeg: `ffmpeg -version`
- Ensure `FFMPEG_ENABLED=true`
- Try HLS link in player page

### Admin commands denied

- Confirm your numeric Telegram user ID is in `ADMIN_IDS`

---

## Security checklist

- Use strong random `LINK_SIGNING_SECRET`
- Use HTTPS in production
- Restrict `ADMIN_IDS`
- Set safe `MAX_FILE_SIZE_MB`
- Consider external storage for serious scale

---

## Project structure

```text
telegram-file-link-bot/
|
|-- bot/
|   |-- __init__.py
|   |-- main.py
|   |-- handlers.py
|   |-- config.py
|   `-- database.py
|
|-- server/
|   |-- __init__.py
|   |-- api.py
|   `-- streaming.py
|
|-- templates/
|   `-- player.html
|
|-- utils/
|   |-- __init__.py
|   `-- file_manager.py
|
|-- deploy/
|   |-- telegram-file-link-bot.service
|   `-- nginx.conf.example
|
|-- .env.example
|-- requirements.txt
|-- Procfile
|-- runtime.txt
|-- colab_setup.ipynb
`-- README.md
```

---

## Screenshots placeholders

- `docs/screenshots/01-upload-response.png`
- `docs/screenshots/02-player-page.png`
- `docs/screenshots/03-admin-stats.png`

---

## License

Use MIT (or your preferred license).
