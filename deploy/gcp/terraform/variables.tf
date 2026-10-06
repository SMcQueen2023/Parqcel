variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Primary GCP region"
  type        = string
  default     = "us-central1"
}

variable "artifact_registry_repo" {
  description = "Artifact Registry Docker repository name"
  type        = string
  default     = "parqcel"
}
