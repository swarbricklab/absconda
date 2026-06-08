# Dockerfile for absconda container build tool
# Includes: absconda, Docker CLI, gcloud CLI, git, ssh

FROM python:3.11-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    openssh-client \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-buildx-plugin && \
    rm -rf /var/lib/apt/lists/*

# Install Google Cloud CLI
RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" > /etc/apt/sources.list.d/google-cloud-sdk.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

# NumPy gives gcloud's IAP TCP forwarding a faster tunnel (otherwise gcloud emits
# a performance warning on every connection). Pin gcloud to this image's Python
# (where numpy is installed) rather than any apt-pulled /usr/bin/python3, and
# allow it to load site packages so it actually sees numpy.
RUN pip install --no-cache-dir numpy
ENV CLOUDSDK_PYTHON=/usr/local/bin/python3 \
    CLOUDSDK_PYTHON_SITEPACKAGES=1

# Install absconda
COPY . /opt/absconda
WORKDIR /opt/absconda
RUN pip install --no-cache-dir .

# Set up SSH config directory
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# Default working directory for builds
WORKDIR /workspace

ENTRYPOINT ["absconda"]
CMD ["--help"]
