"""Controlled lab traffic generator.

Sends UDP packets at a configurable rate for a configurable duration.
Enforces rate and duration limits. Designed for authorised lab and
benchmarking environments only.
"""

import socket
import time
import threading
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Immutable snapshot of a completed or stopped test."""
    target_ip: str
    target_port: int
    requested_duration: int
    requested_rate: int
    protocol: str
    start_time: datetime
    end_time: datetime
    total_packets: int
    stopped_by_user: bool

    @property
    def actual_duration(self) -> float:
        return (self.end_time - self.start_time).total_seconds()


@dataclass
class TestState:
    """Mutable state of the currently running test."""
    target_ip: str = ""
    target_port: int = 0
    duration: int = 0
    rate: int = 0
    protocol: str = "UDP"
    start_time: Optional[datetime] = None
    total_packets: int = 0
    running: bool = False
    stop_event: Optional[threading.Event] = None
    thread: Optional[threading.Thread] = None

    def elapsed(self) -> float:
        if self.start_time is None:
            return 0.0
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    def remaining(self) -> float:
        return max(0.0, self.duration - self.elapsed())

    def snapshot_dict(self) -> dict:
        """Return a JSON-safe dict for the Streamlit dashboard."""
        return {
            "running": self.running,
            "target_ip": self.target_ip,
            "target_port": self.target_port,
            "duration": self.duration,
            "rate": self.rate,
            "protocol": self.protocol,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "elapsed": round(self.elapsed(), 1),
            "remaining": round(self.remaining(), 1),
            "total_packets": self.total_packets,
        }


class TrafficGenerator:
    """Thread-safe lab traffic generator with hard-coded safety limits."""

    # Absolute hard ceiling regardless of config
    HARD_MAX_RATE = 1000
    HARD_MAX_DURATION = 300  # 5 minutes

    def __init__(self, max_rate: int = 500, max_duration: int = 120):
        self._lock = threading.Lock()
        self.max_rate = min(max_rate, self.HARD_MAX_RATE)
        self.max_duration = min(max_duration, self.HARD_MAX_DURATION)
        self.state = TestState()
        self.history: List[TestResult] = []
        self._log_lines: List[str] = []

    # ---- public API ---------------------------------------------------

    def is_running(self) -> bool:
        with self._lock:
            return self.state.running

    def get_state(self) -> dict:
        with self._lock:
            return self.state.snapshot_dict()

    def get_logs(self, n: int = 50) -> List[str]:
        with self._lock:
            return list(self._log_lines[-n:])

    def start(
        self,
        target_ip: str,
        target_port: int,
        duration: int,
        rate: int,
    ) -> str:
        """Start a new test. Returns a status message."""
        with self._lock:
            if self.state.running:
                return "⚠️ A test is already running. Use /stop first."

            # Clamp to safety limits
            safe_rate = min(rate, self.max_rate, self.HARD_MAX_RATE)
            safe_duration = min(duration, self.max_duration, self.HARD_MAX_DURATION)

            self.state = TestState(
                target_ip=target_ip,
                target_port=target_port,
                duration=safe_duration,
                rate=safe_rate,
                protocol="UDP",
                start_time=datetime.now(timezone.utc),
                total_packets=0,
                running=True,
                stop_event=threading.Event(),
            )
            stop_evt = self.state.stop_event

        msg = (
            f"🚀 Test started → {target_ip}:{target_port}\n"
            f"Duration: {safe_duration}s | Rate: {safe_rate} pps | Protocol: UDP"
        )
        self._log(msg)

        t = threading.Thread(
            target=self._run_test,
            args=(target_ip, target_port, safe_duration, safe_rate, stop_evt),
            daemon=True,
        )
        with self._lock:
            self.state.thread = t
        t.start()
        return msg

    def stop(self) -> str:
        """Immediately stop the active test."""
        with self._lock:
            if not self.state.running:
                return "ℹ️ No test is currently running."
            if self.state.stop_event:
                self.state.stop_event.set()
        return "🛑 Stop signal sent. Test will halt momentarily."

    # ---- internal -----------------------------------------------------

    def _log(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        line = f"[{ts}] {msg}"
        logger.info(msg)
        with self._lock:
            self._log_lines.append(line)
            # Keep log buffer bounded
            if len(self._log_lines) > 200:
                self._log_lines = self._log_lines[-100:]

    def _run_test(
        self,
        ip: str,
        port: int,
        duration: int,
        rate: int,
        stop_event: threading.Event,
    ):
        """Worker thread: sends UDP packets at *rate* pps for *duration* seconds."""
        payload = b"LAB-TEST-PACKET"  # Small, identifiable payload
        interval = 1.0 / rate if rate > 0 else 1.0
        packets_sent = 0
        stopped_by_user = False

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.5)
            deadline = time.monotonic() + duration

            while time.monotonic() < deadline:
                if stop_event.is_set():
                    stopped_by_user = True
                    break

                try:
                    sock.sendto(payload, (ip, port))
                    packets_sent += 1
                except OSError as exc:
                    self._log(f"⚠️ Send error: {exc}")
                    # Continue — transient errors are expected in labs

                with self._lock:
                    self.state.total_packets = packets_sent

                # Rate limiting: sleep for the inter-packet interval
                # Use a short sleep loop so stop_event is checked frequently
                sleep_until = time.monotonic() + interval
                while time.monotonic() < sleep_until:
                    if stop_event.is_set():
                        stopped_by_user = True
                        break
                    time.sleep(min(0.01, interval))
                if stopped_by_user:
                    break

            sock.close()
        except Exception as exc:
            self._log(f"❌ Test error: {exc}")
        finally:
            end_time = datetime.now(timezone.utc)
            with self._lock:
                self.state.total_packets = packets_sent
                start = self.state.start_time or end_time
                result = TestResult(
                    target_ip=ip,
                    target_port=port,
                    requested_duration=duration,
                    requested_rate=rate,
                    protocol="UDP",
                    start_time=start,
                    end_time=end_time,
                    total_packets=packets_sent,
                    stopped_by_user=stopped_by_user,
                )
                self.history.append(result)
                if len(self.history) > 50:
                    self.history = self.history[-50:]
                self.state.running = False
                self.state.stop_event = None
                self.state.thread = None

            reason = "user stop" if stopped_by_user else "completed"
            self._log(
                f"✅ Test finished ({reason}) → {ip}:{port} | "
                f"Sent {packets_sent} packets in {result.actual_duration:.1f}s"
            )
