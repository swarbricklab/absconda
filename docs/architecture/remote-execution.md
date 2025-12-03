# Architecture: Remote Execution

Design and implementation of remote build infrastructure.

## Overview

Remote execution enables building containers on cloud infrastructure, providing:
- **Performance**: More powerful instances than local machines
- **Bandwidth**: Faster upload to registries (cloud → registry)
- **Cost**: Pay only for build time
- **Portability**: Same workflow across different machines

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Local Machine                          │
│                                                               │
│  ┌──────────────┐                                            │
│  │   User CLI   │                                            │
│  └──────┬───────┘                                            │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────┐                                            │
│  │ Remote       │                                            │
│  │ Manager      │                                            │
│  └──────┬───────┘                                            │
│         │                                                     │
│         ├─── provision ──► Terraform                          │
│         ├─── start/stop ──► Cloud API                        │
│         └─── build ──────► SSH                               │
└──────────────────────────────────────────────────────────────┘
                          │
                       SSH │
                          │
┌──────────────────────────▼───────────────────────────────────┐
│                     Remote Builder                            │
│                    (GCP VM Instance)                          │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Docker Engine                                        │   │
│  │                                                       │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐             │   │
│  │  │ Build 1 │  │ Build 2 │  │ Build 3 │             │   │
│  │  └─────────┘  └─────────┘  └─────────┘             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Build Cache                                          │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
                          │
                          │ Push
                          ▼
                 ┌────────────────┐
                 │  Container     │
                 │  Registry      │
                 │  (ghcr.io)     │
                 └────────────────┘
```

## Components

### 1. Remote Manager

**Location**: `src/absconda/remote.py`

**Responsibilities**:
- Load remote configuration
- Track remote builder state
- Lifecycle management (provision, start, stop, destroy)
- Execute builds remotely
- Handle errors and retries

**Key methods**:

```python
class RemoteManager:
    def list_builders(self) -> List[RemoteBuilder]:
        """List all configured remote builders."""
        pass
    
    def status(self, name: str) -> BuilderStatus:
        """Check status of a remote builder."""
        pass
    
    def provision(self, name: str):
        """Provision new remote builder infrastructure."""
        pass
    
    def start(self, name: str):
        """Start a stopped remote builder."""
        pass
    
    def stop(self, name: str):
        """Stop a running remote builder."""
        pass
    
    def destroy(self, name: str):
        """Destroy remote builder infrastructure."""
        pass
    
    def build(self, name: str, context: BuildContext) -> BuildResult:
        """Execute build on remote builder."""
        pass
```

### 2. Configuration System

**Location**: `absconda-remote.yaml`

**Structure**:

```yaml
builders:
  gcp-builder:
    provider: gcp
    project: my-gcp-project
    region: us-central1
    zone: us-central1-a
    machine_type: n1-standard-8
    disk_size: 100
    terraform_dir: terraform/gcp
    
  aws-builder:
    provider: aws
    region: us-east-1
    instance_type: t3.xlarge
    terraform_dir: terraform/aws

defaults:
  auto_start: false
  auto_stop: true
  timeout: 3600
```

**Validation**:

```python
from pydantic import BaseModel

class RemoteBuilderConfig(BaseModel):
    provider: str
    project: Optional[str]
    region: str
    zone: Optional[str]
    machine_type: str
    terraform_dir: Path
    
    # Validation
    @validator('provider')
    def validate_provider(cls, v):
        if v not in ['gcp', 'aws', 'azure']:
            raise ValueError(f"Unknown provider: {v}")
        return v
```

### 3. State Management

**Location**: `~/.local/share/absconda/remote-state.json`

**Purpose**: Track provisioned builders and their state

**Structure**:

```json
{
  "builders": {
    "gcp-builder": {
      "provider": "gcp",
      "status": "running",
      "ip_address": "34.123.45.67",
      "provisioned_at": "2024-12-01T10:30:00Z",
      "last_used": "2024-12-03T15:45:00Z",
      "builds_count": 42
    }
  },
  "version": "1.0"
}
```

**Operations**:

```python
class StateManager:
    def save_builder_state(self, name: str, state: BuilderState):
        """Save builder state to disk."""
        
    def load_builder_state(self, name: str) -> BuilderState:
        """Load builder state from disk."""
        
    def delete_builder_state(self, name: str):
        """Remove builder state."""
```

### 4. Terraform Integration

**Location**: `terraform/gcp/`, `terraform/aws/`

**Purpose**: Declarative infrastructure management

**GCP Example** (`terraform/gcp/main.tf`):

```hcl
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project
  region  = var.region
}

resource "google_compute_instance" "builder" {
  name         = "absconda-builder"
  machine_type = var.machine_type
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.disk_size
    }
  }

  network_interface {
    network = "default"
    access_config {}  # Ephemeral external IP
  }

  metadata_startup_script = file("${path.module}/startup.sh")

  tags = ["absconda-builder"]
}

output "instance_ip" {
  value = google_compute_instance.builder.network_interface[0].access_config[0].nat_ip
}
```

**Startup script** (`terraform/gcp/startup.sh`):

```bash
#!/bin/bash
set -e

# Update system
apt-get update
apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/download/v2.23.0/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Install Python and Absconda
apt-get install -y python3-pip
pip3 install absconda

# Configure Docker
cat > /etc/docker/daemon.json <<EOF
{
  "features": {
    "buildkit": true
  },
  "max-concurrent-downloads": 10,
  "max-concurrent-uploads": 10
}
EOF

systemctl restart docker

# Ready
touch /var/lib/cloud/instance/boot-finished
```

## Execution Flow

### Build Workflow

```
1. User: absconda build --remote-builder gcp-builder
              │
              ▼
2. Load config: absconda-remote.yaml
              │
              ▼
3. Check state: Is builder running?
              │
              ├─► No: Start builder
              │       │
              │       └─► Wait for ready
              │
              ▼
4. Prepare context:
   - Generate Dockerfile
   - Collect build context
              │
              ▼
5. Transfer: rsync to remote
   - Dockerfile
   - environment.yaml
   - Additional files
              │
              ▼
6. Execute: SSH docker build
              │
              ▼
7. Push: docker push to registry
              │
              ▼
8. Cleanup (optional): Remove build context
              │
              ▼
9. Stop (optional): Stop builder if auto_stop
```

### Implementation

```python
class RemoteBuilder:
    def build(self, env_file: Path, repo: str, tags: List[str]) -> BuildResult:
        """Execute remote build."""
        
        # 1. Ensure builder is running
        if self.status() != 'running':
            self.start()
            self.wait_for_ready()
        
        # 2. Generate Dockerfile locally
        dockerfile = self.generate_dockerfile(env_file)
        
        # 3. Create build context
        context_dir = self.prepare_context(env_file, dockerfile)
        
        # 4. Transfer to remote
        remote_path = self.transfer_context(context_dir)
        
        # 5. Execute build
        result = self.ssh_execute([
            'docker', 'build',
            '-f', f'{remote_path}/Dockerfile',
            '-t', f'{repo}:{tags[0]}',
            remote_path
        ])
        
        if result.returncode != 0:
            raise BuildError(f"Remote build failed: {result.stderr}")
        
        # 6. Push to registry
        for tag in tags:
            self.ssh_execute(['docker', 'push', f'{repo}:{tag}'])
        
        # 7. Cleanup
        if self.config.cleanup:
            self.ssh_execute(['rm', '-rf', remote_path])
        
        # 8. Auto-stop
        if self.config.auto_stop:
            self.stop()
        
        return BuildResult(success=True, image=f'{repo}:{tags[0]}')
```

## SSH Communication

### Authentication

**OS Login (GCP)**:

```python
def init_ssh_keys(self):
    """Initialize SSH keys for OS Login."""
    
    # Generate SSH key if needed
    key_path = Path.home() / '.ssh' / 'id_rsa'
    if not key_path.exists():
        subprocess.run(['ssh-keygen', '-t', 'rsa', '-N', '', '-f', str(key_path)])
    
    # Add to OS Login
    subprocess.run([
        'gcloud', 'compute', 'os-login', 'ssh-keys', 'add',
        '--key-file', f'{key_path}.pub'
    ])
```

**SSH Config**:

```bash
# ~/.ssh/config
Host absconda-builder-*
    User j_reeves_garvan_org_au
    IdentityFile ~/.ssh/id_rsa
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

### File Transfer

**rsync for efficiency**:

```python
def transfer_context(self, local_dir: Path, remote_dir: str) -> None:
    """Transfer build context to remote."""
    
    # Exclude unnecessary files
    excludes = [
        '--exclude', '.git',
        '--exclude', '.venv',
        '--exclude', '__pycache__',
        '--exclude', '*.pyc',
    ]
    
    cmd = [
        'rsync',
        '-avz',
        '--delete',
        *excludes,
        f'{local_dir}/',
        f'{self.ssh_user}@{self.ip}:{remote_dir}/'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TransferError(f"rsync failed: {result.stderr}")
```

**SSH execution**:

```python
def ssh_execute(self, cmd: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    """Execute command on remote via SSH."""
    
    ssh_cmd = [
        'ssh',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        f'{self.ssh_user}@{self.ip}',
        ' '.join(cmd)
    ]
    
    if capture_output:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True)
    else:
        # Stream output
        result = subprocess.run(ssh_cmd)
    
    return result
```

## Lifecycle Management

### Provision

```python
def provision(self) -> None:
    """Provision remote builder infrastructure."""
    
    # 1. Validate configuration
    self.validate_config()
    
    # 2. Check if already provisioned
    if self.is_provisioned():
        raise ProvisionError(f"Builder {self.name} already provisioned")
    
    # 3. Run Terraform
    terraform_dir = self.config.terraform_dir
    env = self.get_terraform_env()
    
    subprocess.run(
        ['terraform', 'init'],
        cwd=terraform_dir,
        env=env,
        check=True
    )
    
    subprocess.run(
        ['terraform', 'apply', '-auto-approve'],
        cwd=terraform_dir,
        env=env,
        check=True
    )
    
    # 4. Get outputs
    result = subprocess.run(
        ['terraform', 'output', '-json'],
        cwd=terraform_dir,
        env=env,
        capture_output=True,
        text=True,
        check=True
    )
    
    outputs = json.loads(result.stdout)
    
    # 5. Save state
    self.state.ip_address = outputs['instance_ip']['value']
    self.state.status = 'running'
    self.state.provisioned_at = datetime.now()
    self.save_state()
    
    # 6. Wait for ready
    self.wait_for_ready()
```

### Start/Stop

```python
def start(self) -> None:
    """Start stopped remote builder."""
    
    if not self.is_provisioned():
        raise StateError(f"Builder {self.name} not provisioned")
    
    if self.status() == 'running':
        print(f"Builder {self.name} already running")
        return
    
    # Start instance (GCP example)
    subprocess.run([
        'gcloud', 'compute', 'instances', 'start',
        self.instance_name,
        f'--zone={self.config.zone}',
        f'--project={self.config.project}'
    ], check=True)
    
    self.state.status = 'running'
    self.save_state()
    
    self.wait_for_ready()

def stop(self) -> None:
    """Stop running remote builder."""
    
    if self.status() != 'running':
        print(f"Builder {self.name} not running")
        return
    
    # Stop instance
    subprocess.run([
        'gcloud', 'compute', 'instances', 'stop',
        self.instance_name,
        f'--zone={self.config.zone}',
        f'--project={self.config.project}'
    ], check=True)
    
    self.state.status = 'stopped'
    self.save_state()
```

### Destroy

```python
def destroy(self) -> None:
    """Destroy remote builder infrastructure."""
    
    if not self.is_provisioned():
        raise StateError(f"Builder {self.name} not provisioned")
    
    # Confirm
    confirm = input(f"Destroy builder {self.name}? [yes/no]: ")
    if confirm != 'yes':
        print("Cancelled")
        return
    
    # Run Terraform destroy
    subprocess.run(
        ['terraform', 'destroy', '-auto-approve'],
        cwd=self.config.terraform_dir,
        env=self.get_terraform_env(),
        check=True
    )
    
    # Delete state
    self.delete_state()
```

## Error Handling

### Connection Errors

```python
def wait_for_ready(self, timeout: int = 300) -> None:
    """Wait for remote builder to be ready."""
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            # Test SSH connection
            result = self.ssh_execute(['echo', 'ready'], capture_output=True)
            if result.returncode == 0:
                # Test Docker
                result = self.ssh_execute(['docker', 'ps'], capture_output=True)
                if result.returncode == 0:
                    print(f"Builder {self.name} ready")
                    return
        except Exception as e:
            pass
        
        time.sleep(10)
    
    raise TimeoutError(f"Builder {self.name} not ready after {timeout}s")
```

### Build Errors

```python
def build_with_retry(self, max_retries: int = 3) -> BuildResult:
    """Execute build with retry logic."""
    
    for attempt in range(max_retries):
        try:
            return self.build()
        except BuildError as e:
            if attempt < max_retries - 1:
                print(f"Build failed (attempt {attempt + 1}/{max_retries}): {e}")
                print("Retrying...")
                time.sleep(30)
            else:
                raise
```

### Cleanup on Failure

```python
def build_with_cleanup(self) -> BuildResult:
    """Execute build with guaranteed cleanup."""
    
    context_dir = None
    try:
        # Prepare and transfer
        context_dir = self.prepare_context()
        remote_path = self.transfer_context(context_dir)
        
        # Build
        result = self.execute_build(remote_path)
        
        return result
        
    finally:
        # Always cleanup
        if context_dir:
            shutil.rmtree(context_dir)
        
        if self.config.auto_stop:
            self.stop()
```

## Cost Optimization

### Auto-Stop

```yaml
builders:
  gcp-builder:
    auto_stop: true
    stop_delay: 300  # seconds
```

**Implementation**:

```python
def build(self) -> BuildResult:
    """Build with auto-stop."""
    
    try:
        result = self.execute_build()
        return result
    finally:
        if self.config.auto_stop:
            # Delay to allow multiple builds
            time.sleep(self.config.stop_delay)
            
            # Check if more builds queued
            if not self.has_pending_builds():
                self.stop()
```

### Spot Instances

```hcl
# terraform/gcp/compute.tf
resource "google_compute_instance" "builder" {
  name         = "absconda-builder"
  machine_type = var.machine_type
  
  scheduling {
    preemptible         = true
    automatic_restart   = false
    on_host_maintenance = "TERMINATE"
  }
  
  # ... other config
}
```

**Pros**: 60-90% cost reduction  
**Cons**: Can be terminated anytime

### Build Cache

Persist Docker cache between builds:

```bash
# On remote builder
docker system df  # Check cache usage

# Configure cache limit
# /etc/docker/daemon.json
{
  "builder": {
    "gc": {
      "enabled": true,
      "defaultKeepStorage": "20GB"
    }
  }
}
```

## Security

### Network Isolation

```hcl
# terraform/gcp/network.tf
resource "google_compute_firewall" "builder_ssh" {
  name    = "absconda-builder-ssh"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = [var.allowed_ssh_ip]  # Your IP only
  target_tags   = ["absconda-builder"]
}
```

### IAM Roles

```hcl
# terraform/gcp/iam.tf
resource "google_service_account" "builder" {
  account_id   = "absconda-builder"
  display_name = "Absconda Builder Service Account"
}

resource "google_project_iam_member" "builder_storage" {
  project = var.project
  role    = "roles/storage.admin"  # For GCR/Artifact Registry
  member  = "serviceAccount:${google_service_account.builder.email}"
}
```

### Secrets Management

```python
def build_with_secrets(self, secrets: Dict[str, str]) -> BuildResult:
    """Build with secrets passed securely."""
    
    # Create temporary secrets file
    secrets_file = '/tmp/secrets.env'
    
    # Transfer secrets
    self.ssh_execute([
        f'cat > {secrets_file}',
        '<<EOF',
        *[f'{k}={v}' for k, v in secrets.items()],
        'EOF'
    ])
    
    # Build with secrets
    result = self.ssh_execute([
        'docker', 'build',
        '--secret', f'id=secrets,src={secrets_file}',
        ...
    ])
    
    # Remove secrets
    self.ssh_execute(['rm', '-f', secrets_file])
    
    return result
```

## Monitoring

### Build Metrics

```python
class BuildMetrics:
    def __init__(self):
        self.builds_total = 0
        self.builds_success = 0
        self.builds_failed = 0
        self.total_build_time = 0
        self.total_cost = 0
    
    def record_build(self, duration: float, success: bool, cost: float):
        self.builds_total += 1
        if success:
            self.builds_success += 1
        else:
            self.builds_failed += 1
        self.total_build_time += duration
        self.total_cost += cost
    
    def report(self):
        print(f"Total builds: {self.builds_total}")
        print(f"Success rate: {self.builds_success / self.builds_total * 100:.1f}%")
        print(f"Average build time: {self.total_build_time / self.builds_total:.1f}s")
        print(f"Total cost: ${self.total_cost:.2f}")
```

### Health Checks

```python
def health_check(self) -> HealthStatus:
    """Check remote builder health."""
    
    checks = {
        'ssh_connection': self.check_ssh(),
        'docker_running': self.check_docker(),
        'disk_space': self.check_disk(),
        'network': self.check_network(),
    }
    
    return HealthStatus(checks=checks)
```

## Future Enhancements

### Planned Features

1. **Build queue**: Multiple builds in parallel
2. **Auto-scaling**: Spin up/down based on load
3. **Multi-region**: Failover between regions
4. **Build farm**: Pool of builders
5. **Cost tracking**: Detailed cost reports

### Experimental Ideas

1. **Kubernetes-based builds**: Use K8s jobs
2. **Serverless builds**: Cloud Build, AWS CodeBuild
3. **P2P builds**: Distributed builder network
4. **Build caching service**: Shared cache across users

## Related Documentation

- [Design Overview](design-overview.md) - Overall architecture
- [Remote Builders Guide](../guides/remote-builders.md) - User guide
- [Building Images Guide](../guides/building-images.md) - Build process
- [Configuration Reference](../reference/configuration.md) - Config files

## References

- **Terraform GCP Provider**: https://registry.terraform.io/providers/hashicorp/google/latest/docs
- **Google Compute Engine**: https://cloud.google.com/compute/docs
- **Docker BuildKit**: https://docs.docker.com/build/buildkit/
- **SSH Best Practices**: https://www.ssh.com/academy/ssh/security
