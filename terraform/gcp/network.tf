# VPC Network
resource "google_compute_network" "absconda" {
  name                    = var.network
  auto_create_subnetworks = false
  description             = "Network for Absconda remote builders"
}

# Subnet
resource "google_compute_subnetwork" "absconda" {
  name          = var.subnet
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.absconda.id
  description   = "Subnet for Absconda remote builders in ${var.region}"

  # Enable private Google access for pulling container images
  private_ip_google_access = true
}

# Firewall: Allow SSH from IAP (Identity-Aware Proxy)
resource "google_compute_firewall" "allow_iap_ssh" {
  name    = "${var.network}-allow-iap-ssh"
  network = google_compute_network.absconda.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # IAP's IP range for SSH
  source_ranges = ["35.235.240.0/20"]
  
  target_tags = ["absconda-builder"]
  description = "Allow SSH via Identity-Aware Proxy"
}

# Firewall: Allow egress for package downloads and container registry
resource "google_compute_firewall" "allow_egress" {
  name      = "${var.network}-allow-egress"
  network   = google_compute_network.absconda.name
  direction = "EGRESS"

  allow {
    protocol = "tcp"
  }

  allow {
    protocol = "udp"
  }

  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["absconda-builder"]
  description        = "Allow all egress for builder VM"
}

# Cloud Router for NAT (required for internet access without external IP)
resource "google_compute_router" "absconda" {
  name    = "${var.network}-router"
  region  = var.region
  network = google_compute_network.absconda.id
}

# Cloud NAT for outbound internet access
resource "google_compute_router_nat" "absconda" {
  name   = "${var.network}-nat"
  router = google_compute_router.absconda.name
  region = var.region

  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = false
    filter = "ERRORS_ONLY"
  }
}
