# Example: Data Science Environment

Complete walkthrough for building a comprehensive data science environment with NumPy, pandas, scikit-learn, and Jupyter.

## Overview

This example demonstrates:
- Building a full data science stack
- Jupyter Lab integration
- Local and remote development
- HPC deployment with Singularity

**Use case**: Machine learning, data analysis, and interactive computing.

## Prerequisites

- Docker installed
- Absconda installed
- 4GB+ disk space (for full scientific Python stack)
- Optional: Singularity (for HPC deployment)

## Step 1: Create Environment File

Create `data-science-env.yaml`:

```yaml
name: data-science
channels:
  - conda-forge
dependencies:
  # Core Python
  - python=3.11
  
  # Scientific computing
  - numpy=1.26
  - pandas=2.2
  - scipy=1.11
  - scikit-learn=1.4
  
  # Visualization
  - matplotlib=3.8
  - seaborn=0.13
  - plotly=5.18
  
  # Jupyter
  - jupyter=1.0
  - ipykernel=6.28
  
  # Development tools
  - pip
  - pip:
      - jupyterlab==4.0.11
      - ipywidgets==8.1.1
      - pandas-profiling==3.6.6

labels:
  org.opencontainers.image.title: "Data Science Environment"
  org.opencontainers.image.description: "Python ML/AI stack with Jupyter Lab"
  org.opencontainers.image.authors: "datascience@example.com"
  org.opencontainers.image.version: "2024.01"

env:
  PYTHONUNBUFFERED: "1"
```

**Package breakdown**:
- **NumPy/pandas/SciPy**: Core numerical computing
- **scikit-learn**: Machine learning algorithms
- **matplotlib/seaborn/plotly**: Visualization
- **Jupyter/JupyterLab**: Interactive notebooks

## Step 2: Validate and Build

### Validate Environment

```bash
absconda validate --file data-science-env.yaml
```

**Expected output**:

```
Using policy profile default from built-in defaults.
Environment data-science is valid with 11 dependency entries.
```

### Build Image

```bash
absconda build \
  --file data-science-env.yaml \
  --repository ghcr.io/yourusername/data-science \
  --tag 2024.01 \
  --push
```

**Build time**: ~5-10 minutes (depending on network)  
**Image size**: ~2 GB (full scientific Python stack)

## Step 3: Run Jupyter Lab

### Start Jupyter Server

```bash
docker run -p 8888:8888 \
  -v $PWD:/work \
  -w /work \
  ghcr.io/yourusername/data-science:2024.01 \
  jupyter lab --ip=0.0.0.0 --allow-root --no-browser
```

**Output**:

```
[I 2024-01-15 10:30:00.000 ServerApp] Jupyter Server 2.12.5 is running at:
[I 2024-01-15 10:30:00.000 ServerApp] http://localhost:8888/lab?token=abc123...
```

Open browser to `http://localhost:8888/lab?token=abc123...`

### Docker Compose Setup

**docker-compose.yml**:

```yaml
version: '3.8'

services:
  jupyter:
    image: ghcr.io/yourusername/data-science:2024.01
    ports:
      - "8888:8888"
    volumes:
      - ./notebooks:/work
      - ./data:/data:ro
    working_dir: /work
    command: jupyter lab --ip=0.0.0.0 --allow-root --no-browser
    environment:
      - JUPYTER_ENABLE_LAB=yes
```

Start:

```bash
docker-compose up -d
docker-compose logs -f jupyter  # Get token
```

## Step 4: Test Scientific Stack

### Create Test Notebook

Create `test_environment.ipynb`:

```python
# Cell 1: Import packages
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

print("All imports successful!")

# Cell 2: Load data
iris = load_iris()
X = pd.DataFrame(iris.data, columns=iris.feature_names)
y = pd.Series(iris.target, name='species')

print(f"Dataset shape: {X.shape}")
X.head()

# Cell 3: Visualize
sns.pairplot(pd.concat([X, y], axis=1), hue='species')
plt.show()

# Cell 4: Train model
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

clf = RandomForestClassifier(n_estimators=100, random_state=42)
clf.fit(X_train, y_train)

y_pred = clf.predict(X_test)
print(classification_report(y_test, y_pred))

# Cell 5: Feature importance
importance = pd.DataFrame({
    'feature': X.columns,
    'importance': clf.feature_importances_
}).sort_values('importance', ascending=False)

plt.figure(figsize=(10, 6))
sns.barplot(data=importance, x='importance', y='feature')
plt.title('Feature Importance')
plt.show()
```

### Run from Command Line

```bash
docker run --rm \
  -v $PWD:/work \
  -w /work \
  ghcr.io/yourusername/data-science:2024.01 \
  python -c "
import numpy as np
import pandas as pd
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier

# Load and train
iris = load_iris()
clf = RandomForestClassifier()
clf.fit(iris.data, iris.target)

print(f'Accuracy: {clf.score(iris.data, iris.target):.2f}')
"
```

**Output**: `Accuracy: 1.00`

## Step 5: HPC Deployment

### Build and Convert to Singularity

```bash
# Build and push
absconda publish \
  --file data-science-env.yaml \
  --repository ghcr.io/yourusername/data-science \
  --tag 2024.01 \
  --singularity-out data-science.sif
```

**Output**:

```
Image pushed: ghcr.io/yourusername/data-science:2024.01
INFO:    Converting OCI blobs to SIF format
INFO:    Starting build...
Singularity image written to data-science.sif
```

**SIF size**: ~2 GB

### Generate HPC Wrappers

```bash
absconda wrap \
  --image ghcr.io/yourusername/data-science:2024.01 \
  --commands python,jupyter,ipython \
  --output-dir ./wrappers \
  --extra-mounts /scratch/$PROJECT,/g/data/$PROJECT
```

### Generate Module File

```bash
absconda module \
  --name data-science/2024.01 \
  --wrapper-dir ./wrappers \
  --description "Python data science stack with Jupyter" \
  --image ghcr.io/yourusername/data-science:2024.01 \
  --output-dir ./modulefiles
```

### Deploy to HPC

```bash
# Copy to HPC
rsync -av wrappers/ gadi:/g/data/a56/apps/data-science/2024.01/wrappers/
rsync -av modulefiles/ gadi:/g/data/a56/apps/modulefiles/
rsync data-science.sif gadi:/g/data/a56/apps/data-science/2024.01/

# Use on HPC
ssh gadi
module use /g/data/a56/apps/modulefiles
module load data-science/2024.01

# Run analysis
python analysis.py

# Start Jupyter (with port forwarding)
jupyter lab --no-browser --port=8888
```

## Step 6: Production Workflow

### Example Analysis Script

**analysis.py**:

```python
#!/usr/bin/env python3
"""Example data analysis pipeline."""

import argparse
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
import matplotlib.pyplot as plt
import seaborn as sns


def load_data(input_path):
    """Load and preprocess data."""
    df = pd.read_csv(input_path)
    print(f"Loaded {len(df)} samples")
    return df


def train_model(X, y):
    """Train and evaluate model."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    
    # Cross-validation
    cv_scores = cross_val_score(clf, X_train, y_train, cv=5)
    print(f"CV Score: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")
    
    # Train final model
    clf.fit(X_train, y_train)
    
    # Evaluate
    y_pred = clf.predict(X_test)
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))
    
    return clf


def plot_results(clf, X, output_path):
    """Generate visualizations."""
    # Feature importance
    importance = pd.DataFrame({
        'feature': X.columns,
        'importance': clf.feature_importances_
    }).sort_values('importance', ascending=False)
    
    plt.figure(figsize=(10, 6))
    sns.barplot(data=importance, x='importance', y='feature')
    plt.title('Feature Importance')
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"Plot saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Run ML analysis')
    parser.add_argument('--input', required=True, help='Input CSV file')
    parser.add_argument('--output', default='results.png', help='Output plot')
    args = parser.parse_args()
    
    # Load data
    df = load_data(args.input)
    
    # Separate features and target (assumes last column is target)
    X = df.iloc[:, :-1]
    y = df.iloc[:, -1]
    
    # Train model
    clf = train_model(X, y)
    
    # Generate visualizations
    plot_results(clf, X, args.output)


if __name__ == '__main__':
    main()
```

### Run Analysis

```bash
# Local
docker run --rm \
  -v $PWD:/work \
  -w /work \
  ghcr.io/yourusername/data-science:2024.01 \
  python analysis.py --input data.csv --output results.png

# HPC
module load data-science/2024.01
python analysis.py --input /g/data/a56/data/dataset.csv --output results.png
```

## Step 7: CI/CD Integration

### GitHub Actions Workflow

**.github/workflows/build-env.yml**:

```yaml
name: Build Data Science Environment

on:
  push:
    branches: [main]
    paths:
      - 'data-science-env.yaml'
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      packages: write
      contents: read
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install Absconda
        run: pip install absconda
      
      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Build and push
        run: |
          absconda build \
            --file data-science-env.yaml \
            --repository ghcr.io/${{ github.repository_owner }}/data-science \
            --tag $(date +%Y.%m) \
            --push
          
          # Also tag as latest
          docker tag ghcr.io/${{ github.repository_owner }}/data-science:$(date +%Y.%m) \
            ghcr.io/${{ github.repository_owner }}/data-science:latest
          docker push ghcr.io/${{ github.repository_owner }}/data-science:latest
```

## Variations

### Add GPU Support

**data-science-gpu.yaml**:

```yaml
name: data-science-gpu
channels:
  - pytorch
  - nvidia
  - conda-forge
dependencies:
  - python=3.11
  - numpy=1.26
  - pandas=2.2
  - pytorch=2.1.0
  - pytorch-cuda=12.1
  - cudatoolkit=12.1
  - scikit-learn=1.4
  - jupyter=1.0
  - pip
  - pip:
      - jupyterlab==4.0.11
```

### Add R Integration

**data-science-r.yaml**:

```yaml
name: data-science-r
channels:
  - conda-forge
  - r
dependencies:
  - python=3.11
  - numpy=1.26
  - pandas=2.2
  - r-base=4.3
  - r-essentials
  - r-ggplot2
  - rpy2=3.5
  - jupyter=1.0
  - pip
  - pip:
      - jupyterlab==4.0.11
```

### Snapshot for Reproducibility

```bash
# Create environment
conda env create -f data-science-env.yaml

# Export exact versions
conda activate data-science
conda env export > data-science-snapshot.yaml

# Build from snapshot
absconda build \
  --file data-science-env.yaml \
  --snapshot data-science-snapshot.yaml \
  --repository ghcr.io/yourusername/data-science \
  --tag 2024.01-locked
```

## Troubleshooting

### Jupyter Not Starting

**Error**: `Jupyter command not found`

**Solution**: Ensure jupyter is in conda dependencies:

```yaml
dependencies:
  - jupyter=1.0
  - ipykernel=6.28
```

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'sklearn'`

**Solution**: Package name is `scikit-learn` not `sklearn`:

```yaml
dependencies:
  - scikit-learn=1.4  # Correct
```

### Plot Not Displaying

Add `matplotlib` backend configuration:

```python
import matplotlib
matplotlib.use('Agg')  # For non-interactive backend
import matplotlib.pyplot as plt
```

## Next Steps

- [GPU PyTorch Example](gpu-pytorch.md) - Deep learning with GPU
- [R Bioconductor Example](r-bioconductor.md) - Bioinformatics with R
- [HPC Singularity Example](hpc-singularity.md) - Complete HPC workflow
- [Building Images Guide](../guides/building-images.md) - Advanced options

## Complete Files

All files available in [`examples/`](../../examples/) directory:
- `data-science-env.yaml`
- `test_environment.ipynb`
- `analysis.py`
- `docker-compose.yml`
