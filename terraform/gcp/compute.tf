# Data source for the latest Ubuntu image
data "google_compute_image" "ubuntu" {
  family  = "ubuntu-2204-lts"
  project = "ubuntu-os-cloud"
}

# Compute Engine instance for the builder
resource "google_compute_instance" "builder" {
  name         = "absconda-builder"
  machine_type = var.builder_machine_type
  zone         = var.zone

  tags = ["absconda-builder"]

  boot_disk {
    initialize_params {
      image = data.google_compute_image.ubuntu.self_link
      size  = 100 # GB - larger disk for Docker images/layers
      type  = "pd-standard"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.absconda.id
    
    # No external IP - use Cloud NAT for internet access
    # If you need direct external access, uncomment:
    # access_config {}
  }

  service_account {
    email  = google_service_account.builder.email
    scopes = ["cloud-platform"]
  }

  # Startup script to install Docker and configure the builder
  metadata_startup_script = <<-EOF
    #!/bin/bash
    set -e
    
    # Log all output
    exec > >(tee -a /var/log/startup-script.log)
    exec 2>&1
    
    echo "Starting Absconda builder setup..."
    
    # Install Docker on Ubuntu
    echo "Installing Docker..."
    apt-get update
    apt-get install -y ca-certificates curl gnupg
    
    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Add Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$${VERSION_CODENAME}") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker Engine with Buildx plugin
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Verify installations
    docker --version
    docker buildx version
    
    # Configure Docker daemon for better build performance
    cat > /etc/docker/daemon.json <<DOCKEREOF
    {
      "log-driver": "json-file",
      "log-opts": {
        "max-size": "10m",
        "max-file": "3"
      },
      "storage-driver": "overlay2"
    }
DOCKEREOF
    
    systemctl restart docker
    
    # Fetch GitHub credentials from Secret Manager
    echo "Configuring GitHub Container Registry authentication..."
    GITHUB_TOKEN=$(gcloud secrets versions access latest --secret=absconda-github-token --project=${var.project})
    GITHUB_USERNAME=$(gcloud secrets versions access latest --secret=absconda-github-username --project=${var.project})
    
    # Create Docker config directory for root
    mkdir -p /root/.docker
    
    # Login to GHCR (credentials stored in /root/.docker/config.json)
    echo "$${GITHUB_TOKEN}" | docker login ghcr.io -u "$${GITHUB_USERNAME}" --password-stdin
    
    # Create working directory (ownership will be set by provisioner after OS Login)
    mkdir -p /var/lib/absconda
    chmod 755 /var/lib/absconda
    
    echo "Absconda builder Docker setup complete"
    echo "OS Login user configuration will be handled by Terraform provisioner"
    
    # Signal that the builder is ready
    touch /var/lib/absconda/ready
  EOF

  metadata = {
    enable-oslogin = "TRUE"
  }

  # Allow the instance to be stopped for updates
  allow_stopping_for_update = true

  # Provision OS Login SSH access and finalize configuration
  # This establishes the OS Login user and then sets up permissions
  provisioner "local-exec" {
    when    = create
    command = <<-EOT
      echo "Setting up SSH access via OS Login..."
      echo "Waiting for instance to boot..."
      sleep 45
      
      # Initial SSH connection to establish OS Login user
      gcloud compute ssh ${self.name} \
        --zone=${self.zone} \
        --tunnel-through-iap \
        --project=${var.project} \
        --command="echo 'SSH access configured successfully.'" || \
        { echo "Warning: Initial SSH setup failed."; exit 1; }
      
      # Wait for startup script to complete
      echo "Waiting for startup script to complete..."
      gcloud compute ssh ${self.name} \
        --zone=${self.zone} \
        --tunnel-through-iap \
        --project=${var.project} \
        --command="while [ ! -f /var/lib/absconda/ready ]; do echo 'Waiting for startup script...'; sleep 5; done; echo 'Startup script complete.'" || \
        { echo "Warning: Startup script check failed."; exit 1; }
      
      # Now configure permissions for the OS Login user
      echo "Configuring permissions for OS Login user..."
      gcloud compute ssh ${self.name} \
        --zone=${self.zone} \
        --tunnel-through-iap \
        --project=${var.project} \
        --command="sudo chown \$(whoami):\$(whoami) /var/lib/absconda && sudo usermod -aG docker \$(whoami) && echo 'Permissions configured for '\$(whoami)" || \
        echo "Warning: Permission configuration failed."
      
      echo "Absconda builder provisioning complete."
    EOT
  }

  labels = {
    environment = "absconda"
    purpose     = "remote-builder"
  }
}
