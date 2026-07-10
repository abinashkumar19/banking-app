resource "aws_dynamodb_table" "accounts" {
  name         = "${var.project_name}-${var.environment}-accounts"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "account_id"

  attribute {
    name = "account_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "transactions" {
  name         = "${var.project_name}-${var.environment}-transactions"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "account_id"
  range_key    = "transaction_id"

  attribute {
    name = "account_id"
    type = "S"
  }

  attribute {
    name = "transaction_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# IAM policy granting the backend app's IRSA role least-privilege access
# to just these two tables (and their indexes, if you add any later).
resource "aws_dynamodb_table" "users" {
  name         = "${var.project_name}-${var.environment}-users"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "email"

  attribute {
    name = "email"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# One id-keyed table per generic microservice (transfers, cards, loans, ...).
resource "aws_dynamodb_table" "generic" {
  for_each = toset(local.generic_services)

  name         = "${var.project_name}-${var.environment}-${each.value}"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_iam_policy" "dynamodb_app_access" {
  name        = "${var.project_name}-${var.environment}-dynamodb-app-access"
  description = "Allows the VeeraBank backend pods to read/write their DynamoDB tables"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AppTableAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = concat(
          [
            aws_dynamodb_table.accounts.arn,
            "${aws_dynamodb_table.accounts.arn}/index/*",
            aws_dynamodb_table.transactions.arn,
            "${aws_dynamodb_table.transactions.arn}/index/*",
            aws_dynamodb_table.users.arn,
            "${aws_dynamodb_table.users.arn}/index/*",
          ],
          [for t in aws_dynamodb_table.generic : t.arn],
          [for t in aws_dynamodb_table.generic : "${t.arn}/index/*"],
        )
      }
    ]
  })
}
