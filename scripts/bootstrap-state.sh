#!/usr/bin/env bash
# One-time setup: creates the S3 bucket + DynamoDB table terraform needs
# for remote state. Run this ONCE, before the first `terraform init` /
# before the first CI/CD run. Safe to re-run (skips anything that already
# exists).
#
# Run this in AWS CloudShell (console, top-right icon) or any shell with
# the AWS CLI configured against this account.

set -euo pipefail

BUCKET="veerabank-tfstate-517798688687-6b6ca11c"
TABLE="veerabank-terraform-locks"
REGION="us-east-1"

echo "== Creating S3 bucket: $BUCKET in $REGION =="
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "Bucket already exists and is accessible, skipping create."
else
  # head-bucket said "no" (404, or a 403 we can't distinguish from 404),
  # but create-bucket can still fail with BucketAlreadyExists - notably
  # us-east-1 returns that generic error even when *this* account already
  # owns the bucket, instead of the friendlier BucketAlreadyOwnedByYou.
  # So: attempt the create, then re-check access rather than trusting
  # create-bucket's error message alone.
  set +e
  CREATE_OUTPUT=$(aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" 2>&1)
  CREATE_STATUS=$?
  set -e

  if [ $CREATE_STATUS -eq 0 ]; then
    echo "Bucket created."
  elif aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
    echo "Bucket creation reported an error, but it's accessible under this account - continuing."
  else
    echo "$CREATE_OUTPUT" >&2
    echo ""
    echo "== Bucket name '$BUCKET' is not usable by this account =="
    echo "S3 bucket names are unique across ALL of AWS, not just your account."
    echo "This exact name is already taken by someone else (or an orphaned"
    echo "bucket from another account). Pick a new name, e.g.:"
    echo ""
    echo "  BUCKET=\"veerabank-tfstate-\$(date +%s)\""
    echo ""
    echo "...then update both this script's BUCKET variable and the"
    echo "backend \"s3\" { bucket = ... } block in terraform/main.tf to match,"
    echo "and re-run this script."
    exit 1
  fi
fi

echo "== Enabling versioning =="
aws s3api put-bucket-versioning \
  --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

echo "== Enabling default encryption (AES256) =="
aws s3api put-bucket-encryption \
  --bucket "$BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

echo "== Blocking public access =="
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "== Creating DynamoDB lock table: $TABLE =="
if aws dynamodb describe-table --table-name "$TABLE" --region "$REGION" >/dev/null 2>&1; then
  echo "Table already exists, skipping create."
else
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION"
fi

echo ""
echo "Done. terraform/main.tf already points at this bucket/table -"
echo "you can now run 'terraform init' locally, or rerun the GitHub Actions workflow."
