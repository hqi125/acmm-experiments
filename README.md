# ACMM Experiment Packages

This directory is the EP-6 proof workspace for experiment artifacts that are independent of the
ACMM main repository. It is intended to become a separate version-controlled experiments repository;
ACMM consumes packages from filesystem paths and does not install them with `pip`.


## WSL workspace setup

If the Windows checkout is a sibling of the main repo at
`/mnt/d/MEng/4-Fall-2026/ece-699/acmm-experiments`, create a stable WSL link once:

```text
ln -s /mnt/d/MEng/4-Fall-2026/ece-699/acmm-experiments ~/acmm-experiments
```

Verify it with `readlink -f ~/acmm-experiments`. Keep the main repo and experiment-package repo as
separate Git roots; ACMM consumes package source through filesystem paths and copies immutable
revisions into its managed runtime store.

Experiment directories currently include:

- `controlled_authoritative_state_interference_v1/` — the frozen historical authoritative-state
  interference study formerly embedded in the ACMM main repository.
- `minimal_agent_baseline_v1/` — the frozen first experiment in the new research roadmap. It
  contains the final 16-scenario Contract, package-owned structured scenario assets, deterministic
  no-apparatus runtime evaluators, and the completed 384-run acquisition/interpretation baseline.

A normal workflow from the ACMM development environment is:

```text
acmm package validate ../acmm-experiments/minimal_agent_baseline_v1
acmm package install ../acmm-experiments/minimal_agent_baseline_v1
acmm package apply minimal_agent_baseline_v1
acmm run minimal_agent_baseline_v1 --preview
```

Experiment-specific tests stay with each package. From the ACMM virtual environment, run:

```text
pytest ../acmm-experiments/controlled_authoritative_state_interference_v1/tests
```
## Local secrets

Do not place provider API keys or other live credentials in Experiment Packages. Local `.env`,
`secrets/`, and common Ollama API-key filenames are ignored as a last-resort safeguard, but secrets
should normally live outside this repository (for example under `~/.config/acmm/`). If this repo is
hosted on GitHub, enable Secret Protection / Push Protection in repository settings when available.

