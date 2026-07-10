# ---------------------------------------------------------------------------
# SES - lets the notification-writer Lambda send each new user a real
# welcome email (separate from the SNS -> SQS -> DynamoDB in-app
# notification, and separate from the ops-alert SNS email subscription in
# sns.tf). Set var.ses_sender_email to enable it.
#
# SES starts every account in the sandbox: both the sender AND every
# recipient address must be verified before mail actually sends. AWS
# emails a confirmation link to the sender address below - click it once.
# To email arbitrary (unverified) recipients, request SES production
# access in the AWS console.
# ---------------------------------------------------------------------------

resource "aws_ses_email_identity" "sender" {
  count = var.ses_sender_email != "" ? 1 : 0
  email = var.ses_sender_email
}
