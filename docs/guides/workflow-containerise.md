# Containerising a Snakemake Workflow

Snakemake workflows often pin per-rule conda environments via the `conda:`
directive. When you want the same workflow to run under Singularity/Apptainer
or Docker, Snakemake also supports a `container:` directive. The
`absconda workflow` subcommands automate the conversion: scan the workflow,
build and publish one image per unique env file, then rewrite the workflow to
reference the images. The original `conda:` lines are preserved (commented
out) for reference and easy revert.

## TL;DR

```bash
# One-shot: scan, build+push every env, rewrite workflow.
absconda workflow apply path/to/snakemake-project
```

For finer control, run the three steps separately:

```bash
absconda workflow scan          path/to/snakemake-project
# Review absconda-workflow.yaml, edit image repos if needed
absconda workflow containerise  path/to/snakemake-project
absconda workflow update        path/to/snakemake-project
```

## The manifest

`scan` produces `absconda-workflow.yaml` at the workflow root. It deduplicates
env files by content hash, so two rules pointing at the same `envs/qc.yaml`
collapse to a single image.

```yaml
workflow:
  type: snakemake
  root: /abs/path/to/project
  scanned_at: 2026-05-28T03:14:15Z
envs:
  - hash: sha256:abc…
    env_file: envs/qc.yaml
    env_name: qc
    rules: [fastqc, multiqc]
    image: null        # populated by `containerise` from config defaults
    tag: null
    image_ref: null    # populated by `containerise` after publish succeeds
  - hash: sha256:def…
    env_file: envs/align.yaml
    env_name: align
    rules: [align]
    image: null
    tag: null
    image_ref: null
references:
  - {file: Snakefile, line: 7,  env_file: envs/qc.yaml,    rule: fastqc}
  - {file: Snakefile, line: 14, env_file: envs/qc.yaml,    rule: multiqc}
  - {file: Snakefile, line: 21, env_file: envs/align.yaml, rule: align}
```

The manifest is hand-editable. To pin a custom repository or tag, fill in
`image:` and/or `tag:` before running `containerise`. To force a rebuild
even when `image_ref` is already populated, use `--force-rebuild`.

## What `update` writes

Per-rule rewrite comments the original `conda:` line and inserts a `container:`
line at the same indent, marked with a recognisable comment so the operation
is idempotent and revertible.

```python
rule fastqc:
    input: "data/{sample}.fq.gz"
    output: "qc/{sample}_fastqc.html"
    # absconda: replaced conda env with container
    # conda: "envs/qc.yaml"
    container: "docker://ghcr.io/yourorg/qc:20260528"
    shell: "fastqc {input} -o qc/"
```

Re-running `update` with a refreshed manifest updates the `container:` line in
place rather than stacking new blocks. `absconda workflow update --revert`
strips the marker blocks and restores the original `conda:` directives.

## Limitations (v1)

- **Snakemake only.** Nextflow support is planned; the manifest layer is
  designed to extend to `.nf` parsers.
- **Quoted, single-line `conda:` directives only.** `conda:` references built
  by Python expressions (`conda: f"envs/{wildcards.tool}.yaml"`) are not
  rewritten. Run `absconda workflow scan` to see what is detected.
- **No `--use-conda + --use-singularity` hybrid mode.** This subcommand
  replaces, rather than nests, the conda directives.

## Running the workflow under Singularity

After `update`, run Snakemake with Singularity enabled:

```bash
snakemake --use-singularity --singularity-args="--bind /scratch:/scratch" -j 8
```

You no longer need `--use-conda`. If you prefer to keep the option for envs
that fall outside the rewrite (e.g. unquoted `conda:`), Snakemake will use
`conda:` for those rules and `container:` for the rest.
