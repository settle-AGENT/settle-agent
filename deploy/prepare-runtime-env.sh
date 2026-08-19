#!/usr/bin/env bash

set -euo pipefail

deploy_root="${DEPLOY_ROOT:-/opt/fsai}"

cd "$deploy_root"

: "${AWS_REGION:?AWS_REGION is required}"
: "${RDS_SECRET_ID:?RDS_SECRET_ID is required}"
: "${APP_SECRET_ID:?APP_SECRET_ID is required}"
: "${RDS_ENDPOINT:?RDS_ENDPOINT is required}"
: "${RDS_PORT:?RDS_PORT is required}"
: "${RDS_DATABASE:?RDS_DATABASE is required}"
: "${AWS_S3_BUCKET:?AWS_S3_BUCKET is required}"

rds_secret_json="$(
  aws secretsmanager get-secret-value \
    --region "$AWS_REGION" \
    --secret-id "$RDS_SECRET_ID" \
    --query SecretString \
    --output text
)"

db_username="$(printf '%s' "$rds_secret_json" | jq -er '.username')"
db_password="$(printf '%s' "$rds_secret_json" | jq -er '.password')"

app_secret_json="$(
  aws secretsmanager get-secret-value \
    --region "$AWS_REGION" \
    --secret-id "$APP_SECRET_ID" \
    --query SecretString \
    --output text
)"

auth_passcode="$(printf '%s' "$app_secret_json" | jq -er '.AUTH_PASSCODE')"
jwt_secret="$(printf '%s' "$app_secret_json" | jq -er '.JWT_SECRET')"

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
