"""
test_assistant_core.py
=======================
Unit tests for the hardware-independent parts of the voice assistant:
intent parsing, config/custom-commands, the local knowledge base, the
weather client (network mocked), email message building (network
mocked), and the reminder scheduler.

These run on any machine with plain Python 3 -- no microphone,
speakers, speech_recognition, or pyttsx3 required, since assistant_core.py
only imports those lazily inside Speaker/Listener (which live in the
voice_assistant_*.py scripts, not here).

Run with:
    python3 -m unittest test_assistant_core.py -v
"""

import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from assistant_core import (
    AssistantConfig,
    ConfigError,
    EmailClient,
    EmailError,
    IntentParser,
    KnowledgeBase,
    ReminderManager,
    WeatherClient,
    WeatherError,
    build_email_message,
    build_search_url,
    date_response,
    duration_to_seconds,
    greeting_response,
    time_response,
)


class TestIntentParser(unittest.TestCase):
    def setUp(self):
        self.parser = IntentParser()

    def test_greeting(self):
        for phrase in ["hello", "hey there, how are you", "good morning"]:
            self.assertEqual(self.parser.parse(phrase).name, "greeting")

    def test_time_and_date(self):
        self.assertEqual(self.parser.parse("what time is it").name, "time")
        self.assertEqual(self.parser.parse("what's today's date").name, "date")

    def test_search(self):
        intent = self.parser.parse("search for python tutorials")
        self.assertEqual(intent.name, "search")
        self.assertEqual(intent.slots["query"], "python tutorials")

    def test_reminder_slots(self):
        intent = self.parser.parse("remind me to check the oven in 5 minutes")
        self.assertEqual(intent.name, "reminder")
        self.assertEqual(intent.slots["task"], "check the oven")
        self.assertEqual(intent.slots["amount"], 5.0)
        self.assertEqual(intent.slots["unit"], "minutes")

    def test_reminder_no_task(self):
        intent = self.parser.parse("remind me in 10 seconds")
        self.assertEqual(intent.slots["task"], "")

    def test_email_slots(self):
        intent = self.parser.parse(
            "send an email to bob@example.com saying meeting moved to 3pm"
        )
        self.assertEqual(intent.name, "send_email")
        self.assertEqual(intent.slots["recipient"], "bob@example.com")
        self.assertEqual(intent.slots["body"], "meeting moved to 3pm")

    def test_weather_with_and_without_city(self):
        self.assertEqual(self.parser.parse("weather in Paris").slots["city"], "paris")
        self.assertEqual(self.parser.parse("what's the weather").slots["city"], "")

    def test_question_fallback(self):
        self.assertEqual(self.parser.parse("who wrote romeo and juliet").name, "question")

    def test_add_command(self):
        intent = self.parser.parse("add a command good night that says sleep well")
        self.assertEqual(intent.name, "add_command")
        self.assertEqual(intent.slots["trigger"], "good night")
        self.assertEqual(intent.slots["response"], "sleep well")

    def test_exit(self):
        self.assertEqual(self.parser.parse("exit").name, "exit")

    def test_unknown(self):
        self.assertEqual(self.parser.parse("asdkjfh gibberish nonsense").name, "unknown")

    def test_custom_command_priority(self):
        parser = IntentParser(custom_commands={"good night": "Sleep well!"})
        self.assertEqual(parser.parse("good night").name, "custom")


class TestResponseGenerators(unittest.TestCase):
    def test_greeting_response(self):
        self.assertEqual(greeting_response(), "Hello! How can I help you today?")

    def test_time_response(self):
        now = datetime(2026, 7, 25, 14, 30)
        self.assertEqual(time_response(now), "The current time is 02:30 PM.")

    def test_date_response(self):
        now = datetime(2026, 7, 25, 14, 30)
        self.assertEqual(date_response(now), "Today's date is Saturday, July 25, 2026.")

    def test_search_url(self):
        self.assertIn("google.com/search?q=best+pizza", build_search_url("best pizza"))


class TestKnowledgeBase(unittest.TestCase):
    def test_known_question(self):
        kb = KnowledgeBase()
        self.assertEqual(kb.answer("What is the capital of France?"),
                         "The capital of France is Paris.")

    def test_unknown_question(self):
        kb = KnowledgeBase()
        self.assertIsNone(kb.answer("totally unknown question"))


class TestDurationParsing(unittest.TestCase):
    def test_valid_units(self):
        self.assertEqual(duration_to_seconds(5, "minutes"), 300)
        self.assertEqual(duration_to_seconds(2, "hours"), 7200)
        self.assertEqual(duration_to_seconds(10, "seconds"), 10)

    def test_invalid_unit(self):
        with self.assertRaises(ValueError):
            duration_to_seconds(1, "fortnights")


class TestEmailMessageBuilding(unittest.TestCase):
    def test_valid_message(self):
        msg = build_email_message("me@example.com", "bob@example.com", "Hi", "body text")
        self.assertEqual(msg["To"], "bob@example.com")
        self.assertEqual(msg.get_content().strip(), "body text")

    def test_invalid_recipient(self):
        with self.assertRaises(EmailError):
            build_email_message("me@example.com", "not-an-email", "Hi", "body")

    def test_send_uses_env_password_and_calls_smtp(self):
        os.environ["ASSISTANT_EMAIL_PASSWORD"] = "test-password"
        try:
            client = EmailClient("smtp.example.com", 465, "me@example.com")
            fake_smtp = MagicMock()
            fake_smtp.__enter__ = MagicMock(return_value=fake_smtp)
            fake_smtp.__exit__ = MagicMock(return_value=False)
            factory = MagicMock(return_value=fake_smtp)

            client.send("bob@example.com", "Subject", "Body", smtp_client_factory=factory)

            fake_smtp.login.assert_called_once_with("me@example.com", "test-password")
            fake_smtp.send_message.assert_called_once()
        finally:
            del os.environ["ASSISTANT_EMAIL_PASSWORD"]

    def test_send_without_password_raises(self):
        os.environ.pop("ASSISTANT_EMAIL_PASSWORD", None)
        client = EmailClient("smtp.example.com", 465, "me@example.com")
        with self.assertRaises(EmailError):
            client.send("bob@example.com", "Subject", "Body")


class TestWeatherClient(unittest.TestCase):
    def _mock_session(self, status_code=200, json_payload=None):
        session = MagicMock()
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_payload or {}
        session.get.return_value = response
        return session

    def test_successful_lookup(self):
        session = self._mock_session(200, {
            "weather": [{"description": "clear sky"}],
            "main": {"temp": 25.4, "feels_like": 24.9},
            "name": "Colombo",
        })
        client = WeatherClient(api_key="fake-key", units="metric", session=session)
        sentence = client.get_weather_sentence("Colombo")
        self.assertIn("Colombo", sentence)
        self.assertIn("clear sky", sentence)

    def test_missing_api_key(self):
        client = WeatherClient(api_key=None, session=self._mock_session())
        with self.assertRaises(WeatherError):
            client.get_weather_sentence("Colombo")

    def test_unauthorized(self):
        session = self._mock_session(401)
        client = WeatherClient(api_key="bad-key", session=session)
        with self.assertRaises(WeatherError):
            client.get_weather_sentence("Colombo")

    def test_city_not_found(self):
        session = self._mock_session(404)
        client = WeatherClient(api_key="fake-key", session=session)
        with self.assertRaises(WeatherError):
            client.get_weather_sentence("Nowhereville")


class TestReminderManager(unittest.TestCase):
    def test_reminder_fires_after_duration(self):
        alerts = []
        manager = ReminderManager(alert_callback=alerts.append)
        manager.schedule("test task", 0.2, "seconds")
        self.assertEqual(manager.pending_count, 1)
        time.sleep(0.4)
        self.assertEqual(alerts, ["Reminder: test task"])
        self.assertEqual(manager.pending_count, 0)

    def test_cancel_all(self):
        manager = ReminderManager(alert_callback=lambda m: None)
        manager.schedule("task", 10, "seconds")
        self.assertEqual(manager.pending_count, 1)
        manager.cancel_all()
        self.assertEqual(manager.pending_count, 0)


class TestAssistantConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cfg_path = Path(self.tmpdir) / "assistant_config.json"

    def test_missing_config_defaults(self):
        config = AssistantConfig(self.cfg_path)
        self.assertEqual(config.custom_commands, {})

    def test_add_and_persist_custom_command(self):
        config = AssistantConfig(self.cfg_path)
        config.add_custom_command("good night", "Sleep well!")
        reloaded = AssistantConfig(self.cfg_path)
        self.assertEqual(reloaded.custom_commands["good night"], "Sleep well!")

    def test_malformed_config_raises(self):
        self.cfg_path.write_text("{not valid json")
        with self.assertRaises(ConfigError):
            AssistantConfig(self.cfg_path)

    def test_env_var_takes_priority_for_api_key(self):
        os.environ["OPENWEATHERMAP_API_KEY"] = "env-key-123"
        try:
            config = AssistantConfig(self.cfg_path)
            self.assertEqual(config.weather_api_key, "env-key-123")
        finally:
            del os.environ["OPENWEATHERMAP_API_KEY"]


if __name__ == "__main__":
    unittest.main(verbosity=2)