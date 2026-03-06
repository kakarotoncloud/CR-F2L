"""Telegram message handlers."""

from __future__ import annotations

import asyncio
import html
import logging
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from bot.config import Settings
from bot.database import Database
from utils.file_manager import (
    build_storage_path,
    is_streamable,
    sanitize_filename,
    sign_payload,
)

logger = logging.getLogger(__name__)


def pretty_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


class RateLimiter:
    """Simple in-memory sliding window rate limiter by user ID."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._store: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        now = time.time()
        dq = self._store[user_id]
        threshold = now - self.window_seconds
        while dq and dq[0] < threshold:
            dq.popleft()
        if len(dq) >= self.limit:
            return False
        dq.append(now)
        return True


def _extract_file_meta(message: Message) -> dict[str, Any] | None:
    if message.document:
        media = message.document
        return {
            "telegram_file_id": media.file_id,
            "telegram_unique_id": media.file_unique_id,
            "file_name": media.file_name or f"{media.file_unique_id}.bin",
            "mime_type": media.mime_type or "application/octet-stream",
            "file_size": media.file_size or 0,
        }

    if message.video:
        media = message.video
        return {
            "telegram_file_id": media.file_id,
            "telegram_unique_id": media.file_unique_id,
            "file_name": media.file_name or f"{media.file_unique_id}.mp4",
            "mime_type": media.mime_type or "video/mp4",
            "file_size": media.file_size or 0,
        }

    if message.audio:
        media = message.audio
        return {
            "telegram_file_id": media.file_id,
            "telegram_unique_id": media.file_unique_id,
            "file_name": media.file_name or f"{media.file_unique_id}.mp3",
            "mime_type": media.mime_type or "audio/mpeg",
            "file_size": media.file_size or 0,
        }

    if message.voice:
        media = message.voice
        return {
            "telegram_file_id": media.file_id,
            "telegram_unique_id": media.file_unique_id,
            "file_name": f"{media.file_unique_id}.ogg",
            "mime_type": media.mime_type or "audio/ogg",
            "file_size": media.file_size or 0,
        }

    if message.animation:
        media = message.animation
        return {
            "telegram_file_id": media.file_id,
            "telegram_unique_id": media.file_unique_id,
            "file_name": media.file_name or f"{media.file_unique_id}.mp4",
            "mime_type": media.mime_type or "video/mp4",
            "file_size": media.file_size or 0,
        }

    if message.photo:
        media = message.photo
        return {
            "telegram_file_id": media.file_id,
            "telegram_unique_id": media.file_unique_id,
            "file_name": f"{media.file_unique_id}.jpg",
            "mime_type": "image/jpeg",
            "file_size": media.file_size or 0,
        }

    return None


def register_handlers(app: Client, settings: Settings, db: Database) -> None:
    limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)

    async def ensure_user(message: Message) -> int | None:
        if not message.from_user:
            return None
        await db.upsert_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            is_bot=bool(message.from_user.is_bot),
        )
        return message.from_user.id

    def is_admin(user_id: int | None) -> bool:
        return bool(user_id and user_id in settings.admin_ids)

    @app.on_message(filters.private & filters.command("start"))
    async def start_handler(_: Client, message: Message) -> None:
        user_id = await ensure_user(message)
        if user_id is None:
            return
        await message.reply_text(
            (
                "Hi! Send me any file (document, video, audio, photo), and I will return:\n"
                "- Direct download link\n"
                "- Streaming/player link (for audio/video)\n\n"
                "Use /help for all commands."
            )
        )

    @app.on_message(filters.private & filters.command("help"))
    async def help_handler(_: Client, message: Message) -> None:
        await ensure_user(message)
        await message.reply_text(
            (
                "<b>Available commands</b>\n"
                "/start - Intro\n"
                "/help - This help\n"
                "/expire [minutes|default] - Set link expiry for your uploads\n\n"
                "<b>Admin commands</b>\n"
                "/stats - Usage statistics\n"
                "/users - Recent users\n"
                "/broadcast &lt;text&gt; - Send message to all users"
            ),
            parse_mode=ParseMode.HTML,
        )

    @app.on_message(filters.private & filters.command("expire"))
    async def expiry_handler(_: Client, message: Message) -> None:
        user_id = await ensure_user(message)
        if user_id is None:
            return

        tokens = (message.text or "").split(maxsplit=1)
        if len(tokens) == 1:
            current = await db.get_user_expiry(user_id)
            if current is None:
                await message.reply_text(
                    f"Using default expiry: {settings.default_link_expiry_seconds // 60} minutes"
                )
            else:
                await message.reply_text(f"Your custom expiry: {current // 60} minutes")
            return

        raw = tokens[1].strip().lower()
        if raw == "default":
            await db.set_user_expiry(user_id, None)
            await message.reply_text("Expiry reset to default.")
            return

        if not raw.isdigit():
            await message.reply_text("Usage: /expire <minutes> or /expire default")
            return

        minutes = int(raw)
        if minutes < 1 or minutes > 7 * 24 * 60:
            await message.reply_text("Choose 1 to 10080 minutes (7 days max).")
            return
        await db.set_user_expiry(user_id, minutes * 60)
        await message.reply_text(f"Custom expiry set to {minutes} minutes.")

    @app.on_message(filters.private & filters.command("stats"))
    async def stats_handler(_: Client, message: Message) -> None:
        user_id = await ensure_user(message)
        if not is_admin(user_id):
            await message.reply_text("You are not allowed to use this command.")
            return

        stats = await db.get_stats()
        await message.reply_text(
            (
                "<b>Bot stats</b>\n"
                f"Users: <code>{stats['users']}</code>\n"
                f"Files indexed: <code>{stats['files']}</code>\n"
                f"Links generated: <code>{stats['links']}</code>\n"
                f"Stored size: <code>{pretty_bytes(stats['total_size_bytes'])}</code>"
            ),
            parse_mode=ParseMode.HTML,
        )

    @app.on_message(filters.private & filters.command("users"))
    async def users_handler(_: Client, message: Message) -> None:
        user_id = await ensure_user(message)
        if not is_admin(user_id):
            await message.reply_text("You are not allowed to use this command.")
            return

        rows = await db.list_users(limit=50)
        if not rows:
            await message.reply_text("No users yet.")
            return

        lines = ["<b>Recent users</b>"]
        for row in rows:
            username = f"@{row['username']}" if row["username"] else "-"
            first_name = html.escape(row["first_name"] or "-")
            lines.append(f"<code>{row['user_id']}</code> | {username} | {first_name}")
        await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    @app.on_message(filters.private & filters.command("broadcast"))
    async def broadcast_handler(client: Client, message: Message) -> None:
        user_id = await ensure_user(message)
        if not is_admin(user_id):
            await message.reply_text("You are not allowed to use this command.")
            return

        text = (message.text or "").split(maxsplit=1)
        if len(text) < 2:
            await message.reply_text("Usage: /broadcast <message>")
            return

        payload = text[1].strip()
        user_ids = await db.all_user_ids()
        sent = 0
        failed = 0
        for uid in user_ids:
            try:
                await client.send_message(uid, payload)
                sent += 1
            except FloodWait as flood_wait:
                await asyncio.sleep(flood_wait.value + 1)
                try:
                    await client.send_message(uid, payload)
                    sent += 1
                except Exception:  # noqa: BLE001
                    failed += 1
            except Exception:  # noqa: BLE001
                failed += 1
        await message.reply_text(f"Broadcast complete. Sent: {sent}, Failed: {failed}")

    @app.on_message(
        filters.private
        & (filters.document | filters.video | filters.audio | filters.photo | filters.animation | filters.voice)
    )
    async def file_handler(client: Client, message: Message) -> None:
        user_id = await ensure_user(message)
        if user_id is None:
            return

        if not limiter.allow(user_id):
            await message.reply_text("Rate limit exceeded. Please wait a little before uploading again.")
            return

        meta = _extract_file_meta(message)
        if not meta:
            await message.reply_text("Unsupported media type.")
            return

        max_bytes = settings.max_file_size_mb * 1024 * 1024
        if meta["file_size"] > max_bytes:
            await message.reply_text(
                f"File too large. Max allowed size is {settings.max_file_size_mb} MB.",
            )
            return

        existing = await db.get_file_by_unique_id(meta["telegram_unique_id"])
        if existing:
            file_id = int(existing["file_id"])
            file_name = existing["file_name"]
            mime_type = existing.get("mime_type")
            file_size = int(existing["file_size"])
            local_path = _resolve_path(existing["local_path"])
            if not local_path.exists():
                status = await message.reply_text("Downloading file from Telegram...")
                local_path.parent.mkdir(parents=True, exist_ok=True)
                downloaded_path = await client.download_media(message=message, file_name=str(local_path))
                if not downloaded_path:
                    await status.edit_text("Failed to download file from Telegram.")
                    return
                actual_path = _resolve_path(downloaded_path)
                if not actual_path.exists():
                    await status.edit_text("Download finished but file not found on disk.")
                    return
                local_path = actual_path
                await db.update_file_path(file_id=file_id, local_path=str(actual_path))
                await status.delete()
        else:
            file_name = sanitize_filename(meta["file_name"])
            local_path = build_storage_path(
                settings.storage_path.resolve(),
                telegram_unique_id=meta["telegram_unique_id"],
                file_name=file_name,
            )
            status = await message.reply_text("Downloading file from Telegram...")
            local_path.parent.mkdir(parents=True, exist_ok=True)
            downloaded_path = await client.download_media(message=message, file_name=str(local_path))
            if not downloaded_path:
                await status.edit_text("Failed to download file from Telegram.")
                return
            actual_path = _resolve_path(downloaded_path)
            if not actual_path.exists():
                await status.edit_text("Download finished but file not found on disk.")
                return

            file_size = int(meta["file_size"])
            mime_type = meta["mime_type"]
            file_id = await db.add_file(
                owner_id=user_id,
                telegram_file_id=meta["telegram_file_id"],
                telegram_unique_id=meta["telegram_unique_id"],
                file_name=file_name,
                mime_type=mime_type,
                file_size=file_size,
                local_path=str(actual_path),
            )
            await status.delete()

        expiry_seconds = await db.get_user_expiry(user_id)
        if expiry_seconds is None:
            expiry_seconds = settings.default_link_expiry_seconds

        token, expires_at = sign_payload(
            payload={"file_id": file_id, "user_id": user_id},
            secret=settings.link_signing_secret,
            expiry_seconds=expiry_seconds,
        )
        await db.add_link(token=token, file_id=file_id, link_type="file", expires_at=expires_at)

        download_link = f"{settings.public_base_url}/d/{token}"
        stream_player_link = f"{settings.public_base_url}/player/{token}"
        stream_raw_link = f"{settings.public_base_url}/s/{token}"
        ttl_minutes = max(expiry_seconds // 60, 1)

        supports_stream = is_streamable(file_name, mime_type)
        text_lines = [
            "<b>File indexed successfully</b>",
            f"<b>Name:</b> <code>{html.escape(file_name)}</code>",
            f"<b>Size:</b> <code>{pretty_bytes(file_size)}</code>",
            f"<b>Expires in:</b> <code>{ttl_minutes} minutes</code>",
            "",
            f"<b>Download:</b>\n{download_link}",
        ]
        if supports_stream:
            text_lines.extend(
                [
                    "",
                    f"<b>Streaming page:</b>\n{stream_player_link}",
                    "",
                    f"<b>Raw stream URL:</b>\n{stream_raw_link}",
                ]
            )
        else:
            text_lines.extend(["", "Streaming page is available for video/audio files."])

        await message.reply_text(
            "\n".join(text_lines),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    @app.on_message(filters.private & ~filters.command(["start", "help", "stats", "users", "broadcast", "expire"]))
    async def fallback_handler(_: Client, message: Message) -> None:
        if message.text:
            await ensure_user(message)
            await message.reply_text("Send a file to generate links, or use /help.")

    logger.info("Telegram handlers registered.")
