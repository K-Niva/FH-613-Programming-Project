"""status_checker.py
This file contains the core logic that reads an Excel file of web addresses (URLs),
checks each URL one-by-one to see whether the website is reachable (HTTP status),
and writes the results back to a new Excel file.

The idea is to read websites sequentially with a time buffer (no parallel blasting of requests) and to
keep the original spreadsheet unchanged by writing to a new output file.

Non‑technical summary:
- We open your spreadsheet.
- We find the column that looks like it contains URLs (prefer a header called 'URL').
- For each URL that belongs to rmit.edu.au:
    - We try to contact the website's server.
    - We record a status number (e.g., 200 = OK, 404 = Not Found).
    - If anything goes wrong (network issue, typo, etc.), It will be recorded in the file and returned.
- We save a new spreadsheet with extra columns showing what happened.
"""

import os
import time
import datetime as dt
from typing import Optional, Tuple

import httpx                        # A modern library for making web requests (talking to websites).
import pandas as pd                 # A toolkit for reading/writing Excel and working with tables.
from urllib.parse import urlparse   # Used to safely read parts of a URL (like the domain name).
from zoneinfo import ZoneInfo       # Built-in in Python 3.9+

# Settings you can change via environment variables (e.g., in Docker or shell).
DEFAULT_ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "rmit.edu.au")                     # Only check URLs on this domain
DEFAULT_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))                                # How long to wait for a website (in seconds)
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.10"))                               # Pause between checks (seconds)
USER_AGENT = os.getenv("USER_AGENT", "URLStatusChecker/1.0 (+https://example.local)")   # Current program identification

MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")


def _is_allowed_host(url: str, allowed_root: str) -> bool:
    """Return True if the URL's website belongs to the allowed domain.
    Example: if allowed_root is 'rmit.edu.au', allow 'www.rmit.edu.au' and 'study.rmit.edu.au'.
    """
    try:
        host = urlparse(url.strip()).hostname or ""  # Pull the website's host part (e.g., 'www.rmit.edu.au')
    except Exception:
        return False
    allowed_root = allowed_root.lower().strip()
    host = host.lower()
    # Either an exact match (host == allowed_root) or a subdomain (host ends with '.allowed_root')
    return host == allowed_root or host.endswith("." + allowed_root)


def _normalize_url(url: str) -> str:
    """Make the URL tidy and ensure it has a scheme (http/https).
    If websites are recorded as 'www.rmit.edu.au', we interpret it as 'https://www.rmit.edu.au'.
    """
    url = (url or "").strip()
    if not url:
        return url
    parsed = urlparse(url)
    if not parsed.scheme:  # No 'http' or 'https' at the front? Assume 'https' for safety.
        return "https://" + url
    return url


def _head_then_get_status(client: httpx.Client, url: str, timeout: float):
    """Try to check the website in a low‑impact way.
    1) We try a HEAD request first (asks for headers only, not the whole page).
    2) If that fails or isn't allowed by the server, we try a normal GET.
    We follow redirects (e.g., when a page moves from http to https).

    Returns a 5‑part tuple:
      (status_code, final_url, error_message, elapsed_ms, redirected)
    """
    import time as _t
    start = _t.perf_counter()
    redirected = False
    try:
        # Try asking the server for *just the headers* (quick test)
        r = client.head(url, timeout=timeout, follow_redirects=True)
        elapsed_ms = (_t.perf_counter() - start) * 1000.0
        redirected = (str(r.url) != url) or (len(r.history) > 0)
        return r.status_code, str(r.url), "", elapsed_ms, redirected
    except httpx.HTTPStatusError as e:
        # The server replied with an HTTP error (e.g., 404) that raised an exception.
        elapsed_ms = (_t.perf_counter() - start) * 1000.0
        return e.response.status_code, str(e.request.url), f"HTTPStatusError: {e}", elapsed_ms, True
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.NetworkError, httpx.ProtocolError):
        # If the HEAD attempt failed due to network/timeout issues, try a normal GET request.
        try:
            start2 = _t.perf_counter()
            r = client.get(url, timeout=timeout, follow_redirects=True)
            elapsed_ms = (_t.perf_counter() - start2) * 1000.0
            redirected = (str(r.url) != url) or (len(r.history) > 0)
            return r.status_code, str(r.url), "", elapsed_ms, redirected
        except Exception as e2:
            # Still couldn't reach the site — record the error message for the spreadsheet.
            elapsed_ms = (_t.perf_counter() - start) * 1000.0
            return None, url, f"RequestError: {e2.__class__.__name__}: {e2}", elapsed_ms, redirected
    except Exception as e:
        # Any other unexpected problem.
        elapsed_ms = (_t.perf_counter() - start) * 1000.0
        return None, url, f"Error: {e.__class__.__name__}: {e}", elapsed_ms, redirected


def _detect_url_column(df: pd.DataFrame) -> str:
    """automatically try to find which column contains URLs.
    In order to increase program rebustnessm, We first look for a column literally named 'URL'/'Urls'/'Link' (case‑insensitive),
    then fall back to any column whose name contains the letters 'url'.
    If all else fails, we just use the first column in the sheet.
    """
    for name in df.columns:
        if str(name).strip().lower() in {"url", "urls", "link"}:
            return name
    for name in df.columns:
        if "url" in str(name).lower():
            return name
    return df.columns[0] if len(df.columns) > 0 else None   # Fallback to using first column

def _now_melbourne_iso() -> str:
    """Return current time in Australia/Melbourne as ISO string with offset (seconds precision)."""
    return dt.datetime.now(MELBOURNE_TZ).replace(microsecond=0).isoformat()

def process_excel(input_xlsx: str, output_xlsx: str, allowed_root: str = DEFAULT_ALLOWED_DOMAIN,
                  timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Main entry point called by both the web app and the command‑line tool.

    What it does:
      - Open the input Excel file.
      - Identify the URL column.
      - For each row, check the URL if it belongs to the allowed domain.
      - Add new columns with the results.
      - Save a brand‑new Excel file with those results.

    The returned dictionary is a simple summary you can print or log.
    """
    # Read the entire Excel file into a table.
    df = pd.read_excel(input_xlsx, engine="openpyxl")
    if df.empty:
        raise ValueError("Input Excel file appears to be empty.")

    # Figure out which column contains the URLs.
    url_col = _detect_url_column(df)
    if not url_col:
        raise ValueError("Could not detect a URL column in the workbook. Please include a 'URL' column.")

    # Prepare/clear the output columns we will fill in.
    df["checking_time"] = pd.NaT    # When we checked it
    df["status_code"] = pd.NA       # 200, 404, etc.
    df["final_url"] = pd.NA         # After redirects, where did we end up?
    df["redirected"] = pd.NA        # True/False
    df["elapsed_ms"] = pd.NA        # How long it took, in milliseconds
    df["error"] = pd.NA             # Any problem text

    headers = {"User-Agent": USER_AGENT}
    processed = 0  # How many URLs we actually attempted to check
    skipped = 0    # How many URLs we skipped (wrong domain, empty, etc.)
    errors = 0     # How many ended in an error

    # Use a single HTTP client for all requests — more efficient and consistent.
    with httpx.Client(headers=headers) as client:
        # Go through the URLs in order, one by one.
        for idx, raw in enumerate(df[url_col].tolist()):
            url = (str(raw) or "")
            url = _normalize_url(url)

            # Only check URLs that belong to e.g. rmit.edu.au
            if not url or not _is_allowed_host(url, allowed_root):
                df.at[idx, "checking_time"] = _now_melbourne_iso()
                df.at[idx, "error"] = "Skipped: domain not allowed"
                skipped += 1
                continue

            # Try to reach the site and collect the status information.
            status_code, final_url, err, elapsed_ms, redirected = _head_then_get_status(client, url, timeout=timeout)

            # Record our findings into the new columns for this row.
            df.at[idx, "checking_time"] = _now_melbourne_iso()
            df.at[idx, "status_code"] = status_code
            df.at[idx, "final_url"] = final_url
            df.at[idx, "redirected"] = bool(redirected)
            df.at[idx, "elapsed_ms"] = round(float(elapsed_ms), 2)
            df.at[idx, "error"] = err

            processed += 1
            if err or status_code is None:
                errors += 1

            # Adjustible delay to avoid triggering any defense mechanism on RMIT server.
            time.sleep(REQUEST_DELAY)

    # Save results as a new spreadsheet so the original stays untouched.
    df.to_excel(output_xlsx, index=False, engine="openpyxl")

    # Return a tiny summary that can be printed by the caller.
    return {
        "total_rows": len(df),
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "output_xlsx": output_xlsx
    }
