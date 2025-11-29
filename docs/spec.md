# Absconda Specification

## 1. Overview
Absconda is a command-line utility that consumes a Conda environment definition (YAML) and emits a reproducible Dockerfile. It bridges data science reproducibility gaps by allowing teams to promote a vetted environment directly into container form without hand-authoring Dockerfiles.

### Goals
- **Zero-friction handoff** from Conda environments to Docker images.
- **Deterministic builds** that pin exact package versions and base images.
- **Team-ready ergonomics**: sensible defaults, guardrails, and clear diagnostics.

### Non-goals
- Acting as a generic Dockerfile templating engine for non-Conda projects.
- Replacing full-featured CI/CD or registry tooling; the built-in `build`/`publish` commands are thin wrappers around Docker/Podman/Singularity and stay intentionally minimal.

### Target Platforms
- **Primary**: Linux/amd64 containers destined for Docker and Singularity (NCI focus). All templates, policy profiles, and tests default to this target.
- **Secondary**: Linux/arm64 (Apple Silicon) images produced via multi-arch builds or dedicated profiles. Mac execution is treated as a best-effort extension that reuses the Linux templates wherever possible.

## 2. Personas & Use Cases
| Persona | Needs | Representative Scenarios |
| --- | --- | --- |
| Data Scientist | Quickly containerize notebooks for sharing or deployment. | Generates a Dockerfile from `env.yaml`, tweaks only runtime entrypoints. |
| MLOps Engineer | Enforces consistent base images and build policy. | Applies organization policies (base images, labels, extra packages) while reviewing generated Dockerfiles. |
| Platform Engineer | Integrates Absconda into CI pipelines. | Runs Absconda headlessly to regenerate Dockerfiles whenever `env.yaml` changes. |

## 3. User Stories
1. As a data scientist, I can run `absconda --file env.yaml > Dockerfile` to produce a Dockerfile that installs all Conda dependencies and activates the environment.
2. As an MLOps engineer, I can specify metadata (labels, maintainer, default shell) via command-line flags or config files.
3. As a platform engineer, I can run Absconda in CI to fail fast when the environment file is invalid or references unavailable channels.
4. As any user, I can validate the Dockerfile before building via a `--dry-run` flag that performs schema and package resolution checks.

## 4. Functional Requirements
1. **Input Handling**
   - Accepts a path to a Conda environment YAML via `--file/-f` (default `env.yaml`).
   - Validates YAML structure (name, channels, dependencies) and surfaces actionable errors.
   - Supports optional layered overrides through `--var key=value` pairs that can replace tokens inside templates.
   - Optionally ingests a snapshot (full `conda env export` output) via `--snapshot path/to/export.yaml`; Absconda stores the snapshot alongside the generated Dockerfile and uses it for pre-flight checks and conflict hints.
   - Reads an optional policy configuration file (`absconda-policy.yaml`) that defines image profiles, allowed channels, required labels, and hook references. CLI flag `--policy PATH` overrides the default search path.

2. **Output Generation**
   - Writes the Dockerfile to STDOUT by default; optional `--output` path writes directly to disk.
   - Enables deterministic ordering of RUN steps and environment variables.
   - Supports `--base-image` override; otherwise infers from environment (e.g., `condaforge/miniforge3` for linux-64).

3. **Templating & Customization**
   - Provides built-in template covering common Python workflows (micromamba or mamba-based installs).
   - Allows custom template path via `--template path/to/template.jinja` with documented placeholders.
   - Inserts optional build metadata (labels, maintainer, git SHA) via CLI flags or environment variables.
   - Supports multi-stage builds via `--multi-stage` (or policy profile) where a builder stage solves the environment and a runtime stage copies the resulting `/opt/conda/envs/<name>` plus shared libraries and activation script. Multi-stage is the default; single-stage can be forced when policy allows.
   - Emits composable template fragments (base image block, dependency install block, runtime activation block). Policy profiles declaratively select fragments (e.g., `non_root_user`, `apt_cleanup`, `gpu_drivers`).

4. **Validation & Diagnostics**
   - Offers `absconda validate env.yaml` subcommand for schema checks without generating output.
   - Emits warnings for unpinned package versions, missing channels, or unsupported platforms.
   - Returns non-zero exit codes on validation or generation failures.
   - Evaluates policy rules: channel allowlists, required metadata, enforced fragments, and optional security scanners defined in `absconda-policy.yaml`. Violations are surfaced with actionable remediation steps.

5. **Quality of Life**
   - `--help` flag documents all options with examples.
   - `--version` prints semantic version (pulled from package metadata).
   - Supports tracing via `ABS_CONDA_LOG=debug` environment variable.

## 5. Non-Functional Requirements
- **Performance**: Generate Dockerfile for typical env (<150 deps) in <1s on modern hardware.
- **Reliability**: Unit coverage for YAML parsing and template rendering; golden tests for Dockerfile output.
- **Portability**: Works on macOS, Linux, Windows (WSL) with Python 3.9+ runtime.
- **Security**: No remote code execution; only reads local files and optional HTTP(S) channel metadata.
- **Observability**: Structured logs (JSON) when `--json-logs` is enabled.

## 6. CLI Contract
```
Usage: absconda [COMMAND] [OPTIONS]

Commands:
   generate   (default) Generate Dockerfile from Conda env
   validate   Check env file without output
   build      Render Dockerfile, run docker build, optionally tag image
   publish    Build (if needed) and push image to registry; can emit Singularity .sif via `singularity pull`

Options:
  -f, --file PATH           Conda environment file (default: env.yaml)
      --output PATH         Write Dockerfile to path instead of STDOUT
      --base-image NAME     Override base image (default inferred)
      --template PATH       Custom template file
   --policy PATH         Path to policy config (default: absconda-policy.yaml)
   --profile NAME        Policy profile to apply (default: profile in config)
   --multi-stage         Force multi-stage builder/runtime template
   --builder-base NAME   Base image for builder stage (overrides profile)
   --runtime-base NAME   Base image for runtime stage (overrides profile)
   --image NAME          Target image reference for build/publish commands
   --push                When used with build, push image after successful build
   --singularity-out PATH  Produce Singularity .sif via `singularity pull` (publish)
      --label KEY=VALUE     Repeatable Docker label entries
      --build-arg KEY=VALUE Repeatable build args
      --var KEY=VALUE       Template variable overrides
      --dry-run             Validate without writing
      --json-logs           Emit structured logs
  -q, --quiet               Suppress non-essential output
  -v, --verbose             Increase log verbosity (repeatable)
      --version             Show version and exit
  -h, --help                Show help message
```

## 7. Architecture & Components
1. **CLI Frontend** (Typer/Click): parses arguments, handles subcommands.
2. **Environment Loader**: reads YAML, applies overrides, resolves channels.
3. **Policy Loader**: parses `absconda-policy.yaml`, resolves profiles, and dynamically imports optional hook modules (e.g., `policy_hooks.py`).
4. **Template Engine** (Jinja2): renders Dockerfile sections (base layer, multi-stage fragments, runtime activation, entrypoint).
5. **Diagnostics Module**: aggregates warnings/errors, maps to exit codes (including policy compliance failures).
6. **Build Orchestrator**: when invoked via `absconda build/publish`, shells out to Docker/Podman, handles tagging, pushes, and optional Singularity pulls while streaming logs.
7. **Writers**: stream output either to STDOUT or file; ensure atomic writes.

### Data Flow
1. CLI receives file path → Environment Loader parses YAML into internal model.
2. Validation passes results to Diagnostics.
3. Template Engine consumes model + options to render Dockerfile string.
4. Writer outputs string to requested destination.

### Extensibility Hooks
- Template plugins to inject organization-specific steps (e.g., security scanning, apt installs).
- Channel resolvers for private Conda repositories.
- Policy hook API: Python module exposing `before_render(context)`/`after_validate(model)` functions referenced from the config file.
- Output adapters (future) for OCI build recipes.

## 8. Error Handling & Edge Cases
- Missing file → exit code 2 with message "Environment file not found".
- Invalid YAML → display line/column details from parser.
- Unsupported OS arch requested → warn and default to known base image.
- Empty dependencies list → still produce valid Dockerfile with just base image and metadata.
- Duplicate package specs → deduplicate while preserving order, warn user.

## 9. Testing Strategy
- **Unit Tests**: YAML parsing, CLI flag parsing, template rendering, diagnostics.
- **Golden Tests**: sample `env.yaml` fixtures vs. expected Dockerfile outputs.
- **Integration Tests**: run `absconda generate` in temporary dirs, ensure idempotency and exit codes.
- **Static Analysis**: linting (ruff/flake8), typing (mypy/pyright).

## 10. Release Plan & Roadmap
1. **MVP (v0.1)**
   - CLI with `generate` command, default template, base image inference.
   - Basic diagnostics and unit tests.
2. **v0.2**
   - Custom template support, `validate` command, logging improvements.
3. **v0.3**
   - Structured logging, policy hooks, CI integration guide.
4. **v1.0**
   - Stable API/CLI, comprehensive docs, signed releases.

## 11. Documentation Deliverables
- Quickstart in `README.md` with examples.
- Detailed CLI reference (autogenerated help).
- Template authoring guide explaining placeholders and best practices.
- Troubleshooting section covering common validation errors.
- Policy configuration guide explaining profile schema, hook integration, and sample security extensions.

## 12. Environment Resolution Strategy
- **Loose environment files remain the source of truth.** Absconda treats minimally pinned `env.yaml` files as canonical specs, leaning on `mamba`/`conda` to solve them inside the Docker build. Warnings (not hard failures) are emitted for unpinned specs so teams remain aware of the potential drift.
- **Snapshots as hints, not locks.** A user-supplied snapshot (`--snapshot exported-env.yaml`) is copied next to the generated Dockerfile and hashed into the image as metadata. During `absconda validate`, the snapshot is diffed against the loose spec to flag major version deltas and suggest candidate pins but the solver still runs against the loose spec.
- **Conflict guidance for humans or agents.** When the solver fails, Absconda emits a `resolution_notes.md` artifact (and optional JSON) that: 1) surfaces the exact solver trace, 2) points to the snapshot for comparison, and 3) outlines a repeatable checklist an on-call engineer or automation agent can follow (e.g., "compare package X between env.yaml and snapshot, try pinning to snapshot version, rerun absconda").
- **Base image policy.** Builder stages continue to use `mambaorg/micromamba:1.5.5`, while runtime stages now default to the slimmer `debian:bookworm-slim` to keep artifacts lean without sacrificing glibc compatibility. Users can still point to Rocky-Linux or other bases via policy profiles/CLI flags, and experimental Alpine profiles keep their extra guardrails (musl compatibility checks, glibc shims).
- **Solver customization hooks.** Flags expose solver choice (`--solver mamba|conda`), parallelism, and remote channel allowances so CI can mimic local behavior.

## 13. Container Runtime & Singularity Compatibility
- **Activation baked into the image.** Runtime stage exports `CONDA_PREFIX=/opt/conda/envs/<name>`, `CONDA_DEFAULT_ENV=<name>`, and prepends `/opt/conda/envs/<name>/bin` plus `/opt/conda/bin` to PATH. A lightweight `/usr/local/bin/absconda-entrypoint` script (copied from the builder stage) simply re-asserts these variables and `exec`s the requested command. Docker containers inherit the entrypoint, while Singularity conversions still observe the ENV defaults, so the environment is "on" even without shell hooks.
- **Multi-stage layout.** Default profile uses two stages: (1) **builder** (`mambaorg/micromamba:1.5.5`) installs micromamba, solves the loose env, and captures optional snapshot metadata; (2) **runtime** (`debian:bookworm-slim`) copies `/opt/conda/envs/<name>`, `/opt/conda/condabin`, shared libraries discovered via `ldd`, the entrypoint script, and any required OS packages. Additional fragments (e.g., GPU, Alpine runtime) can expand this pattern.
- **Singularity workflow.** `absconda publish --singularity-out env.sif --image ghcr.io/org/proj:tag` builds/pushes the Docker image, then shells out to `singularity pull docker://ghcr.io/org/proj:tag` to create a SIF artifact for NCI. Documentation includes a verification command (`singularity exec env.sif python -c "import sys; print(sys.prefix)"`) and guidance for Snakemake users referencing images via the `container:` field.
- **No manual activation required.** Because activation is purely ENV-based (no `conda init`), images behave consistently under Docker, Apptainer/Singularity, and workflow managers like Snakemake or Nextflow.
- **Conda-pack as the default mover.** Instead of bespoke copy logic, the builder stage runs `conda-pack` to create a relocatable tarball of the solved environment. The runtime stage unpacks it under `/opt/conda/envs/<name>` and applies the activation script. This keeps runtime images lean, guarantees shared objects travel with the env, and limits the number of code paths we must test. Optional validation still runs `lddtree` on representative binaries to document external dependencies inside `resolution_notes.md`.

## 14. Policy Configuration System
- **Config file:** Absconda searches for `absconda-policy.yaml` (current directory → repo root → `~/.config/absconda/`). The file declares version, named profiles, channel policies, required template fragments, metadata rules, and optional security scanners. CLI `--policy` overrides the path.
- **Profiles:** Each profile (e.g., `default`, `rocky`, `hardened-gpu`) specifies builder/runtime base images, whether multi-stage is mandatory, env prefix, required labels, allowed channels, and default fragments (`non_root_user`, `apt_cleanup`, `gpu_drivers`). Users pick a profile via `--profile` or rely on the config's default.
- **Hooks:** The config can reference a Python module (e.g., `policy_hooks.py`) that exposes functions like `before_render(context)`, `after_validate(model)`, or `on_build_finished(result)`. Hooks can inject custom RUN instructions, enforce bespoke audits, or emit additional artifacts without forking Absconda.
- **Transparency & extensibility:** Policies are just YAML + optional Python, living alongside project code so security experts can review/extend them. Absconda surfaces every enforced rule in `absconda validate` output and exit codes, keeping teams informed when a policy blocks a build.

## 15. Build & Publish Workflow
- **Generate-first philosophy.** `absconda generate` remains the core command that outputs Dockerfiles for any environment. Users can still redirect to `docker build - < Dockerfile` if they prefer manual control.
- **Optional orchestration.** `absconda build` and `absconda publish` wrap Docker/Podman and Singularity CLIs. `build` renders templates to a temp scratch dir, runs `docker buildx build`, applies tags, and optionally pushes when `--push` is set. `publish` ensures the image exists (building if necessary), pushes to the configured registry, and optionally runs `singularity pull` to produce a `.sif` artifact.
- **Pluggable tooling.** The build orchestrator respects environment variables (`DOCKER_HOST`, `APPTAINER_CACHEDIR`) and surfaces exact commands in logs for reproducibility. Future adapters (e.g., `--builder podman`, `--singularity apptainer`) can reuse the same abstraction layer.
- **Delegated authentication.** Absconda does not manage registry credentials directly; it surfaces helpful messages if Docker/Podman lacks a login and points users to the relevant CLI commands, keeping the security model simple.

## 16. Planned Extensions
- **Conda + pip + renv environments.** Users will be able to supply both `env.yaml` and `renv.lock`. Absconda's builder stage installs micromamba, restores the Conda env, then runs `Rscript -e 'renv::restore()'` inside the env to materialize R packages. The runtime stage copies both the packed Conda env (via `conda-pack`) and the `renv/library` tree, installs a minimal `.Rprofile` that auto-loads renv, and ensures `R_LIBS_SITE` points at the restored library so no manual activation is required. This feature will be guarded behind a policy fragment/CLI flag (`--renv-lock`) until stabilized.
- **Multi-arch publishing.** Future profiles can enable Docker buildx multi-arch output (linux/amd64 + linux/arm64) so Apple Silicon users get native performance while the default remains Linux.

## 17. Open Questions
- Should `absconda publish` also support OCI registries that require OIDC/device flow login, or do we delegate auth entirely to Docker/Podman (current plan favors delegation)?
- What criteria signal readiness to promote the renv integration from experimental to default (test coverage, sample workloads, user opt-in rate)?
