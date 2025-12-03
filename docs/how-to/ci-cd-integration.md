# How to: CI/CD Integration

Integrate Absconda into automated CI/CD pipelines for continuous container builds and deployments.

## Overview

This guide covers:
- GitHub Actions workflows
- GitLab CI pipelines
- Jenkins pipelines
- CircleCI configuration
- Azure DevOps pipelines
- Best practices for automated builds

## GitHub Actions

### Basic Workflow

**`.github/workflows/build.yml`**:

```yaml
name: Build Container

on:
  push:
    branches: [main]
    paths:
      - 'environment.yaml'
      - 'src/**'
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install Absconda
        run: |
          pip install absconda
      
      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Build and push container
        run: |
          absconda build \
            --file environment.yaml \
            --repository ghcr.io/${{ github.repository }} \
            --tag ${{ github.sha }} \
            --tag latest \
            --push
```

### Advanced Workflow

**`.github/workflows/ci.yml`**:

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
    tags: ['v*']
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install absconda pytest
      
      - name: Validate environment file
        run: |
          absconda validate --file environment.yaml
      
      - name: Run tests
        run: |
          pytest tests/

  build:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Install Absconda
        run: pip install absconda
      
      - name: Login to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,prefix={{branch}}-
      
      - name: Build container
        run: |
          absconda build \
            --file environment.yaml \
            --repository ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }} \
            --tag ${{ github.sha }}
      
      - name: Test container
        run: |
          docker run --rm ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }} \
            python -c "import sys; print(f'Python {sys.version}')"
      
      - name: Push container
        if: github.event_name != 'pull_request'
        run: |
          for tag in ${{ steps.meta.outputs.tags }}; do
            docker tag ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }} $tag
            docker push $tag
          done
      
      - name: Generate SBOM
        uses: anchore/sbom-action@v0
        with:
          image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}

  deploy:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: |
          # Add deployment logic here
          echo "Deploying ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}"
```

### Matrix Builds

Build multiple variants:

```yaml
name: Multi-variant Build

on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
        variant: ['minimal', 'full']
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Install Absconda
        run: pip install absconda
      
      - name: Login to registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Build container
        run: |
          absconda build \
            --file environment-${{ matrix.variant }}.yaml \
            --repository ghcr.io/${{ github.repository }} \
            --tag py${{ matrix.python-version }}-${{ matrix.variant }} \
            --push
```

### Scheduled Builds

Rebuild weekly to get security updates:

```yaml
name: Weekly Rebuild

on:
  schedule:
    - cron: '0 0 * * 0'  # Every Sunday at midnight
  workflow_dispatch:  # Manual trigger

jobs:
  rebuild:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install Absconda
        run: pip install absconda
      
      - name: Login to registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Rebuild and push
        run: |
          absconda build \
            --file environment.yaml \
            --repository ghcr.io/${{ github.repository }} \
            --tag weekly-$(date +%Y%m%d) \
            --tag latest \
            --push
```

## GitLab CI

### Basic Pipeline

**`.gitlab-ci.yml`**:

```yaml
image: docker:latest

services:
  - docker:dind

variables:
  DOCKER_HOST: tcp://docker:2376
  DOCKER_TLS_CERTDIR: "/certs"
  IMAGE_TAG: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA

stages:
  - build
  - test
  - push

before_script:
  - apk add --no-cache python3 py3-pip
  - pip3 install absconda
  - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin $CI_REGISTRY

build:
  stage: build
  script:
    - absconda build --file environment.yaml --repository $CI_REGISTRY_IMAGE --tag $CI_COMMIT_SHA
  artifacts:
    reports:
      dotenv: build.env

test:
  stage: test
  script:
    - docker run --rm $IMAGE_TAG python -c "import sys; assert sys.version_info >= (3, 11)"
  dependencies:
    - build

push:
  stage: push
  script:
    - docker tag $IMAGE_TAG $CI_REGISTRY_IMAGE:latest
    - docker push $CI_REGISTRY_IMAGE:latest
  only:
    - main
```

### Advanced Pipeline

```yaml
image: docker:latest

services:
  - docker:dind

variables:
  DOCKER_HOST: tcp://docker:2376
  DOCKER_TLS_CERTDIR: "/certs"

stages:
  - validate
  - build
  - test
  - security
  - push
  - deploy

validate:
  stage: validate
  script:
    - apk add --no-cache python3 py3-pip
    - pip3 install absconda
    - absconda validate --file environment.yaml

build:
  stage: build
  before_script:
    - apk add --no-cache python3 py3-pip
    - pip3 install absconda
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin $CI_REGISTRY
  script:
    - |
      absconda build \
        --file environment.yaml \
        --repository $CI_REGISTRY_IMAGE \
        --tag $CI_COMMIT_SHA \
        --tag $CI_COMMIT_REF_SLUG
  artifacts:
    expire_in: 1 week

test:
  stage: test
  script:
    - docker run --rm $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA python -m pytest /app/tests
  dependencies:
    - build

security_scan:
  stage: security
  image: aquasec/trivy:latest
  script:
    - trivy image --exit-code 0 --severity HIGH,CRITICAL $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
  allow_failure: true

push_tags:
  stage: push
  before_script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin $CI_REGISTRY
  script:
    - docker pull $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
    - docker tag $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA $CI_REGISTRY_IMAGE:latest
    - docker push $CI_REGISTRY_IMAGE:latest
  only:
    - main
    - tags

deploy_production:
  stage: deploy
  script:
    - kubectl set image deployment/myapp app=$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
  environment:
    name: production
    url: https://myapp.example.com
  only:
    - main
  when: manual
```

## Jenkins

### Declarative Pipeline

**`Jenkinsfile`**:

```groovy
pipeline {
    agent any
    
    environment {
        REGISTRY = 'ghcr.io'
        IMAGE_NAME = "${REGISTRY}/yourorg/app"
        DOCKER_CREDS = credentials('docker-credentials')
    }
    
    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        
        stage('Install Absconda') {
            steps {
                sh 'pip install absconda'
            }
        }
        
        stage('Validate') {
            steps {
                sh 'absconda validate --file environment.yaml'
            }
        }
        
        stage('Build') {
            steps {
                sh '''
                    echo "$DOCKER_CREDS_PSW" | docker login $REGISTRY -u "$DOCKER_CREDS_USR" --password-stdin
                    
                    absconda build \
                        --file environment.yaml \
                        --repository $IMAGE_NAME \
                        --tag ${BUILD_NUMBER} \
                        --tag latest
                '''
            }
        }
        
        stage('Test') {
            steps {
                sh '''
                    docker run --rm $IMAGE_NAME:${BUILD_NUMBER} \
                        python -c "import sys; print(f'Python {sys.version}')"
                '''
            }
        }
        
        stage('Push') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    docker push $IMAGE_NAME:${BUILD_NUMBER}
                    docker push $IMAGE_NAME:latest
                '''
            }
        }
        
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                input message: 'Deploy to production?', ok: 'Deploy'
                sh 'kubectl set image deployment/myapp app=$IMAGE_NAME:${BUILD_NUMBER}'
            }
        }
    }
    
    post {
        always {
            sh 'docker logout $REGISTRY'
        }
        success {
            echo 'Build succeeded!'
        }
        failure {
            echo 'Build failed!'
        }
    }
}
```

### Multi-branch Pipeline

```groovy
pipeline {
    agent any
    
    environment {
        REGISTRY = 'ghcr.io'
        IMAGE_NAME = "${REGISTRY}/yourorg/app"
    }
    
    stages {
        stage('Build') {
            steps {
                script {
                    def tagName = env.BRANCH_NAME == 'main' ? 'latest' : env.BRANCH_NAME
                    
                    sh """
                        pip install absconda
                        
                        absconda build \
                            --file environment.yaml \
                            --repository ${IMAGE_NAME} \
                            --tag ${BUILD_NUMBER} \
                            --tag ${tagName} \
                            --push
                    """
                }
            }
        }
    }
}
```

## CircleCI

**`.circleci/config.yml`**:

```yaml
version: 2.1

orbs:
  docker: circleci/docker@2.4.0

jobs:
  build_and_push:
    docker:
      - image: cimg/python:3.11
    steps:
      - checkout
      
      - setup_remote_docker:
          docker_layer_caching: true
      
      - run:
          name: Install Absconda
          command: pip install absconda
      
      - run:
          name: Login to Registry
          command: |
            echo "$DOCKER_PASSWORD" | docker login ghcr.io -u "$DOCKER_USERNAME" --password-stdin
      
      - run:
          name: Build Container
          command: |
            absconda build \
              --file environment.yaml \
              --repository ghcr.io/$CIRCLE_PROJECT_USERNAME/$CIRCLE_PROJECT_REPONAME \
              --tag $CIRCLE_SHA1 \
              --tag latest \
              --push
      
      - run:
          name: Test Container
          command: |
            docker run --rm ghcr.io/$CIRCLE_PROJECT_USERNAME/$CIRCLE_PROJECT_REPONAME:$CIRCLE_SHA1 \
              python -m pytest

workflows:
  build_and_deploy:
    jobs:
      - build_and_push:
          context: docker-hub-creds
          filters:
            branches:
              only: main
```

## Azure DevOps

**`azure-pipelines.yml`**:

```yaml
trigger:
  branches:
    include:
      - main
      - develop
  paths:
    include:
      - environment.yaml
      - src/*

pool:
  vmImage: 'ubuntu-latest'

variables:
  containerRegistry: 'myregistry.azurecr.io'
  imageName: 'myapp'
  dockerRegistryServiceConnection: 'azure-container-registry'

stages:
  - stage: Build
    displayName: 'Build Container'
    jobs:
      - job: Build
        displayName: 'Build and Push'
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '3.11'
          
          - script: |
              pip install absconda
            displayName: 'Install Absconda'
          
          - task: Docker@2
            displayName: 'Login to Container Registry'
            inputs:
              command: login
              containerRegistry: $(dockerRegistryServiceConnection)
          
          - script: |
              absconda build \
                --file environment.yaml \
                --repository $(containerRegistry)/$(imageName) \
                --tag $(Build.BuildId) \
                --tag latest \
                --push
            displayName: 'Build and Push Container'
          
          - script: |
              docker run --rm $(containerRegistry)/$(imageName):$(Build.BuildId) \
                python -c "import sys; print(sys.version)"
            displayName: 'Test Container'

  - stage: Deploy
    displayName: 'Deploy to Production'
    dependsOn: Build
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - deployment: Deploy
        displayName: 'Deploy Container'
        environment: 'production'
        strategy:
          runOnce:
            deploy:
              steps:
                - script: |
                    kubectl set image deployment/myapp \
                      app=$(containerRegistry)/$(imageName):$(Build.BuildId)
                  displayName: 'Update Kubernetes Deployment'
```

## Best Practices

### Caching

**GitHub Actions**:

```yaml
- name: Cache Absconda
  uses: actions/cache@v4
  with:
    path: ~/.cache/absconda
    key: ${{ runner.os }}-absconda-${{ hashFiles('environment.yaml') }}
```

**GitLab CI**:

```yaml
cache:
  key: ${CI_COMMIT_REF_SLUG}
  paths:
    - .docker/
```

### Parallel Builds

**GitHub Actions**:

```yaml
jobs:
  build:
    strategy:
      matrix:
        env: [dev, staging, prod]
    runs-on: ubuntu-latest
    steps:
      - name: Build ${{ matrix.env }}
        run: |
          absconda build \
            --file environment-${{ matrix.env }}.yaml \
            --tag ${{ matrix.env }}
```

### Security Scanning

**GitHub Actions with Trivy**:

```yaml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ghcr.io/${{ github.repository }}:${{ github.sha }}
    format: 'sarif'
    output: 'trivy-results.sarif'

- name: Upload Trivy results to GitHub Security
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: 'trivy-results.sarif'
```

### Semantic Versioning

**GitHub Actions**:

```yaml
- name: Determine version
  id: version
  run: |
    if [[ $GITHUB_REF == refs/tags/* ]]; then
      VERSION=${GITHUB_REF#refs/tags/v}
    else
      VERSION=$(git describe --tags --always)
    fi
    echo "version=$VERSION" >> $GITHUB_OUTPUT

- name: Build with version
  run: |
    absconda build \
      --file environment.yaml \
      --tag ${{ steps.version.outputs.version }}
```

### Environment-Specific Builds

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches:
      - main
      - develop

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Determine environment
        id: env
        run: |
          if [[ $GITHUB_REF == refs/heads/main ]]; then
            echo "name=production" >> $GITHUB_OUTPUT
          else
            echo "name=staging" >> $GITHUB_OUTPUT
          fi
      
      - name: Build container
        run: |
          absconda build \
            --file environment-${{ steps.env.outputs.name }}.yaml \
            --repository ghcr.io/${{ github.repository }} \
            --tag ${{ steps.env.outputs.name }}
```

## Troubleshooting

### Docker in Docker Issues

**GitLab CI Error**: Cannot connect to Docker daemon

**Solution**: Use `docker:dind` service:

```yaml
services:
  - docker:dind

variables:
  DOCKER_HOST: tcp://docker:2376
  DOCKER_TLS_CERTDIR: "/certs"
```

### Rate Limiting

**Error**: Docker Hub rate limit exceeded

**Solution**: Authenticate to increase limits:

```yaml
- name: Login to Docker Hub
  uses: docker/login-action@v3
  with:
    username: ${{ secrets.DOCKER_USERNAME }}
    password: ${{ secrets.DOCKER_PASSWORD }}
```

### Large Build Times

**Problem**: Builds take too long

**Solution**: Use layer caching:

```yaml
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3
  with:
    driver-opts: |
      image=moby/buildkit:latest
      cache-from=type=registry,ref=ghcr.io/${{ github.repository }}:buildcache
      cache-to=type=registry,ref=ghcr.io/${{ github.repository }}:buildcache,mode=max
```

## Complete Example

**`.github/workflows/complete.yml`**:

```yaml
name: Complete CI/CD Pipeline

on:
  push:
    branches: [main, develop]
    tags: ['v*']
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 0 * * 0'  # Weekly rebuild

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install absconda pytest
      - run: absconda validate --file environment.yaml
      - run: pytest tests/

  build:
    needs: validate
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      security-events: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Login to Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Install Absconda
        run: pip install absconda
      
      - name: Build container
        run: |
          absconda build \
            --file environment.yaml \
            --repository ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }} \
            --tag ${{ github.sha }}
      
      - name: Test container
        run: |
          docker run --rm ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }} \
            python -m pytest
      
      - name: Scan for vulnerabilities
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          format: 'sarif'
          output: 'trivy-results.sarif'
      
      - name: Upload scan results
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'
      
      - name: Push container
        if: github.event_name != 'pull_request'
        run: |
          docker tag ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }} \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
          docker push ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          docker push ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

  deploy:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://myapp.example.com
    steps:
      - name: Deploy to Kubernetes
        run: |
          kubectl set image deployment/myapp \
            app=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
```

## Related Documentation

- [Secrets and Authentication](secrets-and-auth.md) - Managing credentials
- [Building Images Guide](../guides/building-images.md) - Build process
- [Remote Builders Guide](../guides/remote-builders.md) - Cloud builds
- [Configuration Reference](../reference/configuration.md) - Config files

## Further Reading

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitLab CI/CD](https://docs.gitlab.com/ee/ci/)
- [Jenkins Pipeline](https://www.jenkins.io/doc/book/pipeline/)
- [CircleCI Documentation](https://circleci.com/docs/)
- [Azure Pipelines](https://learn.microsoft.com/en-us/azure/devops/pipelines/)
