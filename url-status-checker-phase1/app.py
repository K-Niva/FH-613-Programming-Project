"""app.py
This file runs the small website (web server) that lets you upload an Excel file,
process it, and then download a new Excel file with results.

Non‑technical summary:
- Visit http://localhost:8080 in your web browser.
- Use the form to upload your Excel file (must be .xlsx).
- The app checks the URLs (only those on rmit.edu.au) one by one.
- Then it auto downloads a Excel file.
"""

import os
from pathlib import Path
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from status_checker import process_excel  # Reuse the same core logic as the CLI

# Folders where we store uploads and outputs on disk (these are created if missing).
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"xlsx"}  # Only allow Excel .xlsx files.

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret")  # Secret key used by Flask to protect forms/messages


def allowed_file(filename: str) -> bool:
    """Return True if the user uploaded an Excel .xlsx file."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/", methods=["GET"])  # Enable web gui when accessed.
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])  # The form on the homepage sends the file here.
def upload():
    # Basic checks: did the user actually attach a file?
    if "file" not in request.files:
        flash("No file part in request.")
        return redirect(url_for("index"))
    file = request.files["file"]
    if file.filename == "":
        flash("No file selected.")
        return redirect(url_for("index"))
    if not allowed_file(file.filename):
        flash("Please upload an .xlsx file.")
        return redirect(url_for("index"))

    # Save the uploaded file to the 'uploads' folder (safe name prevents odd characters).
    filename = secure_filename(file.filename)
    input_path = UPLOAD_DIR / filename
    file.save(input_path)

    # Decide the output filename and location.
    output_name = input_path.stem + "_checked.xlsx" 
    output_path = OUTPUT_DIR / output_name

    try:
        # Run the core checker logic (this takes care of reading, checking, and writing the Excel).
        result = process_excel(str(input_path), str(output_path))
        # If everything is okay, trigger the download.
        return redirect(url_for("download", fname=output_name, summary=os.path.basename(output_name)))
    except Exception as e:
        # If anything goes wrong (e.g., bad Excel file), show error and return to the gui.
        flash(f"Error: {e}")
        return redirect(url_for("index"))


@app.route("/download/<path:fname>")  # When the user clicks the download link, send the file.
def download(fname):
    path = OUTPUT_DIR / fname
    if not path.exists():
        flash("File not found.")
        return redirect(url_for("index"))
    # send_file tells the browser to download this file.
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    # Run the web server. '0.0.0.0' makes it visible to Docker/other machines on your network if needed.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=False)
