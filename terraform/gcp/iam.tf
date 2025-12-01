# Service Account for Builder VM
resource "google_service_account" "builder" {
  account_id   = split("@", var.builder_sa)[0]
  display_name = "Absconda Remote Builder"
  description  = "Service account for Absconda remote builder VMs"
}

# Grant the service account necessary permissions
# Adjust these based on your specific needs

# Storage Admin for GCS bucket access (if using GCS for artifacts)
resource "google_project_iam_member" "builder_storage" {
  project = var.project
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

# Log Writer for Cloud Logging
resource "google_project_iam_member" "builder_logging" {
  project = var.project
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

# Monitoring Metric Writer for Cloud Monitoring
resource "google_project_iam_member" "builder_monitoring" {
  project = var.project
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

# Optional: Artifact Registry Reader (if using Artifact Registry for base images)
# Uncomment if needed
# resource "google_project_iam_member" "builder_artifact_registry" {
#   project = var.project
#   role    = "roles/artifactregistry.reader"
#   member  = "serviceAccount:${google_service_account.builder.email}"
# }
