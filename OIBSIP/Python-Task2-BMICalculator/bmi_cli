"""
BMI Calculator - Beginner Tier
A simple command-line tool that calculates Body Mass Index (BMI) and
classifies it into standard health categories.

BMI formula: BMI = weight (kg) / height (m)^2
"""


def get_positive_float(prompt: str) -> float:
    """
    Repeatedly prompt the user until a valid, positive numeric value is entered.
    Rejects non-numeric input and negative/zero values with a helpful message.
    """
    while True:
        raw_value = input(prompt).strip()
        try:
            value = float(raw_value)
        except ValueError:
            print(f"  ⚠️  '{raw_value}' is not a valid number. Please enter a number like 70 or 1.75.")
            continue

        if value <= 0:
            print("  ⚠️  Value must be greater than zero. Please try again.")
            continue

        return value


def calculate_bmi(weight_kg: float, height_m: float) -> float:
    """Calculate BMI given weight in kilograms and height in meters."""
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


def main():
    print("=" * 40)
    print("        BMI CALCULATOR")
    print("=" * 40)

    weight = get_positive_float("Enter your weight in kilograms (kg): ")
    height = get_positive_float("Enter your height in meters (m): ")

    bmi = calculate_bmi(weight, height)
    category = classify_bmi(bmi)

    print("-" * 40)
    print(f"Your BMI is: {bmi:.2f}")
    print(f"Category:    {category}")
    print("-" * 40)

    # Friendly category reference table
    print("Reference ranges:")
    print("  Underweight   : < 18.5")
    print("  Normal weight : 18.5 - 24.9")
    print("  Overweight    : 25 - 29.9")
    print("  Obese         : >= 30")


if __name__ == "__main__":
    main()