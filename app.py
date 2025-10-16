import os
import logging
import uuid
import boto3
from flask import Flask, render_template, request, jsonify, Response
from werkzeug.utils import secure_filename
from botocore.exceptions import ClientError
import datetime as dt

# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_SOURCE_PREFIX = "source/"
S3_PROCESSED_PREFIX = "processed/"

# --- AWS Clients ---
# IMPORTANT: Hardcode the region to ensure it works correctly
AWS_REGION = "ap-southeast-2"  # <-- Make sure this matches your AWS Region

s3_client = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
progress_table = dynamodb.Table('url-processing-jobs')

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Render the upload form page."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload, either immediate or scheduled recurring job."""
    if 'file' not in request.files or 'email' not in request.form:
        return jsonify({'success': False, 'message': 'Form is incomplete.'}), 400

    file = request.files['file']
    email = request.form.get('email', '').strip()

    # --- NEW: Capture schedule form data ---
    is_scheduled = request.form.get('enable-schedule')
    start_date = request.form.get('schedule_start_date')
    end_date = request.form.get('schedule_end_date')
    process_time = request.form.get('schedule_process_time')

    if not file.filename or not email or not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Invalid file or email provided.'}), 400

    filename = secure_filename(file.filename)
    local_filepath = os.path.join(UPLOAD_FOLDER, filename)
    job_id = str(uuid.uuid4())  # This will be the ID for the schedule or the single job

    try:
        # Save the uploaded file locally first
        file.save(local_filepath)
        s3_key = f"{S3_SOURCE_PREFIX}{filename}"

        # Upload to S3 first
        s3_client.upload_file(local_filepath, S3_BUCKET_NAME, s3_key)

        # --- NEW: Logic to create either a schedule or a one-off job ---
        if is_scheduled and start_date and end_date and process_time:
            # This is a recurring schedule template
            item = {
                'job_id': job_id,
                'job_type': 'SCHEDULE_TEMPLATE',
                'job_status': 'ACTIVE',
                'recipient_email': email,
                'original_filename': filename,
                's3_key': s3_key,
                'schedule_start_date': start_date,
                'schedule_end_date': end_date,
                'schedule_process_time': process_time,
                'upload_time': dt.datetime.utcnow().isoformat()
            }
            progress_table.put_item(Item=item)
            message = f"Successfully created a daily schedule (ID: {job_id}) to run from {start_date} to {end_date}."
        else:
            # This is an immediate, on-demand job (the original behavior)
            item = {
                'job_id': job_id,
                'job_type': 'JOB_RUN',
                'job_status': 'PENDING',
                'original_filename': filename,
                'recipient_email': email,
                'upload_time': dt.datetime.utcnow().isoformat()
            }
            progress_table.put_item(Item=item)

            # For immediate jobs, we add metadata to the S3 object
            # so that the S3 trigger on the Lambda function processes it.
            s3_client.copy_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                CopySource={'Bucket': S3_BUCKET_NAME, 'Key': s3_key},
                Metadata={'recipient-email': email, 'job-id': job_id},
                MetadataDirective='REPLACE'
            )
            message = 'File upload successful. Processing has started immediately.'

        return jsonify({
            'success': True,
            'message': message,
            'job_id': job_id
        }), 200

    except Exception as e:
        app.logger.error(f"Error during upload for job {job_id}: {e}", exc_info=True)
        try:
            progress_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression="SET job_status = :s, error_message = :e",
                ExpressionAttributeValues={':s': 'ERROR', ':e': str(e)}
            )
        except Exception as db_error:
            app.logger.error(f"Could not update DynamoDB with error state for job {job_id}: {db_error}")

        return jsonify({'success': False, 'message': 'An unexpected server error occurred during upload.'}), 500
    finally:
        if os.path.exists(local_filepath):
            os.remove(local_filepath)


@app.route('/status/<job_id>')
def get_status(job_id):
    """Fetch job or schedule status from DynamoDB."""
    try:
        response = progress_table.get_item(Key={'job_id': job_id})
        item = response.get('Item', {})
        return jsonify(item)
    except Exception as e:
        app.logger.error(f"Could not fetch status for job {job_id}: {e}")
        return jsonify({'status': 'ERROR', 'error_message': 'Could not fetch status.'}), 500


@app.route('/download/<filename>')
def download_file(filename):
    """Allow users to download processed files from S3."""
    s3_key = f"{S3_PROCESSED_PREFIX}{secure_filename(filename)}"
    try:
        s3_object = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        return Response(
            s3_object['Body'].iter_chunks(),
            mimetype='application/octet-stream',
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return "File not found.", 404
        else:
            app.logger.error(f"Error downloading {s3_key} from S3: {e}")
            return "Error downloading file.", 500


if __name__ == '__main__':
    app.run(debug=True)
