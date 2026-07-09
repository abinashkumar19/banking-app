import os
import boto3

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
ACCOUNTS_TABLE = os.getenv("ACCOUNTS_TABLE", "veerabank-dev-accounts")
TRANSACTIONS_TABLE = os.getenv("TRANSACTIONS_TABLE", "veerabank-dev-transactions")

# boto3 automatically picks up credentials from the IRSA-mounted
# web identity token on the pod - no access keys needed in-cluster.
_dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)

accounts_table = _dynamodb.Table(ACCOUNTS_TABLE)
transactions_table = _dynamodb.Table(TRANSACTIONS_TABLE)
