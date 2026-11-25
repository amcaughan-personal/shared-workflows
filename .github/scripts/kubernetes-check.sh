#!/usr/bin/env bash
# Validates a directory of Kubernetes manifests with kubeconform: every plain manifest, and
# every kustomization rendered with kubectl kustomize. Helm chart files (Chart.yaml,
# values.yaml, templates/) and kustomization.yaml files themselves aren't manifests.
#   kubernetes-check.sh <dir> <CRDs-catalog commit> [kubernetes version]
#
# Custom resources (e.g. Argo CD Applications, Karpenter NodePools) are checked against the
# community CRDs-catalog (github.com/datreeio/CRDs-catalog) at a pinned commit. -strict
# fails on fields a schema doesn't define, so typos are caught.
set -euo pipefail
dir="$1"; catalog_commit="$2"; k8s_version="${3:-master}"
rendered="$(mktemp -d)"

mapfile -t manifests < <(find "$dir" -name '*.yaml' -not -path '*/templates/*' \
  -not -name 'Chart.yaml' -not -name 'values.yaml' -not -name 'kustomization.yaml' | sort)
while IFS= read -r k; do
  out="$rendered/$(printf '%s' "$k" | tr '/' '_').yaml"
  kubectl kustomize "$k" > "$out"
  echo "rendered $k"
done < <(find "$dir" -name kustomization.yaml -exec dirname {} \; | sort)

kubeconform -strict -summary -output text -kubernetes-version "$k8s_version" \
  -schema-location default \
  -schema-location "https://raw.githubusercontent.com/datreeio/CRDs-catalog/${catalog_commit}/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json" \
  "${manifests[@]}" "$rendered"/*.yaml
