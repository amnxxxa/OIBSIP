# BMI Calculator

## Beginner Tier — `bmi_cli.py`
Command-line tool. No extra dependencies (standard library only).

Run:
```
python3 bmi_cli.py
```
You'll be prompted for weight (kg) and height (m). Non-numeric or
negative/zero input is rejected with a helpful message and re-prompted.

## Advanced Tier — `bmi_gui.py` + `bmi_core.py`
A tkinter desktop app with:
- Labeled weight/height inputs and a Calculate button
- Color-coded result (blue=underweight, green=normal, orange=overweight, red=obese)
- Named users, saved to a local SQLite database (`bmi_records.db`, created automatically)
- "View Graph" button showing a matplotlib line chart of a selected user's BMI history
- Error handling around every database read/write

### Setup
```
pip install matplotlib
```
`tkinter` ships with most Python installations. If it's missing (common on
some Linux distros), install it via your package manager, e.g.:
```
sudo apt install python3-tk        # Debian/Ubuntu
sudo dnf install python3-tkinter   # Fedora
```

### Run
```
python3 bmi_gui.py
```

### Files
- `bmi_core.py` — pure logic: BMI math, category classification, input
  validation, and the `BMIDatabase` SQLite wrapper. No GUI dependencies,
  so it can be unit tested or reused independently.
- `bmi_gui.py` — the tkinter GUI and the matplotlib trend-chart pop-up.
  Imports `bmi_core.py`.

### Notes
- This sandbox environment doesn't have `tkinter` installed, so the GUI
  itself couldn't be launched here — but `bmi_core.py` (BMI math,
  classification, input validation, and all SQLite operations) has been
  tested directly and works correctly. Run `bmi_gui.py` on your own
  machine, where tkinter is normally available by default.