"""Low-volume heartbeat used to validate the pilot telemetry pipeline."""

import json
import os
from datetime import UTC, datetime, timedelta

import boto3


def handler(event, _context):
    now = datetime.now(UTC)
    payload = {"type": "telemetry_heartbeat", "at": now.isoformat(), "event": event}
    boto3.client("s3").put_object(Bucket=os.environ["TELEMETRY_BUCKET"], Key=f"telemetry/heartbeats/{now:%Y/%m/%d/%H}.json", Body=json.dumps(payload).encode(), ContentType="application/json")
    boto3.client("dynamodb").put_item(TableName=os.environ["DEVICE_STATE_TABLE"], Item={"device_id": {"S": "system#telemetry-heartbeat"}, "recorded_at": {"S": now.isoformat()}, "expires_at": {"N": str(int((now + timedelta(days=31)).timestamp()))}})
    boto3.client("sns").publish(TopicArn=os.environ["ALERT_TOPIC_ARN"], Subject="GPS telemetry heartbeat", Message=json.dumps(payload))
    return {"ok": True, "at": now.isoformat()}
