output "artifact_registry_repo" {
  description = "Artifact Registry repository resource name"
  value       = google_artifact_registry_repository.parqcel.name
}

output "github_deployer_service_account" {
  description = "Service account for GitHub deployments"
  value       = google_service_account.github_deployer.email
}

output "runtime_service_account" {
  description = "Runtime service account for Cloud Run service/job"
  value       = google_service_account.runtime.email
}
