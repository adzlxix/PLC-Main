from datetime import datetime


class Color:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"


def menu_title(title: str) -> None:
    print(
        "\n"
        + Color.CYAN
        + Color.BOLD
        + f"=== {title} ==="
        + Color.RESET
    )


def parse_date_input(prompt: str) -> str:
    """
    Ask user for a date in MM-DD-YYYY format.
    Allows ENTER to mean 'today'.
    """
    while True:
        value = input(f"{prompt} ").strip()
        if value == "":
            return datetime.now().strftime("%m-%d-%Y")
        try:
            dt = datetime.strptime(value, "%m-%d-%Y")
            return dt.strftime("%m-%d-%Y")
        except ValueError:
            print(Color.RED + "Invalid date. Use MM-DD-YYYY." + Color.RESET)


def confirm(prompt: str) -> bool:
    """
    Ask user for Yes/No (Y/N).
    """
    while True:
        ans = input(f"{prompt} (Y/N): ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please answer Y or N.")


def numeric_input(prompt: str, allow_float: bool = True) -> float:
    """
    Ask the user for a numeric value.
    - If allow_float=True, accepts decimal numbers.
    - If allow_float=False, forces whole integers.
    """
    while True:
        value = input(f"{prompt} ").strip()
        try:
            if allow_float:
                return float(value)
            else:
                return int(value)
        except ValueError:
            print(Color.RED + "Please enter a valid number." + Color.RESET)
