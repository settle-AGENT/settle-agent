#!/usr/bin/env bash

set -euo pipefail

deploy_root="${DEPLOY_ROOT:-/opt/fsai}"

# Extract a required field from a secret JSON blob, reporting which field failed.
extract_field() {
  local label="$1" json="$2" field="$3" value
  if ! value="$(printf '%s' "$json" | jq -er ".${field}")"; then
    echo "FAIL: ${label} secret is missing field '${field}' (absent or null)." >&2
    echo "FAIL: ${label} secret top-level keys: $(printf '%s' "$json" | jq -rc 'keys' 2>&1)" >&2
    exit 1
  fi
  printf '%s' "$value"
}

cd "$deploy_root"

: "${AWS_REGION:?AWS_REGION is required}"
: "${RDS_SECRET_ID:?RDS_SECRET_ID is required}"
: "${APP_SECRET_ID:?APP_SECRET_ID is required}"
: "${RDS_ENDPOINT:?RDS_ENDPOINT is required}"
: "${RDS_PORT:?RDS_PORT is required}"
: "${RDS_DATABASE:?RDS_DATABASE is required}"
: "${AWS_S3_BUCKET:?AWS_S3_BUCKET is required}"

command -v jq >/dev/null || { echo "FAIL: jq is not installed on this instance." >&2; exit 1; }
command -v aws >/dev/null || { echo "FAIL: aws CLI is not installed on this instance." >&2; exit 1; }

echo "Fetching RDS secret: ${RDS_SECRET_ID}" >&2
rds_secret_json="$(
  aws secretsmanager get-secret-value \
    --region "$AWS_REGION" \
    --secret-id "$RDS_SECRET_ID" \
    --query SecretString \
    --output text
)"

db_username="$(extract_field RDS "$rds_secret_json" username)"
db_password="$(extract_field RDS "$rds_secret_json" password)"

echo "Fetching app secret: ${APP_SECRET_ID}" >&2
app_secret_json="$(
  aws secretsmanager get-secret-value \
    --region "$AWS_REGION" \
    --secret-id "$APP_SECRET_ID" \
    --query SecretString \
    --output text
)"

auth_passcode="$(extract_field App "$app_secret_json" AUTH_PASSCODE)"
jwt_secret="$(extract_field App "$app_secret_json" JWT_SECRET)"

dotenv_line() {
  local key="$1"
  local value="$2"
  if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    printf 'secret %s contains a line break and cannot be written to an env file\n' "$key" >&2
    return 1
  fi
  printf '%s=%s\n' "$key" "$value"
}

runtime_env="$(mktemp "${deploy_root}/.env.secrets.XXXXXX")"
chmod 600 "$runtime_env"

{
  dotenv_line DB_URL "jdbc:postgresql://${RDS_ENDPOINT}:${RDS_PORT}/${RDS_DATABASE}"
  dotenv_line DB_USERNAME "$db_username"
  dotenv_line DB_PASSWORD "$db_password"
  dotenv_line AUTH_PASSCODE "$auth_passcode"
  dotenv_line JWT_SECRET "$jwt_secret"
  dotenv_line AWS_REGION "$AWS_REGION"
  dotenv_line AWS_S3_BUCKET "$AWS_S3_BUCKET"
} > "$runtime_env"

mv "$runtime_env" "${deploy_root}/.env.secrets"
