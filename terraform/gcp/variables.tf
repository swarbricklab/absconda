variable "project" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "australia-southeast1"
}

variable "zone" {
  description = "GCP zone for the builder VM"
  type        = string
  default     = "australia-southeast1-a"
}

variable "network" {
  description = "Name of the VPC network"
  type        = string
  default     = "absconda-network"
}

variable "subnet" {
  description = "Name of the subnet"
  type        = string
  default     = "absconda-subnet"
}

variable "builder_sa" {
  description = "Service account email for the builder VM"
  type        = string
}

variable "builder_machine_type" {
  description = "Machine type for the builder VM"
  type        = string
  default     = "e2-standard-4"
}

variable "state_bucket" {
  description = "GCS bucket for Terraform state (without gs:// prefix)"
  type        = string
}

variable "state_prefix" {
  description = "Prefix for Terraform state files in the bucket"
  type        = string
  default     = "absconda-remote"
}

variable "github_token" {
  description = "GitHub personal access token for GHCR authentication"
  type        = string
  sensitive   = true
}

variable "github_username" {
  description = "GitHub username for GHCR authentication"
  type        = string
}
