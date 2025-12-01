terraform {
  required_version = ">= 1.5"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    # Bucket and prefix configured via -backend-config or environment variables
    # Example: terraform init -backend-config="bucket=${TF_VAR_state_bucket}"
  }
}

provider "google" {
  project = var.project
  region  = var.region
}
