# ---------------------------------------------------------------------------
# RDS (Aurora MySQL Serverless v2) - system of record for user accounts.
# Replaces the old DynamoDB "users" table: registration, login, and profile
# data now live here so they can be queried/joined relationally.
# ---------------------------------------------------------------------------

resource "random_password" "db_master" {
  length      = 24
  special     = false # Aurora master password disallows some special chars
  min_upper   = 2
  min_lower   = 2
  min_numeric = 2
}

resource "aws_db_subnet_group" "users" {
  name       = "${var.project_name}-${var.environment}-users-db"
  subnet_ids = local.private_subnet_ids
}

resource "aws_security_group" "users_db" {
  name        = "${var.project_name}-${var.environment}-users-db-sg"
  description = "Allow MySQL (3306) from the EKS worker nodes to the users Aurora cluster"
  vpc_id      = local.vpc_id

  ingress {
    description     = "MySQL from EKS nodes"
    from_port        = 3306
    to_port          = 3306
    protocol         = "tcp"
    security_groups  = [module.eks.node_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_rds_cluster" "users" {
  cluster_identifier     = "${var.project_name}-${var.environment}-users-db"
  engine                 = "aurora-mysql"
  engine_mode            = "provisioned"
  # No engine_version pinned on purpose: Aurora MySQL minor versions get
  # retired periodically, and a hardcoded one (e.g. 3.07.1) will eventually
  # 400 with "Cannot find version ... for aurora-mysql". Omitting it lets
  # AWS pick its current default, which is always installable.
  database_name          = "veerabank_users"
  master_username         = "veerabank_admin"
  master_password         = random_password.db_master.result
  db_subnet_group_name    = aws_db_subnet_group.users.name
  vpc_security_group_ids  = [aws_security_group.users_db.id]

  storage_encrypted      = true
  skip_final_snapshot    = true
  backup_retention_period = 7

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 4
  }
}

resource "aws_rds_cluster_instance" "users" {
  cluster_identifier = aws_rds_cluster.users.id
  instance_class      = "db.serverless"
  engine               = aws_rds_cluster.users.engine
  engine_version       = aws_rds_cluster.users.engine_version
}

# Credentials handed to the users-service pod via Secrets Manager (never
# baked into the image or a k8s manifest in plaintext).
resource "aws_secretsmanager_secret" "users_db" {
  name = "${var.project_name}-${var.environment}-users-db-credentials"
}

resource "aws_secretsmanager_secret_version" "users_db" {
  secret_id = aws_secretsmanager_secret.users_db.id
  secret_string = jsonencode({
    username = aws_rds_cluster.users.master_username
    password = random_password.db_master.result
    host     = aws_rds_cluster.users.endpoint
    port     = 3306
    dbname   = aws_rds_cluster.users.database_name
  })
}

resource "aws_iam_policy" "users_db_secret_access" {
  name        = "${var.project_name}-${var.environment}-users-db-secret-access"
  description = "Allows the users-service pod to read its Aurora MySQL credentials"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadUsersDbSecret"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.users_db.arn
      }
    ]
  })
}
