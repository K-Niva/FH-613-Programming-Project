import os
import logging
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import boto3
from botocore.exceptions import ClientError

# --- Configuration ---
# A temporary folder to store the file before it's uploaded to S3
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}

# IMPORTANT: Make sure this environment variable is set in your deployment environment
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "your-s3-bucket-name-here") 
S3_SOURCE_PREFIX = "source/"

# Initialize boto3 S3 client
s3_client = boto3.client("s3")

# --- Flask App Initialization ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'your-very-secret-key' # Change this in a real application

# Configure logging for production environments like Gunicorn
if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

# Ensure the temporary upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Checks if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Renders the main upload page."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Handles the file upload from the user.
    1. Validates the request.
    2. Saves the file temporarily.
    3. Uploads the file to S3 with the recipient's email in the metadata.
    4. Returns a JSON response to the front-end.
    """
    if 'file' not in request.files or 'email' not in request.form:
        app.logger.warning("Upload attempt with incomplete form.")
        return jsonify({
            'success': False,
            'message': 'Form is incomplete. File and email are required.'
        }), 400

    file = request.files['file']
    email = request.form.get('email', '').strip()

    if not file.filename or not email:
        return jsonify({
            'success': False,
            'message': 'No file selected or email provided. Please fill out both fields.'
        }), 400

    if not allowed_file(file.filename):
        return jsonify({
            'success': False,
            'message': f"Invalid file type. Allowed file types are: {', '.join(ALLOWED_EXTENSIONS)}"
        }), 400

    filename = secure_filename(file.filename)
    local_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        # Save the file to a temporary location on the server
        file.save(local_filepath)

        # Prepare the key for the S3 object
        s3_key = f"{S3_SOURCE_PREFIX}{filename}"

        # Prepare the metadata to be attached to the S3 object
        extra_args = {
            'Metadata': {
                'recipient-email': email
            }
        }

        # Upload the file to S3, including the metadata
        s3_client.upload_file(local_filepath, S3_BUCKET_NAME, s3_key, ExtraArgs=extra_args)
        app.logger.info(f"Successfully uploaded {s3_key} to S3 for recipient {email}")

        # Return a JSON success message to the front-end
        return jsonify({
            'success': True,
            'message': f'Your file has been received and is now being processed. A report will be sent to <strong>{email}</strong> shortly.'
        }), 200

    except ClientError as e:
        app.logger.error("S3 upload failed: %s", e, exc_info=True)
        return jsonify({
            'success': False,
            'message': 'Server error: Could not upload file to storage. Please try again later.'
        }), 500
    except Exception as e:
        app.logger.error("An unexpected error occurred during upload: %s", e, exc_info=True)
        return jsonify({
            'success': False,
            'message': 'An unexpected server error occurred. Please check the file format and try again.'
        }), 500
    finally:
        # IMPORTANT: Clean up the temporary file from the server's disk
        if os.path.exists(local_filepath):
            os.remove(local_filepath)

if __name__ == '__main__':
    app.run(debug=True, port=5001)