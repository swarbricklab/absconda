# R + renv Support

Absconda can bundle an R `renv.lock` snapshot alongside your Conda environment so R code works out-of-the-box in Docker (and Singularity) images.

## Prerequisites
- Your `env.yaml` must install an R runtime (`r-base`, `mro-base`, etc.) so `Rscript` is available during the build.
- Generate an `renv.lock` from your project (inside the same directory you would normally run renv):

```r
renv::snapshot(prompt = FALSE)
```

## CLI usage
Pass the lock file to any rendering/building command via `--renv-lock`:

```bash
absconda generate --file env.yaml --renv-lock renv.lock --output Dockerfile
absconda build --file env.yaml --renv-lock renv.lock --repository ghcr.io/acme/r-lab
absconda publish --file env.yaml --renv-lock renv.lock --repository ghcr.io/acme/r-lab \
  --singularity-out dist/r-lab.sif
```

What happens under the hood:

1. The builder stage copies `renv.lock`, ensures the Conda env contains `renv`, and runs `renv::restore()` inside the micromamba environment.
2. The restored `renv/` directory, `renv.lock`, and a generated `.Rprofile` are staged under `/opt/absconda/renv`.
3. The runtime image sets `R_PROFILE_USER`, `R_LIBS_SITE`, and the relevant `RENV_*` variables so every `Rscript` session automatically sources `renv/activate.R` and picks up the restored packages.

## Runtime behavior
- Environment variables:
  - `R_PROFILE_USER=/opt/absconda/renv/.Rprofile`
  - `RENV_PROJECT=/opt/absconda/renv`
  - `RENV_PATHS_ROOT=/opt/absconda/renv`
  - `RENV_PATHS_LIBRARY=/opt/absconda/renv/renv/library`
  - `RENV_PATHS_LIBRARY_ROOT=/opt/absconda/renv/renv/library`
  - `R_LIBS_SITE=/opt/absconda/renv/renv/library`
- No manual `renv::activate()` calls are required. Launching `R` or `Rscript` immediately exposes the restored packages.

## Troubleshooting
- **Missing Rscript:** Conda environments lacking `r-base` will fail when `renv::restore()` runs. Add an explicit `r-base` (or similar) dependency to `env.yaml`.
- **Mismatched R versions:** If `renv.lock` targets a different R minor release, consider pinning `r-base` in `env.yaml` to match the lockfile (`r-base=4.3.*`).
- **Custom library paths:** For bespoke workflows, extend the generated `.Rprofile` via policy fragments or by baking additional scripts into the runtime stage.

## Future enhancements
- Cache restored renv libraries between builds to speed up CI workflows.
- Emit warnings when `renv.lock` references packages unavailable on the configured CRAN mirror.
