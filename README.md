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

