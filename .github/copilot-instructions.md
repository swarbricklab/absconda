# Copilot Instructions for Absconda Project

## Important Guidelines

**ALWAYS CHECK WITH THE USER** before:
- Making architectural decisions or choosing different approaches than requested
- Installing/removing dependencies or tools
- Changing infrastructure or deployment patterns
- Deviating from the user's explicit instructions

## Python Environment

This project uses a virtual environment located at `.venv/`. 

**IMPORTANT**: Always activate the virtual environment before running `absconda` commands.

### Activating the venv

When starting a new terminal or running commands:

```bash
cd /Users/johree/projects/absconda
source .venv/bin/activate
```

Or in one line:
```bash
cd /Users/johree/projects/absconda && source .venv/bin/activate && <command>
```

### Environment Variables (direnv)

This project uses `direnv` to automatically load environment variables from `.env`.

**Setup (one-time)**:
- direnv hook is configured in `~/.zshrc`: `eval "$(direnv hook zsh)"`
- `.envrc` loads variables from `.env` when you `cd` into the project directory

**Usage**:
- Variables are automatically loaded when you `cd` into `/Users/johree/projects/absconda`
- If you start in the directory, run: `cd .. && cd -` to trigger direnv
- Or manually: `eval "$(direnv export zsh)"`

**Required variables**:
- `GCP_PROJECT`, `GCP_REGION`, `GCP_ZONE`
- `TF_VAR_*` variables for Terraform
- See `.env` for full list

## Running Commands

### Local builds
```bash
cd /Users/johree/projects/absconda && source .venv/bin/activate
absconda build --file examples/minimal-env.yaml --repository <repo> --tag <tag>
```

### Remote builds (GCP)
```bash
cd /Users/johree/projects/absconda && source .venv/bin/activate
absconda build --file examples/minimal-env.yaml --repository <repo> --tag <tag> --remote-builder gcp-builder
```

### Remote management
```bash
cd /Users/johree/projects/absconda && source .venv/bin/activate
absconda remote list
absconda remote status gcp-builder
absconda remote provision gcp-builder
absconda remote start/stop gcp-builder
absconda remote init gcp-builder  # First-time SSH setup
```

## Testing

```bash
cd /Users/johree/projects/absconda && source .venv/bin/activate
python -m pytest tests/ -v
```

## Common Issues

### "command not found: absconda"
- **Solution**: Activate the venv first: `source .venv/bin/activate`

### "Required environment variable 'X' is not set"
- **Solution**: Make sure direnv is active. Run `cd /Users/johree/projects/absconda` or `eval "$(direnv export zsh)"`

### Remote build fails with "${GCP_PROJECT} is not a valid project ID"
- **Solution**: direnv not loaded. Run `cd /Users/johree/projects/absconda` to trigger direnv

### SSH permission denied on GCP
- **Solution**: Run `absconda remote init gcp-builder` to set up OS Login
- **Note**: OS Login username is `j_reeves_garvan_org_au` (check with `gcloud compute os-login describe-profile`)

## Project Structure

- `src/absconda/` - Main package source
- `examples/` - Sample environment files
- `tests/` - Test suite
- `terraform/gcp/` - GCP infrastructure as code
- `.env` - Environment variables (git-ignored)
- `.envrc` - direnv configuration
- `absconda-remote.yaml` - Remote builder configuration

## Development Workflow

1. Make code changes
2. Install in development mode: `pip install -e .` (with venv activated)
3. Run tests: `python -m pytest tests/ -v`
4. Test locally: `absconda build --file examples/minimal-env.yaml ...`
5. Test remotely: Add `--remote-builder gcp-builder` flag
