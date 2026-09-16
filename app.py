"""Streamlit dashboard for the Telegram Lab Traffic Generator.

This is the entry-point that Streamlit Community Cloud runs.
It launches the Telegram bot in a background thread and renders
a real-time dashboard.
"""

import atexit
import time
from datetime import datetime, timezone

import streamlit as st

# ── Page config (must be first Streamlit call) ──────────────────────────
st.set_page_config(
    page_title="Lab Traffic Generator",
    page_icon="🔬",
    layout="wide",
)

from telegram_bot import (
    start_bot,
    stop_bot,
    is_bot_running,
    is_bot_connected,
    get_generator,
)
from config import get_authorized_user_ids, get_max_duration, get_max_rate

# ── Start bot once per process ──────────────────────────────────────────
if "bot_started" not in st.session_state:
    start_bot()
    atexit.register(stop_bot)
    st.session_state.bot_started = True

# ── Shared objects ──────────────────────────────────────────────────────
generator = get_generator()


# ── Helper ──────────────────────────────────────────────────────────────
def _mask(token_present: bool) -> str:
    return "✅ Configured" if token_present else "❌ Not configured"


# ═══════════════════════════════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════════════════════════════

st.title("🔬 Lab Traffic Generator")
st.caption("Telegram-controlled network traffic generator for authorised lab environments.")

# ── Sidebar: configuration overview ────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")
    st.metric("Bot Token", _mask(True))  # token is loaded at import time
    auth_ids = get_authorized_user_ids()
    st.metric("Authorised Users", len(auth_ids) if auth_ids else "⚠️ None")
    st.metric("Max Duration", f"{get_max_duration()}s")
    st.metric("Max Rate", f"{get_max_rate()} pps")
    st.divider()
    st.subheader("Bot Status")
    if is_bot_connected():
        st.success("🟢 Connected & polling")
    elif is_bot_running():
        st.warning("🟡 Starting…")
    else:
        st.error("🔴 Not running")

# ── Main area ──────────────────────────────────────────────────────────

state = generator.get_state()

col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Current Test")
    if state["running"]:
        st.success("🟢 Test in progress")
        st.markdown(f"**Destination:** `{state['target_ip']}:{state['target_port']}`")
        st.markdown(f"**Protocol:** {state['protocol']}")

        if state["start_time"]:
            st.markdown(f"**Start time:** {state['start_time']}")

        m1, m2, m3 = st.columns(3)
        m1.metric("Elapsed", f"{state['elapsed']}s")
        m2.metric("Remaining", f"{state['remaining']}s")
        m3.metric("Rate", f"{state['rate']} pps")

        st.metric("Total Packets Sent", f"{state['total_packets']:,}")

        # Stop button
        if st.button("🛑 Stop Test", type="primary", use_container_width=True):
            generator.stop()
            st.toast("Stop signal sent!")
            time.sleep(0.5)
            st.rerun()
    else:
        st.info("⚪ No test running. Send `/send` via Telegram to start one.")

with col2:
    st.subheader("📜 Recent Logs")
    logs = generator.get_logs(30)
    if logs:
        log_text = "\n".join(reversed(logs))
        st.code(log_text, language="text")
    else:
        st.caption("No log entries yet.")

# ── Auto-refresh while a test is running ────────────────────────────────
if state["running"]:
    time.sleep(2)
    st.rerun()
