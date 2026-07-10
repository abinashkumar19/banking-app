import os
import boto3

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ENV_PREFIX = os.getenv("TABLE_PREFIX", "veerabank-dev")

# boto3 auto-picks up credentials from the IRSA web-identity token
# mounted on the pod - no static access keys needed in-cluster.
_dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
_sns = boto3.client("sns", region_name=AWS_REGION)


def table(name: str):
    """Get a DynamoDB table handle, prefixed like every other table
    in this project (veerabank-dev-<name>)."""
    return _dynamodb.Table(f"{ENV_PREFIX}-{name}")


def sns_publish(topic_arn_env: str, subject: str, message: str):
    """Publish to an SNS topic whose ARN is read from an env var
    (wired in via the k8s deployment). No-ops with a log line if
    the env var isn't set, so services don't crash in envs without SNS."""
    topic_arn = os.getenv(topic_arn_env)
    if not topic_arn:
        print(f"[sns_publish] {topic_arn_env} not set, skipping publish: {subject}")
        return
    _sns.publish(TopicArn=topic_arn, Subject=subject, Message=message)
