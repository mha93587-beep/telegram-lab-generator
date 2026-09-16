"""Telegram bot integration for the lab traffic generator.

Runs the python-telegram-bot polling loop in a background thread so it
does not block the Streamlit event loop.
"""

import asyncio
import logging
import threading
from typing import Optional

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from config import (
    get_telegram_token,
    get_authorized_user_ids,
    get_max_duration,
    get_max_rate,
    validate_ip,
    validate_port,
    validate_duration,
    validate_rate,
)
from traffic_generator import TrafficGenerator

logger = logging.getLogger(__name__)

# ── Module-level singleton guard ────────────────────────────────────────
_bot_lock = threading.Lock()
_bot_thread: Optional[threading.Thread] = None
_bot_app: Optional[Application] = None
_generator: Optional[TrafficGenerator] = None
_bot_running = False
_bot_connected = False


def get_generator() -> TrafficGenerator:
    """Return the shared TrafficGenerator instance."""
    global _generator
    if _generator is None:
        _generator = TrafficGenerator(
            max_rate=get_max_rate(),
            max_duration=get_max_duration(),
        )
    return _generator


def is_bot_running() -> bool:
    return _bot_running


def is_bot_connected() -> bool:
    return _bot_connected


# ── Authorisation decorator ─────────────────────────────────────────────

def authorized(func):
    """Decorator: reject commands from unauthorised users."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        allowed = get_authorized_user_ids()
        if allowed and user_id not in allowed:
            await update.message.reply_text(
                "🚫 You are not authorised to use this bot."
            )
            logger.warning("Unauthorised access attempt by user %s", user_id)
            return
        return await func(update, context)
    return wrapper


# ── Command handlers ────────────────────────────────────────────────────

@authorized
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help / available commands."""
    max_dur = get_max_duration()
    max_r = get_max_rate()
    text = (
        "🔬 *Lab Traffic Generator*\n\n"
        "Available commands:\n"
        "/start — show this help\n"
        "/status — current test status\n"
        "/send <IP> <port> <duration> <rate> — start a test\n"
        "/stop — stop the running test\n\n"
        f"Limits: max duration={max_dur}s, max rate={max_r} pps\n"
        "Only private/lab IPs are accepted (RFC 1918).\n\n"
        "Example:\n"
        "`/send 192.168.1.100 8080 30 100`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


@authorized
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current test status."""
    gen = get_generator()
    state = gen.get_state()
    if state["running"]:
        text = (
            "🟢 *Test Running*\n"
            f"Target: `{state['target_ip']}:{state['target_port']}`\n"
            f"Protocol: {state['protocol']}\n"
            f"Rate: {state['rate']} pps\n"
            f"Elapsed: {state['elapsed']}s\n"
            f"Remaining: {state['remaining']}s\n"
            f"Packets sent: {state['total_packets']}"
        )
    else:
        text = "⚪ No test is currently running."
    await update.message.reply_text(text, parse_mode="Markdown")


@authorized
async def cmd_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parse parameters and start a lab test."""
    args = context.args
    if not args or len(args) != 4:
        await update.message.reply_text(
            "Usage: `/send <IP> <port> <duration> <rate>`\n"
            "Example: `/send 192.168.1.100 8080 30 100`",
            parse_mode="Markdown",
        )
        return

    ip_str, port_str, dur_str, rate_str = args
    max_dur = get_max_duration()
    max_r = get_max_rate()

    try:
        ip = validate_ip(ip_str)
        port = validate_port(int(port_str))
        duration = validate_duration(int(dur_str), max_dur)
        rate = validate_rate(int(rate_str), max_r)
    except (ValueError, TypeError) as exc:
        await update.message.reply_text(f"❌ Validation error: {exc}")
        return

    gen = get_generator()
    result_msg = gen.start(ip, port, duration, rate)
    await update.message.reply_text(result_msg)


@authorized
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the running test."""
    gen = get_generator()
    result_msg = gen.stop()
    await update.message.reply_text(result_msg)


# ── Bot lifecycle ───────────────────────────────────────────────────────

def _run_bot_in_thread():
    """Entry point for the background thread that runs the Telegram bot."""
    global _bot_app, _bot_connected, _bot_running

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        token = get_telegram_token()
        app = (
            Application.builder()
            .token(token)
            .build()
        )
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("send", cmd_send))
        app.add_handler(CommandHandler("stop", cmd_stop))

        _bot_app = app
        _bot_connected = True
        _bot_running = True
        logger.info("Telegram bot polling started.")

        # run_polling blocks until the application shuts down
        loop.run_until_complete(
            app.run_polling(
                drop_pending_updates=True,
                close_loop=False,
            )
        )
    except Exception:
        logger.exception("Telegram bot thread crashed.")
    finally:
        _bot_running = False
        _bot_connected = False
        loop.close()


def start_bot() -> None:
    """Start the Telegram bot in a daemon thread (idempotent)."""
    global _bot_thread
    with _bot_lock:
        if _bot_thread is not None and _bot_thread.is_alive():
            logger.debug("Bot thread already running – skipping.")
            return
        _bot_thread = threading.Thread(
            target=_run_bot_in_thread,
            daemon=True,
            name="telegram-bot",
        )
        _bot_thread.start()
        logger.info("Telegram bot thread launched.")


def stop_bot() -> None:
    """Request a graceful shutdown of the bot (best-effort)."""
    global _bot_app
    if _bot_app is not None:
        try:
            # Schedule shutdown from the bot's own event loop
            loop = _bot_app._loop  # type: ignore[attr-defined]
            if loop and loop.is_running():
                loop.call_soon_threadsafe(_bot_app.stop_running)
        except Exception:
            logger.debug("Could not cleanly stop bot.", exc_info=True)
