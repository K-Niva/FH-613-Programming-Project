import boto3
import uuid
import json
from datetime import datetime, timedelta

AWS_REGION = "ap-southeast-2"
DYNAMODB_TABLE_NAME = 'url-processing-jobs'
PROCESSING_LAMBDA_NAME = '2025RMIT-URL-Scanner'

s3_client = boto3.client('s3', region_name=AWS_REGION)
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
lambda_client = boto3.client('lambda', region_name=AWS_REGION)
progress_table = dynamodb.Table(DYNAMODB_TABLE_NAME)

def lambda_handler(event, context):
    s3_record = event['Records'][0]['s3']
    s3_bucket_name = s3_record['bucket']['name']
    s3_key = s3_record['object']['key']

    try:
        s3_object_meta = s3_client.head_object(Bucket=s3_bucket_name, Key=s3_key)
        metadata = s3_object_meta['Metadata']
        recipient_email = metadata['recipient-email']

        schedule_time = metadata.get('schedule-time') 
        schedule_days = metadata.get('schedule-days')   

    except Exception as e:
        print(f"Error getting metadata: {e}")
        return {'statusCode': 500, 'body': 'Failed to get metadata from S3 object.'}

    if schedule_time and schedule_days:
        try:
            schedule_id = str(uuid.uuid4())
            start_date = datetime.utcnow().strftime('%Y-%m-%d')
            end_date = (datetime.utcnow() + timedelta(days=int(schedule_days))).strftime('%Y-%m-%d')

            schedule_item = {
                'job_id': schedule_id,
                'job_type': 'SCHEDULE_TEMPLATE',
                'job_status': 'ACTIVE',
                's3_key': s3_key,
                'original_filename': s3_key.split('/')[-1],
                'recipient_email': recipient_email,
                'schedule_start_date': start_date,
                'schedule_end_date': end_date,
                'schedule_process_time': schedule_time, # "HH:MM" in UTC
                'last_run_date': None
            }
            progress_table.put_item(Item=schedule_item)
            print(f"Created schedule {schedule_id} for {s3_key}")
            
        except Exception as e:
            print(f"Error creating schedule: {e}")
            return {'statusCode': 500, 'body': 'Failed to create schedule.'}

    else:
        print(f"Triggering immediate processing for {s3_key}")
        
        s3_event = { "Records": [event['Records'][0]] }
        
        lambda_client.invoke(
            FunctionName=PROCESSING_LAMBDA_NAME,
            InvocationType='Event',
            Payload=json.dumps(s3_event)
        )

    return {'statusCode': 200, 'body': 'Processing initiated.'}