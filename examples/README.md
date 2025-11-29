# Absconda Examples

A couple of ready-to-use Conda environment definitions you can feed into `absconda generate`.

## 1. Minimal Python runtime
- File: `minimal-env.yaml`
- Includes: Python 3.11, pip, and a single `pip` dependency (`rich`).
- Usage:
  ```bash
  absconda generate --file examples/minimal-env.yaml --output Dockerfile
  ```
  The resulting Dockerfile targets the default multi-stage layout.

## 2. Data science starter
- File: `data-science-env.yaml`
- Includes: Python 3.10, NumPy, pandas, and JupyterLab via pip.
- Usage:
  ```bash
  absconda generate --file examples/data-science-env.yaml --output Dockerfile.ds
  ```
  Ships as a multi-stage Dockerfile by default; tweak `--runtime-base` if you need something other than `debian:bookworm-slim` in the final image.

Feel free to copy these as a baseline for your own projects.
