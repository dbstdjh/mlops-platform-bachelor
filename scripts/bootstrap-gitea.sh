#!/usr/bin/env bash
set -euo pipefail

KUBECTL="${KUBECTL:-minikube kubectl --}"
NAMESPACE="${NAMESPACE:-mldlc}"
GITEA_ADMIN_USER="${GITEA_ADMIN_USER:-mldlc-admin}"
GITEA_ADMIN_EMAIL="${GITEA_ADMIN_EMAIL:-admin@mldlc.local}"
GITEA_ADMIN_TOKEN_NAME="${GITEA_ADMIN_TOKEN_NAME:-mldlc-control-plane}"
GITEA_ADMIN_TOKEN_SCOPES="${GITEA_ADMIN_TOKEN_SCOPES:-all}"

validate() {
  local name="$1"
  local value="$2"
  local pattern="$3"

  if [[ ! "$value" =~ $pattern ]]; then
    printf 'Invalid %s value for Gitea bootstrap: %s\n' "$name" "$value" >&2
    exit 1
  fi
}

validate GITEA_ADMIN_USER "$GITEA_ADMIN_USER" '^[A-Za-z0-9_.-]+$'
validate GITEA_ADMIN_EMAIL "$GITEA_ADMIN_EMAIL" '^[A-Za-z0-9_.@+-]+$'
validate GITEA_ADMIN_TOKEN_NAME "$GITEA_ADMIN_TOKEN_NAME" '^[A-Za-z0-9_.-]+$'
validate GITEA_ADMIN_TOKEN_SCOPES "$GITEA_ADMIN_TOKEN_SCOPES" '^[A-Za-z0-9_:,.-]+$'

read -r -a KUBECTL_CMD <<< "$KUBECTL"

kctl() {
  "${KUBECTL_CMD[@]}" "$@"
}

gitea() {
  local command="$1"
  kctl -n "$NAMESPACE" exec deploy/gitea -- su git -c "$command"
}

printf 'Bootstrapping local Gitea registry in namespace %s...\n' "$NAMESPACE"

kctl -n "$NAMESPACE" rollout status deployment/gitea --timeout=240s

gitea 'gitea migrate'

if ! create_output="$(gitea "gitea admin user create --username $GITEA_ADMIN_USER --email $GITEA_ADMIN_EMAIL --admin --random-password --must-change-password=false" 2>&1)"; then
  if ! printf '%s' "$create_output" | grep -Eiq 'already|exists|duplicate'; then
    printf '%s\n' "$create_output" >&2
    exit 1
  fi
fi

token_name="${GITEA_ADMIN_TOKEN_NAME}-$(date -u +%Y%m%d%H%M%S)"
token_output="$(gitea "gitea admin user generate-access-token --username $GITEA_ADMIN_USER --token-name $token_name --scopes $GITEA_ADMIN_TOKEN_SCOPES --raw")"
token="$(printf '%s\n' "$token_output" | tail -n 1 | tr -d '\r')"

if [[ -z "$token" ]]; then
  printf 'Gitea did not return an admin token.\n' >&2
  exit 1
fi

token_b64="$(printf '%s' "$token" | base64 | tr -d '\n')"
kctl -n "$NAMESPACE" patch secret platform-secret --type merge -p "{\"data\":{\"GITEA_ADMIN_TOKEN\":\"$token_b64\"}}"

kctl -n "$NAMESPACE" rollout restart deployment/api
kctl -n "$NAMESPACE" rollout status deployment/api --timeout=180s

printf 'Gitea bootstrap complete; Control Plane has a fresh admin token.\n'
