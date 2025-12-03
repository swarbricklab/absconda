# Absconda Specification

## 1. Overview
Absconda is a command-line utility that consumes a Conda environment definition (YAML) and emits a reproducible Dockerfile. It bridges data science reproducibility gaps by allowing teams to promote a vetted environment directly into container form without hand-authoring Dockerfiles.

Many users run Absconda from restricted HPC systems (e.g., NCI) where Docker and root privileges are unavailable. To keep those teams unblocked, Absconda can ship Dockerfiles to a managed remote build server (for example, a cloud VM) while still doing validation and rendering locally.

3. As a platform engineer, I can run Absconda in CI to fail fast when the environment file is invalid or references unavailable channels.
4. As a platform or infrastructure engineer, I can point `absconda build/publish` at a managed remote build server (any cloud or on-prem host) so heavy Docker builds happen remotely while validation still runs locally.
5. As any user, I can validate the Dockerfile before building via a `--dry-run` flag that performs schema and package resolution checks.
- **Zero-friction handoff** from Conda environments to Docker images.
- **Fast-path for existing environments**: build directly from conda-packed tarballs, skipping solver overhead entirely.
- **Deterministic builds** that pin exact package versions and base images.
- **Team-ready ergonomics**: sensible defaults, guardrails, and clear diagnostics.
- **Remote-friendly builds**: when local Docker isn't allowed, Absconda can offload the Docker build to a remote host without sacrificing the local feedback loop.

### Non-goals
   - When remote builds are requested, always performs validation and Dockerfile rendering locally before contacting the build server to minimize wasted/cloud costs.
- Acting as a generic Dockerfile templating engine for non-Conda projects.
- Replacing full-featured CI/CD or registry tooling; the built-in `build`/`publish` commands are thin wrappers around Docker/Podman/Singularity and stay intentionally minimal.

### Target Platforms
- **Primary**: Linux/amd64 containers destined for Docker and Singularity (NCI focus). All templates, policy profiles, and tests default to this target.
- **Secondary**: Linux/arm64 (Apple Silicon) images produced via multi-arch builds or dedicated profiles. Mac execution is treated as a best-effort extension that reuses the Linux templates wherever possible.

   --remote-builder NAME  Optional remote builder target (e.g., `default-remote`); falls back to local Docker when omitted
     --remote-off          Shut down the remote builder VM after the run completes (best-effort)
## 2. Personas & Use Cases
| Persona | Needs | Representative Scenarios |
| --- | --- | --- |
| Data Scientist | Quickly containerize notebooks for sharing or deployment. | Generates a Dockerfile from `env.yaml`, tweaks only runtime entrypoints. Alternatively, conda-packs a working local environment and uses `--tarball` for instant Docker builds. |
6. **Build Orchestrator**: when invoked via `absconda build/publish`, shells out to Docker/Podman, handles tagging, pushes, and optional Singularity pulls while streaming logs.
7. **Remote Build Coordinator**: optional module that provisions, starts, labels, and tears down remote build servers (initially a single cloud VM with Docker + Buildx). It relies on Terraform or the provider’s CLI/SDK to ensure the VM exists, performs health checks, copies rendered Dockerfiles/context via `scp`/`rsync`, and proxies logs/events back to the CLI. In the low-concurrency default, the coordinator manages a simple lease/lock so only one build runs at a time; callers can wait or retry rather than scaling out automatically.
| Platform Engineer | Integrates Absconda into CI pipelines. | Runs Absconda headlessly to regenerate Dockerfiles whenever `env.yaml` changes. |

- **Remote build servers.** Users can opt into a `--remote-builder` profile (starting with `default-remote`) that provisions or resumes a VM on their chosen provider (cloud or on-prem) preloaded with Docker Engine and Buildx. Absconda always performs validation and Dockerfile rendering locally, then streams the build context to the VM via SSH/SCP, triggers the Docker build remotely, and forwards logs in real time. After the build/publish operation, the coordinator can optionally stop the VM (`--remote-off`) to avoid lingering costs.
- **Infrastructure-as-code workflow.** Provisioning for the remote builder relies on Terraform modules (or equivalent IaC) checked into the repository. The CLI shell-outs to `terraform apply/destroy` or calls the provider’s CLI/SDK when a builder needs to be created on-demand. Remote builders store a small metadata file that indicates their active/inactive status so the CLI can skip re-provisioning and focus on start/stop operations.
1. As a data scientist, I can run `absconda --file env.yaml > Dockerfile` to produce a Dockerfile that installs all Conda dependencies and activates the environment.
2. As an MLOps engineer, I can specify metadata (labels, maintainer, default shell) via command-line flags or config files.
3. As a user with an existing working environment, I can run `absconda --tarball my-env.tar.gz` to build a Docker image directly from a conda-packed tarball, skipping the environment solving step entirely.
- **Autoscaling builders.** Build server orchestration expands beyond a single VM to a small pool of on-demand instances (managed instance groups, auto-scaling sets, Kubernetes jobs, etc.) so concurrent `absconda build` invocations can queue or burst safely.
4. As any user, I can validate the Dockerfile before building via a `--dry-run` flag that performs schema and package resolution checks.

## 4. Functional Requirements
1. **Input Handling**
   - Accepts a path to a Conda environment YAML via `--file/-f` (default `env.yaml`).
   - **Alternatively**, accepts a pre-packed conda tarball via `--tarball/-t PATH` for fast Docker builds from existing environments. When `--tarball` is specified, `--file` becomes optional (for metadata extraction) and environment solving is skipped entirely.
   - Validates YAML structure (name, channels, dependencies) and surfaces actionable errors.
   - Supports optional layered overrides through `--var key=value` pairs that can replace tokens inside templates.
   - Optionally ingests a snapshot (full `conda env export` output) via `--snapshot path/to/export.yaml`; Absconda stores the snapshot alongside the generated Dockerfile and uses it for pre-flight checks and conflict hints.
   - Reads an optional policy configuration file (`absconda-policy.yaml`) that defines image profiles, allowed channels, required labels, and hook references. CLI flag `--policy PATH` overrides the default search path.
   - When building from a tarball, the tarball is copied into the Docker build context and unpacked directly in the Dockerfile, avoiding conda/mamba solver invocations.

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
   - Emits a deterministic build-context tarball (rendered Dockerfile, env files, helper assets, manifest) whenever a remote build is requested so the remote host receives identical inputs to local `docker build`.

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
   build      Render Dockerfile, run docker build, optionally push
   publish    Build, push, and optionally emit a Singularity .sif via `singularity pull`
   wrap       Generate wrapper scripts for container commands
   module     Generate environment module file

Common options:
  -f, --file PATH           Conda environment file (default: env.yaml)
  -t, --tarball PATH        Pre-packed conda tarball (alternative to --file; skips solving)
     --snapshot PATH       Optional exported snapshot for validation hints
     --output PATH         Write Dockerfile to path instead of STDOUT (generate)
     --template PATH       Custom template file
     --policy PATH         Policy config (default: absconda-policy.yaml)
     --profile NAME        Policy profile to apply (default defined in config)
     --builder-base NAME   Base image for builder stage (overrides profile)
     --runtime-base NAME   Base image for runtime stage (overrides profile)
     --multi-stage/--single-stage   Force template selection (otherwise profile default)
     --var KEY=VALUE       Template variable overrides
     --json-logs           Emit structured logs
  -q, --quiet               Suppress non-essential output
  -v, --verbose             Increase log verbosity (repeatable)
     --version             Show version and exit
  -h, --help                Show help message

Build/publish specific options:
     --repository TEXT     Target OCI repository (optional; defaults to {registry}/{organization}/{env-name} from config)
     --tag TEXT            Image tag override; defaults to `YYYYMMDD`
     --context PATH        Docker build context directory (default: current directory)
     --push                Push image after build (build command only; publish always pushes)
   --remote-builder NAME  Optional remote builder target (e.g., `default-remote`); falls back to local Docker when omitted
   --remote-off          Shut down the remote builder VM after the run completes (best-effort)
   --remote-wait SECONDS  Max seconds to wait for a busy remote builder before failing (default: generously high due to low expected concurrency)
     --singularity-out PATH  Emit `.sif` artifact via `singularity pull` (publish)

Remote builder management commands:

```
absconda remote list [-c PATH]
absconda remote provision <builder> [--config PATH]
absconda remote start|stop <builder> [--config PATH]
absconda remote status <builder> [--config PATH]
```

All remote subcommands share the same config discovery order as `--remote-builder` and simply execute the commands defined in `absconda-remote.yaml`, making it easy to wrap Terraform or cloud CLIs without duplicating logic.

Wrapper generation commands:

```
absconda wrap --image IMAGE_REF --commands CMD1,CMD2 [OPTIONS]
  --image TEXT              Container image reference (e.g., ghcr.io/org/env:tag)
  --commands TEXT           Comma-separated list of commands to wrap
  --runtime TEXT            Container runtime: singularity (default) or docker
  --output-dir PATH         Directory for wrapper scripts (default from config)
  --image-cache PATH        SIF cache directory for Singularity (default from config)
  --extra-mounts PATH,PATH  Additional volume mounts (comma-separated paths)
  --env VAR1,VAR2           Additional environment variables to pass through
  --gpu                     Enable GPU support (--nv for Singularity, --gpus all for Docker)

absconda module --name NAME --wrapper-dir PATH [OPTIONS]
  --name TEXT               Module name with version (e.g., myenv/1.0)
  --wrapper-dir PATH        Directory containing wrapper scripts
  --output-dir PATH         Directory for module file (default from config)
  --description TEXT        Module description for help text
  --image TEXT              Container image reference (for metadata)
  --runtime TEXT            Container runtime: singularity or docker
```

## 7. Architecture & Components
1. **CLI Frontend** (Typer/Click): parses arguments, handles subcommands.
2. **Config System**: implements XDG Base Directory specification, loading configuration from `/etc/xdg/absconda/config.yaml` (system-wide) and `~/.config/absconda/config.yaml` (user-level) with hierarchical merging. Provides registry and organization defaults for auto-generating repository names.
3. **Environment Loader**: reads YAML, applies overrides, resolves channels. Also handles tarball input mode where it copies the tarball into build context and generates a simplified Dockerfile that unpacks the tarball directly.
4. **Policy Loader**: parses `absconda-policy.yaml`, resolves profiles, and dynamically imports optional hook modules (e.g., `policy_hooks.py`).
5. **Template Engine** (Jinja2): renders Dockerfile sections (base layer, multi-stage fragments, runtime activation, entrypoint).
6. **Diagnostics Module**: aggregates warnings/errors, maps to exit codes (including policy compliance failures).
7. **Build Orchestrator**: when invoked via `absconda build/publish`, shells out to Docker/Podman, handles tagging, pushes, and optional Singularity pulls while streaming logs.
8. **Writers**: stream output either to STDOUT or file; ensure atomic writes.

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

## 8. Configuration System
- **XDG Base Directory support**: Absconda searches for configuration files following the XDG Base Directory specification. System-wide config at `/etc/xdg/absconda/config.yaml` provides defaults for all users (useful for shared HPC systems like NCI). User-level config at `~/.config/absconda/config.yaml` overrides system settings. Environment variables can override both.
- **Registry and organization**: Config files specify `registry` (e.g., `ghcr.io`) and `organization` (e.g., team or project name). When `--repository` is omitted from build/publish commands, Absconda auto-generates the repository name as `{registry}/{organization}/{env-name}`, where `env-name` comes from the environment YAML's `name:` field (slugified for safety).
- **Simplified tagging**: Default tag format is `YYYYMMDD` (build date) without prefixes, keeping image references clean and predictable. Users can override with `--tag` for custom versioning schemes.
- **Remote builder discovery**: The config system extends to remote builder definitions. If `absconda-remote.yaml` isn't found locally, Absconda searches XDG config directories, enabling teams to maintain centralized remote builder configurations.
- **Team deployment model**: System-wide configs enable "install once, use everywhere" deployment on shared infrastructure. Admins can configure registry credentials, remote builders, and organization defaults in `/etc/xdg/absconda/config.yaml`, while individual users can still override settings locally if needed.

## 9. Tarball Fast-Path Workflow
- **Pre-packed environments**: Users who have already created and tested a conda environment locally can use `conda-pack` to create a relocatable tarball: `conda pack -n myenv -o myenv.tar.gz`. This tarball contains the complete environment with all packages, binaries, and shared libraries.
- **Tarball input mode**: When `--tarball PATH` is specified, Absconda switches to a simplified build path:
  1. Validates the tarball file exists and is readable
  2. Copies the tarball into the Docker build context
  3. Generates a streamlined Dockerfile that unpacks the tarball directly into the target location (e.g., `/opt/conda/envs/myenv`)
  4. Sets up activation scripts without invoking conda/mamba solvers
- **Benefits**: Eliminates solver overhead (can save minutes to hours for complex environments), guarantees bit-for-bit reproduction of a tested local environment, and simplifies CI/CD when environments are pre-validated.
- **Metadata extraction**: Absconda attempts to extract environment name and Python version from the tarball's `conda-meta/` directory. If `--file` is also provided, it takes precedence for metadata (labels, name) but the environment dependencies are still sourced from the tarball, not solved from the YAML.
- **Compatibility**: Tarball mode works with both single-stage and multi-stage Dockerfiles. In multi-stage builds, the tarball is unpacked in the runtime stage directly, skipping the builder stage entirely since solving is unnecessary.
- **Activation guarantees**: The generated Dockerfile ensures the unpacked environment is properly activated by setting `PATH`, `CONDA_PREFIX`, and other environment variables, just as in YAML-based builds.
- **Use cases**: 
  - Reproducible research: Package an exact working environment from your laptop
  - CI/CD optimization: Pre-solve environments in one job, build containers in parallel downstream
  - Air-gapped deployments: Transfer environments across network boundaries as tarballs
  - Team sharing: "It works on my machine" → "Here's my machine as a tarball"

## 11. Error Handling & Edge Cases
- Missing file → exit code 2 with message "Environment file not found".
- Missing tarball → exit code 2 with message "Tarball not found: PATH".
- Invalid tarball format → exit code 3 with message "Invalid conda-pack tarball: missing conda-meta directory".
- Both `--file` and `--tarball` provided → use tarball for environment content, YAML for metadata only, warn user about this behavior.
- Invalid YAML → display line/column details from parser.
- Unsupported OS arch requested → warn and default to known base image.
- Empty dependencies list → still produce valid Dockerfile with just base image and metadata.
- Duplicate package specs → deduplicate while preserving order, warn user.

## 12. Testing Strategy
- **Unit Tests**: YAML parsing, CLI flag parsing, template rendering, diagnostics, tarball validation.
- **Golden Tests**: sample `env.yaml` fixtures vs. expected Dockerfile outputs, tarball mode Dockerfile variants.
- **Integration Tests**: run `absconda generate` in temporary dirs, ensure idempotency and exit codes. Test `--tarball` with sample conda-packed environment.
- **Tarball Tests**: Create fixture tarball with `conda pack`, verify Dockerfile generation, test build and container activation with unpacked tarball.
- **Static Analysis**: linting (ruff/flake8), typing (mypy/pyright).

## 13. Release Plan & Roadmap
1. **MVP (v0.1)**
   - CLI with `generate` command, default template, base image inference.
   - Basic diagnostics and unit tests.
2. **v0.2**
   - Custom template support, `validate` command, logging improvements.
3. **v0.3**
   - Structured logging, policy hooks, CI integration guide.
4. **v1.0**
   - Stable API/CLI, comprehensive docs, signed releases.

## 14. Documentation Deliverables
- Quickstart in `README.md` with examples.
- Detailed CLI reference (autogenerated help).
- Template authoring guide explaining placeholders and best practices.
- Troubleshooting section covering common validation errors.
- Policy configuration guide explaining profile schema, hook integration, and sample security extensions.

## 15. Environment Resolution Strategy
- **Loose environment files remain the source of truth.** Absconda treats minimally pinned `env.yaml` files as canonical specs, leaning on `mamba`/`conda` to solve them inside the Docker build. Warnings (not hard failures) are emitted for unpinned specs so teams remain aware of the potential drift.
- **Snapshots as hints, not locks.** A user-supplied snapshot (`--snapshot exported-env.yaml`) is copied next to the generated Dockerfile and hashed into the image as metadata. During `absconda validate`, the snapshot is diffed against the loose spec to flag major version deltas and suggest candidate pins but the solver still runs against the loose spec.
- **Conflict guidance for humans or agents.** When the solver fails, Absconda emits a `resolution_notes.md` artifact (and optional JSON) that: 1) surfaces the exact solver trace, 2) points to the snapshot for comparison, and 3) outlines a repeatable checklist an on-call engineer or automation agent can follow (e.g., "compare package X between env.yaml and snapshot, try pinning to snapshot version, rerun absconda").
- **Base image policy.** Builder stages continue to use `mambaorg/micromamba:1.5.5`, while runtime stages now default to the slimmer `debian:bookworm-slim` to keep artifacts lean without sacrificing glibc compatibility. Users can still point to Rocky-Linux or other bases via policy profiles/CLI flags, and experimental Alpine profiles keep their extra guardrails (musl compatibility checks, glibc shims).
- **Solver customization hooks.** Flags expose solver choice (`--solver mamba|conda`), parallelism, and remote channel allowances so CI can mimic local behavior.

## 16. Container Runtime & Singularity Compatibility

## 17. Policy Configuration System
- **Config file:** Absconda searches for `absconda-policy.yaml` (current directory → repo root → `~/.config/absconda/`). The file declares version, named profiles, channel policies, required template fragments, metadata rules, and optional security scanners. CLI `--policy` overrides the path.
- **Profiles:** Each profile (e.g., `default`, `rocky`, `hardened-gpu`) specifies builder/runtime base images, whether multi-stage is mandatory, env prefix, required labels, allowed channels, and default fragments (`non_root_user`, `apt_cleanup`, `gpu_drivers`). Users pick a profile via `--profile` or rely on the config's default.
- **Hooks:** The config can reference a Python module (e.g., `policy_hooks.py`) that exposes functions like `before_render(context)`, `after_validate(model)`, or `on_build_finished(result)`. Hooks can inject custom RUN instructions, enforce bespoke audits, or emit additional artifacts without forking Absconda.
- **Transparency & extensibility:** Policies are just YAML + optional Python, living alongside project code so security experts can review/extend them. Absconda surfaces every enforced rule in `absconda validate` output and exit codes, keeping teams informed when a policy blocks a build.

## 18. Build & Publish Workflow
- **Generate-first philosophy.** `absconda generate` remains the core command that outputs Dockerfiles for any environment. Users can still redirect to `docker build - < Dockerfile` if they prefer manual control.
- **Optional orchestration.** `absconda build` and `absconda publish` wrap Docker/Podman and Singularity CLIs. `build` renders templates to a temp scratch dir, runs `docker buildx build`, applies tags, and optionally pushes when `--push` is set. `publish` ensures the image exists (building if necessary), pushes to the configured registry, and optionally runs `singularity pull` to produce a `.sif` artifact.
- **Pluggable tooling.** The build orchestrator respects environment variables (`DOCKER_HOST`, `APPTAINER_CACHEDIR`) and surfaces exact commands in logs for reproducibility. Future adapters (e.g., `--builder podman`, `--singularity apptainer`) can reuse the same abstraction layer.
- **Delegated authentication.** Absconda does not manage registry credentials directly; it surfaces helpful messages if Docker/Podman lacks a login and points users to the relevant CLI commands, keeping the security model simple.
- **Remote build servers.** Users can opt into a `--remote-builder` profile (starting with `default-remote`) that provisions or resumes a VM on the configured provider (AWS, Azure, other cloud/on-prem targets) preloaded with Docker Engine and Buildx. Absconda always performs validation and Dockerfile rendering locally, then tars the scratch build context (Dockerfile, env files, helper assets) and streams it to the VM via SSH/SCP. A small manifest accompanies the tarball so the remote agent can double-check metadata (profile, tag, policy hash) before running `docker build`. After the build/publish operation, the coordinator can optionally stop the VM (`--remote-off`) or keep it warm for a short window; callers can also request a maximum wait time (`--remote-wait`) before falling back or exiting.
- **Remote builder management CLI.** The `absconda remote` command group exposes `list`, `provision`, `start`, `stop`, and `status` subcommands so operators can handle builder lifecycles without launching a build. Each command loads the same `absconda-remote.yaml` file consumed by `--remote-builder`, meaning provider metadata (project, zone, Terraform directory, health probes) lives alongside infrastructure code. Provision/start/stop simply shell out to the configured commands, which keeps credentials out of the repo by letting teams reference environment variables such as `${GCP_PROJECT?}` or `${SERVICE_ACCOUNT_JSON}` inside the YAML.
- **Infrastructure-as-code workflow.** Provisioning for the remote builder relies on Terraform modules (or another IaC tool) checked into the repository. The CLI shell-outs to `terraform apply/destroy` or calls the provider's CLI/SDK when a builder needs to be created on-demand. Remote builders store a small metadata file (e.g., in object storage) that indicates their active/inactive status so the CLI can skip re-provisioning and focus on start/stop operations. During the initial rollout a single VM handles requests, and the CLI simply waits/retries (with progress messages) if the builder is busy rather than auto-scaling.

## 19. Wrapper Scripts and Environment Modules
- **Transparent container execution.** After publishing a containerized environment, users often want to run commands (e.g., `python`, `jupyter`, `R`) as if they were installed locally, without manually typing `docker run` or `singularity exec` invocations. Absconda provides `wrap` and `module` commands to generate wrapper scripts and environment module files that make containers feel like native executables on HPC systems.

### Wrapper Scripts (`absconda wrap`)
- **Purpose:** Generate executable wrapper scripts for specified commands that transparently execute inside a container runtime (Docker or Singularity).
- **Explicit command list:** Users specify which commands to wrap via `--commands python,pip,jupyter`. Absconda assumes these commands exist in the container's PATH and generates one wrapper script per command.
- **Argument preservation:** Wrappers pass all arguments through unmodified using proper shell quoting (`"$@"`), preserving spaces, quotes, and special characters. Exit codes, stdin, stdout, and stderr are all preserved.
- **Runtime selection:** Wrappers default to Singularity (HPC-friendly) unless `--runtime docker` is specified. Separate wrapper scripts are generated for each runtime to avoid runtime detection overhead.
- **Singularity SIF caching:** When generating Singularity wrappers, Absconda converts the Docker image to a Singularity SIF file and caches it in a configurable location (default: `~/.local/absconda/sif-cache/`). Wrappers check if the SIF exists and pull it on first use. SIF filenames are sanitized from image references: `ghcr.io/lab/myenv:1.0` → `lab_myenv_1.0.sif`.
- **Volume mounts:** Wrappers mount only the paths explicitly specified via `--extra-mounts` or configured in `absconda-config.yaml` under `wrappers.default_mounts`. No automatic root filesystem mounting; users must specify every required path (e.g., `$HOME`, `$PWD`, `/scratch/$PROJECT`, `/g/data/$PROJECT`). Environment variable expansion happens at wrapper runtime.
- **Environment variable handling:** Wrappers pass through only explicitly allowed environment variables defined in `wrappers.env_passthrough` config (default: `USER`, `HOME`, `LANG`, `TZ`). All other variables are filtered out. Variables in `wrappers.env_filter` (default: `PATH`, `LD_LIBRARY_PATH`, `PYTHONPATH`) are explicitly blocked to avoid conflicts with the container's environment. CLI flag `--env VAR1,VAR2` adds additional passthrough variables.
- **GPU support:** Optional `--gpu` flag adds appropriate GPU forwarding options (`--nv` for Singularity, `--gpus all` for Docker). GPU flags are only added when explicitly requested, not auto-detected.
- **Network behavior:** Singularity wrappers use default Singularity network behavior (host network). Docker wrappers use isolated networking by default; future `--network host` flag can enable host networking when needed.
- **Output location:** Wrappers are written to `--output-dir` (CLI) or `wrappers.default_output_dir` (config, default: `~/.local/absconda/wrappers/<image-name>`). This directory typically gets added to PATH via an environment module.

**Example wrapper (Singularity):**
```bash
#!/bin/bash
# Auto-generated by absconda wrap for ghcr.io/lab/myenv:1.0
# Command: python
set -euo pipefail

SIF_CACHE="${HOME}/.local/absconda/sif-cache"
SIF_FILE="${SIF_CACHE}/lab_myenv_1.0.sif"
IMAGE_REF="docker://ghcr.io/lab/myenv:1.0"

# Pull SIF if missing
if [[ ! -f "$SIF_FILE" ]]; then
    mkdir -p "$SIF_CACHE"
    echo "Pulling Singularity image to cache..." >&2
    singularity pull "$SIF_FILE" "$IMAGE_REF"
fi

# Build mount arguments from config
MOUNTS=()
MOUNTS+=("-B" "$HOME")
MOUNTS+=("-B" "$PWD")
# Additional mounts from config/CLI...

exec singularity exec \
    "${MOUNTS[@]}" \
    "$SIF_FILE" \
    python "$@"
```

**CLI usage:**
```bash
absconda wrap \
  --image ghcr.io/lab/myenv:1.0 \
  --commands python,pip,jupyter \
  --runtime singularity \
  --output-dir /g/data/$PROJECT/modules/myenv/1.0/bin \
  --image-cache /scratch/$PROJECT/.singularity \
  --extra-mounts /scratch/$PROJECT,/g/data/$PROJECT \
  --gpu
```

### Environment Modules (`absconda module`)
- **Purpose:** Generate Tcl environment module files that add wrapper directories to PATH and set helpful environment variables. Modules provide a familiar interface for HPC users: `module load myenv/1.0` makes wrapped commands available.
- **Module format:** Traditional Tcl format for maximum compatibility with environment modules systems on HPC clusters.
- **Module structure:** Sets `module-whatis` description, prepends wrapper directory to PATH, exports variables indicating image reference and runtime, and configures automatic conflicts with other versions of the same module.
- **Conflict management:** Modules automatically conflict with other versions (e.g., `conflict myenv` prevents `myenv/1.0` and `myenv/2.0` from loading simultaneously).
- **Metadata variables:** Exports `<MODULE>_VERSION`, `<MODULE>_IMAGE`, `<MODULE>_RUNTIME` environment variables (module name uppercased) for introspection and debugging.
- **Help text:** Includes `ModulesHelp` procedure showing description, image reference, and runtime information when users run `module help myenv/1.0`.
- **Output location:** Module files are written to `--output-dir` (CLI) or `modules.default_output_dir` (config, default: `~/.local/absconda/modulefiles`). Users add this directory to `MODULEPATH` or administrators install to system module directories (e.g., `/opt/Modules/modulefiles`).

**Example module file (Tcl):**
```tcl
#%Module1.0
##
## Auto-generated by absconda module
## Image: ghcr.io/lab/myenv:1.0
## Runtime: singularity
##
proc ModulesHelp { } {
    puts stderr "Python 3.11 environment with TensorFlow GPU support"
    puts stderr ""
    puts stderr "Containerized environment: ghcr.io/lab/myenv:1.0"
    puts stderr "Runtime: singularity"
    puts stderr "Wrapped commands: python, pip, jupyter"
}

module-whatis "Python 3.11 with TensorFlow GPU (containerized)"

conflict myenv

prepend-path PATH /g/data/xy00/modules/myenv/1.0/bin

setenv MYENV_VERSION 1.0
setenv MYENV_IMAGE ghcr.io/lab/myenv:1.0
setenv MYENV_RUNTIME singularity
```

**CLI usage:**
```bash
absconda module \
  --name myenv/1.0 \
  --wrapper-dir /g/data/$PROJECT/modules/myenv/1.0/bin \
  --output-dir /g/data/$PROJECT/modulefiles \
  --description "Python 3.11 with TensorFlow GPU support" \
  --image ghcr.io/lab/myenv:1.0 \
  --runtime singularity
```

### Configuration (`absconda-config.yaml`)
Wrapper and module generation behavior is controlled by config file settings:

```yaml
wrappers:
  default_runtime: singularity  # or docker
  default_output_dir: ~/.local/absconda/wrappers
  image_cache: ~/.local/absconda/sif-cache
  default_mounts:
    - $HOME
    - $PWD
    # NCI Gadi specific paths:
    - /scratch/$PROJECT
    - /g/data/$PROJECT
  env_passthrough:  # Only these env vars are passed to container
    - USER
    - HOME
    - LANG
    - TZ
  env_filter:  # Explicitly blocked even if in passthrough
    - PATH
    - LD_LIBRARY_PATH
    - PYTHONPATH

modules:
  default_output_dir: ~/.local/absconda/modulefiles
  format: tcl  # Future: lua support
```

### Complete Workflow Example
```bash
# 1. Build and publish containerized environment
absconda publish --file env.yaml \
  --repository ghcr.io/lab/myenv \
  --tag 1.0 \
  --push

# 2. Generate wrapper scripts for common commands
absconda wrap \
  --image ghcr.io/lab/myenv:1.0 \
  --commands python,pip,jupyter,nvidia-smi \
  --runtime singularity \
  --output-dir /g/data/$PROJECT/modules/myenv/1.0/bin \
  --gpu

# 3. Generate environment module file
absconda module \
  --name myenv/1.0 \
  --wrapper-dir /g/data/$PROJECT/modules/myenv/1.0/bin \
  --output-dir /g/data/$PROJECT/modulefiles \
  --description "Python 3.11 with TensorFlow GPU" \
  --image ghcr.io/lab/myenv:1.0 \
  --runtime singularity

# 4. Use the module (as end user)
module use /g/data/$PROJECT/modulefiles
module load myenv/1.0
python train.py --gpu  # Runs inside container transparently
```

### Design Rationale
- **Separation of concerns:** `wrap` and `module` are separate commands because wrappers and modules serve different purposes. Users might want wrappers without modules (personal use) or generate multiple module variants pointing to the same wrappers (testing/production).
- **Explicit over automatic:** Explicitly listing commands to wrap avoids accidentally wrapping system utilities or creating naming conflicts. Mount paths and environment variables are also explicit to prevent security issues and unexpected behavior.
- **Runtime-specific wrappers:** Separate Docker and Singularity wrappers eliminate runtime detection overhead and allow optimization for each platform's idioms.
- **SIF caching for performance:** Converting Docker images to SIF files upfront improves Singularity startup time and enables offline usage once cached.
- **Module standards:** Tcl modules are universally supported on HPC systems. Conflicts and metadata variables follow established conventions.
- **HPC deployment model:** Output directories default to user-local paths but CLI flags support system-wide installation. This supports both personal workflows and team/cluster-wide deployments on systems like NCI Gadi.

## 20. Planned Extensions
- **Enhanced renv ergonomics.** Build runners already honor `--renv-lock`; upcoming work explores automatically injecting `r-base` (when missing), caching shared renv libraries between builds, and surfacing clearer diagnostics when `Rscript` is absent from the Conda env.
- **Multi-arch publishing.** Future profiles can enable Docker buildx multi-arch output (linux/amd64 + linux/arm64) so Apple Silicon users get native performance while the default remains Linux.
- **Remote caching & diffed uploads.** Investigate BuildKit cache exports, cloud/object-storage layer snapshots, and rsync-style delta uploads so remote builders avoid retransmitting multi-gigabyte contexts.
- **Autoscaling builders.** When concurrency increases, graduate from a single VM to a managed instance group or queue-backed worker pool so multiple builds can run in parallel without manual coordination.
- **Lua module support.** Add `--format lua` flag to `absconda module` for modern Lmod-based module systems.
- **Wrapper auto-discovery.** Option to scan container's `/bin` and `/usr/bin` directories to auto-generate wrappers for all executables (with safeguards to exclude system utilities).
- **Registry authentication helpers.** Detect when Singularity SIF pulls fail due to missing Docker credentials and provide actionable guidance for configuring `singularity remote login`.

## 21. Open Questions
- Should `absconda publish` also support OCI registries that require OIDC/device flow login, or do we delegate auth entirely to Docker/Podman (current plan favors delegation)?
- What heuristics should trigger additional renv safeguards (e.g., verifying `r-base` is pinned, warning when `renv.lock` targets a mismatched R release)?
- Should wrappers support automatic retry logic if SIF pull fails due to transient network issues?
- Do we need a `--network host` flag for Docker wrappers, or is the default isolated networking sufficient for most use cases?
