output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "configure_kubectl" {
  description = "Run this to set up kubectl access"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "dynamodb_accounts_table" {
  value = aws_dynamodb_table.accounts.name
}

output "dynamodb_transactions_table" {
  value = aws_dynamodb_table.transactions.name
}

output "backend_irsa_role_arn" {
  description = "Put this on the Kubernetes ServiceAccount annotation eks.amazonaws.com/role-arn"
  value       = module.backend_app_irsa.iam_role_arn
}

output "vpc_id" {
  value = module.vpc.vpc_id
}
