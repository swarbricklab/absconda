# How-to Guides

Task-focused guides for specific operations and integrations with Absconda.

## Overview

How-to guides are **goal-oriented** instructions for accomplishing specific tasks. If you know what you want to do, start here.

For learning-oriented material, see [Guides](../guides/) section.  
For reference material, see [Reference](../reference/) section.

## Available Guides

### [Multi-Stage Builds](multi-stage-builds.md)
**Goal**: Optimize container images using multi-stage builds

**You'll learn**:
- When to use multi-stage vs single-stage builds
- Creating custom multi-stage templates
- Reducing image size by 50-70%
- Security hardening techniques
- Layer caching optimization

**Time**: 15 minutes

**Prerequisites**: Basic Docker knowledge

---

### [Custom Base Images](custom-base-images.md)
**Goal**: Configure custom base images for specific requirements

**You'll learn**:
- Selecting appropriate base images
- GPU/CUDA base configuration
- Minimal images (Alpine, distroless)
- Organizational base image standards
- Multi-architecture builds
- Version pinning with digests

**Time**: 20 minutes

**Prerequisites**: Understanding of Docker base images

---

### [Secrets and Authentication](secrets-and-auth.md)
**Goal**: Securely handle credentials and secrets

**You'll learn**:
- Private conda channel authentication
- Container registry authentication
- Build-time secrets (BuildKit)
- Runtime secrets (Docker, Kubernetes)
- Secret management tools (Vault, AWS Secrets Manager)
- CI/CD secrets handling
- Security best practices

**Time**: 25 minutes

**Prerequisites**: Basic security concepts

---

### [CI/CD Integration](ci-cd-integration.md)
**Goal**: Automate container builds in CI/CD pipelines

**You'll learn**:
- GitHub Actions workflows
- GitLab CI pipelines
- Jenkins pipelines
- CircleCI configuration
- Azure DevOps pipelines
- Matrix builds and parallel execution
- Security scanning integration
- Automated deployments

**Time**: 30 minutes

**Prerequisites**: Familiarity with your CI/CD platform

---

## Quick Reference

### When to Use Each Guide

| Task | Guide |
|------|-------|
| Reduce image size | [Multi-Stage Builds](multi-stage-builds.md) |
| Need GPU support | [Custom Base Images](custom-base-images.md) |
| Access private packages | [Secrets and Authentication](secrets-and-auth.md) |
| Automate builds | [CI/CD Integration](ci-cd-integration.md) |
| Production optimization | [Multi-Stage Builds](multi-stage-builds.md) |
| Private registries | [Secrets and Authentication](secrets-and-auth.md) |
| Weekly rebuilds | [CI/CD Integration](ci-cd-integration.md) |
| Minimal base image | [Custom Base Images](custom-base-images.md) |

### Common Workflows

#### Production Deployment
1. [Multi-Stage Builds](multi-stage-builds.md) - Optimize image
2. [Custom Base Images](custom-base-images.md) - Use minimal base
3. [Secrets and Authentication](secrets-and-auth.md) - Secure credentials
4. [CI/CD Integration](ci-cd-integration.md) - Automate pipeline

#### GPU Application
1. [Custom Base Images](custom-base-images.md) - CUDA base setup
2. [Multi-Stage Builds](multi-stage-builds.md) - Separate build/runtime
3. [CI/CD Integration](ci-cd-integration.md) - Automated GPU builds

#### Private Repository
1. [Secrets and Authentication](secrets-and-auth.md) - Set up credentials
2. [CI/CD Integration](ci-cd-integration.md) - Configure pipeline
3. [Multi-Stage Builds](multi-stage-builds.md) - Optimize (don't leak secrets)

## Related Documentation

### For Learning
Start with comprehensive guides:
- [Basic Usage](../guides/basic-usage.md)
- [Building Images](../guides/building-images.md)
- [HPC Deployment](../guides/hpc-deployment.md)

### For Reference
Look up syntax and options:
- [CLI Reference](../reference/cli.md)
- [Environment Files](../reference/environment-files.md)
- [Configuration](../reference/configuration.md)

### For Examples
See complete workflows:
- [Minimal Python](../examples/minimal-python.md)
- [Data Science](../examples/data-science.md)
- [GPU PyTorch](../examples/gpu-pytorch.md)

## Structure

Each how-to guide follows this pattern:

1. **Overview**: What you'll accomplish
2. **When to Use**: Specific scenarios
3. **Step-by-Step Instructions**: Concrete tasks
4. **Code Examples**: Working code samples
5. **Troubleshooting**: Common issues and solutions
6. **Best Practices**: Do's and don'ts
7. **Related Documentation**: Next steps

## Getting Help

If you can't find what you need:

1. Check if a [Guide](../guides/) covers your topic more broadly
2. Search the [Examples](../examples/) for similar use cases
3. Review [Concepts](../getting-started/concepts.md) for terminology
4. Consult [Reference](../reference/) documentation for syntax

## Contributing

Have a how-to guide to share?

**Format**:
```markdown
# How to: [Task Title]

## Overview
Brief description of the task

## When to Use
Specific scenarios for this approach

## Prerequisites
- Required knowledge
- Required tools

## Steps
1. Clear, actionable steps
2. With code examples
3. And expected outcomes

## Troubleshooting
Common issues and solutions

## Best Practices
✅ Do this
❌ Don't do this

## Related Documentation
[Links to related docs]
```

**Guidelines**:
- Focus on **one specific task**
- Provide **complete, working examples**
- Include **troubleshooting** section
- Test all code samples
- Use concrete examples (not abstract)

---

**Quick Start**: Jump to [Multi-Stage Builds](multi-stage-builds.md) or return to [Documentation Home](../index.md)
