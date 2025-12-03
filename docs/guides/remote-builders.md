# Remote Builders

Build container images on powerful cloud instances instead of locally.

## Why Use Remote Builders?

- **Faster builds**: Leverage multi-core cloud VMs with fast networking
- **Consistent environment**: Same build platform for entire team
- **No local Docker needed**: Build from any machine with `absconda` installed
- **Cost-effective**: Pay only when building, VMs auto-stop when idle

## Prerequisites

- **Google Cloud SDK** (`gcloud` command)
- **GCP Project** with Compute Engine API enabled
- **Terraform** (for infrastructure provisioning)
- **GCP credentials** configured locally

## Quick Setup

### 1. Install Prerequisites

```bash
# Install gcloud SDK
# See: https://cloud.google.com/sdk/docs/install

# Install Terraform
brew install terraform  # macOS
# or: https://www.terraform.io/downloads

# Login to GCP
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 2. Set Environment Variables

Create `.env` in your project:

```bash
export GCP_PROJECT="your-gcp-project-id"
export GCP_REGION="us-central1"
export GCP_ZONE="us-central1-a"
export TF_VAR_gcp_project="$GCP_PROJECT"
export TF_VAR_gcp_region="$GCP_REGION"
export TF_VAR_gcp_zone="$GCP_ZONE"
```

Source it:

```bash
source .env
```

### 3. Provision Infrastructure with Terraform

```bash
cd terraform/gcp
terraform init
terraform plan
terraform apply
```

This creates:
- GCE instance for building
- Firewall rules
- Service account with necessary permissions
- Artifact Registry (optional)

### 4. Configure Remote Builder

Create `absconda-remote.yaml`:

```yaml
builders:
  gcp-builder:
    provider: gcp
    project: your-gcp-project-id
    zone: us-central1-a
    machine_type: n1-standard-8
    disk_size_gb: 100
    
    # Commands to manage the VM
    start_command: "gcloud compute instances start absconda-builder --zone=us-central1-a"
    stop_command: "gcloud compute instances stop absconda-builder --zone=us-central1-a"
    status_command: "gcloud compute instances describe absconda-builder --zone=us-central1-a --format='value(status)'"
    
    # SSH connection
    ssh_user: your-username
    ssh_host: absconda-builder.us-central1-a.c.your-project.internal
```

Or use XDG config at `~/.config/absconda/config.yaml`:

```yaml
remote_builders:
  gcp-builder:
    provider: gcp
    project: your-gcp-project-id
    zone: us-central1-a
    machine_type: n1-standard-8
```

### 5. Initialize SSH Access

```bash
absconda remote init gcp-builder
```

This sets up OS Login and SSH keys.

## Using Remote Builders

### Build Remotely

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/org/myimage \
  --tag latest \
  --remote-builder gcp-builder \
  --push
```

What happens:
1. Absconda starts the GCP instance (if stopped)
2. Uploads Dockerfile and build context via rsync
3. Runs `docker build` on remote instance
4. Pushes image to registry
5. Optionally stops instance (with `--remote-off`)

### Check Remote Status

```bash
absconda remote status gcp-builder
```

### Manually Control Remote

```bash
# Start instance
absconda remote start gcp-builder

# Stop instance
absconda remote stop gcp-builder

# List all remote builders
absconda remote list
```

## Configuration Details

### Full Remote Builder Config

```yaml
builders:
  gcp-builder:
    provider: gcp
    project: my-gcp-project
    zone: us-central1-a
    machine_type: n1-standard-8      # 8 vCPUs, 30GB RAM
    disk_size_gb: 100                # Boot disk size
    
    # Optional: Use specific image
    image_family: cos-stable         # Container-Optimized OS
    image_project: cos-cloud
    
    # SSH settings
    ssh_user: myusername
    ssh_host: internal-ip-or-hostname
    ssh_port: 22
    
    # Commands (auto-detected if using gcloud)
    start_command: "gcloud compute instances start ..."
    stop_command: "gcloud compute instances stop ..."
    status_command: "gcloud compute instances describe ..."
    
    # Build context upload
    upload_command: "rsync -avz --delete {context}/ {ssh_user}@{ssh_host}:{remote_path}/"
```

### Machine Types

Choose based on your needs:

| Machine Type | vCPUs | Memory | Use Case |
|--------------|-------|--------|----------|
| n1-standard-4 | 4 | 15 GB | Small builds |
| n1-standard-8 | 8 | 30 GB | **Recommended** |
| n1-standard-16 | 16 | 60 GB | Large builds |
| n1-highcpu-16 | 16 | 14.4 GB | CPU-intensive |
| n1-highmem-8 | 8 | 52 GB | Memory-intensive |

Pricing: ~$0.05-0.70/hour depending on type.

## Remote Build Options

### Wait Timeout

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/org/myimage \
  --remote-builder gcp-builder \
  --remote-wait 1800 \
  --push
```

Waits up to 1800 seconds (30 min) if builder is busy.

### Auto-shutdown After Build

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/org/myimage \
  --remote-builder gcp-builder \
  --remote-off \
  --push
```

Stops the VM after successful build to save costs.

### Custom Config Path

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/org/myimage \
  --remote-builder gcp-builder \
  --remote-config ./my-remote-config.yaml \
  --push
```

## Terraform Infrastructure

The provided Terraform configuration creates:

### Compute Instance

```hcl
resource "google_compute_instance" "builder" {
  name         = "absconda-builder"
  machine_type = var.machine_type
  zone         = var.zone

  boot_disk {
    initialize_params {
      size  = var.disk_size_gb
      image = "cos-cloud/cos-stable"
    }
  }

  # Docker pre-installed in Container-Optimized OS
}
```

### Service Account

With permissions for:
- Compute Engine (manage self)
- Artifact Registry (push images)
- Cloud Storage (optional, for build caches)

### Firewall Rules

- SSH access (port 22)
- Optional: Internal Docker registry

### Optional: Artifact Registry

```hcl
resource "google_artifact_registry_repository" "images" {
  repository_id = "absconda-images"
  format        = "DOCKER"
}
```

## Cost Optimization

### 1. Use Preemptible Instances

```yaml
builders:
  gcp-builder:
    machine_type: n1-standard-8
    preemptible: true  # ~80% cost reduction
```

**Trade-off**: Can be terminated by GCP with 30s notice.

### 2. Auto-stop After Builds

Always use `--remote-off`:

```bash
absconda build \
  --file environment.yaml \
  --remote-builder gcp-builder \
  --remote-off \
  --push
```

### 3. Right-size Machine Type

Start with `n1-standard-4`, scale up if needed.

### 4. Use Spot Pricing

Enable in Terraform:

```hcl
resource "google_compute_instance" "builder" {
  scheduling {
    preemptible       = true
    automatic_restart = false
  }
}
```

## Troubleshooting

### SSH Connection Fails

```bash
# Check instance is running
gcloud compute instances list

# Test SSH manually
gcloud compute ssh absconda-builder --zone=us-central1-a

# Re-initialize
absconda remote init gcp-builder
```

### Build Context Too Large

```bash
# Check context size
du -sh .

# Add .dockerignore
echo ".git" >> .dockerignore
echo ".venv" >> .dockerignore
echo "__pycache__" >> .dockerignore
```

### Instance Won't Start

```bash
# Check quota
gcloud compute project-info describe --project=your-project

# Check billing
gcloud beta billing projects describe your-project
```

## Next Steps

- [Building Images](building-images.md) - Using remote builders
- [CI/CD Integration](../how-to/ci-cd-integration.md) - Automate builds
- [Architecture: Remote Execution](../architecture/remote-execution.md) - How it works
