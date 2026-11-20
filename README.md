# shared_workflows

Reusable GitHub Actions workflows for the repos in this org, so CI is defined once and every repo calls it in a few lines.

## Workflows

| Workflow | Does | Used by |
|---|---|---|
| [`python-checks.yml`](.github/workflows/python-checks.yml) | `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest` | data-simulator-api |
| [`security-scan.yml`](.github/workflows/security-scan.yml) | checkov, trivy, gitleaks and actionlint, combined into one report and PR comment | all repos |
| [`format-check.yml`](.github/workflows/format-check.yml) | `terraform fmt`, `terragrunt hcl format`, `bash -n` | repos with Terraform |
| [`terragrunt-plan.yml`](.github/workflows/terragrunt-plan.yml) | read-only `terragrunt plan` via AWS OIDC, with a sanitised report and PR comment | data-simulator-elt |

The individual scanners (`scan-checkov.yml`, `scan-trivy.yml`, `scan-gitleaks.yml`, `scan-actionlint.yml`) and `sarif-report.yml` can also be called on their own.

## Using one

```yaml
# .github/workflows/python-checks.yml in a calling repo
name: python-checks
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  python:
    uses: amcaughan-personal/shared_workflows/.github/workflows/python-checks.yml@<commit sha> # v1.0.0
```

Pin the **commit SHA** of a release tag, with the tag as a comment. A tag can be moved; a SHA can't. Tags matching `v*` are also protected from deletion and retargeting by a repository ruleset.

## Releasing

1. Merge changes to `main` (CI runs actionlint and the unit tests on every PR).
2. Tag the merge commit, e.g. `v1.1.0`, and push the tag.
3. Bump the pinned SHA in the calling repos.

## How it works

- Workflows that use this repo's composite actions (`.github/actions/`) check out this repo at `job.workflow_sha`, the commit the reusable workflow itself runs from. A plain `uses: ./.github/actions/...` would resolve against the *calling* repo's checkout and fail.
- Inputs reach shell scripts through `env:` rather than `${{ }}` interpolation.
