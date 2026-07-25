"""
assistant_core.py
==================
Shared "brain" of the voice assistant: intent parsing, configuration
loading, the local knowledge base, and thin API clients for weather
and email.

Design note
-----------
speech_recognition and pyttsx3 (audio I/O) are imported lazily, only
inside the Speaker/Listener classes that need them. Everything else in
this module is pure Python logic with no hardware or audio-library
dependency, which means it can be unit tested on any machine -
including one with no microphone, no speakers, and neither library
installed.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

try:
    import requests
except ImportError:  # pragma: no cover - requests should normally be present
    requests = None


# --------------------------------------------------------------------------- #
# Intent representation
# --------------------------------------------------------------------------- #

@dataclass
class Intent:
    name: str
    slots: dict = field(default_factory=dict)
    raw_text: str = ""


# --------------------------------------------------------------------------- #
# Configuration (custom commands, API keys, email settings)
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG_PATH = Path(__file__).with_name("assistant_config.json")


class ConfigError(Exception):
    """Raised when the config file is missing, malformed, or unreadable."""


class AssistantConfig:
    """
    Loads assistant_config.json, which holds:
      - custom_commands: user-defined trigger phrases -> response text
      - weather_api_key / weather_units
      - email settings (smtp host/port, from address) -- passwords are
        read from environment variables, never stored in the file
    See README.md "Privacy & Data Handling" for what is stored where.
    """

    def __init__(self, path: Path = DEFAULT_CONFIG_PATH):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            # Not having a config is fine - just means no custom commands yet.
            return {"custom_commands": {}, "weather": {}, "email": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise ConfigError(f"Could not read config at {self.path}: {exc}") from exc

    def reload(self):
        self.data = self._load()

    @property
    def custom_commands(self) -> dict:
        return self.data.get("custom_commands", {})

    def add_custom_command(self, trigger: str, response: str) -> None:
        """Add a new voice-defined command and persist it to disk."""
        trigger = trigger.strip().lower()
        self.data.setdefault("custom_commands", {})[trigger] = response
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except OSError as exc:
            raise ConfigError(f"Could not save config to {self.path}: {exc}") from exc

    @property
    def weather_api_key(self) -> Optional[str]:
        # Prefer environment variable over the config file for secrets.
        return os.environ.get("OPENWEATHERMAP_API_KEY") or self.data.get("weather", {}).get("api_key")

    @property
    def weather_units(self) -> str:
        return self.data.get("weather", {}).get("units", "metric")

    @property
    def email_settings(self) -> dict:
        return self.data.get("email", {})


# --------------------------------------------------------------------------- #
# Local knowledge base for general-knowledge QA (offline fallback)
# --------------------------------------------------------------------------- #

DEFAULT_KB = {
    "who is the president of the united states": "I don't track current officeholders locally, please ask me to search the web for that.",
    "what is the capital of france": "The capital of France is Paris.",
    "what is the capital of japan": "The capital of Japan is Tokyo.",
    "what is the speed of light": "The speed of light is about 299,792 kilometers per second.",
    "how many continents are there": "There are seven continents.",
    "what is the largest planet": "Jupiter is the largest planet in our solar system.",
    "who wrote romeo and juliet": "Romeo and Juliet was written by William Shakespeare.",
}


class KnowledgeBase:
    """
    Simple offline QA store. Looks up a normalized question in a local
    dictionary. If not found, the caller can fall back to a web search
    or a Wikipedia summary lookup (see WikipediaClient).
    """

    def __init__(self, entries: Optional[dict] = None):
        self.entries = dict(DEFAULT_KB)
        if entries:
            self.entries.update(entries)

    @staticmethod
    def _normalize(question: str) -> str:
        question = question.lower().strip()
        question = re.sub(r"[?!.]", "", question)
        question = re.sub(r"\s+", " ", question)
        return question

    def answer(self, question: str) -> Optional[str]:
        return self.entries.get(self._normalize(question))


class WikipediaClient:
    """
    Optional online fallback for general knowledge questions not found
    in the local KnowledgeBase. Uses Wikipedia's public REST summary
    endpoint. Requires network access; fails gracefully if unavailable.
    """

    SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

    def __init__(self, session=None, timeout: float = 5.0):
        self.session = session or (requests.Session() if requests else None)
        self.timeout = timeout

    def summarize(self, topic: str) -> str:
        if self.session is None:
            raise RuntimeError("The 'requests' library is required for Wikipedia lookups.")
        title = topic.strip().replace(" ", "_")
        response = self.session.get(self.SUMMARY_URL.format(title=title), timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        extract = payload.get("extract")
        if not extract:
            raise ValueError(f"No summary found for '{topic}'.")
        return extract


# --------------------------------------------------------------------------- #
# Weather client (OpenWeatherMap)
# --------------------------------------------------------------------------- #

class WeatherError(Exception):
    """Raised when the weather API call fails or returns no usable data."""


class WeatherClient:
    """
    Thin wrapper around the OpenWeatherMap "current weather" endpoint.
    Get a free API key at https://openweathermap.org/api
    """

    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(self, api_key: Optional[str], units: str = "metric", session=None, timeout: float = 5.0):
        self.api_key = api_key
        self.units = units
        self.session = session or (requests.Session() if requests else None)
        self.timeout = timeout

    def get_weather_sentence(self, city: str) -> str:
        if not self.api_key:
            raise WeatherError(
                "No OpenWeatherMap API key configured. Set the OPENWEATHERMAP_API_KEY "
                "environment variable or add it to assistant_config.json."
            )
        if self.session is None:
            raise WeatherError("The 'requests' library is required for weather lookups.")

        params = {"q": city, "appid": self.api_key, "units": self.units}
        try:
            response = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
        except Exception as exc:  # network failure, DNS error, timeout, etc.
            raise WeatherError(f"Could not reach the weather service: {exc}") from exc

        if response.status_code == 401:
            raise WeatherError("The weather API key was rejected. Please check your API key.")
        if response.status_code == 404:
            raise WeatherError(f"I couldn't find weather data for '{city}'.")
        if response.status_code != 200:
            raise WeatherError(f"Weather service returned an error (status {response.status_code}).")

        return self._format(response.json())

    def _format(self, payload: dict) -> str:
        try:
            description = payload["weather"][0]["description"]
            temp = payload["main"]["temp"]
            feels_like = payload["main"]["feels_like"]
            city_name = payload.get("name", "that location")
        except (KeyError, IndexError) as exc:
            raise WeatherError(f"Unexpected weather data format: {exc}") from exc

        unit_symbol = "°C" if self.units == "metric" else "°F" if self.units == "imperial" else "K"
        return (
            f"The weather in {city_name} is {description}, with a temperature of "
            f"{temp:.0f}{unit_symbol}, feeling like {feels_like:.0f}{unit_symbol}."
        )


# --------------------------------------------------------------------------- #
# Email client
# --------------------------------------------------------------------------- #

class EmailError(Exception):
    """Raised when building or sending an email fails."""


def build_email_message(from_addr: str, to_addr: str, subject: str, body: str):
    """
    Pure function: builds an email.message.EmailMessage object.
    Kept separate from the actual SMTP send so it can be unit tested
    without a network connection or real credentials.
    """
    from email.message import EmailMessage

    if not to_addr or "@" not in to_addr:
        raise EmailError(f"'{to_addr}' does not look like a valid email address.")

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject or "(no subject)"
    msg.set_content(body or "")
    return msg


class EmailClient:
    """
    Sends email via SMTP (e.g. a Gmail "app password" test account).
    The SMTP password is read from an environment variable, never
    stored in the config file or in source control.
    """

    def __init__(self, smtp_host: str, smtp_port: int, from_addr: str, password_env_var: str = "ASSISTANT_EMAIL_PASSWORD"):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_addr = from_addr
        self.password_env_var = password_env_var

    def send(self, to_addr: str, subject: str, body: str, smtp_client_factory: Optional[Callable] = None) -> None:
        import smtplib

        password = os.environ.get(self.password_env_var)
        if not password:
            raise EmailError(
                f"No email password found in the {self.password_env_var} environment variable."
            )

        message = build_email_message(self.from_addr, to_addr, subject, body)

        factory = smtp_client_factory or (lambda: smtplib.SMTP_SSL(self.smtp_host, self.smtp_port))
        try:
            with factory() as server:
                server.login(self.from_addr, password)
                server.send_message(message)
        except smtplib.SMTPException as exc:
            raise EmailError(f"Failed to send email: {exc}") from exc
        except OSError as exc:
            raise EmailError(f"Could not connect to SMTP server: {exc}") from exc


# --------------------------------------------------------------------------- #
# Reminders
# --------------------------------------------------------------------------- #

UNIT_TO_SECONDS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}


def duration_to_seconds(amount: float, unit: str) -> float:
    unit = unit.lower().strip()
    if unit not in UNIT_TO_SECONDS:
        raise ValueError(f"Unrecognized time unit '{unit}'.")
    return amount * UNIT_TO_SECONDS[unit]


class ReminderManager:
    """
    Schedules non-blocking reminders using threading.Timer so the
    assistant can keep listening for other commands while a reminder
    is pending. The alert_callback is called (in a background thread)
    once the duration elapses -- typically wired to Speaker.speak().
    """

    def __init__(self, alert_callback: Callable[[str], None]):
        self.alert_callback = alert_callback
        self._timers = []
        self._lock = threading.Lock()

    def schedule(self, task_description: str, amount: float, unit: str) -> float:
        seconds = duration_to_seconds(amount, unit)

        def _fire():
            self.alert_callback(f"Reminder: {task_description}" if task_description else "Reminder! Time's up.")
            with self._lock:
                if timer in self._timers:
                    self._timers.remove(timer)

        timer = threading.Timer(seconds, _fire)
        timer.daemon = True
        with self._lock:
            self._timers.append(timer)
        timer.start()
        return seconds

    def cancel_all(self):
        with self._lock:
            for timer in self._timers:
                timer.cancel()
            self._timers.clear()

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._timers)


# --------------------------------------------------------------------------- #
# Intent parsing (rule-based NLU)
# --------------------------------------------------------------------------- #

class IntentParser:
    """
    Rule-based natural-language-understanding layer.

    Rather than matching a spoken sentence against one fixed keyword,
    this parses free-form input using ordered regex patterns that
    extract *slots* (e.g. the city in "what's the weather like in
    Tokyo", or the duration in "remind me to stretch in 10 minutes").
    Patterns are tried from most specific to least specific so that,
    e.g., "search for the weather in Paris" still resolves to a web
    search rather than the weather intent.

    Swappable design: replace `parse()` with a call into `nltk` or a
    `transformers` zero-shot classifier if those are installed; the
    rest of the assistant only depends on the returned Intent object.
    """

    def __init__(self, custom_commands: Optional[dict] = None):
        self.custom_commands = custom_commands or {}

    def parse(self, text: str) -> Intent:
        raw = text
        text = text.lower().strip()
        text = re.sub(r"[?!.]+$", "", text)

        # 1. Custom, user-defined commands take priority (exact trigger match).
        if text in self.custom_commands:
            return Intent("custom", {"trigger": text}, raw)

        # 2. Exit / stop
        if re.search(r"\b(exit|quit|goodbye|stop listening|shut down)\b", text):
            return Intent("exit", {}, raw)

        # 3. Reminder: "remind me (to <task>)? in <N> <unit>"
        m = re.search(
            r"remind me(?: to (?P<task>.+?))? in (?P<amount>\d+(?:\.\d+)?) (?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)",
            text,
        )
        if m:
            return Intent("reminder", {
                "task": (m.group("task") or "").strip(),
                "amount": float(m.group("amount")),
                "unit": m.group("unit"),
            }, raw)

        # 4. Send email: "send an email to <recipient> saying/about <body>" (subject optional)
        m = re.search(
            r"send (?:an? )?email to (?P<recipient>[\w.+-]+@[\w-]+\.[\w.-]+)"
            r"(?: (?:saying|about|that says)\s+(?P<body>.+))?",
            text,
        )
        if m:
            return Intent("send_email", {
                "recipient": m.group("recipient"),
                "body": (m.group("body") or "").strip(),
            }, raw)

        # 5. Weather: "what's the weather (like)? in/for <city>" or "weather in <city>"
        m = re.search(r"weather(?: like)?\s*(?:in|for)\s+(?P<city>[a-zA-Z\s]+)$", text)
        if m:
            return Intent("weather", {"city": m.group("city").strip()}, raw)
        if "weather" in text:
            # e.g. just "what's the weather" with no city named
            return Intent("weather", {"city": ""}, raw)

        # 6. Add a custom command via voice:
        #    "add a command <trigger> that says <response>"
        m = re.search(r"add a command (?P<trigger>.+?) that says (?P<response>.+)", text)
        if m:
            return Intent("add_command", {
                "trigger": m.group("trigger").strip(),
                "response": m.group("response").strip(),
            }, raw)

        # 7. Web search: "search for X", "look up X", "google X"
        m = re.search(r"(?:search(?: the web)? for|look up|google)\s+(?P<query>.+)", text)
        if m:
            return Intent("search", {"query": m.group("query").strip()}, raw)

        # 8. Time / date
        if re.search(r"\b(what.*time|current time|time is it)\b", text):
            return Intent("time", {}, raw)
        if re.search(r"\b(what.*date|today.*date|what day is it)\b", text):
            return Intent("date", {}, raw)

        # 9. Greeting
        if re.search(r"\b(hello|hi there|hey there|good morning|good afternoon|good evening)\b", text):
            return Intent("greeting", {}, raw)

        # 10. General-knowledge question (fallback QA):
        #     anything phrased as a question word
        if re.match(r"^(who|what|when|where|why|how)\b", text):
            return Intent("question", {"question": text}, raw)

        # 11. Unknown
        return Intent("unknown", {}, raw)


# --------------------------------------------------------------------------- #
# Response generation for the core, non-hardware intents
# (time/date/greeting/search-url building) -- kept here so they're
# testable without importing webbrowser's platform-specific behavior.
# --------------------------------------------------------------------------- #

def greeting_response() -> str:
    return "Hello! How can I help you today?"


def time_response(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    return f"The current time is {now.strftime('%I:%M %p')}."


def date_response(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    return f"Today's date is {now.strftime('%A, %B %d, %Y')}."


def build_search_url(query: str) -> str:
    from urllib.parse import quote_plus
    return f"https://www.google.com/search?q={quote_plus(query)}"