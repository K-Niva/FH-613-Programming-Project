"""check_urls.py
This is a small command‑line wrapper. It lets you run the URL checker without the web page.

Non‑technical summary:
- You run:  python check_urls.py URL.xlsx
- It reads your Excel file, checks the URLs, and writes a new file named URL_checked.xlsx
- If you provide a second argument, that becomes the output file name.
"""

import sys
from pathlib import Path
from status_checker import process_excel  # Import the core function from status_checker.py

def main():
    # Expect at least one argument: the path to the input Excel file.
    if len(sys.argv) < 2:
        print("Usage: python check_urls.py <input.xlsx> [output.xlsx]")
        sys.exit(1)

    input_xlsx = Path(sys.argv[1]).resolve()

    # If the user supplies an output file name, use it; otherwise create one automatically.
    if len(sys.argv) >= 3:
        output_xlsx = Path(sys.argv[2]).resolve()
    else:
        output_xlsx = input_xlsx.with_name(input_xlsx.stem + "_checked.xlsx")

    # Hand the work to the shared function and print a small summary.
    result = process_excel(str(input_xlsx), str(output_xlsx))
    print("Done.")
    print(result)

#if __name__ == "__main__":
#    main()
