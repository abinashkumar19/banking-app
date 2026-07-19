
```
veerabank-eks/
├── terraform/
│   ├── rds.tf                # Aurora MySQL replica of the users table (fed by users-db-sync)
│   ├── s3.tf                 # per-user history bucket
│   ├── lambda.tf             # user-history Lambda+API GW, notification-writer, users-db-sync
│   ├── ses.tf                # SES sender identity for welcome emails
│   ├── sns.tf                # user-registered topic: email sub + SQS/Lambda sub
│   ├── dynamodb.tf           # users table (streams-enabled) + accounts + transfers + otp_codes + 16 generic tables
│   └── vpc.tf eks.tf ecr.tf variables.tf outputs.tf main.tf
├── backend/
│   ├── common/                # shared DynamoDB, SNS, S3, and SMTP-mailer helpers
│   ├── lambdas/
│   │   ├── transactions_history/  # general-purpose per-user S3 history, behind API Gateway
│   │   ├── notification_writer/   # SQS -> DynamoDB notifications table + SES welcome email
│   │   └── users_db_sync/         # DynamoDB Streams -> Aurora MySQL replication
│   └── services/
│       ├── accounts/          # account CRUD + balance (DynamoDB)
│       ├── transactions/      # atomic balance update (DynamoDB) + history (S3 via Lambda)
│       ├── users/             # register (OTP-gated) + login + profile update, SNS publish + history event
│       ├── chatbot/           # stateless Groq chat-completions wrapper for the support widget
│       ├── transfers/ cards/ loans/ payments/ beneficiaries/
│       ├── statements/ notifications/ kyc/ fixed-deposits/ cheques/
│       ├── disputes/ audit-log/ fraud-detection/ support-tickets/
│       └── rewards/ admin/ reports/      (generic CRUD template, 17 services)
├── frontend/                  # single-page HTML/CSS/JS dashboard, served via nginx
└── k8s/
    ├── services/               # deployment + service manifest per microservice
    ├── frontend/               # frontend deployment + service
    ├── app-secrets.example.yaml # shape of the app-secrets Secret (SMTP + Groq) - reference only, never fill in and apply for real
    ├── ingress.yaml            # path-based routing: /accounts, /users, /transfers, /chatbot, ... , / -> frontend
    ├── namespace.yaml
    └── serviceaccount.yaml     # one shared IRSA-linked service account for all backend pods
```
