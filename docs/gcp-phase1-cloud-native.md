# Parqcel GCP Phase 1: Cloud-Native Foundation with CI/CD

This document defines a practical first implementation phase for running Parqcel workloads in GCP with repeatable CI/CD.

## Scope

Phase 1 focuses on:

- Containerized API and worker images.
- Cloud Run service for synchronous control-plane operations.
- Cloud Run Job for asynchronous data workloads.
- Artifact Registry image publishing.
- GitHub Actions deployment pipeline using Workload Identity Federation.
- Cloud Build pipelines for image build/push and deployment.

Phase 1 does not include full web UI replacement, tenant billing, or advanced platform features.

## Target Architecture (Phase 1)

- API: Cloud Run service named `parqcel-api`.
- Worker: Cloud Run Job named `parqcel-worker`.
- Images: Artifact Registry repository `parqcel`.
- Data artifacts: Cloud Storage bucket(s).
- Job trigger: Initially manual/API-triggered; later Pub/Sub or Cloud Tasks.

## Repository Artifacts Added

- `.github/workflows/gcp-deploy.yml`
- `deploy/gcp/cloudbuild-api.yaml`
- `deploy/gcp/cloudbuild-worker.yaml`
- `deploy/gcp/terraform/main.tf`
- `deploy/gcp/terraform/variables.tf`
- `deploy/gcp/terraform/outputs.tf`

## Required GitHub Secrets and Variables

GitHub Actions workflow expects:

- Secrets:
  - `GCP_WIF_PROVIDER`
  - `GCP_WIF_SERVICE_ACCOUNT`
- Variables:
  - `GCP_PROJECT_ID`
  - `GCP_REGION` (example: `us-central1`)
  - `GCP_AR_REPO` (example: `parqcel`)
  - `PARQCEL_API_SERVICE` (example: `parqcel-api`)
  - `PARQCEL_WORKER_JOB` (example: `parqcel-worker`)

## One-Time Platform Bootstrap

1. Create or select a GCP project.
2. Enable services:
   - Cloud Run API
   - Artifact Registry API
   - Cloud Build API
   - IAM API
3. Provision base infra with Terraform in `deploy/gcp/terraform`.
4. Create a Workload Identity Federation provider and bind it to a deployer service account.
5. Add the GitHub secrets/variables listed above.

## Deployment Flow

1. Push to `main`.
2. GitHub Actions authenticates to GCP via Workload Identity Federation.
3. Cloud Build builds and pushes API image.
4. Cloud Build deploys API Cloud Run service.
5. Cloud Build builds and pushes worker image.
6. Cloud Build creates/updates worker Cloud Run Job.

## Recommended Next Steps After Phase 1

1. Add signed URL upload/download flow for dataset artifacts.
2. Add Pub/Sub or Cloud Tasks for queued worker execution.
3. Add structured job state persistence in Cloud SQL or Firestore.
4. Add environment promotion pipeline (dev, stage, prod) with approval gates.
5. Add integration tests that validate deployed endpoints.
