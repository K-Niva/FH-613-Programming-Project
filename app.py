import os
import time
import json
import datetime as dt
import logging
from flask import Flask, render_template, request, send_from_directory, Response
from werkzeug.utils import secure_filename
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import boto3
from botocore.exceptions import ClientError

UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}

DEFAULT_ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "rmit.edu.au")
DEFAULT_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.10"))
USER_AGENT = os.getenv("USER_AGENT", "URLStatusChecker/1.0 (FlaskWebApp)")
MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "rmit-url-scan-data")
S3_SOURCE_PREFIX = "source/"
s3_client = boto3.client("s3")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.secret_key = 'supersecretkey'

if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _is_allowed_host(url: str, allowed_root: str) -> bool:
    try:
        host = urlparse(url.strip()).hostname or ""
    except Exception:
        return False
    allowed_root = allowed_root.lower().strip()
    host = host.lower()
    return host == allowed_root or host.endswith("." + allowed_root)

def _normalize_url(url: str) -> str:
