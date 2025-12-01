# Absconda Remote Builder - GCP Terraform Module

This Terraform module provisions a remote builder VM for Absconda on Google Cloud Platform.

## What It Creates

- **VPC Network & Subnet**: Isolated network (`absconda-network`) with private subnet
- **Cloud NAT**: Enables internet access without external IPs (secure egress)
- **Firewall Rules**: SSH via Identity-Aware Proxy (IAP), controlled egress
- **Service Account**: Dedicated identity with minimal permissions (logging, monitoring, storage)
- **Compute Instance**: Container-Optimized OS VM with Docker pre-configured

## Prerequisites

1. **GCP Project**: Active GCP project with billing enabled
2. **Authentication**: Application Default Credentials configured
   ```bash
   gcloud auth application-default login
   ```
3. **APIs Enabled**:
   ```bash
   gcloud services enable compute.googleapis.com \
     iap.googleapis.com \
     logging.googleapis.com \
     monitoring.googleapis.com
   ```
4. **State Bucket**: GCS bucket for Terraform state
   ```bash
   gsutil mb -p ctp-archive -l australia-southeast1 gs://absconda-tfstate
   gsutil versioning set on gs://absconda-tfstate
   ```

## Configuration

The module reads variables from your environment (loaded via `.env` and `direnv`):

```bash
# Required
TF_VAR_project=ctp-archive
TF_VAR_region=australia-southeast1
TF_VAR_zone=australia-southeast1-a
TF_VAR_builder_sa=absconda-builder@ctp-archive.iam.gserviceaccount.com
TF_VAR_state_bucket=absconda-tfstate

# Optional (uses defaults if not set)
TF_VAR_network=absconda-network
TF_VAR_subnet=absconda-subnet
TF_VAR_builder_machine_type=e2-standard-4
TF_VAR_state_prefix=absconda-remote
```

## Usage

### Initialize Terraform

```bash
cd terraform/gcp
terraform init \
  -backend-config="bucket=${TF_VAR_state_bucket}" \
  -backend-config="prefix=${TF_VAR_state_prefix}"
```

### Plan and Apply

```bash
# Review changes
terraform plan

# Apply changes
terraform apply
```

### Check Outputs

```bash
terraform output
# Shows: instance name, zone, IP, SSH command, etc.
```

## Connecting to the Builder

Use Identity-Aware Proxy (IAP) for secure SSH without public IPs:

```bash
# Get the SSH command from Terraform output
terraform output -raw ssh_command

# Or manually:
gcloud compute ssh absconda-builder \
  --zone=australia-southeast1-a \
  --tunnel-through-iap
```

## Integration with Absconda CLI

Update `examples/remote-builder.yaml`:

```yaml
remote_builders:
  gcp-builder:
    host: absconda-builder
    user: <your-username>  # Or use OS Login
    workspace: /var/lib/absconda
    ssh_key_path: ~/.ssh/google_compute_engine
    provision_command: |
      cd terraform/gcp && \
      terraform init -backend-config="bucket=${TF_VAR_state_bucket}" -backend-config="prefix=${TF_VAR_state_prefix}" && \
      terraform apply -auto-approve
    start_command: gcloud compute instances start absconda-builder --zone=${GCP_ZONE}
    stop_command: gcloud compute instances stop absconda-builder --zone=${GCP_ZONE}
    health_command: gcloud compute instances describe absconda-builder --zone=${GCP_ZONE} --format="value(status)"
```

Then use:

```bash
# Provision the builder
absconda remote provision gcp-builder

# Check status
absconda remote status gcp-builder

# Start/stop (cost savings when not in use)
absconda remote start gcp-builder
absconda remote stop gcp-builder
```

## Cost Optimization

- **Machine Type**: Default `e2-standard-4` (~$120/month if running 24/7)
- **Stop When Idle**: Use `absconda remote stop` to save ~90% of compute costs
- **Preemptible/Spot**: Modify `compute.tf` to use spot instances for ~70% savings
- **Disk**: 50GB standard persistent disk (~$2/month)
- **Network**: Cloud NAT egress charges apply ($0.045/GB)

**Example**: Running 8 hours/day = ~$40/month instead of $120/month

## Customization

### Change Machine Type

```bash
export TF_VAR_builder_machine_type=e2-standard-8  # More CPU/memory
terraform apply
```

### Add External IP (Not Recommended)

Uncomment in `compute.tf`:
```hcl
network_interface {
  access_config {}  # Assigns external IP
}
```

### Use Preemptible VM

Add to `google_compute_instance.builder` in `compute.tf`:
```hcl
scheduling {
  preemptible       = true
  automatic_restart = false
}
```

## Troubleshooting

### SSH Connection Issues

```bash
# Check IAP tunnel
gcloud compute ssh absconda-builder --zone=australia-southeast1-a --tunnel-through-iap --dry-run

# Verify firewall rules
gcloud compute firewall-rules list --filter="name:iap"

# Check VM status
gcloud compute instances describe absconda-builder --zone=australia-southeast1-a
```

### Startup Script Logs

```bash
# SSH into the VM
gcloud compute ssh absconda-builder --zone=australia-southeast1-a --tunnel-through-iap

# Check startup logs
sudo journalctl -u google-startup-scripts.service
cat /var/log/startup-script.log
```

### Docker Issues

```bash
# On the VM
sudo systemctl status docker
sudo docker ps
sudo docker info
```

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

This will remove:
- Compute instance
- Service account
- Firewall rules
- NAT gateway and router
- Subnet and VPC network

**Note**: The Terraform state bucket must be deleted manually if no longer needed.

## Security Notes

- **No External IP**: VM uses Cloud NAT for egress, reducing attack surface
- **IAP for SSH**: Identity-Aware Proxy provides zero-trust access without VPN
- **OS Login**: Enabled by default for centralized SSH key management
- **Minimal Permissions**: Service account has only required IAM roles
- **Private Subnet**: VM is not directly accessible from the internet

For production use, consider:
- VPC Service Controls
- Private Google Access for API calls
- Cloud Armor for DDoS protection
- Shielded VMs for additional integrity protection
