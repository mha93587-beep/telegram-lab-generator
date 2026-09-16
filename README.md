# 🔬 Telegram Lab Traffic Generator

A **Python-based, Telegram-controlled network traffic generator** built for authorised laboratory and benchmarking environments. Deployed on **Streamlit Community Cloud** — no Docker, no systemd, no root required.

> **⚠️ IMPORTANT:** This tool is designed exclusively for controlled lab and benchmarking environments. It enforces strict rate limits, duration limits, IP validation, and user authorisation. It is **not** a DDoS or flooding tool.

---

## 📁 Project Structure

```
telegram-lab-generator/
├── app.py                          # Streamlit dashboard (entry point)
├── telegram_bot.py                 # Telegram bot integration
├── traffic_generator.py            # Controlled traffic engine
├── config.py                       # Configuration & validation
├── requirements.txt                # Python dependencies
├── README.md                       # This file
└── .streamlit/
    └── secrets.toml.example        # Example secrets template
```

### File Responsibilities

| File | Responsibility |
|---|---|
| `app.py` | Streamlit entry point. Renders the real-time dashboard, starts the bot in a background thread, provides a UI stop button. |
| `telegram_bot.py` | Handles all Telegram commands (`/start`, `/status`, `/send`, `/stop`). Runs the polling loop in a daemon thread. Enforces user authorisation. |
| `traffic_generator.py` | Thread-safe UDP packet generator with rate limiting. Maintains test state, history, and logs. Enforces hard safety ceilings. |
| `config.py` | Loads secrets from `st.secrets` or environment variables. Validates IP addresses, ports, durations, and rates. Blocks multicast/broadcast. |
| `requirements.txt` | Pinned dependencies for Streamlit Community Cloud. |
| `.streamlit/secrets.toml.example` | Template for configuring secrets (never committed with real values). |

---

## 🚀 Deployment on Streamlit Community Cloud

### Prerequisites

1. A **GitHub account** (Streamlit Community Cloud deploys from GitHub)
2. A **Telegram bot token** from [@BotFather](https://t.me/BotFather)
3. Your **Telegram user ID** (get it from [@userinfobot](https://t.me/userinfobot))

### Step-by-Step

#### 1. Push to GitHub

```bash
# Create a new repo on GitHub, then:
cd telegram-lab-generator
git init
git add .
git commit -m "Initial commit: lab traffic generator"
git remote add origin https://github.com/YOUR_USERNAME/telegram-lab-generator.git
git push -u origin main
```

> **🛑 Never commit `.streamlit/secrets.toml` with real credentials.** Add it to `.gitignore`.

#### 2. Create a `.gitignore`

```gitignore
.streamlit/secrets.toml
__pycache__/
*.pyc
```

#### 3. Deploy on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **"New app"**
3. Connect your GitHub repository
4. Set **Main file path** to `app.py`
5. Click **"Deploy"**

#### 4. Configure Secrets

In the Streamlit Community Cloud dashboard:

1. Open your deployed app's settings (⋮ → **Settings**)
2. Go to the **Secrets** tab
3. Paste your secrets in TOML format:

```toml
TELEGRAM_BOT_TOKEN = "123456789:ABCdefGhIJKlmNoPQRsTUVwxYZ"
AUTHORIZED_TELEGRAM_USER_IDS = "111111111,222222222"
MAX_DURATION = "120"
MAX_RATE = "500"
```

4. Click **Save** — the app will restart automatically

---

## 🤖 Telegram Commands

| Command | Description | Example |
|---|---|---|
| `/start` | Show help and available commands | `/start` |
| `/status` | Show current test status | `/status` |
| `/send <IP> <port> <duration> <rate>` | Start a controlled traffic test | `/send 192.168.1.100 8080 30 100` |
| `/stop` | Immediately stop the running test | `/stop` |

### `/send` Parameters

| Parameter | Description | Constraints |
|---|---|---|
| `IP` | Destination lab server IP | Must be private/RFC 1918. No multicast/broadcast. |
| `port` | Destination port | 1–65535 |
| `duration` | Test duration in seconds | 1 to `MAX_DURATION` (default 120, hard cap 300) |
| `rate` | Max packets per second | 1 to `MAX_RATE` (default 500, hard cap 1000) |

### Command Examples

```
/send 192.168.1.100 8080 30 100
→ Send to 192.168.1.100:8080, 30 seconds, 100 pps

/send 10.0.0.5 5000 60 250
→ Send to 10.0.0.5:5000, 60 seconds, 250 pps

/status
→ Shows: target, elapsed time, packets sent, rate

/stop
→ Immediately halts the running test
```

---

## 📊 Streamlit Dashboard

The web dashboard shows:

- **Bot connection status** — whether the Telegram polling loop is active
- **Configuration overview** — authorised users count, max duration, max rate
- **Current test status** — destination, protocol, start time, elapsed/remaining time, rate, packet count
- **Stop button** — immediately stop the active test from the web UI
- **Recent logs** — timestamped test events (start, stop, errors)

> The dashboard **never** exposes the Telegram bot token or other secrets.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│         Streamlit Community Cloud Process        │
│                                                  │
│  ┌──────────────┐    ┌────────────────────────┐  │
│  │  Streamlit    │    │  Background Thread     │  │
│  │  Dashboard    │◄──►│  Telegram Bot Polling  │  │
│  │  (app.py)     │    │  (telegram_bot.py)     │  │
│  └──────┬───────┘    └──────────┬─────────────┘  │
│         │                       │                 │
│         │    ┌──────────────┐   │                 │
│         └───►│  Traffic     │◄──┘                 │
│              │  Generator   │                     │
│              │  (thread-    │──── UDP packets ──► │
│              │   safe)      │    to lab target    │
│              └──────────────┘                     │
└─────────────────────────────────────────────────┘
```

### Key Design Decisions

| Concern | Solution |
|---|---|
| Bot + Streamlit coexistence | Bot runs in a daemon thread; Streamlit reruns don't restart it (singleton guard via `st.session_state` + thread lock) |
| Shared state safety | `TrafficGenerator` uses `threading.Lock` for all state access |
| No duplicate bots | Module-level lock + alive-check prevents multiple polling loops |
| Auto-cleanup | Daemon threads die when the process exits; `atexit` handler requests graceful shutdown |
| Auto-refresh dashboard | `st.rerun()` with 2-second delay while a test is active |
| No inbound ports needed | Telegram uses outbound HTTPS polling; Streamlit Cloud provides the web endpoint |

---

## 🛡️ Safety Controls

| Control | Implementation |
|---|---|
| **Authorised users only** | `AUTHORIZED_TELEGRAM_USER_IDS` — only listed Telegram IDs can execute commands |
| **Private IPs only** | Validates against RFC 1918 + CGNAT ranges; rejects public IPs |
| **No multicast/broadcast** | Explicitly blocked in `validate_ip()` |
| **Rate limiting** | Configurable `MAX_RATE` with a hard ceiling of 1000 pps in code |
| **Duration limiting** | Configurable `MAX_DURATION` with a hard ceiling of 300 seconds in code |
| **Single test at a time** | `start()` rejects if a test is already running |
| **Immediate stop** | `/stop` command and dashboard button trigger `threading.Event` |
| **Input validation** | All parameters (IP, port, duration, rate) are validated before use |
| **No secrets exposure** | Dashboard masks the token; logs omit sensitive data |

### Hard-Coded Safety Ceilings

Even if `MAX_RATE` or `MAX_DURATION` are set higher in configuration, the code enforces:

- **Maximum rate:** 1000 packets/second
- **Maximum duration:** 300 seconds (5 minutes)

These cannot be overridden via configuration.

---

## ⚙️ Configuration Reference

| Variable | Description | Default | Hard Limit |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | *(required)* | — |
| `AUTHORIZED_TELEGRAM_USER_IDS` | Comma-separated Telegram user IDs | *(empty = no access)* | — |
| `MAX_DURATION` | Max test duration in seconds | `120` | `300` |
| `MAX_RATE` | Max packets per second | `500` | `1000` |

### Configuration via Environment Variables

For local development, you can use environment variables instead of Streamlit secrets:

```bash
export TELEGRAM_BOT_TOKEN="your-token-here"
export AUTHORIZED_TELEGRAM_USER_IDS="123456789"
export MAX_DURATION="60"
export MAX_RATE="200"
streamlit run app.py
```

---

## 🧪 Local Development

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/telegram-lab-generator.git
cd telegram-lab-generator

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure secrets (copy and edit)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your real values

# Run locally
streamlit run app.py
```

---

## 🔧 Troubleshooting

### Bot Not Connecting

| Symptom | Solution |
|---|---|
| Dashboard shows "🔴 Not running" | Check that `TELEGRAM_BOT_TOKEN` is set correctly in Streamlit Secrets |
| Bot doesn't respond to commands | Verify you've messaged the correct bot; check that your user ID is in `AUTHORIZED_TELEGRAM_USER_IDS` |
| "Unauthorised" message | Your Telegram user ID is not in the allowed list. Get your ID from [@userinfobot](https://t.me/userinfobot) |

### Test Issues

| Symptom | Solution |
|---|---|
| `/send` returns validation error | Check that the target IP is in a private range (192.168.x.x, 10.x.x.x, 172.16-31.x.x) |
| "A test is already running" | Use `/stop` first, then start a new test |
| Low packet count | Streamlit Cloud has limited network throughput; this is expected for a cloud-hosted lab tool |
| Send errors in logs | The target server may be unreachable from Streamlit Cloud's network; use this for reachable lab targets |

### Streamlit Cloud Issues

| Symptom | Solution |
|---|---|
| App crashes on start | Check the logs in Streamlit Cloud dashboard; ensure `requirements.txt` is present |
| Secrets not loading | Verify secrets are saved in TOML format in the Streamlit Cloud settings |
| App sleeps/restarts | Streamlit Community Cloud may idle apps; the bot restarts automatically on the next visit |

### Getting Your Telegram User ID

1. Open Telegram and message [@userinfobot](https://t.me/userinfobot)
2. It will reply with your user ID (a number like `123456789`)
3. Add this number to `AUTHORIZED_TELEGRAM_USER_IDS`

### Creating a Bot Token

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Follow the prompts to name your bot
4. Copy the token (format: `123456789:ABCdefGhIJKlmNoPQRsTUVwxYZ`)
5. Add it to `TELEGRAM_BOT_TOKEN`

---

## 📄 License

This project is provided as-is for authorised laboratory and benchmarking use only. Use responsibly and only against systems you own or have explicit permission to test.
