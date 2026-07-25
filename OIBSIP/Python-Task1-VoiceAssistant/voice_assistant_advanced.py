"""
voice_assistant_advanced.py
============================
Advanced-tier voice assistant. Builds on assistant_core.py's rule-based
NLU, and adds:
  - Free-form intent parsing (not just fixed keywords) -- see assistant_core.IntentParser
  - Sending email via voice command (smtplib)
  - Timed reminders with an audible (spoken) alert
  - Live weather via OpenWeatherMap
  - General-knowledge QA (local knowledge base, with optional Wikipedia fallback)
  - Voice- or config-defined custom commands
  - All beginner-tier features (greeting, time/date, web search, retry-on-error, TTS)

See README.md for setup, required API keys, and a full data-privacy note.

Run:
    python3 voice_assistant_advanced.py
"""

import sys
import webbrowser

from assistant_core import (
    AssistantConfig,
    ConfigError,
    IntentParser,
    KnowledgeBase,
    WikipediaClient,
    WeatherClient,
    WeatherError,
    EmailClient,
    EmailError,
    ReminderManager,
    greeting_response,
    time_response,
    date_response,
    build_search_url,
)

MAX_RETRIES = 3


class Speaker:
    """Text-to-speech output using pyttsx3."""

    def __init__(self):
        import pyttsx3
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", 175)

    def speak(self, text: str):
        print(f"Assistant: {text}")
        self.engine.say(text)
        self.engine.runAndWait()


class Listener:
    """Microphone speech-to-text using speech_recognition (Google Web Speech API)."""

    def __init__(self):
        import speech_recognition as sr
        self.sr = sr
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

    def listen_once(self) -> str:
        with self.microphone as source:
            print("Listening...")
            audio = self.recognizer.listen(source, timeout=6, phrase_time_limit=8)
        return self.recognizer.recognize_google(audio)


class VoiceAssistant:
    """
    Ties together the parser, config, and all the feature clients.
    handle_intent() contains the actual command-dispatch logic and is
    kept independent of Speaker/Listener so it can be unit tested with
    a fake speaker (see test_assistant_core.py).
    """

    def __init__(self, speaker: Speaker, config: AssistantConfig):
        self.speaker = speaker
        self.config = config
        self.parser = IntentParser(custom_commands=config.custom_commands)
        self.knowledge_base = KnowledgeBase()
        self.wikipedia = WikipediaClient()
        self.reminders = ReminderManager(alert_callback=self.speaker.speak)

        email_cfg = config.email_settings
        self.email_client = None
        if email_cfg.get("smtp_host") and email_cfg.get("from_address"):
            self.email_client = EmailClient(
                smtp_host=email_cfg["smtp_host"],
                smtp_port=email_cfg.get("smtp_port", 465),
                from_addr=email_cfg["from_address"],
                password_env_var=email_cfg.get("password_env_var", "ASSISTANT_EMAIL_PASSWORD"),
            )

        self.weather_client = WeatherClient(
            api_key=config.weather_api_key,
            units=config.weather_units,
        )

    def refresh_custom_commands(self):
        self.parser.custom_commands = self.config.custom_commands

    def handle_intent(self, intent) -> bool:
        """Returns False if the assistant should stop running."""
        name = intent.name
        slots = intent.slots

        if name == "greeting":
            self.speaker.speak(greeting_response())

        elif name == "time":
            self.speaker.speak(time_response())

        elif name == "date":
            self.speaker.speak(date_response())

        elif name == "search":
            query = slots["query"]
            self.speaker.speak(f"Searching the web for {query}.")
            webbrowser.open(build_search_url(query))

        elif name == "weather":
            city = slots.get("city", "")
            if not city:
                self.speaker.speak("Which city would you like the weather for?")
                return True
            try:
                sentence = self.weather_client.get_weather_sentence(city.title())
                self.speaker.speak(sentence)
            except WeatherError as exc:
                self.speaker.speak(f"Sorry, I couldn't get the weather. {exc}")

        elif name == "send_email":
            if self.email_client is None:
                self.speaker.speak(
                    "Email isn't configured yet. Please add smtp_host and from_address "
                    "to assistant_config.json."
                )
                return True
            recipient = slots["recipient"]
            body = slots.get("body") or "(No message content was provided.)"
            subject = "Voice Assistant Message"
            try:
                self.email_client.send(recipient, subject, body)
                self.speaker.speak(f"Email sent to {recipient}.")
            except EmailError as exc:
                self.speaker.speak(f"Sorry, I couldn't send that email. {exc}")

        elif name == "reminder":
            task = slots.get("task", "")
            amount = slots["amount"]
            unit = slots["unit"]
            try:
                seconds = self.reminders.schedule(task, amount, unit)
                label = f"in {amount:g} {unit}" if amount != 1 else f"in {amount:g} {unit.rstrip('s')}"
                self.speaker.speak(f"Okay, I'll remind you {label}.")
            except ValueError as exc:
                self.speaker.speak(f"Sorry, I couldn't schedule that reminder. {exc}")

        elif name == "add_command":
            trigger = slots["trigger"]
            response = slots["response"]
            try:
                self.config.add_custom_command(trigger, response)
                self.refresh_custom_commands()
                self.speaker.speak(f"Got it. I'll now respond to '{trigger}'.")
            except ConfigError as exc:
                self.speaker.speak(f"Sorry, I couldn't save that command. {exc}")

        elif name == "custom":
            trigger = slots["trigger"]
            self.speaker.speak(self.config.custom_commands.get(trigger, "Okay."))

        elif name == "question":
            question = slots["question"]
            answer = self.knowledge_base.answer(question)
            if answer is None:
                try:
                    # Fall back to a live Wikipedia summary if it's not in
                    # the local knowledge base.
                    topic = question
                    for lead in ("what is ", "who is ", "who was ", "what are "):
                        if topic.startswith(lead):
                            topic = topic[len(lead):]
                            break
                    answer = self.wikipedia.summarize(topic)
                except Exception:
                    answer = (
                        "I don't have an answer for that in my local knowledge base, "
                        "and I couldn't reach an online source either."
                    )
            self.speaker.speak(answer)

        elif name == "exit":
            self.speaker.speak("Goodbye!")
            return False

        else:
            self.speaker.speak(
                "I didn't quite understand that. You can ask me for the time, date, "
                "weather, to search something, send an email, set a reminder, or ask "
                "a general knowledge question."
            )

        return True


def main():
    try:
        config = AssistantConfig()
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        sys.exit(1)

    try:
        speaker = Speaker()
    except Exception as exc:
        print(f"Could not initialize text-to-speech (pyttsx3): {exc}")
        sys.exit(1)

    try:
        listener = Listener()
    except Exception as exc:
        print(f"Could not initialize the microphone: {exc}")
        sys.exit(1)

    assistant = VoiceAssistant(speaker, config)
    speaker.speak(
        "Hello! I'm your advanced voice assistant. Ask me for the time, date, or weather, "
        "have me search the web, send an email, set a reminder, or ask a general "
        "knowledge question. Say 'exit' to quit."
    )

    running = True
    while running:
        retries = 0
        text = None
        while retries < MAX_RETRIES:
            try:
                text = listener.listen_once()
                print(f"You said: {text}")
                break
            except listener.sr.UnknownValueError:
                retries += 1
                speaker.speak("Sorry, I didn't catch that. Could you please repeat?")
            except listener.sr.RequestError as exc:
                speaker.speak(
                    "I'm having trouble reaching the speech recognition service. "
                    "Please check your internet connection."
                )
                print(f"RequestError detail: {exc}")
                break
            except listener.sr.WaitTimeoutError:
                retries += 1
                speaker.speak("I didn't hear anything. Please try again.")

        if text is None:
            if retries >= MAX_RETRIES:
                speaker.speak("I'm having trouble understanding. Let's try again in a moment.")
            continue

        intent = assistant.parser.parse(text)
        running = assistant.handle_intent(intent)


if __name__ == "__main__":
    main()