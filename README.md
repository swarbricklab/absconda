# Absconda

This tool creates a Dockerfile based on a Conda environment definition file.

Basic usage:
```
absconda --file env.yaml > Dockerfile
```

## Examples

Sample environment files live under `examples/`:

| File | Description | Command |
| --- | --- | --- |
| `examples/minimal-env.yaml` | Tiny Python 3.11 runtime with pip + `rich` | `absconda generate --file examples/minimal-env.yaml --output Dockerfile` |
| `examples/data-science-env.yaml` | NumPy/Pandas + JupyterLab starter (multi-stage) | `absconda generate --file examples/data-science-env.yaml --output Dockerfile.ds` |

Copy one as a starting point or tweak the dependencies to match your project.

## Build patterns

Absconda defaults to a **multi-stage** Dockerfile: the builder stage uses `mambaorg/micromamba:1.5.5` to solve the environment, and the runtime stage starts from `debian:bookworm-slim` before unpacking the `conda-pack` artifact. This keeps the final image slimmer because the heavy solver layer never ships inside the runtime layer.

Need a specialized runtime? Pass `--runtime-base` (or set it in your policy profile) to swap in any OCI image with glibc available. You can also force a single-stage Dockerfile with `--single-stage`, though that tends to be larger because the solver tooling stays in the final image.

## Building and publishing images

Absconda can drive Docker for you when you're ready to go from an environment file straight to an image:

```
absconda build \
	--repository ghcr.io/acme/lab \
	--file examples/minimal-env.yaml \
	--context .
```

- `--repository` is required and should point at the registry/repository you already have access to.
- Tags default to `<env-name>-YYYYMMDD` (slugified env name + UTC date). Use `--tag custom-tag` to override.
- `--push` uploads the result after a successful local build.
- The command shells out to `docker build`, so make sure Docker/Podman is installed and logged in first.

For registries plus Singularity targets, use `publish`:

```
absconda publish \
	--repository ghcr.io/acme/lab \
	--file examples/data-science-env.yaml \
	--singularity-out dist/data-science.sif
```

`publish` always pushes the Docker image and, when `--singularity-out` is set, converts the pushed image into a `.sif` artifact via `singularity pull`. The directory is created for you if it does not exist yet.

Both commands accept the same templating overrides as `generate` (`--template`, `--builder-base`, `--runtime-base`, `--multi-stage/--single-stage`) plus `--context` for swapping the Docker build context when your environment expects additional local files.

## R + renv environments

Bring R libraries along with your Conda environment by pointing Absconda at an `renv.lock` file:

```
absconda build \
	--repository ghcr.io/acme/r-lab \
	--file examples/minimal-env.yaml \
	--renv-lock path/to/renv.lock \
	--context .
```

How it works:

- The builder stage copies your `renv.lock`, installs `renv` inside the Conda env (make sure you include `r-base`/`r` in `env.yaml`), and runs `renv::restore()`.
- The runtime image gains `/opt/absconda/renv` containing the restored `renv/` tree and `.Rprofile` that auto-sources `renv/activate.R`.
- `R_PROFILE_USER`, `RENv_*` vars, and `R_LIBS_SITE` are set so `Rscript` and interactive R sessions see the restored packages without any manual activation.

You can use `--renv-lock` with `generate`, `build`, or `publish`. Combine it with `--singularity-out` to ship the same setup to Apptainer/Singularity clusters.

