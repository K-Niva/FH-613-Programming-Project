import boto3
import json
from datetime import datetime

AWS_REGION = "ap-southeast-2"
DYNAMODB_TABLE_NAME = 'url-processing-jobs'
PROCESSING_LAMBDA_NAME = '2025RMIT-URL-Scanner'
S3_BUCKET_NAME = "rmit-url-scan-data"

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
lambda_client = boto3.client('lambda', region_name=AWS_REGION)
progress_table = dynamodb.Table(DYNAMODB_TABLE_NAME)

def lambda_handler(event, context):
    print("--- Starting Scheduled Job Scan ---")

    now_utc = datetime.utcnow()
    today_str = now_utc.strftime('%Y-%m-%d')

    response = progress_table.scan(
        FilterExpression="job_type = :type AND job_status = :status",
        ExpressionAttributeValues={':type': 'SCHEDULE_TEMPLATE', ':status': 'ACTIVE'}
    )

    schedules = response.get('Items', [])
    print(f"Found {len(schedules)} active schedules.")

    for schedule in schedules:
        schedule_id = schedule['job_id']
        start_date = schedule.get('schedule_start_date')
        end_date = schedule.get('schedule_end_date')

        if not (start_date <= today_str <= end_date):
            if today_str > end_date:
                progress_table.update_item(
                    Key={'job_id': schedule_id},
                    UpdateExpression="SET job_status = :s",
                    ExpressionAttributeValues={':s': 'EXPIRED'}
                )
            continue

        last_run_date = schedule.get('last_run_date')
        if last_run_date == today_str:
            continue  

        process_hour, process_minute = map(int, schedule['schedule_process_time'].split(':'))

        if now_utc.hour == process_hour and now_utc.minute >= process_minute:
            print(f"Triggering run for schedule ID: {schedule_id}")

            try:
                s3_event = {
                    "Records": [{
                        "s3": {
                            "bucket": {"name": S3_BUCKET_NAME},
                            "object": {"key": schedule['s3_key']}
                        }
                    }]
                }
                s3_client = boto3.client('s3', region_name=AWS_REGION)
                s3_client.copy_object(
                    Bucket=S3_BUCKET_NAME,
                    CopySource={'Bucket': S3_BUCKET_NAME, 'Key': schedule['s3_key']},
                    Key=schedule['s3_key'],
                    Metadata={
                        'recipient-email': schedule['recipient_email'],
                        'job-id': str(uuid.uuid4())
                    },
                    MetadataDirective='REPLACE'
                )

                lambda_client.invoke(
                    FunctionName=PROCESSING_LAMBDA_NAME,
                    InvocationType='Event',
                    Payload=json.dumps(s3_event)
                )

                progress_table.update_item(
                    Key={'job_id': schedule_id},
                    UpdateExpression="SET last_run_date = :d",
                    ExpressionAttributeValues={':d': today_str}
                )
                print(f"Successfully triggered job for schedule {schedule_id}.")

            except Exception as e:
                print(f"ERROR: Failed to trigger job for schedule {schedule_id}: {e}")

    return {'statusCode': 200, 'body': 'Scheduler run complete.'}