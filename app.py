import os
import logging
from flask import Flask, render_template, request, Response
from werkzeug.utils import secure_filename
import boto3
from botocore.exceptions import ClientError

# --- Configuration ---
UPLOAD_FOLDER = '/tmp/uploads' # Use temporary directory
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}

# These must be set as environment variables where you host your Flask app
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_SOURCE_PREFIX = "source/"

# Initialize S3 client
s3_client = boto3.client("s3")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.urandom(24) # Use a secure, random secret key

# Setup logging
if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
else:
    logging.basicConfig(level=logging.INFO)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if not S3_BUCKET_NAME:
        app.logger.error("FATAL: S3_BUCKET_NAME environment variable is not set.")
        return Response("Server configuration error.", status=500)

    if 'file' not in request.files or 'email' not in request.form:
        return Response("Form is incomplete. File and email are required.", status=400)

    file = request.files['file']
    email = request.form.get('email', '').strip()

    if not file.filename or not email:
        return Response("No file selected or email provided.", status=400)

    if not allowed_file(file.filename):
        return Response(f"Invalid file type. Allowed types are: {', '.join(ALLOWED_EXTENSIONS)}", status=400)
        
    filename = secure_filename(file.filename)
    # Save temporarily to upload to S3
    local_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(local_filepath)

    s3_key = f"{S3_SOURCE_PREFIX}{filename}"
    
    try:
        # We add the recipient's email as metadata for the Lambda function to use
        extra_args = {
            'Metadata': {
                'recipient-email': email
            }
        }

        s3_client.upload_file(local_filepath, S3_BUCKET_NAME, s3_key, ExtraArgs=extra_args)
        app.logger.info(f"Successfully uploaded {s3_key} to S3 for recipient {email}")

    except ClientError as e:
        app.logger.error("S3 upload failed: %s", e, exc_info=True)
        return Response(f"Failed to upload file to our system: {e}", status=500)
    
    finally:
        # Clean up the temporary file
        if os.path.exists(local_filepath):
            os.remove(local_filepath)

    # Return a success message to the user. The Lambda will handle the rest.
    return render_template('success.html', user_email=email)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)