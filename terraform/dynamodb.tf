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

# ---------------------------------------------------------------------------
# "users" table - source of truth for registration/login. Streams feed the
# users-db-sync Lambda (see lambda.tf), which replicates every write into
# the Aurora MySQL "users" table (see rds.tf) for relational querying.
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "users" {
  name         = "${var.project_name}-${var.environment}-users"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "email"
    type = "S"
  }

  global_secondary_index {
    name            = "email-index"
    hash_key        = "email"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  # Required so the users-db-sync Lambda can consume inserts/updates/deletes
  # and mirror them into RDS.
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"
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
