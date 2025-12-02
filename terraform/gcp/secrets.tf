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

resource "google_secret_manager_secret" "github_username" {
  secret_id = "absconda-github-username"
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

resource "google_secret_manager_secret_version" "github_username" {
  secret      = google_secret_manager_secret.github_username.id
  secret_data = var.github_username
}

# Grant the builder service account access to read the secret
resource "google_secret_manager_secret_iam_member" "builder_access" {
  secret_id = google_secret_manager_secret.github_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.builder_sa}"
}

resource "google_secret_manager_secret_iam_member" "builder_username_access" {
  secret_id = google_secret_manager_secret.github_username.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.builder_sa}"
}
