terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  required_services = [
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "iam.googleapis.com",
    "serviceusage.googleapis.com",
  ]
}

resource "google_project_service" "required" {
  for_each           = toset(local.required_services)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "parqcel" {
  location      = var.region
  repository_id = var.artifact_registry_repo
  description   = "Parqcel container images"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "github_deployer" {
  account_id   = "parqcel-gh-deployer"
  display_name = "Parqcel GitHub deployer"
}

resource "google_project_iam_member" "github_deployer_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "github_deployer_build_editor" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "github_deployer_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "github_deployer_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_service_account" "runtime" {
  account_id   = "parqcel-runtime"
  display_name = "Parqcel runtime"
}

resource "google_project_iam_member" "runtime_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}
