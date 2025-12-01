# Secret Manager secret for GitHub token
resource "google_secret_manager_secret" "github_token" {
  secret_id = "absconda-github-token"
  project   = var.project

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = {
    purpose = "absconda-ghcr-auth"
  }
}

# Secret version containing the actual token value
resource "google_secret_manager_secret_version" "github_token" {
  secret      = google_secret_manager_secret.github_token.id
  secret_data = var.github_token
}

# Grant the builder service account access to read the secret
resource "google_secret_manager_secret_iam_member" "builder_access" {
  secret_id = google_secret_manager_secret.github_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.builder_sa}"
}
