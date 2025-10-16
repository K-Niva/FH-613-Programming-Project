import os
import logging
import uuid
import boto3
from flask import Flask, render_template, request, jsonify, Response
from werkzeug.utils import secure_filename
from botocore.exceptions import ClientError
import datetime as dt
from datetime import datetime
import pytz  # ✅ Added for timezone handling

# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_SOURCE_PREFIX = "source/"
S3_PROCESSED_PREFIX = "processed/"

# --- AWS Clients ---
AWS_REGION = "ap-southeast-2"  # Ensure it matches your AWS region

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


# --- UPDATED /upload FUNCTION BELOW ---
@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload, creating an immediate job AND a recurring schedule if requested."""
    if 'file' not in request.files or 'email' not in request.form:
        return jsonify({'success': False, 'message': 'Form is incomplete.'}), 400

    file = request.files['file']
    email = request.form.get('email', '').strip()

    is_scheduled = request.form.get('enable-schedule')
    start_date = request.form.get('schedule_start_date')
    end_date = request.form.get('schedule_end_date')
    process_time = request.form.get('schedule_process_time')  # User provides time in AEST

    if not file.filename or not email or not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Invalid file or email provided.'}), 400

    filename = secure_filename(file.filename)
    local_filepath = os.path.join(UPLOAD_FOLDER, filename)

    try:
        file.save(local_filepath)
        s3_key = f"{S3_SOURCE_PREFIX}{filename}"
        s3_client.upload_file(local_filepath, S3_BUCKET_NAME, s3_key)

        job_id_for_polling = None  # ID for frontend polling

        if is_scheduled and start_date and end_date and process_time:
            # --- START: AEST to UTC conversion ---
            try:
                aest_tz = pytz.timezone('Australia/Sydney')  # Handles AEST/AEDT
                naive_datetime_str = f"{start_date} {process_time}"
                naive_dt = datetime.strptime(naive_datetime_str, '%Y-%m-%d %H:%M')
                aest_dt = aest_tz.localize(naive_dt, is_dst=None)
                utc_dt = aest_dt.astimezone(pytz.utc)
                utc_process_time_str = utc_dt.strftime('%H:%M')

                print(f"DEBUG: Converted {process_time} AEST on {start_date} → {utc_process_time_str} UTC.")
            except Exception as e:
                print(f"WARNING: Timezone conversion failed, using input time. Error: {e}")
                utc_process_time_str = process_time
            # --- END: AEST to UTC conversion ---

            # --- Create schedule template ---
            schedule_id = str(uuid.uuid4())
            schedule_item = {
                'job_id': schedule_id,
                'job_type': 'SCHEDULE_TEMPLATE',
                'job_status': 'ACTIVE',
                'recipient_email': email,
                'original_filename': filename,
                's3_key': s3_key,
                'schedule_start_date': start_date,
                'schedule_end_date': end_date,
                'schedule_process_time': utc_process_time_str,  # ✅ Store UTC version
                'upload_time': dt.datetime.utcnow().isoformat()
            }
            progress_table.put_item(Item=schedule_item)

            # --- Create immediate job run ---
            initial_run_id = str(uuid.uuid4())
            run_item = {
                'job_id': initial_run_id,
                'job_type': 'JOB_RUN',
                'job_status': 'PENDING',
                'original_filename': filename,
                'recipient_email': email,
                'parent_schedule_id': schedule_id,
                'upload_time': dt.datetime.utcnow().isoformat()
            }
            progress_table.put_item(Item=run_item)

            # --- Trigger Lambda via S3 metadata update ---
            s3_client.copy_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                CopySource={'Bucket': S3_BUCKET_NAME, 'Key': s3_key},
                Metadata={'recipient-email': email, 'job-id': initial_run_id},
                MetadataDirective='REPLACE'
            )

            job_id_for_polling = initial_run_id
            message = (
                f"File accepted. Processing now and scheduled daily from {start_date} to {end_date} "
                f"at {process_time} AEST ({utc_process_time_str} UTC)."
            )

        else:
            # --- Standard one-time on-demand job ---
            on_demand_job_id = str(uuid.uuid4())
            item = {
                'job_id': on_demand_job_id,
                'job_type': 'JOB_RUN',
                'job_status': 'PENDING',
                'original_filename': filename,
                'recipient_email': email,
                'upload_time': dt.datetime.utcnow().isoformat()
            }
            progress_table.put_item(Item=item)

            s3_client.copy_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                CopySource={'Bucket': S3_BUCKET_NAME, 'Key': s3_key},
                Metadata={'recipient-email': email, 'job-id': on_demand_job_id},
                MetadataDirective='REPLACE'
            )
            job_id_for_polling = on_demand_job_id
            message = 'File upload successful. Processing has started immediately.'

        return jsonify({
            'success': True,
            'message': message,
            'job_id': job_id_for_polling
        }), 200

    except Exception as e:
        app.logger.error(f"Error during upload: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'An unexpected server error occurred during upload.'}), 500
    finally:
        if os.path.exists(local_filepath):
            os.remove(local_filepath)
# --- END UPDATED FUNCTION ---


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
