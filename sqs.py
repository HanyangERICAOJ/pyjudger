import json
import os
from time import sleep
import boto3

from judge import judge

SLEEP_SECONDS = 10

def polling_judge_queue():
    try:
        client = boto3.client(
            'sqs',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_KEY'),
            region_name=os.getenv('AWS_REGION'),
        )

        response = client.receive_message(
            QueueUrl=os.getenv('AWS_SQS_URL'),
        )

        message = response['Messages']
        if len(message) == 0:
            # No message
            sleep(SLEEP_SECONDS)
            return
        
        submission_id = json.loads(message[0]['Body'])['id']
        judge_result = judge(11)

        if judge_result:
            client.delete_message(
                QueueUrl=os.getenv('AWS_SQS_URL'),
                ReceiptHandle=message[0]['ReceiptHandle'],
            )
        else:
            pass
    except (BaseException) as err:
        sleep(SLEEP_SECONDS)
        return
