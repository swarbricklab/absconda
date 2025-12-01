output "builder_instance_name" {
  description = "Name of the builder VM instance"
  value       = google_compute_instance.builder.name
}

output "builder_instance_zone" {
  description = "Zone of the builder VM instance"
  value       = google_compute_instance.builder.zone
}

output "builder_internal_ip" {
  description = "Internal IP address of the builder VM"
  value       = google_compute_instance.builder.network_interface[0].network_ip
}

output "builder_service_account" {
  description = "Service account email used by the builder VM"
  value       = google_service_account.builder.email
}

output "network_name" {
  description = "Name of the VPC network"
  value       = google_compute_network.absconda.name
}

output "subnet_name" {
  description = "Name of the subnet"
  value       = google_compute_subnetwork.absconda.name
}

output "ssh_command" {
  description = "Command to SSH into the builder via IAP"
  value       = "gcloud compute ssh ${google_compute_instance.builder.name} --zone=${google_compute_instance.builder.zone} --tunnel-through-iap"
}
