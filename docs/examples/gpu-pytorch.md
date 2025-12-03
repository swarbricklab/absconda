# Example: GPU PyTorch Environment

Complete walkthrough for building a GPU-enabled PyTorch environment for deep learning.

## Overview

This example demonstrates:
- CUDA/GPU-enabled container builds
- PyTorch with GPU support
- Training on GPUs (local and HPC)
- Multi-GPU setups

**Use case**: Deep learning, neural network training, GPU-accelerated computing.

## Prerequisites

- NVIDIA GPU with CUDA support
- NVIDIA Container Toolkit installed
- Docker installed
- Absconda installed

## Step 1: Check GPU Availability

### Local GPU Check

```bash
# Check NVIDIA driver
nvidia-smi
```

**Expected output**:

```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.129.03   Driver Version: 535.129.03   CUDA Version: 12.2   |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  NVIDIA A100         Off  | 00000000:00:1E.0 Off |                    0 |
| N/A   30C    P0    44W / 250W |      0MiB / 40960MiB |      0%      Default |
+-------------------------------+----------------------+----------------------+
```

### Docker GPU Support

```bash
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
```

If this works, you're ready for GPU containers!

## Step 2: Create Environment File

Create `pytorch-gpu-env.yaml`:

```yaml
name: pytorch-gpu
channels:
  - pytorch
  - nvidia
  - conda-forge
dependencies:
  # Python
  - python=3.11
  
  # PyTorch with CUDA
  - pytorch=2.1.0
  - pytorch-cuda=12.1
  - torchvision=0.16.0
  - torchaudio=2.1.0
  
  # CUDA toolkit
  - cudatoolkit=12.1
  - cudnn=8.9
  
  # Scientific computing
  - numpy=1.26
  - pandas=2.2
  - scikit-learn=1.4
  
  # Visualization
  - matplotlib=3.8
  - tensorboard=2.15
  
  # Jupyter
  - jupyter=1.0
  - pip
  - pip:
      - jupyterlab==4.0.11
      - transformers==4.36.0
      - datasets==2.16.0
      - accelerate==0.25.0
      - wandb==0.16.2

labels:
  org.opencontainers.image.title: "PyTorch GPU Environment"
  org.opencontainers.image.description: "PyTorch 2.1 with CUDA 12.1 support"
  org.opencontainers.image.authors: "ml-team@example.com"
  org.opencontainers.image.version: "2.1.0-cuda12.1"

env:
  CUDA_VISIBLE_DEVICES: "0"
  PYTHONUNBUFFERED: "1"
```

**Key components**:
- **pytorch=2.1.0**: PyTorch framework
- **pytorch-cuda=12.1**: CUDA integration
- **cudatoolkit=12.1**: NVIDIA CUDA toolkit
- **transformers/datasets**: Hugging Face libraries for NLP
- **accelerate**: Multi-GPU training
- **wandb**: Experiment tracking

## Step 3: Build GPU-Enabled Container

### Using Custom Base Image

For GPU support, use CUDA base image:

```bash
absconda build \
  --file pytorch-gpu-env.yaml \
  --repository ghcr.io/yourusername/pytorch-gpu \
  --tag 2.1.0-cuda12.1 \
  --runtime-base nvidia/cuda:12.2.0-runtime-ubuntu22.04 \
  --push
```

**Build time**: 10-15 minutes  
**Image size**: ~6-8 GB (includes CUDA runtime)

### Custom GPU Template

For more control, create `gpu-template.j2`:

```dockerfile
# Builder stage
FROM nvidia/cuda:12.2.0-devel-ubuntu22.04 AS builder

# Install micromamba
RUN apt-get update && \
    apt-get install -y wget bzip2 && \
    wget -qO- https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C / bin/micromamba && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV MAMBA_ROOT_PREFIX=/opt/conda

# Install Conda packages
COPY {{ env_filename }} /tmp/env.yaml
RUN micromamba create -y -n {{ name }} -f /tmp/env.yaml && \
    micromamba clean -afy

# Runtime stage
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Copy environment
COPY --from=builder /opt/conda/envs/{{ name }} /opt/conda/envs/{{ name }}

ENV PATH=/opt/conda/envs/{{ name }}/bin:$PATH
ENV CUDA_VISIBLE_DEVICES=0

# Labels
{% for key, value in labels.items() %}
LABEL {{ key }}="{{ value }}"
{% endfor %}

CMD ["python"]
```

Build:

```bash
absconda generate \
  --file pytorch-gpu-env.yaml \
  --template gpu-template.j2 \
  --output Dockerfile.gpu

docker build -t ghcr.io/yourusername/pytorch-gpu:2.1.0-cuda12.1 -f Dockerfile.gpu .
```

## Step 4: Test GPU Access

### Verify CUDA in Container

```bash
docker run --rm --gpus all \
  ghcr.io/yourusername/pytorch-gpu:2.1.0-cuda12.1 \
  python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda}'); print(f'GPU count: {torch.cuda.device_count()}')"
```

**Expected output**:

```
CUDA available: True
CUDA version: 12.1
GPU count: 1
```

### Test PyTorch GPU

```bash
docker run --rm --gpus all \
  ghcr.io/yourusername/pytorch-gpu:2.1.0-cuda12.1 \
  python -c "
import torch
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'Device name: {torch.cuda.get_device_name(0)}')

# Create tensor on GPU
x = torch.rand(3, 3).cuda()
print(f'Tensor device: {x.device}')
print(x)
"
```

**Output**:

```
PyTorch version: 2.1.0+cu121
CUDA available: True
Device name: NVIDIA A100-SXM4-40GB
Tensor device: cuda:0
tensor([[0.1234, 0.5678, 0.9012],
        [0.3456, 0.7890, 0.1234],
        [0.5678, 0.9012, 0.3456]], device='cuda:0')
```

## Step 5: Training Example

### Simple Neural Network

**train_mnist.py**:

```python
#!/usr/bin/env python3
"""Train a simple CNN on MNIST using PyTorch."""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
import argparse
from tqdm import tqdm


class SimpleCNN(nn.Module):
    def __init__(self):
        super(SimpleCNN, self).__init__()
        self.conv1 = nn.Conv2d(1, 32, 3, 1)
        self.conv2 = nn.Conv2d(32, 64, 3, 1)
        self.dropout1 = nn.Dropout(0.25)
        self.dropout2 = nn.Dropout(0.5)
        self.fc1 = nn.Linear(9216, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x):
        x = self.conv1(x)
        x = nn.functional.relu(x)
        x = self.conv2(x)
        x = nn.functional.relu(x)
        x = nn.functional.max_pool2d(x, 2)
        x = self.dropout1(x)
        x = torch.flatten(x, 1)
        x = self.fc1(x)
        x = nn.functional.relu(x)
        x = self.dropout2(x)
        x = self.fc2(x)
        return nn.functional.log_softmax(x, dim=1)


def train(model, device, train_loader, optimizer, epoch):
    model.train()
    pbar = tqdm(train_loader, desc=f'Epoch {epoch}')
    for batch_idx, (data, target) in enumerate(pbar):
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = nn.functional.nll_loss(output, target)
        loss.backward()
        optimizer.step()
        
        if batch_idx % 100 == 0:
            pbar.set_postfix({'loss': f'{loss.item():.4f}'})


def test(model, device, test_loader):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += nn.functional.nll_loss(output, target, reduction='sum').item()
            pred = output.argmax(dim=1, keepdim=True)
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)
    accuracy = 100. * correct / len(test_loader.dataset)
    
    print(f'\nTest set: Average loss: {test_loss:.4f}, '
          f'Accuracy: {correct}/{len(test_loader.dataset)} ({accuracy:.2f}%)\n')
    
    return accuracy


def main():
    parser = argparse.ArgumentParser(description='PyTorch MNIST Training')
    parser.add_argument('--batch-size', type=int, default=64, help='input batch size')
    parser.add_argument('--epochs', type=int, default=10, help='number of epochs')
    parser.add_argument('--lr', type=float, default=0.01, help='learning rate')
    parser.add_argument('--no-cuda', action='store_true', help='disables CUDA training')
    parser.add_argument('--save-model', action='store_true', help='save model')
    args = parser.parse_args()

    # Device configuration
    use_cuda = not args.no_cuda and torch.cuda.is_available()
    device = torch.device("cuda" if use_cuda else "cpu")
    print(f'Using device: {device}')
    if use_cuda:
        print(f'GPU: {torch.cuda.get_device_name(0)}')

    # Data loaders
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])
    
    train_dataset = datasets.MNIST('./data', train=True, download=True, transform=transform)
    test_dataset = datasets.MNIST('./data', train=False, transform=transform)
    
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)

    # Model, optimizer
    model = SimpleCNN().to(device)
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    # Training loop
    best_accuracy = 0.0
    for epoch in range(1, args.epochs + 1):
        train(model, device, train_loader, optimizer, epoch)
        accuracy = test(model, device, test_loader)
        
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            if args.save_model:
                torch.save(model.state_dict(), "mnist_cnn_best.pt")
                print(f'Model saved with accuracy: {accuracy:.2f}%')

    print(f'\nBest accuracy: {best_accuracy:.2f}%')


if __name__ == '__main__':
    main()
```

### Run Training

```bash
docker run --rm --gpus all \
  -v $PWD:/work \
  -w /work \
  ghcr.io/yourusername/pytorch-gpu:2.1.0-cuda12.1 \
  python train_mnist.py --epochs 5 --save-model
```

**Output**:

```
Using device: cuda
GPU: NVIDIA A100-SXM4-40GB
Downloading MNIST...
Epoch 1: 100%|████████| 938/938 [00:15<00:00, loss: 0.0234]
Test set: Average loss: 0.0456, Accuracy: 9856/10000 (98.56%)

Epoch 2: 100%|████████| 938/938 [00:14<00:00, loss: 0.0123]
Test set: Average loss: 0.0312, Accuracy: 9890/10000 (98.90%)
...
Best accuracy: 99.12%
```

## Step 6: Multi-GPU Training

### Data Parallel Training

**train_multi_gpu.py**:

```python
import torch
import torch.nn as nn

# Check for multiple GPUs
if torch.cuda.device_count() > 1:
    print(f"Using {torch.cuda.device_count()} GPUs")
    model = nn.DataParallel(model)

model = model.to('cuda')

# Training proceeds as normal
# Data is automatically split across GPUs
```

### Run on Multiple GPUs

```bash
docker run --rm --gpus all \
  -v $PWD:/work \
  -w /work \
  ghcr.io/yourusername/pytorch-gpu:2.1.0-cuda12.1 \
  python train_multi_gpu.py
```

### Distributed Data Parallel (DDP)

For better performance on multiple GPUs:

```python
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP

# Initialize process group
dist.init_process_group(backend='nccl')
local_rank = int(os.environ['LOCAL_RANK'])
torch.cuda.set_device(local_rank)

# Wrap model with DDP
model = model.to(local_rank)
model = DDP(model, device_ids=[local_rank])
```

Run:

```bash
docker run --rm --gpus all \
  -v $PWD:/work \
  -w /work \
  ghcr.io/yourusername/pytorch-gpu:2.1.0-cuda12.1 \
  torchrun --nproc_per_node=2 train_ddp.py
```

## Step 7: HPC Deployment

### Build for HPC

```bash
absconda publish \
  --file pytorch-gpu-env.yaml \
  --repository ghcr.io/yourusername/pytorch-gpu \
  --tag 2.1.0-cuda12.1 \
  --singularity-out pytorch-gpu.sif
```

### Deploy to HPC

```bash
# Copy to HPC
rsync pytorch-gpu.sif gadi:/g/data/a56/apps/pytorch/2.1.0/

# Test on GPU node
ssh gadi
qsub -I -q gpuvolta -l ncpus=12,ngpus=1,mem=96GB,walltime=1:00:00 -l storage=gdata/a56

# In interactive session
singularity exec --nv \
  /g/data/a56/apps/pytorch/2.1.0/pytorch-gpu.sif \
  python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

### PBS Job Script

**train_gpu.pbs**:

```bash
#!/bin/bash
#PBS -P a56
#PBS -q gpuvolta
#PBS -l ncpus=12
#PBS -l ngpus=1
#PBS -l mem=96GB
#PBS -l walltime=10:00:00
#PBS -l storage=gdata/a56
#PBS -N pytorch_training

cd $PBS_O_WORKDIR

# Load Singularity
module load singularity

# Run training
singularity exec --nv \
  /g/data/a56/apps/pytorch/2.1.0/pytorch-gpu.sif \
  python train_mnist.py \
    --epochs 50 \
    --batch-size 128 \
    --save-model \
    --lr 0.001
```

Submit:

```bash
qsub train_gpu.pbs
```

### Multi-GPU PBS Job

**train_multi_gpu.pbs**:

```bash
#!/bin/bash
#PBS -P a56
#PBS -q gpuvolta
#PBS -l ncpus=48
#PBS -l ngpus=4
#PBS -l mem=384GB
#PBS -l walltime=24:00:00
#PBS -l storage=gdata/a56
#PBS -N pytorch_ddp

cd $PBS_O_WORKDIR

module load singularity

# DDP training on 4 GPUs
singularity exec --nv \
  /g/data/a56/apps/pytorch/2.1.0/pytorch-gpu.sif \
  torchrun --nproc_per_node=4 train_ddp.py \
    --epochs 100 \
    --batch-size 256
```

## Step 8: Experiment Tracking

### WandB Integration

**train_with_wandb.py**:

```python
import wandb

# Initialize wandb
wandb.init(
    project="mnist-classification",
    config={
        "learning_rate": 0.01,
        "epochs": 10,
        "batch_size": 64
    }
)

# Log metrics during training
wandb.log({
    "epoch": epoch,
    "train_loss": loss.item(),
    "test_accuracy": accuracy,
    "learning_rate": optimizer.param_groups[0]['lr']
})

# Save model
wandb.save("mnist_cnn_best.pt")
```

Run with WandB:

```bash
docker run --rm --gpus all \
  -v $PWD:/work \
  -w /work \
  -e WANDB_API_KEY=$WANDB_API_KEY \
  ghcr.io/yourusername/pytorch-gpu:2.1.0-cuda12.1 \
  python train_with_wandb.py
```

## Variations

### TensorFlow GPU

**tensorflow-gpu-env.yaml**:

```yaml
name: tensorflow-gpu
channels:
  - conda-forge
dependencies:
  - python=3.11
  - cudatoolkit=12.1
  - cudnn=8.9
  - pip
  - pip:
      - tensorflow[and-cuda]==2.15.0
      - tensorboard==2.15.0
```

### JAX GPU

**jax-gpu-env.yaml**:

```yaml
name: jax-gpu
channels:
  - conda-forge
dependencies:
  - python=3.11
  - cudatoolkit=12.1
  - pip
  - pip:
      - jax[cuda12_pip]==0.4.20
      - flax==0.7.5
      - optax==0.1.7
```

## Troubleshooting

### CUDA Not Available

**Error**: `torch.cuda.is_available()` returns `False`

**Solution 1**: Ensure `--gpus all` flag:

```bash
docker run --rm --gpus all ...
```

**Solution 2**: Check NVIDIA Container Toolkit:

```bash
docker run --rm --gpus all nvidia/cuda:12.2.0-base nvidia-smi
```

**Solution 3**: Check pytorch-cuda compatibility:

```yaml
dependencies:
  - pytorch=2.1.0
  - pytorch-cuda=12.1  # Must match your CUDA version
```

### Out of Memory

**Error**: `CUDA out of memory`

**Solution**: Reduce batch size or use gradient accumulation:

```python
# Smaller batch size
batch_size = 32  # Instead of 64

# Or gradient accumulation
accumulation_steps = 4
for i, (data, target) in enumerate(train_loader):
    loss = loss / accumulation_steps
    loss.backward()
    if (i + 1) % accumulation_steps == 0:
        optimizer.step()
        optimizer.zero_grad()
```

### Wrong CUDA Version

**Error**: `CUDA runtime version mismatch`

**Solution**: Match pytorch-cuda with host CUDA:

```bash
# Check host CUDA
nvidia-smi  # Shows CUDA version

# Use matching pytorch-cuda
# CUDA 11.8 → pytorch-cuda=11.8
# CUDA 12.1 → pytorch-cuda=12.1
```

## Next Steps

- [Data Science Example](data-science.md) - CPU-based ML
- [HPC Singularity Example](hpc-singularity.md) - Complete HPC workflow
- [Building Images Guide](../guides/building-images.md) - Custom base images
- [Custom Base Images](../how-to/custom-base-images.md) - GPU base configuration

## Complete Files

All files in [`examples/`](../../examples/):
- `pytorch-gpu-env.yaml`
- `train_mnist.py`
- `train_multi_gpu.py`
- `train_with_wandb.py`
- `train_gpu.pbs`
- `gpu-template.j2`
