# SNS topic published to by the users-service on first-time registration.
# Subscribe an email/SMS endpoint to this topic to actually receive them
# (see the aws_sns_topic_subscription example below, commented out since
# it needs a real email/phone number).
resource "aws_sns_topic" "user_registered" {
  name = "${var.project_name}-${var.environment}-user-registered"
}

resource "aws_iam_policy" "sns_publish_user_registered" {
  name        = "${var.project_name}-${var.environment}-sns-publish-user-registered"
  description = "Allows the users-service to publish to the user-registered SNS topic"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PublishUserRegistered"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.user_registered.arn
      }
    ]
  })
}

# Uncomment and set a real address to actually receive the notifications:
# resource "aws_sns_topic_subscription" "user_registered_email" {
#   topic_arn = aws_sns_topic.user_registered.arn
#   protocol  = "email"
#   endpoint  = "you@example.com"
# }

output "sns_user_registered_topic_arn" {
  value = aws_sns_topic.user_registered.arn
}
