# shared-workflows

Reusable GitHub Actions workflows for the repos in this org, so CI is defined once and every repo calls it in a few lines.

## Workflows

| Workflow | Does | Used by |
|---|---|---|
| [`python-checks.yml`](.github/workflows/python-checks.yml) | `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest` | data-simulator-api |
| [`security-scan.yml`](.github/workflows/security-scan.yml) | checkov, trivy, gitleaks and actionlint, combined into one report and PR comment. Fails on any Checkov finding (skip deliberate ones inline), fixable HIGH/CRITICAL vulnerabilities, leaked secrets or workflow errors. Comments only when there are findings (`comment_when_clean: true` to always comment). `scans` picks which run (all four by default), e.g. `"trivy, gitleaks, actionlint"` in repos without infrastructure code | all repos |
| [`format-check.yml`](.github/workflows/format-check.yml) | `terraform fmt`, `terragrunt hcl format`, `bash -n` | repos with Terraform |
| [`terragrunt-plan.yml`](.github/workflows/terragrunt-plan.yml) | read-only `terragrunt plan` of every stack under `terragrunt_working_dir`, via an OIDC role passed as the `aws_role_arn` secret. Safe for public repos: the PR comment and step summary list resource addresses and types only; the log shows only one-line error summaries with the account ID masked; plan files never leave the runner | data-simulator-api, -elt, -analytics |

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
    uses: amcaughan-personal/shared-workflows/.github/workflows/python-checks.yml@<commit sha> # v1.2.3
```

Pin the **commit SHA** of a version tag, with the version in a comment: the caller runs
exactly the code it was tested with, and Dependabot reads the comment to propose newer
versions.

## Updating callers

Every merge to `main` is tagged automatically ([`tag.yml`](.github/workflows/tag.yml)):
the next patch version, or the next minor or major version if the PR has a
`release: minor` or `release: major` label. Use major for breaking changes, such as a removed
input. Tags can't be moved or deleted.

Calling repos' Dependabot sees new tags and opens a PR bumping their pins, grouped and
without the 7-day cooldown that applies to third-party updates.

## How it works

- Workflows that use this repo's composite actions (`.github/actions/`) check out this repo at `job.workflow_sha`, the commit the reusable workflow itself runs from. A plain `uses: ./.github/actions/...` would resolve against the *calling* repo's checkout and fail.
- Inputs reach shell scripts through `env:` rather than `${{ }}` interpolation.
