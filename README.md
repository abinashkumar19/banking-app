# Cloud Bank on EKS

AWS banking app: Terraform-provisioned infra, **21 FastAPI microservices +
1 frontend**, deployed to EKS via ECR images + a single ALB Ingress.

- **User accounts**: **DynamoDB** is the source of truth for registration/
  login. Every write is streamed (DynamoDB Streams) by the `users-db-sync`
  Lambda into an **Aurora MySQL (Serverless v2)** replica, so the same data
  can also be queried/joined relationally — the users-service pod itself
  never talks to RDS directly.
- **Email verification (OTP) + login alerts**: registration is gated on a
  6-digit code emailed to the person via Gmail SMTP (`users-service`
  `/users/otp/send` + `/users/otp/verify`, backed by a short-lived
  `otp_codes` DynamoDB table with TTL). Every successful login also fires
  a "new sign-in to your account" email to that person's own address.
  Credentials (`SMTP_USER`, `SMTP_APP_PASSWORD`) live only as a GitHub
  Actions secret + a k8s Secret populated at deploy time — never in the repo.
- **Support chatbot**: a stateless `chatbot-service` wraps Groq's chat-
  completions API (`GROQ_API_KEY`, same secret-handling as SMTP above) and
  answers questions about the app from a floating widget in the frontend.
- **Profile self-service**: `PATCH /users/{id}` lets a person update only
  their display name and avatar photo — email/phone/password are untouched.
- **Per-user activity history** lives in **S3**, one folder per user
  (`s3://<bucket>/<user_id>/...`), written and read through a Lambda behind
  API Gateway. Any service can log an event there (transactions, account
  openings, ...) tagged with an `event_type`; fetching a user's folder
  returns their whole combined history, newest first (balances themselves
  stay in DynamoDB, updated atomically per transaction).
- **New user registration** publishes to **SNS**, which fans out to (a) an
  optional ops-alert email subscriber, and (b) an SQS queue consumed by a
  Lambda that both writes an in-app notification *and* sends the new user a
  personal welcome email via **SES** — all configured in Terraform, not
  left as commented-out placeholders.
- **Accounts**: `accounts-service` enforces **exactly one account per
  registered user** — it looks the user up in `users-service` (so an
  account can never be opened for someone who hasn't registered, and
  `owner_name` always matches their one registered name) and uses a
  DynamoDB `TransactWriteItems` call (account item + a per-user lock
  item) so two simultaneous "open an account" requests for the same user
  can't both succeed.
- **Transfers**: `transfers-service` moves real money — a transfer is a
  single atomic transaction that debits the sender, credits the
  recipient, and writes the ledger row, all-or-nothing, with the balance
  check enforced inside the transaction itself (no possible overdraft
  race). It has its own DynamoDB table with GSIs so either party can
  pull their transfer history. Every transfer also carries the sender's
  name and email, so the recipient always knows who paid them.
- Everything else (cards, loans, payments, ...) still uses one simple
  DynamoDB table per service.

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

Set a real inbox for the SNS ops-alert email subscription before applying
(optional):
```bash
export TF_VAR_notification_email="you@example.com"
```
AWS will send that address a subscription-confirmation email — it must be
clicked before delivery starts, same as any SNS email subscription.

To send new users a real welcome email, also set a verified SES sender
(optional — skip this and registration still works, it just won't email
anyone):
```bash
export TF_VAR_ses_sender_email="notifications@yourdomain.com"
```
AWS emails that address a verification link — click it once. SES accounts
start in the sandbox, so recipient addresses need verifying too until you
request production access in the SES console.

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
- 21 DynamoDB tables (`accounts`, `transactions`, `users`, `transfers` with
  custom schemas; `otp_codes` for email-verification codes, TTL-expiring;
  the other 16 are generic id-keyed tables)
- 22 ECR repos (21 microservices, including `chatbot`, + frontend)
- An SNS topic (`user-registered`) the `users` service publishes to on
  first-time registration
- AWS Load Balancer Controller + EBS CSI driver, each with their own IRSA role
- One shared IRSA role for all backend pods, scoped to all DynamoDB tables + SNS publish

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

`users-service` (SMTP for OTP emails) and `chatbot-service` (Groq) also
need an `app-secrets` k8s Secret at runtime — see `k8s/app-secrets.example.yaml`
for the shape. In CI this is created automatically from GitHub Actions
secrets (see "CI/CD" below); for a manual/local deploy, copy that file,
fill in real values, and `kubectl apply -f` it yourself.

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
| users | POST | `/users/register` | Register; requires a verified OTP first; publishes SNS on first-time registration |
| users | POST | `/users/login` | Login |
| users | GET | `/users/{id}` | Get a user |
| users | PATCH | `/users/{id}` | Update profile — `full_name` and/or `profile_photo` only |
| users | POST | `/users/otp/send` | Email a 6-digit verification code (5 min expiry) |
| users | POST | `/users/otp/verify` | Verify a code before registering |
| chatbot | POST | `/chatbot/message` | `{message, history}` -> `{reply}`, via Groq |
| accounts | POST | `/accounts` | Create an account |
| accounts | GET | `/accounts` | List accounts |
| accounts | GET | `/accounts/{id}` | Get one account |
| accounts | DELETE | `/accounts/{id}` | Delete an account |
| transactions | POST | `/transactions` | Deposit or withdraw (atomic, overdraft-safe) |
| transactions | GET | `/transactions/{account_id}` | List an account's transactions |
| transfers | POST | `/transfers` | Move money; body includes `sender_name`/`sender_email`, shown to the recipient |
| the other 16 | POST/GET/DELETE | `/{service}/items[/​{id}]` | Generic CRUD, same shape on every one |

## CI/CD (fully automated)

`.github/workflows/deploy.yml` runs the whole pipeline on every push to `main`
(or manually via "Run workflow"):

```
terraform apply  →  build & push all 22 images to ECR  →  sync app-secrets (SMTP + Groq)
                                                         →  kubectl apply (all manifests)
                                                         →  wait for every rollout
                                                         →  wait for ALB
                                                         →  print the single ingress URL
```

Two jobs: `terraform` provisions/updates infra and exposes its outputs
(a JSON map of service name → ECR repo URL, the shared backend IRSA role
ARN, and the SNS topic ARN) to the `deploy` job, which loops over every
service, builds and pushes its image, renders each k8s manifest
(substituting those outputs in via `sed` instead of hand-editing 22 files),
**creates/updates the `app-secrets` k8s Secret directly from GitHub
Actions secrets** (SMTP credentials + `GROQ_API_KEY` — never written to
the repo or a file on disk), applies everything, waits for each
deployment's rollout, and polls the Ingress until the ALB hostname shows
up — that URL is written to the job summary.

**One-time setup before the first CI run:**

1. **Remote state** — the CI workflow itself creates the S3 bucket + DynamoDB
   lock table on its first run if they don't exist yet (see the "Ensure
   state bucket + lock table exist" step in `deploy.yml`), so **there's
   nothing to do here for CI**. `terraform/main.tf`'s `backend "s3"` block
   already has a bucket name baked in; if that exact bucket doesn't exist
   in your account, CI creates it automatically on the first push.

   Only run this yourself if you want to run `terraform` **locally**
   (outside CI) — it does the same thing plus points `main.tf` at whatever
   bucket it ends up using and runs `terraform init -reconfigure` for you:
   ```bash
   bash scripts/bootstrap-state.sh
   ```

2. **GitHub secrets** (repo → Settings → Secrets and variables → Actions —
   or set them on a GitHub **Environment**, e.g. `production`, and add
   `environment: production` to the jobs in `deploy.yml`, if you want
   environment-scoped protection rules on top):
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   (an IAM user/role with EKS, EC2, VPC, IAM, DynamoDB, ECR, S3, RDS,
   Lambda, SES, and SNS/SQS permissions)
   - `SMTP_USER`, `SMTP_APP_PASSWORD` — a Gmail address + app password
     `users-service` sends OTP and login-notification emails from.
     `SMTP_APP_PASSWORD` is a Google Account **App Password**
     (Google Account → Security → 2-Step Verification → App passwords),
     not your normal Gmail password. (Host/port/from-address default to
     Gmail's — nothing else to set.)
   - `GROQ_API_KEY` — for the chatbot widget, from
     [console.groq.com](https://console.groq.com/keys).

3. Push to `main` — the whole stack stands up from nothing to a live ALB URL
   with no manual steps.

Subsequent pushes just update the image and re-apply manifests (terraform
apply is a no-op if infra hasn't changed). The `app-secrets` sync step runs
every deploy too, so rotating a secret in GitHub and re-running the
workflow (or pushing again) is all it takes to rotate it in the cluster.

## Notes

- Withdrawals use a DynamoDB conditional `UpdateExpression` so balance checks
  and debits happen atomically — no race condition between concurrent requests.
- SNS topic `user-registered` has no subscribers by default — uncomment
  `aws_sns_topic_subscription` in `terraform/sns.tf` and set a real email to
  actually receive the welcome notifications.
- If `app-secrets` isn't present (e.g. a fresh local cluster before the
  first CI run), `users-service` logs and skips sending OTP emails instead
  of failing the request, and `chatbot-service` returns a 503 with a clear
  message instead of crashing — apply `k8s/app-secrets.example.yaml` (with
  real values) to fix both.
- The 16 generic services (`cards`, `loans`, ...) share one CRUD
  template — flesh out the business logic in `backend/services/<name>/app/main.py`
  as each one's real requirements get defined.
- `users` password hashing (`hashlib.sha256`) is demo-grade — swap for
  bcrypt/argon2 before this handles real customer data.
- Swap `single_nat_gateway = true` for one-per-AZ in `vpc.tf` if you want prod-grade HA.
- Add an ACM cert + uncomment the HTTPS annotations in `k8s/ingress.yaml` for TLS.
