import os
import datetime as dt
import time
from urllib.parse import urlparse, unquote_plus
import pandas as pd
import boto3
from botocore.exceptions import ClientError
import httpx
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

# --- Environment Variables ---
# Make sure these are set in your Lambda's configuration
S3_PROCESSED_PREFIX = os.getenv("S3_PROCESSED_PREFIX", "processed/")
VERIFIED_SENDER_EMAIL = os.getenv("VERIFIED_SENDER_EMAIL")
ALLOWED_RECIPIENTS = os.getenv("ALLOWED_RECIPIENTS", "").split(',')

# --- AWS Clients and Configuration ---
AWS_REGION = "ap-southeast-2"
s3_client = boto3.client('s3', region_name=AWS_REGION)
ses_client = boto3.client('ses', region_name=AWS_REGION)
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
progress_table = dynamodb.Table('url-processing-jobs')


def is_valid_domain(url: str, allowed_domain: str) -> bool:
    """Checks if the URL's hostname belongs to the allowed domain."""
    if not url:
        return False
    try:
        hostname = urlparse(url).hostname
        if hostname:
            return hostname.lower() == allowed_domain.lower() or hostname.lower().endswith(f'.{allowed_domain.lower()}')
    except Exception:
        return False
    return False

def send_email_with_attachment_ses(recipient_email, subject, body_text, file_path):
    """Sends an email with an attachment using the Amazon SES API."""
    if not all([VERIFIED_SENDER_EMAIL, recipient_email]):
        print("ERROR: VERIFIED_SENDER_EMAIL and a recipient email must be configured.")
        return

    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = VERIFIED_SENDER_EMAIL
    msg['To'] = recipient_email
    msg_body = MIMEMultipart('alternative')
    text_part = MIMEText(body_text, 'plain')
    msg_body.attach(text_part)
    msg.attach(msg_body)
    attachment_filename = os.path.basename(file_path)
    try:
        with open(file_path, 'rb') as f:
            part = MIMEApplication(f.read(), Name=attachment_filename)
        part.add_header('Content-Disposition', 'attachment', filename=attachment_filename)
        msg.attach(part)
    except IOError as e:
        print(f"Error opening attachment file: {e}")
        raise

    try:
        response = ses_client.send_raw_email(
            Source=VERIFIED_SENDER_EMAIL,
            Destinations=[recipient_email],
            RawMessage={'Data': msg.as_string()}
        )
        print(f"Email sent successfully to {recipient_email}. Message ID: {response['MessageId']}")
    except ClientError as e:
        print(f"FATAL: Failed to send email via SES to {recipient_email}: {e.response['Error']['Message']}")
        raise e

def find_url_column(df):
    """Heuristically finds the column most likely to contain URLs in a DataFrame."""
    candidate_names = ['url', 'website', 'link', 'links', 'site', 'homepage']
    for col in df.columns:
        if col.strip().lower() in candidate_names:
            print(f"Found URL column by common name: '{col}'")
            return col
    best_candidate, max_score = None, 0
    for col in df.columns:
        sample = df[col].dropna().head(20)
        if len(sample) == 0: continue
        score = sum(1 for item in sample if isinstance(item, str) and '.' in item and ' ' not in item) / len(sample)
        if score > max_score and score > 0.5:
            max_score, best_candidate = score, col
    if best_candidate:
        print(f"Detected URL column by content analysis: '{best_candidate}' with {max_score:.0%} confidence.")
        return best_candidate
    return None

def _normalize_url(url: str) -> str:
    """Strips whitespace and adds a default scheme to a URL if missing."""
    url = (url or "").strip()
    if not url: return ""
    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url

def process_url(url):
    """Processes a single URL to check its status, redirects, and performance."""
    start_time = time.perf_counter()
    normalized_url = _normalize_url(url)
    result = {'checking_time': dt.datetime.utcnow().isoformat(), 'status_code': None, 'final_url': normalized_url, 'redirected': False, 'elapsed_ms': None, 'error': None}
    if not normalized_url:
        result['error'] = 'No URL Provided'
        result['elapsed_ms'] = round((time.perf_counter() - start_time) * 1000, 2)
        return result
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.head(normalized_url)
            result.update({'status_code': response.status_code, 'final_url': str(response.url), 'redirected': normalized_url != str(response.url)})
    except httpx.RequestError as e:
        result['error'] = f"RequestError: {type(e).__name__}"
    except Exception as e:
        result['error'] = f"Unexpected Error: {type(e).__name__}"
    result['elapsed_ms'] = round((time.perf_counter() - start_time) * 1000, 2)
    return result

def lambda_handler(event, context):
    print("--- Starting URL Scan triggered by S3 event ---")

    try:
        s3_record = event['Records'][0]['s3']
        s3_bucket_name = s3_record['bucket']['name']
        source_s3_key = unquote_plus(s3_record['object']['key'])
    except (KeyError, IndexError):
        print("Error: Malformed S3 event.")
        return {'statusCode': 400, 'body': 'Malformed S3 event.'}

    if source_s3_key.startswith(S3_PROCESSED_PREFIX):
        return {'statusCode': 200, 'body': 'Ignoring file in processed directory.'}

    job_id = None
    final_recipient_email = None

    try:
        s3_object_meta = s3_client.head_object(Bucket=s3_bucket_name, Key=source_s3_key)
        metadata = s3_object_meta['Metadata']
        
        user_provided_email = metadata.get('recipient-email')
        job_id = metadata.get('job-id')

        if not job_id:
            raise KeyError("Metadata is missing the required 'job-id'.")

        # --- THIS IS THE CRITICAL VALIDATION LOGIC ---
        print(f"Validating recipient for Job ID: {job_id}")
        if user_provided_email and user_provided_email.lower().strip() in [email.lower().strip() for email in ALLOWED_RECIPIENTS]:
            final_recipient_email = user_provided_email
            print(f"Recipient '{final_recipient_email}' is authorized. Proceeding with job.")
        else:
            error_message = f"Unauthorized recipient email provided: '{user_provided_email}'. This is not a valid email address. Make sure it's a valid email address that is allowed to use this service."
            print(f"FATAL for Job ID {job_id}: {error_message}")
            progress_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression="SET job_status = :s, error_message = :e",
                ExpressionAttributeValues={':s': 'ERROR', ':e': error_message}
            )
            # Stop the execution immediately
            return {'statusCode': 403, 'body': error_message}

    except (ClientError, KeyError) as e:
        error_body = f"FATAL: Could not retrieve or validate metadata from S3. Error: {e}"
        print(error_body)
        return {'statusCode': 500, 'body': error_body}

    # --- Processing continues only if validation passed ---
    original_filename = os.path.basename(source_s3_key)
    local_filepath = f"/tmp/{original_filename}"
    local_output_path = None
    
    try:
        s3_client.download_file(s3_bucket_name, source_s3_key, local_filepath)
        df = pd.read_excel(local_filepath, engine="openpyxl") if local_filepath.lower().endswith('.xlsx') else pd.read_csv(local_filepath)
        total_urls = len(df)

        progress_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression="SET job_status = :s, total_urls = :t, original_filename = :o",
            ExpressionAttributeValues={':s': 'PROCESSING', ':t': total_urls, ':o': original_filename}
        )

        url_column_name = find_url_column(df)
        if not url_column_name:
            raise ValueError("Could not automatically detect a URL column.")

        results_list = []
        skipped_count = 0
        allowed_domain = "rmit.edu.au"

        for index, row in df.iterrows():
            url = row.get(url_column_name)
            if is_valid_domain(_normalize_url(url), allowed_domain):
                result = process_url(url)
            else:
                skipped_count += 1
                result = {
                    'checking_time': dt.datetime.utcnow().isoformat(), 'status_code': 'N/A',
                    'final_url': _normalize_url(url), 'redirected': False, 'elapsed_ms': 0,
                    'error': f'Skipped: URL is not from the {allowed_domain} domain.'
                }
            results_list.append(result)

            if (index + 1) % 5 == 0 or (index + 1) == total_urls:
                print(f"Updating progress for Job ID {job_id}: {index + 1}/{total_urls}")
                progress_table.update_item(Key={'job_id': job_id}, UpdateExpression="SET processed_urls = :p", ExpressionAttributeValues={':p': index + 1})

        results_df = pd.DataFrame(results_list)
        df.rename(columns={url_column_name: 'original_url'}, inplace=True)
        final_df = pd.concat([df.reset_index(drop=True), results_df.reset_index(drop=True)], axis=1)

        output_filename = f"processed_{dt.date.today().strftime('%Y-%m-%d')}_{original_filename}"
        local_output_path = f"/tmp/{output_filename}"
        if output_filename.lower().endswith('.xlsx'):
            final_df.to_excel(local_output_path, index=False, engine="openpyxl")
        else:
            final_df.to_csv(local_output_path, index=False)
        
        processed_s3_key = f"{S3_PROCESSED_PREFIX}{output_filename}"
        s3_client.upload_file(local_output_path, s3_bucket_name, processed_s3_key)
        
        email_subject = f"Your URL Scan Results for '{original_filename}' are Ready"
        email_body = f"Hello,\n\nPlease find your processed URL scan file attached.\n\nJob ID: {job_id}"
        
        send_email_with_attachment_ses(final_recipient_email, email_subject, email_body, local_output_path)

        print(f"Marking Job ID {job_id} as COMPLETE. Skipped URLs: {skipped_count}")
        progress_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression="SET job_status = :s, result_filename = :f, skipped_urls = :k",
            ExpressionAttributeValues={':s': 'COMPLETE', ':f': output_filename, ':k': skipped_count}
        )

    except Exception as e:
        print(f"An error occurred during processing for job {job_id}: {e}")
        if job_id:
             progress_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression="SET job_status = :s, error_message = :e",
                ExpressionAttributeValues={':s': 'ERROR', ':e': str(e)}
            )
    finally:
        if os.path.exists(local_filepath): os.remove(local_filepath)
        if local_output_path and os.path.exists(local_output_path): os.remove(local_output_path)

    return {'statusCode': 200, 'body': 'Process completed.'}