"""
BMI Calculator - Advanced Tier - GUI Application
tkinter GUI + SQLite persistence + matplotlib trend chart.

Run with:  python3 bmi_gui.py
Requires:  tkinter (usually ships with Python; on Debian/Ubuntu install
           with `sudo apt install python3-tk` if missing) and matplotlib
           (`pip install matplotlib`).
"""

import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from bmi_core import (
    calculate_bmi,
    classify_bmi,
    validate_measurement,
    BMIDatabase,
    BMIDatabaseError,
    CATEGORY_COLORS,
)


class BMIApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BMI Calculator")
        self.geometry("420x430")
        self.resizable(False, False)
        self.configure(bg="#F5F5F5")

        # Try to open the database up front; surface any failure clearly.
        try:
            self.db = BMIDatabase()
        except BMIDatabaseError as exc:
            messagebox.showerror("Database Error", str(exc))
            self.db = None

        self._build_widgets()

    # ------------------------------------------------------------------ UI
    def _build_widgets(self):
        pad = {"padx": 10, "pady": 6}

        title = tk.Label(self, text="BMI Calculator", font=("Segoe UI", 18, "bold"),
                          bg="#F5F5F5")
        title.grid(row=0, column=0, columnspan=2, pady=(15, 10))

        # --- Name field
        tk.Label(self, text="Name:", bg="#F5F5F5", font=("Segoe UI", 11)).grid(
            row=1, column=0, sticky="e", **pad)
        self.name_var = tk.StringVar()
        tk.Entry(self, textvariable=self.name_var, width=20).grid(
            row=1, column=1, sticky="w", **pad)

        # --- Weight field
        tk.Label(self, text="Weight (kg):", bg="#F5F5F5", font=("Segoe UI", 11)).grid(
            row=2, column=0, sticky="e", **pad)
        self.weight_var = tk.StringVar()
        tk.Entry(self, textvariable=self.weight_var, width=20).grid(
            row=2, column=1, sticky="w", **pad)

        # --- Height field
        tk.Label(self, text="Height (m):", bg="#F5F5F5", font=("Segoe UI", 11)).grid(
            row=3, column=0, sticky="e", **pad)
        self.height_var = tk.StringVar()
        tk.Entry(self, textvariable=self.height_var, width=20).grid(
            row=3, column=1, sticky="w", **pad)

        # --- Calculate button
        calc_btn = tk.Button(self, text="Calculate", command=self._on_calculate,
                              bg="#1976D2", fg="white", font=("Segoe UI", 11, "bold"),
                              activebackground="#1565C0", relief="flat", padx=10, pady=4)
        calc_btn.grid(row=4, column=0, columnspan=2, pady=(10, 4))

        # --- Result display (color-coded)
        self.result_var = tk.StringVar(value="Enter your details and press Calculate")
        self.result_label = tk.Label(self, textvariable=self.result_var,
                                      font=("Segoe UI", 13, "bold"), bg="#F5F5F5",
                                      fg="#333333", wraplength=380, justify="center")
        self.result_label.grid(row=5, column=0, columnspan=2, pady=(4, 10))

        # --- Action buttons: Save + View Graph
        btn_frame = tk.Frame(self, bg="#F5F5F5")
        btn_frame.grid(row=6, column=0, columnspan=2, pady=(0, 6))

        self.save_btn = tk.Button(btn_frame, text="Save Record", command=self._on_save,
                                   bg="#388E3C", fg="white", relief="flat", padx=8, pady=4,
                                   state="disabled")
        self.save_btn.grid(row=0, column=0, padx=6)

        graph_btn = tk.Button(btn_frame, text="View Graph", command=self._on_view_graph,
                               bg="#616161", fg="white", relief="flat", padx=8, pady=4)
        graph_btn.grid(row=0, column=1, padx=6)

        # --- Saved-user picker (for viewing history/graphs of past users)
        tk.Label(self, text="Saved users:", bg="#F5F5F5", font=("Segoe UI", 10)).grid(
            row=7, column=0, sticky="e", padx=10, pady=(10, 2))
        self.user_picker = ttk.Combobox(self, state="readonly", width=17)
        self.user_picker.grid(row=7, column=1, sticky="w", padx=10, pady=(10, 2))
        self._refresh_user_list()

        refresh_btn = tk.Button(self, text="Refresh user list", command=self._refresh_user_list,
                                 relief="flat", bg="#E0E0E0")
        refresh_btn.grid(row=8, column=0, columnspan=2, pady=(2, 10))

        # Keep the most recent calculation around so "Save Record" can use it
        self._last_calc = None  # (weight, height, bmi, category)

    # --------------------------------------------------------------- logic
    def _on_calculate(self):
        try:
            weight = validate_measurement(self.weight_var.get(), "Weight")
            height = validate_measurement(self.height_var.get(), "Height")
        except ValueError as exc:
            messagebox.showerror("Invalid Input", str(exc))
            self.save_btn.config(state="disabled")
            return

        bmi = calculate_bmi(weight, height)
        category = classify_bmi(bmi)
        color = CATEGORY_COLORS.get(category, "#333333")

        self.result_var.set(f"BMI: {bmi:.2f}  —  {category}")
        self.result_label.config(fg=color)

        self._last_calc = (weight, height, bmi, category)
        self.save_btn.config(state="normal" if self.name_var.get().strip() else "disabled")

        if not self.name_var.get().strip():
            messagebox.showinfo("Name needed to save",
                                 "Enter a name above if you'd like to save this result.")

    def _on_save(self):
        if self.db is None:
            messagebox.showerror("Database Error", "No database connection is available.")
            return
        if self._last_calc is None:
            messagebox.showwarning("Nothing to save", "Calculate a BMI first.")
            return

        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Name required", "Please enter a name before saving.")
            return

        weight, height, bmi, category = self._last_calc
        try:
            self.db.add_record(name, weight, height, bmi, category)
        except BMIDatabaseError as exc:
            messagebox.showerror("Database Error", f"Could not save record:\n{exc}")
            return

        messagebox.showinfo("Saved", f"Record saved for {name}.")
        self._refresh_user_list()

    def _refresh_user_list(self):
        if self.db is None:
            self.user_picker["values"] = []
            return
        try:
            users = self.db.get_users()
        except BMIDatabaseError as exc:
            messagebox.showerror("Database Error", f"Could not read users:\n{exc}")
            users = []
        self.user_picker["values"] = users
        if users:
            self.user_picker.current(0)

    def _on_view_graph(self):
        if self.db is None:
            messagebox.showerror("Database Error", "No database connection is available.")
            return

        user = self.user_picker.get().strip()
        if not user:
            messagebox.showwarning("No user selected",
                                    "Save at least one record and select a user first.")
            return

        try:
            records = self.db.get_records_for_user(user)
        except BMIDatabaseError as exc:
            messagebox.showerror("Database Error", f"Could not load history:\n{exc}")
            return

        if not records:
            messagebox.showinfo("No data", f"No saved BMI records found for {user}.")
            return

        GraphWindow(self, user, records)


class GraphWindow(tk.Toplevel):
    """Pop-up window showing a matplotlib line chart of a user's BMI trend."""

    def __init__(self, parent, user_name, records):
        super().__init__(parent)
        self.title(f"BMI Trend — {user_name}")
        self.geometry("640x480")

        dates = [r[0][:16].replace("T", " ") for r in records]
        bmis = [r[1] for r in records]
        categories = [r[2] for r in records]

        fig = Figure(figsize=(6.2, 4.4), dpi=100)
        ax = fig.add_subplot(111)

        ax.plot(range(len(bmis)), bmis, marker="o", color="#1976D2", linewidth=2)
        for i, (bmi_val, cat) in enumerate(zip(bmis, categories)):
            ax.scatter(i, bmi_val, color=CATEGORY_COLORS.get(cat, "#333333"), zorder=3)

        ax.axhspan(18.5, 25, color="#2E7D32", alpha=0.06)
        ax.axhspan(25, 30, color="#F9A825", alpha=0.06)
        ax.set_title(f"BMI Trend for {user_name}")
        ax.set_xlabel("Record #")
        ax.set_ylabel("BMI")
        ax.set_xticks(range(len(dates)))
        ax.set_xticklabels(dates, rotation=45, ha="right", fontsize=7)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)


if __name__ == "__main__":
    app = BMIApp()
    app.mainloop()