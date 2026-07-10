import json
import os
import boto3

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ENV_PREFIX = os.getenv("TABLE_PREFIX", "veerabank-dev")

# boto3 auto-picks up credentials from the IRSA web-identity token
# mounted on the pod - no static access keys needed in-cluster.
_dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
_sns = boto3.client("sns", region_name=AWS_REGION)
_s3 = boto3.client("s3", region_name=AWS_REGION)

_db_creds_cache = None


def _get_db_credentials() -> dict:
    """Fetch and cache the Aurora MySQL credentials for the users-service
    from the private S3 credentials bucket. The bucket/key are wired in via
    the DB_CREDS_BUCKET / DB_CREDS_KEY env vars on the users deployment
    (see terraform/rds.tf)."""
    global _db_creds_cache
    if _db_creds_cache is not None:
        return _db_creds_cache

    bucket = os.environ["DB_CREDS_BUCKET"]
    key = os.environ["DB_CREDS_KEY"]
    resp = _s3.get_object(Bucket=bucket, Key=key)
    _db_creds_cache = json.loads(resp["Body"].read())
    return _db_creds_cache


def mysql_connection():
    """Return a new pymysql connection to the users Aurora MySQL cluster,
    using credentials pulled from Secrets Manager."""
    import pymysql  # imported lazily so services that don't need MySQL
                     # (everything except users-service) don't require it

    creds = _get_db_credentials()
    return pymysql.connect(
        host=creds["host"],
        port=int(creds.get("port", 3306)),
        user=creds["username"],
        password=creds["password"],
        database=creds["dbname"],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def table(name: str):
    """Get a DynamoDB table handle, prefixed like every other table
    in this project (veerabank-dev-<name>)."""
    return _dynamodb.Table(f"{ENV_PREFIX}-{name}")


def sns_publish(topic_arn_env: str, subject: str, message):
    """Publish to an SNS topic whose ARN is read from an env var
    (wired in via the k8s deployment). No-ops with a log line if
    the env var isn't set, so services don't crash in envs without SNS.
    `message` can be a plain string or a dict/list (JSON-encoded on the
    way out) - the users-service sends a structured dict so downstream
    subscribers (see backend/lambdas/notification_writer) can parse
    individual fields like the recipient's email."""
    topic_arn = os.getenv(topic_arn_env)
    if not topic_arn:
        print(f"[sns_publish] {topic_arn_env} not set, skipping publish: {subject}")
        return
    body = json.dumps(message) if isinstance(message, (dict, list)) else message
    _sns.publish(TopicArn=topic_arn, Subject=subject, Message=body)
