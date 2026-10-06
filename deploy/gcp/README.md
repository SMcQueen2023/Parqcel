# GCP Deployment Assets

This folder contains Phase 1 cloud-native deployment assets for Parqcel.

## Contents

- `cloudbuild-api.yaml`: Builds and deploys the Cloud Run API service.
- `cloudbuild-worker.yaml`: Builds and upserts the Cloud Run worker job.
- `docker/Dockerfile.api`: Runtime image for the FastAPI control-plane.
- `docker/Dockerfile.worker`: Runtime image for asynchronous processing jobs.
- `terraform/`: Base infrastructure provisioning.

## Prerequisites

- GCP project with billing enabled.
- `gcloud` authenticated to the target project.
- Terraform 1.5+.

## Bootstrap Infrastructure

From `deploy/gcp/terraform`:

```bash
terraform init
terraform apply -var="project_id=YOUR_PROJECT_ID" -var="region=us-central1"
```

## Manual Build/Deploy API

```bash
gcloud builds submit \
  --config deploy/gcp/cloudbuild-api.yaml \
  --substitutions _REGION=us-central1,_REPOSITORY=parqcel,_SERVICE=parqcel-api,_IMAGE_TAG=dev
```

## Manual Build/Deploy Worker Job

```bash
gcloud builds submit \
  --config deploy/gcp/cloudbuild-worker.yaml \
  --substitutions _REGION=us-central1,_REPOSITORY=parqcel,_JOB=parqcel-worker,_IMAGE_TAG=dev
```
