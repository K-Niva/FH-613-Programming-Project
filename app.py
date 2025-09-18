import os
import time
import json
import datetime as dt
import logging # <-- ADDED IMPORT
from flask import Flask, render_template, request, send_from_directory, Response
from werkzeug.utils import secure_filename
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
import pandas as pd


UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}

DEFAULT_ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "rmit.edu.au")
DEFAULT_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.10"))
USER_AGENT = os.getenv("USER_AGENT", "URLStatusChecker/1.0 (FlaskWebApp)")
MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.secret_key = 'supersecretkey'

# --- ADDED LOGGING CONFIGURATION ---
# This ensures logs are visible when running with Gunicorn
if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
# ------------------------------------

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)



def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _is_allowed_host(url: str, allowed_root: str) -> bool:
    """Return True if the URL's website belongs to the allowed domain."""
    try:
        host = urlparse(url.strip()).hostname or ""
    except Exception:
        return False
    allowed_root = allowed_root.lower().strip()
    host = host.lower()
    return host == allowed_root or host.endswith("." + allowed_root)

def _normalize_url(url: str) -> str:
    """Make the URL tidy and ensure it has a scheme (http/https)."""
    url = (url or "").strip()
    if not url:
        return url
    parsed = urlparse(url)
    if not parsed.scheme:
        return "https://" + url
    return url

def _head_then_get_status(client: httpx.Client, url: str, timeout: float):
    """Try to check the website in a low‑impact way."""
    start = time.perf_counter()
    redirected = False
    try:
        r = client.head(url, timeout=timeout, follow_redirects=True)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        redirected = (str(r.url) != url) or (len(r.history) > 0)
        return r.status_code, str(r.url), "", elapsed_ms, redirected
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.NetworkError, httpx.ProtocolError):
        try:
            start2 = time.perf_counter()
            r = client.get(url, timeout=timeout, follow_redirects=True)
            elapsed_ms = (time.perf_counter() - start2) * 1000.0
            redirected = (str(r.url) != url) or (len(r.history) > 0)
            return r.status_code, str(r.url), "", elapsed_ms, redirected
        except Exception as e2:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return None, url, f"RequestError: {e2.__class__.__name__}", elapsed_ms, redirected
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return None, url, f"Error: {e.__class__.__name__}", elapsed_ms, redirected

def _detect_url_column(df: pd.DataFrame) -> str:
    """Automatically try to find which column contains URLs."""
    for name in df.columns:
        if str(name).strip().lower() in {"url", "urls", "link"}:
            return name
    for name in df.columns:
        if "url" in str(name).lower():
            return name
    return df.columns[0] if len(df.columns) > 0 else None

def _now_melbourne_iso() -> str:
    """Return current time in Australia/Melbourne as ISO string."""
    return dt.datetime.now(MELBOURNE_TZ).replace(microsecond=0).isoformat()


def process_dataframe_stream(df: pd.DataFrame, original_filename: str):
    """
    Processes a DataFrame of URLs and yields progress updates as Server-Sent Events.
    """
    def generate():
        try:
            app.logger.info("Starting stream generation for file: %s", original_filename)
            url_col = _detect_url_column(df)
            if not url_col:
                app.logger.error("Could not detect a URL column in the uploaded file.")
                raise ValueError("Could not detect a URL column. Please name it 'URL', 'Link', or similar.")

            total_urls = len(df)
            skipped_count = 0 
            yield f'data: {json.dumps({"message": f"Found {total_urls} rows in {original_filename}"})}\n\n'
            yield f'data: {json.dumps({"total": total_urls})}\n\n'

            
            df["checking_time"] = ""
            df["status_code"] = ""
            df["final_url"] = ""
            df["redirected"] = ""
            df["elapsed_ms"] = ""
            df["error"] = ""

            headers = {"User-Agent": USER_AGENT}
            
            app.logger.info("Beginning URL processing loop for %d URLs.", total_urls)
            with httpx.Client(headers=headers) as client:
                for idx, row in df.iterrows():
                    raw_url = str(row[url_col] or "")
                    url = _normalize_url(raw_url)

                    # --- THIS IS THE CRITICAL LOGGING LINE ---
                    app.logger.info(f"Processing URL #{idx + 1}/{total_urls}: {url}")
                    # -----------------------------------------

                    if not url or not _is_allowed_host(url, DEFAULT_ALLOWED_DOMAIN):
                        df.at[idx, "checking_time"] = _now_melbourne_iso()
                        df.at[idx, "error"] = f"Skipped: not a valid {DEFAULT_ALLOWED_DOMAIN} URL"
                        skipped_count += 1
                    else:
                        status_code, final_url, err, elapsed_ms, redirected = _head_then_get_status(client, url, timeout=DEFAULT_TIMEOUT)
                        df.at[idx, "checking_time"] = _now_melbourne_iso()
                        df.at[idx, "status_code"] = status_code if status_code else "N/A"
                        df.at[idx, "final_url"] = final_url
                        df.at[idx, "redirected"] = bool(redirected)
                        df.at[idx, "elapsed_ms"] = round(float(elapsed_ms), 2)
                        df.at[idx, "error"] = err
                        time.sleep(REQUEST_DELAY)
                    
                    yield f'data: {json.dumps({"checked": idx + 1})}\n\n'
            
            app.logger.info("URL processing loop finished. Preparing to save file.")
            base, ext = os.path.splitext(original_filename)
            output_filename = f"{base}_processed{ext}"
            output_filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], output_filename)
            
            if original_filename.endswith('.xlsx'):
                df.to_excel(output_filepath, index=False, engine="openpyxl")
            else:
                df.to_csv(output_filepath, index=False)
            
            app.logger.info("File successfully saved to: %s", output_filepath)
            yield f'data: {json.dumps({"done": True, "filename": output_filename, "skipped": skipped_count})}\n\n'
        
        except Exception as e:
            app.logger.error("An exception occurred during stream processing: %s", e, exc_info=True)
            error_message = f"An error occurred during processing: {e}"
            yield f'data: {json.dumps({"error": error_message})}\n\n'

    return generate()



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return Response("No file part", status=400)
    file = request.files['file']
    if file.filename == '':
        return Response("No selected file", status=400)

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            if filename.endswith('.xlsx'):
                df = pd.read_excel(filepath, engine="openpyxl")
            else:
                df = pd.read_csv(filepath)
            
            if df.empty:
                 return Response("The uploaded file is empty.", status=400)

            return Response(process_dataframe_stream(df, filename), mimetype='text/event-stream')

        except Exception as e:
            return Response(f"Failed to read or process file: {e}", status=500)
            
    else:
        return Response(f"Allowed file types are: {', '.join(ALLOWED_EXTENSIONS)}", status=400)


@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)
#test

if __name__ == '__main__':
    app.run(debug=True)