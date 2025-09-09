# FH-613-Programming-Project
Project for AI-assisted system for monitoring and validating RMIT Ads landing pages

---

# RMIT URL Status Checker

A Python + Flask tool that reads an Excel file of URLs, checks HTTP status codes **sequentially (one at a time)**, and writes results back to a new file.  

By default, it only processes `rmit.edu.au` URLs (and its subdomains). Others are skipped.

---

## Features

- Upload an `.xlsx` file and download the annotated results.  
- Sequential checks (no parallel/concurrent requests).  
- Only processes `rmit.edu.au` (configurable via `ALLOWED_DOMAIN`).  
- Falls back from `HEAD` to `GET` if `HEAD` is not supported.  
- Adds these columns to the file:
  - `checking time`  
  - `status_code`  
  - `final_url`  
  - `redirected`  
  - `elapsed_ms`  
  - `error`  

---

## Quickstart

If this is your first time running this program, follow this process to setup initial status and install all required dependencies

Skip this section and visit the "Relaunching application" section if it isn't

### 1. Open a terminal
- **Windows**: Command Prompt 
- **macOS/Linux**: Terminal  

### 2. Navigate to the project folder
```bash
cd path/to/url-status-checker-phase1
```

### 3. Create and activate a virtual environment
Windows:
```Command Prompt 
python -m venv .venv
.venv\Scripts\activate.bat
```

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install dependencies
First, upgrade pip:
```bash
python -m pip install -U pip setuptools wheel
```

Then install required packages:
```bash
pip install -r required_packages.txt
```

---

## Running the Program

```bash
python app.py
```
- Open [http://localhost:8080](http://localhost:8080) in your browser.  
- Upload an Excel file (`.xlsx`) with a column named `URL`.  
- Auto download the processed file with extra status info.  

---

## Relaunching application

Once all dependencies have been setup, relaunching only requires reactivating the virtual enviornment

### 1. Open a terminal
- **Windows**: Command Prompt 
- **macOS/Linux**: Terminal  

### 2. Navigate to the project folder
```bash
cd path/to/url-status-checker
```

### 3. Relaunch the application
Windows:
```Command Prompt 
.venv\Scripts\activate.bat
```

macOS/Linux:
```bash
source .venv/bin/activate
```
## 4. Running the Program

```bash
python app.py
```
- Open [http://localhost:8080](http://localhost:8080) in your browser.  
- Upload an Excel file (`.xlsx`) with a column named `URL`.  
- Download the processed file with extra status info.  

---

## Configuration

You can adjust behaviour with environment variables:

- `ALLOWED_DOMAIN` (default: `rmit.edu.au`)  
- `HTTP_TIMEOUT` (seconds, default: `10`)  
- `REQUEST_DELAY` (seconds between requests, default: `0.10`)  
- `USER_AGENT` (default: `URLStatusChecker/1.0 (+https://example.local)`)  

---

## Excel Input Format

- Must have at least one column with URLs.  
- Preferably name it `URL`.  
- Only `rmit.edu.au` and its subdomains will be checked.  
- Others will be skipped with error `"Skipped: domain not allowed"`.  

---

## Troubleshooting

- **`RequestError: ConnectError: [Errno -3] Temporary failure in name resolution`**  

Network/DNS issue. Retry later or check your internet/DNS settings.  

---

## Current known issues

- Depriciated warning message in cmd/terminal while running
- very basic web gui
- this readme file not fully covering all functions
- no implementation for docker (yet?)
- unfinished commenting in code
- for now there is no reason to follow the quickstart section since a complete windows enviorement is provided (consider deleting enviorement before final version?)


