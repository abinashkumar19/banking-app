# VeeraBank on EKS

AWS banking app: Terraform-provisioned infra, **20 FastAPI microservices +
1 frontend**, deployed to EKS via ECR images + a single ALB Ingress.

- **User accounts** live in **Aurora MySQL (Serverless v2)**, not DynamoDB.
- **Transaction history** lives in **S3**, written and read through a Lambda
  behind API Gateway (balances themselves stay in DynamoDB, updated
  atomically per transaction).
- **New user registration** publishes to **SNS**, which fans out to (a) a
  real email subscriber and (b) an SQS queue consumed by a Lambda that
  writes an in-app notification — both configured in Terraform, not left
  as commented-out placeholders.
- Everything else (transfers, cards, loans, payments, ...) still uses one
  simple DynamoDB table per service.

```
veerabank-eks/
├── terraform/
│   ├── rds.tf                # Aurora MySQL Serverless v2 cluster for user accounts
│   ├── s3.tf                 # transaction-history bucket
│   ├── lambda.tf             # transactions-history Lambda+API GW, notification-writer Lambda
│   ├── sns.tf                # user-registered topic: email sub + SQS/Lambda sub
│   ├── dynamodb.tf           # accounts table + 17 generic id-keyed tables
│   └── vpc.tf eks.tf ecr.tf variables.tf outputs.tf main.tf
├── backend/
│   ├── common/                # shared DynamoDB, SNS, and Aurora MySQL helpers
│   ├── lambdas/
│   │   ├── transactions_history/  # S3 read/write, behind API Gateway
│   │   └── notification_writer/   # SQS -> DynamoDB notifications table
│   └── services/
│       ├── accounts/          # account CRUD + balance (DynamoDB)
│       ├── transactions/      # atomic balance update (DynamoDB) + history (S3 via Lambda)
│       ├── users/             # register + login against Aurora MySQL, SNS publish on registration
│       ├── transfers/ cards/ loans/ payments/ beneficiaries/
│       ├── statements/ notifications/ kyc/ fixed-deposits/ cheques/
│       ├── disputes/ audit-log/ fraud-detection/ support-tickets/
│       └── rewards/ admin/ reports/      (generic CRUD template, 17 services)
├── frontend/                  # single-page HTML/CSS/JS dashboard, served via nginx
└── k8s/
    ├── services/               # deployment + service manifest per microservice
    ├── frontend/               # frontend deployment + service
    ├── ingress.yaml            # path-based routing: /accounts, /users, /transfers, ... , / -> frontend
    ├── namespace.yaml
    └── serviceaccount.yaml     # one shared IRSA-linked service account for all backend pods
```

Set a real inbox for the SNS email subscription before applying:
```bash
export TF_VAR_notification_email="you@example.com"
```
AWS will send that address a subscription-confirmation email — it must be
clicked before delivery starts, same as any SNS email subscription.

Every service is reachable at its own path off the single ALB URL:
`/accounts`, `/transactions`, `/users`, `/transfers`, `/cards`, `/loans`,
`/payments`, `/beneficiaries`, `/statements`, `/notifications`, `/kyc`,
`/fixed-deposits`, `/cheques`, `/disputes`, `/audit-log`,
`/fraud-detection`, `/support-tickets`, `/rewards`, `/admin`, `/reports` —
and `/` serves the frontend.

## 1. Provision infra

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

This creates:
- VPC (reused if one already exists — see `vpc.tf`)
- EKS cluster (1.30) with a managed node group
- 20 DynamoDB tables (`accounts`, `transactions`, `users` with custom
  schemas; the other 17 are generic id-keyed tables)
- 21 ECR repos (20 microservices + frontend)
- An SNS topic (`user-registered`) the `users` service publishes to on
  first-time registration
- AWS Load Balancer Controller + EBS CSI driver, each with their own IRSA role
- One shared IRSA role for all backend pods, scoped to all 20 tables + SNS publish

Grab the outputs you'll need next:
```bash
terraform output
```

## 2. Point kubectl at the cluster

```bash
aws eks update-kubeconfig --region us-east-1 --name veerabank-dev-eks
```

## 3. Build and push all images to ECR

```bash
cd ..
ECR_URLS=$(cd terraform && terraform output -json ecr_repository_urls)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

echo "$ECR_URLS" | jq -r 'keys[]' | while read -r svc; do
  url=$(echo "$ECR_URLS" | jq -r --arg s "$svc" '.[$s]')
  if [ "$svc" = "frontend" ]; then
    docker build -f frontend/Dockerfile -t "$url:latest" frontend
  else
    docker build -f "backend/services/$svc/Dockerfile" -t "$url:latest" backend
  fi
  docker push "$url:latest"
done
```

(The CI/CD workflow below does exactly this automatically — this is only
for manual/local runs.)

## 4. Wire up the manifests

In `k8s/serviceaccount.yaml`, replace the role ARN with:
```bash
cd terraform && terraform output -raw backend_irsa_role_arn
```

Each file under `k8s/services/*-deployment.yaml` has a placeholder like
`<ECR_REPO_URL_ACCOUNTS>:latest` — replace with the matching image from
step 3. `k8s/services/users-deployment.yaml` also has
`<SNS_USER_REGISTERED_TOPIC_ARN>` — fill in with
`terraform output -raw sns_user_registered_topic_arn`.
`k8s/frontend/deployment.yaml` has `<ECR_REPO_URL_FRONTEND>:latest`.

## 5. Deploy to the cluster

```bash
cd k8s
kubectl apply -f namespace.yaml
kubectl apply -f serviceaccount.yaml
kubectl apply -f services/
kubectl apply -f frontend/
kubectl apply -f ingress.yaml
```

Watch the ALB come up:
```bash
kubectl get ingress -n veerabank -w
```

Once the ADDRESS field populates with a `*.elb.amazonaws.com` hostname, hit:
```
http://<alb-hostname>/                    -> frontend
http://<alb-hostname>/users/register      -> register a user (fires SNS)
http://<alb-hostname>/accounts            -> accounts API
http://<alb-hostname>/accounts/docs       -> Swagger UI for the accounts service (every service has its own /docs)
```

## API quick reference

| Service | Method | Path | Description |
|---|---|---|---|
| users | POST | `/users/register` | Register; publishes SNS on first-time registration |
| users | POST | `/users/login` | Login |
| users | GET | `/users/{id}` | Get a user |
| accounts | POST | `/accounts` | Create an account |
| accounts | GET | `/accounts` | List accounts |
| accounts | GET | `/accounts/{id}` | Get one account |
| accounts | DELETE | `/accounts/{id}` | Delete an account |
| transactions | POST | `/transactions` | Deposit or withdraw (atomic, overdraft-safe) |
| transactions | GET | `/transactions/{account_id}` | List an account's transactions |
| the other 17 | POST/GET/DELETE | `/{service}/items[/​{id}]` | Generic CRUD, same shape on every one |

## CI/CD (fully automated)

`.github/workflows/deploy.yml` runs the whole pipeline on every push to `main`
(or manually via "Run workflow"):

```
terraform apply  →  build & push all 21 images to ECR  →  kubectl apply (all manifests)
                                                         →  wait for every rollout
                                                         →  wait for ALB
                                                         →  print the single ingress URL
```

Two jobs: `terraform` provisions/updates infra and exposes its outputs
(a JSON map of service name → ECR repo URL, the shared backend IRSA role
ARN, and the SNS topic ARN) to the `deploy` job, which loops over every
service, builds and pushes its image, renders each k8s manifest
(substituting those outputs in via `sed` instead of hand-editing 21 files),
applies them all, waits for each deployment's rollout, and polls the
Ingress until the ALB hostname shows up — that URL is written to the job
summary.

**One-time setup before the first CI run:**

1. **Remote state** (required — GitHub Actions has no local disk between runs):

   Run the bootstrap script once (in AWS CloudShell, or any shell with the
   AWS CLI configured against this account):
   ```bash
   bash scripts/bootstrap-state.sh
   ```
   This creates the S3 bucket (`veerabank-tfstate-517798688687-6b6ca11c`,
   versioned + encrypted + public access blocked) and the DynamoDB lock
   table (`veerabank-terraform-locks`) that `terraform/main.tf`'s
   `backend "s3"` block already points at. Safe to re-run.

2. **GitHub secrets** (repo → Settings → Secrets and variables → Actions):
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   (an IAM user/role with EKS, EC2, VPC, IAM, DynamoDB, ECR, and S3 permissions)

3. Push to `main` — the whole stack stands up from nothing to a live ALB URL
   with no manual steps.

Subsequent pushes just update the image and re-apply manifests (terraform
apply is a no-op if infra hasn't changed).

## Notes

- Withdrawals use a DynamoDB conditional `UpdateExpression` so balance checks
  and debits happen atomically — no race condition between concurrent requests.
- SNS topic `user-registered` has no subscribers by default — uncomment
  `aws_sns_topic_subscription` in `terraform/sns.tf` and set a real email to
  actually receive the welcome notifications.
- The 17 generic services (`transfers`, `cards`, `loans`, ...) share one CRUD
  template — flesh out the business logic in `backend/services/<name>/app/main.py`
  as each one's real requirements get defined.
- `users` password hashing (`hashlib.sha256`) is demo-grade — swap for
  bcrypt/argon2 before this handles real customer data.
- Swap `single_nat_gateway = true` for one-per-AZ in `vpc.tf` if you want prod-grade HA.
- Add an ACM cert + uncomment the HTTPS annotations in `k8s/ingress.yaml` for TLS.
