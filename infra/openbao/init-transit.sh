#!/bin/sh
set -eu

: "${OPENBAO_ADDR:=http://openbao:8200}"
: "${OPENBAO_TOKEN:?OPENBAO_TOKEN is required}"
: "${OPENBAO_KEY_NAME:=password-detective-plugin-platform}"

export VAULT_ADDR="$OPENBAO_ADDR"
export VAULT_TOKEN="$OPENBAO_TOKEN"

bao status >/dev/null 2>&1 || true
if ! bao secrets list -format=json | grep -q '"transit/"'; then
  bao secrets enable transit
fi
if ! bao read -field=type "transit/keys/$OPENBAO_KEY_NAME" >/dev/null 2>&1; then
  bao write "transit/keys/$OPENBAO_KEY_NAME" type=ed25519 exportable=false allow_plaintext_backup=false
fi
