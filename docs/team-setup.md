# Team Member Setup Guide

This guide is for Swarbrick Lab team members who want to use Absconda with the shared GCP infrastructure.

## Prerequisites

- Access to the `ctp-archive` GCP project
- Google Cloud SDK (`gcloud`) installed
- SSH access configured via OS Login

## Quick Start

### 1. Install Absconda (NCI or Local)

**On NCI** (recommended for team members):
```bash
module load absconda
```

**Local installation** (for development):
```bash
git clone git@github.com:swarbricklab/absconda.git
cd absconda
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Authenticate with GCP

```bash
gcloud auth login
gcloud auth application-default login
```

That's it! The system-wide config at `/etc/xdg/absconda/config.yaml` provides all the remote builder settings.

## Usage

### Building Images

Build a local image:
```bash
absconda build --file env.yaml --repository ghcr.io/swarbricklab/my-project --tag v1
```

Build on the remote GCP builder:
```bash
absconda build --file env.yaml --repository ghcr.io/swarbricklab/my-project --tag v1 --remote-builder gcp-builder --push
```

The `--push` flag automatically pushes to GitHub Container Registry using org-level credentials.

### Remote Builder Commands

Check builder status:
```bash
absconda remote status gcp-builder
```

List available builders:
```bash
absconda remote list
```

Start/stop the builder manually:
```bash
absconda remote start gcp-builder
absconda remote stop gcp-builder
```

**Note**: The builder automatically starts when you use `--remote-builder` and stops after the build completes (when using `--remote-off`).

## Configuration

### System-Wide Config (Read-Only)

The system-wide config at `/etc/xdg/absconda/config.yaml` contains:
- GCP project, region, zone
- Remote builder definitions
- Default policy profiles

You don't need to modify this file. It's managed by the infrastructure team.

### User Config (Optional)

Create `~/.config/absconda/config.yaml` to override settings:

```yaml
# Example: Use a different default profile
default_profile: strict

# Example: Add a personal remote builder
remote_builders:
  my-builder:
    host: my-builder-vm
    workspace: /home/me/builds
```

### Environment Variables

You can override GCP settings with environment variables:
```bash
export GCP_PROJECT=ctp-archive
export GCP_REGION=australia-southeast1
export GCP_ZONE=australia-southeast1-a
```

But with `gcloud auth login`, you typically don't need to set these.

## Pushing to GitHub Container Registry

Images are automatically pushed to `ghcr.io/swarbricklab/*` using org-level credentials stored in GCP Secret Manager.

You don't need to configure Docker authentication - it's handled automatically by the remote builder.

## Troubleshooting

### "Builder gcp-builder is unreachable"

Initialize OS Login access:
```bash
absconda remote init gcp-builder
```

This runs the initial `gcloud compute ssh` command to set up your OS Login user.

### "Permission denied" errors

Make sure you're authenticated:
```bash
gcloud auth login
gcloud config set project ctp-archive
```

Check you have the necessary IAM roles in the GCP project.

### "Remote build failed"

Check the builder status:
```bash
absconda remote status gcp-builder
```

If it's stuck, you may need to manually stop and restart:
```bash
absconda remote stop gcp-builder
absconda remote start gcp-builder
```

## Cost Awareness

The remote builder VM:
- **Machine type**: e2-standard-4 (4 vCPUs, 16 GB RAM)
- **Cost**: ~$0.13/hour when running
- **Auto-stops**: After each build (with `--remote-off`)

Always use `--remote-off` unless you're doing multiple builds in sequence.

## Support

For issues with:
- **Absconda itself**: File an issue at https://github.com/swarbricklab/absconda/issues
- **GCP access**: Contact your GCP project admin
- **NCI module**: Contact the NCI support team

## Advanced: Creating Your Own Builder

If you want to use Absconda with your own GCP project:

1. Copy `terraform/gcp/` to your project
2. Update `terraform/gcp/variables.tf` with your project details
3. Create your own `.env` file (see `.env.example`)
4. Run `terraform apply`
5. Create `~/.config/absconda/config.yaml` with your builder definition

See the main README for full documentation.
