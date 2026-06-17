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

# ---------------------------------------------------------------------------
# Builder users (humans driving `absconda ... --remote-builder`)
#
# Absconda shells out to the `gcloud` CLI under the invoking user's identity to
# start/stop the VM and to tunnel over IAP for the build, so each user needs
# these roles in addition to being authenticated. The builder VM's own service
# account (above) is a separate identity and does not cover this.
# ---------------------------------------------------------------------------

locals {
  # Project-level roles every builder user needs.
  builder_user_project_roles = [
    "roles/compute.instanceAdmin.v1",   # start/stop/describe the builder VM
    "roles/iap.tunnelResourceAccessor", # SSH/SCP through the IAP tunnel
    "roles/compute.osAdminLogin",       # OS Login WITH sudo (build runs `sudo docker`)
  ]

  # Cartesian product of users x roles, keyed for for_each.
  builder_user_bindings = {
    for pair in setproduct(var.builder_users, local.builder_user_project_roles) :
    "${pair[0]}|${pair[1]}" => {
      member = pair[0]
      role   = pair[1]
    }
  }
}

resource "google_project_iam_member" "builder_users" {
  for_each = local.builder_user_bindings
  project  = var.project
  role     = each.value.role
  member   = each.value.member
}

# Starting an instance that has a service account attached requires
# iam.serviceAccounts.actAs on that service account.
resource "google_service_account_iam_member" "builder_users_act_as" {
  for_each           = toset(var.builder_users)
  service_account_id = google_service_account.builder.name
  role               = "roles/iam.serviceAccountUser"
  member             = each.value
}
