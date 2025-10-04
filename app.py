import os
import time
import json
import datetime as dt
from flask import Flask, render_template, request, Response
from werkzeug.utils import secure_filename
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import boto3

UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}
USER_AGENT = "Mozilla/5.0"
DEFAULT_TIMEOUT = 10
REQUEST_DELAY = 0.2
DEFAULT_ALLOWED_DOMAIN = "example.com"  # change if you want

MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")

# AWS config (Lambda will listen on S3 bucket events)
S3_BUCKET = os.getenv("S3_BUCKET")
s3_client = boto3.client("s3")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


def _now_melbourne_iso():
    return dt.datetime.now(MELBOURNE_TZ).isoformat(timespec="seconds")


def _normalize_url(raw_url: str) -> str:
    if not raw_url.strip():
        return ""
    if not raw_url.startswith(("http://", "https://")):
        return "http://" + raw_url.strip()
    return raw_url.strip()


def _head_then_get_status(client, url, timeout):
    try:
        r = client.head(url, timeout=timeout, follow_redirects=True)
        return r.status_code, str(r.url), None, r.elapsed.total_seconds() * 1000, r.is_redirect
    except Exception as e:
        return None, url, str(e), 0, False


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def process_dataframe_stream(df: pd.DataFrame, original_filename: str):
    def generate():
        try:
            app.logger.info("Processing file: %s", original_filename)

            url_col = next((c for c in df.columns if c.lower() in ["url", "link"]), None)
            if not url_col:
                raise ValueError("Could not detect a URL column. Please name it 'URL' or 'Link'.")

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
            with httpx.Client(headers=headers) as client:
                for idx, row in df.iterrows():
                    raw_url = str(row[url_col] or "")
                    url = _normalize_url(raw_url)

                    if not url or DEFAULT_ALLOWED_DOMAIN not in url:
                        df.at[idx, "checking_time"] = _now_melbourne_iso()
                        df.at[idx, "error"] = "Skipped: not valid URL"
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

            # Save processed file
            base, ext = os.path.splitext(original_filename)
            output_filename = f"{base}_processed_{dt.datetime.now(MELBOURNE_TZ).strftime('%Y%m%d_%H%M%S')}{ext}"
            output_filepath = os.path.join(DOWNLOAD_FOLDER, output_filename)

            if original_filename.endswith('.xlsx'):
                df.to_excel(output_filepath, index=False, engine="openpyxl")
            else:
                df.to_csv(output_filepath, index=False)

            # ✅ Upload to S3 so Lambda can email
            s3_client.upload_file(output_filepath, S3_BUCKET, output_filename)

            yield f'data: {json.dumps({"done": True, "filename": output_filename, "skipped": skipped_count})}\n\n'

        except Exception as e:
            app.logger.error("Exception: %s", e, exc_info=True)
            yield f'data: {json.dumps({"error": str(e)})}\n\n'

    return generate()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files or 'email' not in request.form:
        return Response("Form incomplete: file and email required.", status=400)

    file = request.files['file']
    email = request.form['email']

    if file.filename == '' or email.strip() == '':
        return Response("No file selected or email missing.", status=400)

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
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
            return Response(f"Error: {e}", status=500)
    else:
        return Response(f"Allowed file types are: {', '.join(ALLOWED_EXTENSIONS)}", status=400)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
