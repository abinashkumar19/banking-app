# VeeraBank on EKS

AWS banking app: Terraform-provisioned infra, FastAPI + DynamoDB backend,
deployed to EKS via ECR image + ALB Ingress.

```
veerabank-eks/
├── terraform/       # VPC, EKS, DynamoDB, ECR, ALB controller, IRSA roles
├── backend/         # FastAPI app (accounts + transactions APIs)
└── k8s/             # Deployment, Service, Ingress manifests
```

## 1. Provision infra

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

This creates:
- VPC (2 AZs, public + private subnets, 1 NAT gateway)
- EKS cluster (1.30) with a managed node group
- Two DynamoDB tables: `<project>-<env>-accounts`, `<project>-<env>-transactions`
- ECR repo for the backend image
- AWS Load Balancer Controller installed via Helm, with its own IRSA role
- An IRSA role for the backend pod, scoped to only those two DynamoDB tables (no static AWS keys anywhere)

Grab the outputs you'll need next:
```bash
terraform output
```

## 2. Point kubectl at the cluster

```bash
aws eks update-kubeconfig --region us-east-1 --name veerabank-dev-eks
```

## 3. Build and push the backend image to ECR

```bash
cd ../backend
ECR_URL=$(cd ../terraform && terraform output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_URL
docker build -t $ECR_URL:latest .
docker push $ECR_URL:latest
```

## 4. Wire up the manifests

In `k8s/serviceaccount.yaml`, replace the role ARN with:
```bash
cd ../terraform && terraform output -raw backend_irsa_role_arn
```

In `k8s/deployment.yaml`, replace `<ECR_REPO_URL>:latest` with the value from step 3.
Also double check `ACCOUNTS_TABLE` / `TRANSACTIONS_TABLE` env values match the
`terraform output dynamodb_accounts_table` / `dynamodb_transactions_table` names.

## 5. Deploy to the cluster

```bash
cd ../k8s
kubectl apply -f namespace.yaml
kubectl apply -f serviceaccount.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
```

Watch the ALB come up:
```bash
kubectl get ingress -n veerabank -w
```

Once the ADDRESS field populates with a `*.elb.amazonaws.com` hostname, hit:
```
http://<alb-hostname>/          -> {"service": "veerabank-backend", "status": "running"}
http://<alb-hostname>/healthz   -> {"status": "ok"}
http://<alb-hostname>/docs      -> Swagger UI
```

## API quick reference

| Method | Path                       | Description               |
|--------|-----------------------------|----------------------------|
| POST   | `/accounts`                 | Create an account          |
| GET    | `/accounts`                 | List accounts              |
| GET    | `/accounts/{id}`            | Get one account             |
| DELETE | `/accounts/{id}`            | Delete an account          |
| POST   | `/transactions`             | Deposit or withdraw (atomic, overdraft-safe) |
| GET    | `/transactions/{account_id}`| List an account's transactions |

## CI/CD (fully automated)

`.github/workflows/deploy.yml` runs the whole pipeline on every push to `main`
(or manually via "Run workflow"):

```
terraform apply  →  build & push image to ECR  →  kubectl apply (all manifests)
                                                 →  wait for ALB
                                                 →  print the single ingress URL
```

Two jobs: `terraform` provisions/updates infra and exposes its outputs
(ECR repo URL, backend IRSA role ARN) to the `deploy` job, which builds the
image, renders the k8s manifests (substituting those outputs in via `sed`
instead of hand-editing files), applies them, and polls the Ingress until the
ALB hostname shows up — that URL is written to the job summary.

**One-time setup before the first CI run:**

1. **Remote state** (required — GitHub Actions has no local disk between runs):
   ```bash
   aws s3 mb s3://veerabank-terraform-state-517798688687 --region us-east-1
   aws dynamodb create-table \
     --table-name veerabank-terraform-locks \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST --region us-east-1
   ```
   Then uncomment the `backend "s3" {}` block in `terraform/main.tf` and fill
   in the bucket name, and commit that.

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
- Swap `single_nat_gateway = true` for one-per-AZ in `vpc.tf` if you want prod-grade HA.
- Add an ACM cert + uncomment the HTTPS annotations in `k8s/ingress.yaml` for TLS.
