#!/usr/bin/env bash
# Plans every Terragrunt stack under a directory, keeping all output on the runner (safe for
# public repos): each stack's full output goes to a log file, and only Terraform's one-line
# "Error:" summaries are printed, with any 12-digit number (an AWS account ID) redacted.
#
#   plan-stacks.sh <working dir> <output dir> [extra terragrunt plan arguments]
#
# Writes <output dir>/index.tsv, one line per stack: stack path, ok or failed, plan JSON path.
# Exit status: 0 if every stack planned, 1 if any failed, 2 if there were no stacks.
set -uo pipefail

working_dir="$1"
out="$2"
shift 2

mkdir -p "$out"
: > "$out/index.tsv"
failed=0

mapfile -t stacks < <(find "$working_dir" -name terragrunt.hcl -not -path '*/.terragrunt-cache/*' -printf '%h\n' | sort)
if (( ${#stacks[@]} == 0 )); then
  echo "::error::No terragrunt.hcl found under $working_dir"
  exit 2
fi

for dir in "${stacks[@]}"; do
  stack="${dir#"$working_dir"/}"
  name="$(printf '%s' "$stack" | tr -c 'A-Za-z0-9._-' '_')"
  log="$out/$name.log"
  if (cd "$dir" \
      && terragrunt plan -input=false -no-color -out="$out/$name.tfplan" "$@" \
      && terragrunt show -json "$out/$name.tfplan" > "$out/$name.json") > "$log" 2>&1; then
    echo "planned  $stack"
    printf '%s\tok\t%s\n' "$stack" "$out/$name.json" >> "$out/index.tsv"
  else
    failed=1
    echo "::group::FAILED   $stack"
    grep -oE '(Error|ERROR):? .*' "$log" | sed -E 's/[0-9]{12}/************/g' | sort -u | head -20
    echo "::endgroup::"
    printf '%s\tfailed\t\n' "$stack" >> "$out/index.tsv"
  fi
  rm -f "$out/$name.tfplan"
done

exit "$failed"
