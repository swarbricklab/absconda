# Absconda Implementation Plan

## 1. Objectives
- Deliver a CLI that converts Conda env specs into Dockerfiles with first-class multi-stage support and runtime activation guarantees.
- Provide an optional orchestration path (`absconda build/publish`) that stays lightweight but convenient for CI and Singularity packaging.
- Ship a transparent, extensible policy configuration system so teams can encode image, security, and metadata requirements without forking the tool.
- Implement XDG Base Directory config support for system-wide and user-level settings, enabling team-friendly defaults for registry, organization, and remote builders on shared infrastructure like NCI.
- Support config-based auto-generation of repository names and tags, eliminating the need for repetitive command-line flags while maintaining override flexibility.
- Optimize for Linux/amd64 containers (Docker + Singularity) while keeping Linux/arm64 (Apple Silicon) as a supported secondary target via buildx profiles.
- Support remote build execution so users without Docker privileges (e.g., on NCI) can push workloads to a managed remote builder while still getting fast local validation.

## 2. Workstreams & Milestones
| Phase | Scope | Key Deliverables |
| --- | --- | --- |
| **Phase 0 – Project Setup (Week 0)** | Repo scaffolding, packaging metadata, CI baseline. | `pyproject.toml`, lint/test infra, placeholder CLI entrypoint, automated formatting. |
| **Phase 1 – Core CLI & Parsing (Weeks 1-2)** | Implement `absconda generate` pipeline: env loader, snapshot ingestion, diagnostics scaffolding, XDG config system. | Environment model, config loader with XDG support, validation errors, snapshot diffing, initial unit tests. |
| **Phase 2 – Template Engine & Multi-Stage Support (Weeks 2-4)** | Build Jinja templates + fragment system, implement multi-stage builder/runtime logic, activation script generation. | Default template fragments, `--multi-stage` flag, policy-driven fragment selection, golden tests for Dockerfile output, Singularity verification script. |
| **Phase 3 – Policy Configuration System (Weeks 4-5)** | YAML schema, profile resolution, hook loading, enforcement messages. | `absconda-policy.yaml` parser, sample policies, hook API docs, validation integration tests. |
| **Phase 4 – Build & Publish Commands (Weeks 5-6)** | Orchestrate Docker/Podman builds, registry pushes, optional Singularity pulls. | `absconda build`, `absconda publish`, streaming logs, error handling, e2e tests using local registry/mocked Singularity. |
| **Phase 5 – Docs & Hardening (Weeks 6-7)** | README refresh, spec alignment, troubleshooting and policy guides, release prep. | Updated docs, CI badges, release notes, v0.1 tag. |
| **Phase 6 – Remote Build Server (Weeks 7-8)** | Provision a cloud/on-prem builder VM via Terraform, ship CLI remote mode, document operational runbooks. | Terraform module + state docs, `--remote-builder/--remote-off/--remote-wait` flags, tarball upload agent, low-concurrency locking + wait/retry messaging. |

## 3. Detailed Tasks
1. **Config System**
   - XDG Base Directory implementation with hierarchical loading (/etc/xdg → ~/.config → env vars).
   - AbscondaConfig dataclass with registry, organization, and remote_builders fields.
   - Config merging semantics and validation.
   - Repository name auto-generation from config + environment name.
   - Integration with CLI for optional --repository/--tag flags.
2. **Environment Loader**
   - Schema validation (name, channels, dependencies, prefix).
   - Snapshot diff + warning surfaces.
   - Channel normalization for policy allowlists.
3. **Template System**
   - Fragment registry (base, builder, runtime, activation, extra RUN hooks).
   - Multi-stage flow that packages the env via `conda-pack`, unpacks it in the runtime stage, and records dependency manifests (`lddtree` summaries) for transparency.
   - Entry-point script generator and tests across sh/bash.
   - Optional renv stage that restores `renv.lock` inside the builder env and injects `.Rprofile`/`R_LIBS` wiring in the runtime image.
4. **Policy Engine**
   - Config discovery order and profile merging semantics.
   - Rule evaluation (allowed channels, labels, fragments).
   - Hook sandbox (importlib), error isolation, logging.
5. **Diagnostics & Tooling**
   - Rich CLI errors with remediation hints.
   - `resolution_notes.md` and JSON emission on solver failures.
   - Logging pipeline (`--json-logs`, verbosity flags).
6. **Build Orchestrator**
   - Temp workspace creation, docker buildx invocation, auth passthrough.
   - Tagging/pushing workflow with retries and progress output.
   - Singularity pull integration (detect `singularity`/`apptainer`, optional skip flag).
7. **Remote Build Server**
   - Terraform module (network, firewall, startup script installing Docker + buildx) plus backend state guidance so multiple teammates can share the same builder.
   - CLI flags `--remote-builder`, `--remote-off`, and `--remote-wait` that wrap provisioning/start/stop, expose wait/retry UX, and fall back to local when disabled.
   - `absconda remote` management commands (list/provision/start/stop/status) that reuse `absconda-remote.yaml`, keep secrets in environment variables, and surface builder health before running expensive builds.
   - Context tarball generator (Dockerfile, env artifacts, manifest) and secure transfer via `gcloud compute scp` or SSH with hashed filenames.
   - Remote agent script that untars, runs `docker build`, streams logs back, and writes status markers for the CLI to poll.
   - Simple lease/lock stored in GCS or Firestore so only one build runs at a time; includes watchdog cleanup for abandoned locks and friendly CLI progress output.
8. **Testing & QA**
   - Unit tests for loaders, policy engine, template fragments.
   - Golden Dockerfile fixtures for major profiles (Ubuntu, Rocky, Alpine, GPU).
   - Integration tests running `absconda build` with sample envs.
   - Optional smoke tests that run resulting container to ensure env activation.

## 4. Tooling & Dependencies
- **Runtime**: Python 3.11+, Typer (CLI), Pydantic (config/schema), Jinja2 (templates), Rich (terminal output).
- **Testing**: Pytest, pytest-snapshot for golden files, coverage.
- **Lint/Format**: Ruff, Black, MyPy (or Pyright for TS-style typing), Pre-commit hooks.
- **External CLIs**: Docker/Podman, Singularity/Apptainer, micromamba (downloaded in template, not runtime dep).
- **Builder utilities**: `conda-pack` (installed inside builder stage) for environment relocation; optional `lddtree`/`ldd` for diagnostics.

## 5. Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Conda-pack failures or missing shared libs after unpack | Crashes at runtime | Treat `conda-pack` as required, verify tar integrity, run `lddtree` on key binaries, document any external lib dependencies in `resolution_notes.md`. |
| Policy hooks misbehave | Build failures or security bypass | Run hooks in try/except, surface detailed errors, allow `--no-policy` escape hatch for emergency. |
| Singularity CLI unavailable in CI | Blocks `.sif` generation | Detect binary presence, make `--singularity-out` optional, document installation steps. |
| Auth complexity for publish | User frustration | Delegate login to Docker/Podman, provide clear error guidance, support env-based creds. |
| Remote builder drift or idle cost | Stale Terraform state, unexpected cloud spend | Store Terraform state remotely, add automated stop-after-build logic, and expose `absconda remote status` so teams can verify builder state before running jobs. |

## 6. Documentation Plan
- Expand `README.md` with quickstart, multi-stage explanation, Singularity workflow.
- `docs/spec.md` (living) + `docs/policy.md` describing schema and hook API.
- `docs/templates.md` for fragment catalog and customization tips.
- `docs/renv.md` explaining how to supply `renv.lock`, required flags, and troubleshooting.
- Troubleshooting guide covering solver issues, policy violations, build/push errors.

## 7. Success Criteria
- `absconda generate` produces deterministic Dockerfiles for sample envs and passes golden tests.
- XDG config system loads settings from system-wide and user-level paths with correct precedence.
- `absconda build/publish` auto-generates repository names from config when --repository is omitted.
- Default tag format (YYYYMMDD) is clean and predictable without environment name prefixes.
- `absconda build/publish` successfully builds, tags, and (optionally) pushes a demo image on macOS/Linux runners.
- Generated containers launch with env active (`python -c "import sys; print(sys.prefix)"` matches target path) under Docker and Singularity.
- Multi-arch builds (amd64 + arm64) can be produced via a profile toggle without altering the default Linux/amd64 output.
- Policy engine can block disallowed channels and enforce labels, with clear messages.
- Documentation enables a new user to go from env.yaml to pushed image + Singularity artifact in <30 minutes.
- Renv integration restores an `renv.lock` fixture and exposes R packages without manual activation steps (unit + integration tests enforce this path).
