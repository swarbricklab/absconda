# Absconda Testing Strategy

The goal of Absconda’s test suite is to prove that every generated artifact—from Dockerfiles to Singularity images—behaves the same way a human-authored environment would, across Linux-first deployments and optional Apple Silicon builds. This document explains the strategy in plain language so contributors know what to expect before writing code.

## 1. Guiding Principles
1. **Linux/amd64 is the reference platform.** Most tests (unit, integration, e2e) execute on Linux runners because Docker and Singularity support there is most mature. Apple Silicon (linux/arm64) coverage is added through targeted multi-arch builds once the Linux path is green.
2. **Reproducible environments.** Every test that involves Conda uses pinned fixture files and runs under `micromamba` to guarantee fast, deterministic resolution.
3. **Single source of truth.** Tests consume the real CLI (`absconda generate|build|publish`) instead of private helper functions whenever feasible, so user-facing behavior is validated directly.
4. **Fast feedback, deep confidence.** We mix lightweight unit tests with slower nightly end-to-end runs (e.g., Singularity conversions) to keep the inner loop quick without sacrificing coverage.

## 2. Test Layers
### 2.1 Unit Tests
- **Environment Loader & Snapshot Diffing:** Feed intentionally malformed `env.yaml` files to confirm validation messages and snapshot hints are readable.
- **Policy Engine:** Verify that `absconda-policy.yaml` parsing, profile inheritance, and hook invocation work as expected. Mock hooks capture edge cases (exceptions, bad return values) without requiring real policy files.
- **Template Fragments:** Render individual fragments (builder base, runtime activation, renv stub) in isolation to ensure variable substitution and conditionals behave across profiles.
- **CLI Parsing:** Use Typer’s testing utilities to confirm flags like `--multi-stage`, `--profile`, and `--renv-lock` map to the right internal options.

### 2.2 Snapshot/Golden Tests
- Maintain fixture directories containing `env.yaml`, optional `renv.lock`, snapshot exports, and expected Dockerfiles.
- On each run, `absconda generate` produces output that is compared byte-for-byte with stored “golden” files. Any drift (e.g., due to template edits) must be reviewed and approved.
- Separate fixtures cover Ubuntu default, Rocky profile, Alpine experimental, GPU hints, and the renv extension (once implemented).

### 2.3 Integration Tests
- **Dockerfile to Image:** Use temporary directories to run `absconda build --image test/absconda:fixture`, then `docker run` the resulting image to validate that `python - <<'EOF'` snippets report the expected `sys.prefix`.
- **Singularity Path:** When `singularity`/`apptainer` is installed, run `absconda publish --singularity-out tmp.sif ...` and execute a trivial script (`python -c ...`, `R -q -e ...`). These tests are optional/skipped on platforms where Singularity is unavailable.
- **Policy Enforcement:** Provide sample policies that intentionally fail (disallowed channel, missing label) and assert that `absconda validate` exits non-zero with actionable text.
- **Multi-arch Smoke:** Trigger `docker buildx build --platform linux/amd64,linux/arm64 --load` for a minimal env to ensure the orchestrator respects the profile toggle. These run in CI environments that support QEMU/buildx (nightly, not per-commit).

### 2.4 End-to-End Scenarios
- **Snakemake Workflow:** Include a tiny Snakemake pipeline referencing the built image via the `container:` field, run it under Singularity, and confirm the env stays active without manual activation steps.
- **Renv Restoration (future milestone):** With `--renv-lock` enabled, run `R -q -e 'library(pkgname)'` inside the container to ensure renv’s library path comes preconfigured.
- **Failure Playbooks:** Trigger solver failures on purpose (e.g., nonexistent package) and assert that `resolution_notes.md` contains solver traces, snapshot diffs, and next-step guidance.

## 3. Tooling & Infrastructure
- **Test Runner:** Pytest with plugins for snapshot testing (`pytest-snapshot` or `approvals`).
- **Container Runtimes:** Docker or Podman for most integration tests; Singularity/Apptainer is optional but encouraged in nightly CI.
- **Mocking External CLIs:** When Docker/Singularity aren’t available, tests swap in lightweight mocks so the build orchestrator can still be exercised without performing real builds.
- **CI Matrix:**
  - Linux/amd64 (required) – full suite.
  - Linux/arm64 (optional) – smoke tests + golden checks once cross-build support lands.
  - macOS (optional) – unit tests and CLI parsing only, to keep coverage broad.

## 4. Quality Gates
Before a change merges:
1. **Unit & Golden Tests** must pass on every PR.
2. **Integration Tests** (Docker build/run) must pass on at least one Linux runner per PR; Singularity and multi-arch tests can run nightly if runtime is prohibitive.
3. **Linters & Type Checks** (Ruff, MyPy) enforced via pre-commit/CI.
4. **Documentation Checks**: When spec or policy docs change, CI verifies Markdown links and code examples (where possible).

## 5. Manual Verification
Some scenarios remain manual but scripted:
- **NCI parity check:** Periodically convert a published Docker image to a Singularity SIF on NCI infrastructure to ensure there are no environment-specific regressions.
- **Security policy review:** When org-specific policies change, security reviewers can run `absconda validate --policy new.yaml --json-logs` to audit enforcement without touching code.

## 6. Reporting & Artifacts
- Test runs emit structured logs that include the policy profile, template version, and Git SHA, aiding reproducibility.
- On failure, the CI pipeline uploads `resolution_notes.md`, Docker build logs, and Singularity transcripts as artifacts for debugging.

By adhering to this layered approach we get quick feedback for contributors, maintain confidence in Linux/Singularity behavior, and leave clear expansion points for renv and multi-arch support as the project grows.
