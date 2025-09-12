import os
import csv
from flask import Flask, render_template, request, send_from_directory, flash, redirect, url_for
import openpyxl
import requests
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.secret_key = 'supersecretkey'

def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['file']

    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        if filename.endswith('.xlsx'):
            output_filename = process_excel(filepath, filename)
        elif filename.endswith('.csv'):
            output_filename = process_csv(filepath, filename)
        else:
            flash('Invalid file type')
            return redirect(request.url)

        return f'''
        Processing complete for {filename}.
        <br><br>
        <a href="/download/{output_filename}">Download the updated file</a>
        '''
    else:
        flash('Allowed file types are .xlsx and .csv')
        return redirect(request.url)


def process_csv(filepath, original_filename):
    """Processes a .csv file, checking the status of ANY valid URL."""
    rows = []
    with open(filepath, 'r', newline='', encoding='utf-8') as infile:
        reader = csv.reader(infile)
        try:
            header = next(reader)
            if "HTTP Status" not in header:
                header.append("HTTP Status")
            rows.append(header)

            for row in reader:
                if row and row[0]:
                    url = row[0].strip()

                    if url.startswith(('http://', 'https://')):
                        try:
                            response = requests.get(url, timeout=10, allow_redirects=True)
                            status_code = response.status_code
                        except requests.exceptions.RequestException:
                            status_code = "Error - Unreachable"
                        row.append(status_code)
                    else:
                        row.append("Not a valid URL")
                else:
                    row.append("")
                rows.append(row)

        except StopIteration:
            pass

    base, ext = os.path.splitext(original_filename)
    output_filename = f"{base}_processed{ext}"
    output_filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], output_filename)
    with open(output_filepath, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.writer(outfile)
        writer.writerows(rows)
    return output_filename

def process_excel(filepath, original_filename):
    """Processes an .xlsx file, checking the status of ANY valid URL."""
    workbook = openpyxl.load_workbook(filepath)
    sheet = workbook.active

    if sheet.cell(row=1, column=2).value != "HTTP Status":
        sheet.cell(row=1, column=2, value="HTTP Status")

    for row in sheet.iter_rows(min_row=2, max_col=1):
        for cell in row:
            if cell.value:
                url = str(cell.value).strip()
                if url.startswith(('http://', 'https://')):
                    try:
                        response = requests.get(url, timeout=10, allow_redirects=True)
                        status_code = response.status_code
                    except requests.exceptions.RequestException:
                        status_code = "Error - Unreachable"
                    
                    sheet.cell(row=cell.row, column=2, value=status_code)
                else:
                    sheet.cell(row=cell.row, column=2, value="Not a valid URL")

    base, ext = os.path.splitext(original_filename)
    output_filename = f"{base}_processed{ext}"
    output_filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], output_filename)
    workbook.save(output_filepath)
    return output_filename

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)