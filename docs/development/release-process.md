# Release Process

Documentation for Absconda's release workflow.

## Table of Contents

- [Versioning](#versioning)
- [Release Workflow](#release-workflow)
- [Changelog Management](#changelog-management)
- [Release Checklist](#release-checklist)
- [Publishing](#publishing)
- [Hotfix Releases](#hotfix-releases)
- [Post-Release](#post-release)

## Versioning

### Semantic Versioning

Absconda follows [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH

1.2.3
│ │ │
│ │ └─ Patch: Bug fixes, documentation updates
│ └─── Minor: New features (backwards compatible)
└───── Major: Breaking changes
```

**Examples**:

| Change | Old | New | Type |
|--------|-----|-----|------|
| Bug fix | 1.2.3 | 1.2.4 | PATCH |
| New feature | 1.2.3 | 1.3.0 | MINOR |
| Breaking change | 1.2.3 | 2.0.0 | MAJOR |

### Version Bumping Rules

**MAJOR (X.0.0)**:
- Breaking CLI changes
- Incompatible API changes
- Major architectural changes
- Removal of deprecated features

Examples:
- Changing default deployment mode
- Removing CLI commands
- Changing environment file format

**MINOR (0.X.0)**:
- New features (backwards compatible)
- New CLI commands/options
- New deployment modes
- Significant enhancements

Examples:
- Adding remote builder support
- Adding new template system
- Adding policy validation

**PATCH (0.0.X)**:
- Bug fixes
- Documentation updates
- Performance improvements
- Security patches

Examples:
- Fixing Docker build errors
- Updating dependencies
- Documentation improvements

### Pre-release Versions

```
1.2.3-alpha.1    # Alpha release
1.2.3-beta.1     # Beta release
1.2.3-rc.1       # Release candidate
```

Use for:
- Testing major changes
- Getting early feedback
- Validating releases

## Release Workflow

### 1. Planning

**Before starting**:
- Review milestone issues
- Check open PRs
- Update project board
- Coordinate with team

**Create release branch** (for MAJOR/MINOR):

```bash
# Update main
git checkout main
git pull origin main

# Create release branch
git checkout -b release/v1.3.0

# Push branch
git push origin release/v1.3.0
```

For PATCH releases, work on main directly.

### 2. Preparation

#### Update Version

Edit `pyproject.toml`:

```toml
[project]
name = "absconda"
version = "1.3.0"  # Update this
```

#### Update CHANGELOG.md

```markdown
# Changelog

All notable changes to this project will be documented in this file.

## [1.3.0] - 2024-01-15

### Added
- Remote builder support for GCP (#123)
- Policy validation system (#124)
- New deployment mode: export-explicit (#125)

### Changed
- Improved template rendering performance (#126)
- Updated default base image to micromamba:1.5 (#127)

### Fixed
- Docker build failures on Apple Silicon (#128)
- Environment parsing with pip dependencies (#129)

### Documentation
- Added remote builder guide (#130)
- Updated HPC deployment examples (#131)

## [1.2.3] - 2024-01-01

...
```

#### Update Documentation

```bash
# Update version in docs
grep -r "version" docs/

# Update installation instructions
vim docs/getting-started/installation.md

# Update examples if needed
vim docs/examples/*.md
```

#### Run Full Test Suite

```bash
# Unit tests
pytest -m unit

# Integration tests
pytest -m integration

# E2E tests (requires Docker)
pytest -m slow

# All tests with coverage
pytest --cov=absconda --cov-report=html
```

#### Code Quality Checks

```bash
# Format
black src/ tests/

# Lint
flake8 src/ tests/

# Type check
mypy src/

# Security check
pip install safety
safety check
```

### 3. Commit Changes

```bash
# Add changes
git add pyproject.toml CHANGELOG.md docs/

# Commit
git commit -m "chore: prepare release v1.3.0"

# Push
git push origin release/v1.3.0
```

### 4. Create Pull Request

Create PR from release branch to main:

**Title**: `Release v1.3.0`

**Description**:
```markdown
## Release v1.3.0

### Summary
Brief description of release.

### Changes
- Feature 1
- Feature 2
- Bug fix 1

### Checklist
- [x] Version bumped
- [x] CHANGELOG updated
- [x] Tests passing
- [x] Documentation updated
- [x] Migration guide (if needed)

### Breaking Changes
None / List if applicable

### Migration Notes
None / Instructions if needed
```

### 5. Review and Merge

- Code review by maintainers
- CI passes all checks
- Approve and merge to main

### 6. Tag Release

```bash
# Switch to main
git checkout main
git pull origin main

# Create annotated tag
git tag -a v1.3.0 -m "Release v1.3.0

Features:
- Remote builder support
- Policy validation

Fixes:
- Docker build issues
"

# Push tag
git push origin v1.3.0
```

### 7. GitHub Release

Create GitHub Release:

1. Go to https://github.com/swarbricklab/absconda/releases
2. Click "Draft a new release"
3. Choose tag: v1.3.0
4. Generate release notes
5. Add highlights:

```markdown
## What's New in v1.3.0

### 🚀 Features

- **Remote Builders**: Build images on GCP instances (#123)
  - Automatic provisioning with Terraform
  - Cost-optimized with auto-stop
  - SSH-based execution
  
- **Policy Validation**: Enforce security and compliance (#124)
  - Block unauthorized packages
  - Enforce base images
  - Validate resource limits

### 🐛 Bug Fixes

- Fixed Docker build failures on Apple Silicon (#128)
- Fixed environment parsing with pip dependencies (#129)

### 📚 Documentation

- [Remote Builder Guide](docs/guides/remote-builders.md)
- [Policy Reference](docs/reference/policies.md)

### 🙏 Thanks

Thanks to all contributors!

**Full Changelog**: https://github.com/swarbricklab/absconda/compare/v1.2.3...v1.3.0
```

6. Publish release

## Changelog Management

### Format

Based on [Keep a Changelog](https://keepachangelog.com/):

```markdown
# Changelog

## [Unreleased]

### Added
- New features in development

## [1.3.0] - 2024-01-15

### Added
- New features

### Changed
- Changes to existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security updates

[Unreleased]: https://github.com/swarbricklab/absconda/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/swarbricklab/absconda/compare/v1.2.3...v1.3.0
```

### Categories

| Category | When to Use | Example |
|----------|-------------|---------|
| Added | New features | "Added remote builder support" |
| Changed | Changes to existing | "Changed default base image" |
| Deprecated | To be removed | "Deprecated --old-flag" |
| Removed | Removed features | "Removed Python 3.8 support" |
| Fixed | Bug fixes | "Fixed build failures" |
| Security | Security fixes | "Fixed CVE-2024-1234" |

### Writing Good Entries

**Good** ✅:
```markdown
- Added remote builder support for GCP with automatic provisioning (#123)
- Fixed Docker build failures on Apple Silicon (#128)
- Updated micromamba base image to 1.5 for better performance (#127)
```

**Bad** ❌:
```markdown
- Various improvements
- Bug fixes
- Updated stuff
```

### During Development

Keep `## [Unreleased]` section up to date:

```bash
# Add entry after each PR
vim CHANGELOG.md

# Example PR
## [Unreleased]

### Added
- Remote builder support (#123)
```

When releasing, move to versioned section:

```markdown
## [1.3.0] - 2024-01-15

### Added
- Remote builder support (#123)

## [Unreleased]

<!-- Empty for next release -->
```

## Release Checklist

### Pre-release Checklist

- [ ] All milestone issues closed
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Version bumped in `pyproject.toml`
- [ ] CHANGELOG.md updated
- [ ] Migration guide written (if breaking changes)
- [ ] Security audit passed
- [ ] Examples tested
- [ ] Performance benchmarks run (if applicable)
- [ ] Release notes drafted

### Release Checklist

- [ ] Release branch created (MAJOR/MINOR)
- [ ] Changes committed
- [ ] PR created and reviewed
- [ ] CI checks passed
- [ ] PR merged to main
- [ ] Tag created and pushed
- [ ] GitHub Release created
- [ ] PyPI package published
- [ ] Docker images published (if applicable)
- [ ] Documentation deployed
- [ ] Announcement posted

### Post-release Checklist

- [ ] Verify installation: `pip install absconda==X.Y.Z`
- [ ] Verify package on PyPI
- [ ] Smoke test on fresh environment
- [ ] Update main branch protection
- [ ] Close milestone
- [ ] Archive release branch
- [ ] Announce on GitHub Discussions
- [ ] Update issue templates (if needed)
- [ ] Celebrate! 🎉

## Publishing

### PyPI

#### Setup (one-time)

```bash
# Install build tools
pip install build twine

# Configure PyPI token
# Create token at https://pypi.org/manage/account/token/

# Add to ~/.pypirc
[pypi]
username = __token__
password = pypi-...
```

#### Build Distribution

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build distributions
python -m build

# Verify contents
tar -tzf dist/absconda-1.3.0.tar.gz
unzip -l dist/absconda-1.3.0-py3-none-any.whl
```

#### Test Upload (TestPyPI)

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Test installation
pip install --index-url https://test.pypi.org/simple/ absconda==1.3.0

# Verify
absconda --version
```

#### Production Upload

```bash
# Upload to PyPI
twine upload dist/*

# Verify on PyPI
open https://pypi.org/project/absconda/

# Test installation
pip install --upgrade absconda
absconda --version
```

### GitHub Actions (Automated)

`.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install build twine
      
      - name: Build package
        run: python -m build
      
      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
        run: twine upload dist/*
      
      - name: Create GitHub Release
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
          draft: false
          prerelease: false
```

Trigger by pushing tag:

```bash
git tag v1.3.0
git push origin v1.3.0
# GitHub Actions automatically builds and publishes
```

## Hotfix Releases

For urgent fixes to production:

### Process

```bash
# Create hotfix branch from tag
git checkout -b hotfix/v1.2.4 v1.2.3

# Make fix
vim src/absconda/module.py

# Add test
vim tests/test_module.py

# Update version
vim pyproject.toml  # 1.2.3 -> 1.2.4

# Update changelog
vim CHANGELOG.md

# Commit
git commit -am "fix: critical bug in X"

# Test
pytest

# Tag
git tag v1.2.4

# Push
git push origin hotfix/v1.2.4
git push origin v1.2.4

# Merge to main
git checkout main
git merge hotfix/v1.2.4
git push origin main

# Merge to develop (if using gitflow)
git checkout develop
git merge hotfix/v1.2.4
git push origin develop
```

### Hotfix Checklist

- [ ] Critical bug identified
- [ ] Hotfix branch created
- [ ] Fix implemented
- [ ] Tests added
- [ ] Version bumped (PATCH)
- [ ] CHANGELOG updated
- [ ] Tests passing
- [ ] Tag created
- [ ] Released to PyPI
- [ ] Merged to main
- [ ] Merged to develop

## Post-Release

### Verification

```bash
# Install from PyPI
pip install --upgrade absconda

# Verify version
absconda --version

# Smoke test
absconda build --file examples/minimal-env.yaml --tag test:latest

# Check documentation
open https://swarbricklab.github.io/absconda/
```

### Communication

#### GitHub Discussions

Post announcement:

```markdown
**Title**: Absconda v1.3.0 Released 🎉

**Category**: Announcements

**Body**:
We're excited to announce Absconda v1.3.0!

## Highlights

- 🚀 Remote builder support for GCP
- 🔒 Policy validation system
- 📦 New deployment mode

## Installation

```bash
pip install --upgrade absconda
```

## Documentation

- [Release Notes](https://github.com/swarbricklab/absconda/releases/tag/v1.3.0)
- [Migration Guide](docs/guides/upgrading.md)

## Feedback

Please report any issues or share feedback!
```

#### Update README

If major features added:

```bash
vim README.md
# Update feature list, examples, etc.
git commit -am "docs: update README for v1.3.0"
git push
```

### Maintenance

```bash
# Close milestone
open https://github.com/swarbricklab/absconda/milestones

# Archive release branch
git branch -d release/v1.3.0
git push origin --delete release/v1.3.0

# Create next milestone
# v1.4.0 or v2.0.0
```

### Monitoring

Watch for issues after release:

- GitHub Issues
- PyPI download stats
- User feedback in Discussions
- CI/CD pipeline

## Release Calendar

### Schedule

**Minor releases**: Every 2-3 months
**Patch releases**: As needed (within days)
**Major releases**: When breaking changes needed

### Planning

| Version | Target Date | Focus |
|---------|-------------|-------|
| v1.3.0 | 2024-01-15 | Remote builders |
| v1.4.0 | 2024-03-15 | Advanced policies |
| v2.0.0 | 2024-06-15 | Template engine rewrite |

### Feature Freeze

**1 week before release**:
- No new features
- Bug fixes only
- Documentation finalization
- Testing

## Troubleshooting

### Failed PyPI Upload

```bash
# Check credentials
twine check dist/*

# Verify token
cat ~/.pypirc

# Try manual upload
twine upload --verbose dist/*
```

### Version Conflicts

```bash
# Version already exists on PyPI
# Must bump version and create new tag
vim pyproject.toml  # Bump to 1.3.1
git commit -am "chore: bump version to 1.3.1"
git tag v1.3.1
python -m build
twine upload dist/*
```

### Failed CI

```bash
# Check GitHub Actions
open https://github.com/swarbricklab/absconda/actions

# Re-run failed jobs
# Or fix and push new commit
```

## Best Practices

### Do's

✅ Follow semantic versioning strictly
✅ Update CHANGELOG for every PR
✅ Test thoroughly before release
✅ Write clear release notes
✅ Communicate changes clearly
✅ Keep main branch stable
✅ Use release branches for MAJOR/MINOR

### Don'ts

❌ Don't skip testing
❌ Don't release on Friday (allow time for hotfixes)
❌ Don't rush releases
❌ Don't ignore CI failures
❌ Don't forget to update documentation
❌ Don't delete release tags
❌ Don't make breaking changes in MINOR/PATCH

## Resources

- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github)
- [Python Packaging Guide](https://packaging.python.org/)

## Quick Reference

```bash
# Version bump
vim pyproject.toml

# Update changelog
vim CHANGELOG.md

# Commit
git commit -am "chore: prepare release v1.3.0"

# Tag
git tag -a v1.3.0 -m "Release v1.3.0"
git push origin v1.3.0

# Build
python -m build

# Publish
twine upload dist/*

# Verify
pip install --upgrade absconda
absconda --version
```

---

**Questions?** See [Contributing Guide](contributing.md) or ask in [Discussions](https://github.com/swarbricklab/absconda/discussions)
