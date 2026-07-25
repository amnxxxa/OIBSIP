"""
BMI Calculator - Advanced Tier - Core Module
Contains BMI math, category classification, and SQLite-backed persistence.
Kept separate from the GUI code so the logic can be tested / reused
without requiring tkinter or matplotlib to be installed.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name("bmi_records.db")

# Category -> display color used by the GUI for color-coded feedback
CATEGORY_COLORS = {
    "Underweight": "#2196F3",   # blue
    "Normal weight": "#2E7D32",  # green
    "Overweight": "#F9A825",    # amber/orange
    "Obese": "#C62828",         # red
}


def calculate_bmi(weight_kg: float, height_m: float) -> float:
    """Calculate BMI given weight in kilograms and height in meters."""
    if height_m <= 0:
        raise ValueError("Height must be greater than zero.")
    return weight_kg / (height_m ** 2)


def classify_bmi(bmi: float) -> str:
    """Classify a BMI value into a standard health category."""
    if bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal weight"
    elif bmi < 30:
        return "Overweight"
    else:
        return "Obese"


def validate_measurement(raw_value: str, field_name: str) -> float:
    """
    Convert a raw string input into a positive float.
    Raises ValueError with a helpful, user-facing message on failure.
    """
    raw_value = (raw_value or "").strip()
    if not raw_value:
        raise ValueError(f"{field_name} cannot be empty.")
    try:
        value = float(raw_value)
    except ValueError:
        raise ValueError(f"{field_name} must be a number (e.g. 70 or 1.75).")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return value


class BMIDatabaseError(Exception):
    """Raised when a database read/write operation fails."""


class BMIDatabase:
    """
    Thin SQLite wrapper that stores BMI records per named user.
    All public methods translate low-level sqlite3 errors into
    BMIDatabaseError so the GUI layer can show a friendly message.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _connect(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            raise BMIDatabaseError(f"Database error: {exc}") from exc
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _init_schema(self):
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_name TEXT NOT NULL,
                        weight_kg REAL NOT NULL,
                        height_m REAL NOT NULL,
                        bmi REAL NOT NULL,
                        category TEXT NOT NULL,
                        recorded_at TEXT NOT NULL
                    )
                    """
                )
        except BMIDatabaseError:
            # Re-raise so the caller (GUI startup) can decide how to handle it
            raise

    def add_record(self, user_name: str, weight_kg: float, height_m: float,
                   bmi: float, category: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO records (user_name, weight_kg, height_m, bmi, category, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_name, weight_kg, height_m, round(bmi, 2), category,
                 datetime.now().isoformat(timespec="seconds")),
            )

    def get_users(self) -> list:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT DISTINCT user_name FROM records ORDER BY user_name COLLATE NOCASE"
            )
            return [row[0] for row in cursor.fetchall()]

    def get_records_for_user(self, user_name: str) -> list:
        """Returns list of (recorded_at, bmi, category) tuples, oldest first."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT recorded_at, bmi, category FROM records
                WHERE user_name = ?
                ORDER BY recorded_at ASC
                """,
                (user_name,),
            )
            return cursor.fetchall()

    def delete_user_records(self, user_name: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM records WHERE user_name = ?", (user_name,))