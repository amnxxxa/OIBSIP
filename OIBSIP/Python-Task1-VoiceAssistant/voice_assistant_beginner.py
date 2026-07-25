"""
voice_assistant_beginner.py
============================
Beginner-tier voice assistant.

Features:
  - Captures voice input from the microphone (speech_recognition)
  - Responds to "hello" with a greeting
  - Tells the current time and date
  - Performs a web search on request (opens the default browser)
  - Retries gracefully if speech isn't understood
  - Speaks every response aloud (pyttsx3)

Setup:
    pip install SpeechRecognition pyttsx3 pyaudio
    (On Linux you may also need: sudo apt install portaudio19-dev)

Run:
    python3 voice_assistant_beginner.py
"""

import sys
import webbrowser

from assistant_core import (
    IntentParser,
    greeting_response,
    time_response,
    date_response,
    build_search_url,
)

MAX_RETRIES = 3  # how many times to ask the user to repeat before giving up


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
        # One-time ambient noise calibration for better accuracy.
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

    def listen_once(self) -> str:
        """
        Records one utterance and returns the recognized text.
        Raises self.sr.UnknownValueError if speech wasn't understood,
        or self.sr.RequestError if the recognition service is unreachable.
        """
        with self.microphone as source:
            print("Listening...")
            audio = self.recognizer.listen(source, timeout=6, phrase_time_limit=8)
        return self.recognizer.recognize_google(audio)


def handle_intent(intent, speaker: Speaker) -> bool:
    """
    Executes a parsed intent. Returns False if the assistant should stop
    running (i.e. an exit intent), True otherwise.
    """
    if intent.name == "greeting":
        speaker.speak(greeting_response())
    elif intent.name == "time":
        speaker.speak(time_response())
    elif intent.name == "date":
        speaker.speak(date_response())
    elif intent.name == "search":
        query = intent.slots["query"]
        speaker.speak(f"Searching the web for {query}.")
        webbrowser.open(build_search_url(query))
    elif intent.name == "exit":
        speaker.speak("Goodbye!")
        return False
    else:
        speaker.speak(
            "I can say hello, tell you the time or date, or search the web for you. "
            "Try one of those!"
        )
    return True


def main():
    try:
        speaker = Speaker()
    except Exception as exc:
        print(f"Could not initialize text-to-speech (pyttsx3): {exc}")
        print("Make sure pyttsx3 is installed and a TTS engine is available on this system.")
        sys.exit(1)

    try:
        listener = Listener()
    except Exception as exc:
        speaker_msg = f"Could not initialize the microphone: {exc}"
        print(speaker_msg)
        print("Make sure SpeechRecognition and PyAudio are installed and a microphone is connected.")
        sys.exit(1)

    parser = IntentParser()
    speaker.speak("Hello! I'm your voice assistant. Say 'hello', ask for the time or date, "
                  "or say 'search for' something. Say 'exit' to quit.")

    running = True
    while running:
        retries = 0
        text = None
        # Graceful error handling: ask the user to repeat if not understood.
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

        intent = parser.parse(text)
        running = handle_intent(intent, speaker)


if __name__ == "__main__":
    main()