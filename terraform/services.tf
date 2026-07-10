# Single source of truth for the microservices in this project.
# accounts, transactions, and users have custom schemas (defined
# explicitly in dynamodb.tf); everything in `generic_services` gets
# a simple id-keyed table generated via for_each.
locals {
  generic_services = [
    "transfers", "cards", "loans", "payments", "beneficiaries",
    "statements", "notifications", "kyc", "fixed-deposits", "cheques",
    "disputes", "audit-log", "fraud-detection", "support-tickets",
    "rewards", "admin", "reports",
  ]

  # Every backend microservice (used for ECR repos + IRSA policy).
  backend_services = concat(["accounts", "transactions", "users"], local.generic_services)

  # Everything that gets its own ECR repo, including the frontend.
  all_images = concat(local.backend_services, ["frontend"])
}
