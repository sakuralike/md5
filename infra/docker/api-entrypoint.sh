#!/bin/sh
set -eu

RUNTIME_SECRET_DIR=/run/password-detective-secrets
RUNTIME_DATA_DIRS="
/var/lib/password-detective/desktop-plugins
/var/lib/password-detective/desktop-updates
/var/lib/password-detective/site-assets
"
FILE_VARIABLES="
APP_SECRET_KEY_FILE
DATABASE_URL_FILE
REDIS_URL_FILE
CANDIDATE_SECRET_KEY_VERSION_FILE
CANDIDATE_SECRET_KEYRING_FILE
CANDIDATE_SECRET_DEDUP_KEY_FILE
DIRECT_MESSAGE_KEY_VERSION_FILE
DIRECT_MESSAGE_KEYRING_FILE
NOTIFICATION_WEBHOOK_SECRET_FILE
NOTIFICATION_SMTP_PASSWORD_FILE
DESKTOP_PLUGIN_S3_ACCESS_KEY_ID_FILE
DESKTOP_PLUGIN_S3_SECRET_ACCESS_KEY_FILE
DESKTOP_PLUGIN_GITHUB_TOKEN_FILE
"

copy_file_backed_settings() {
    umask 077
    mkdir -p "$RUNTIME_SECRET_DIR"
    chown app:app "$RUNTIME_SECRET_DIR"
    chmod 0700 "$RUNTIME_SECRET_DIR"

    for variable_name in $FILE_VARIABLES; do
        source_path=$(printenv "$variable_name" 2>/dev/null || true)
        if [ -z "$source_path" ]; then
            continue
        fi
        if [ ! -f "$source_path" ] || [ ! -r "$source_path" ]; then
            echo "file-backed setting is not readable: $variable_name" >&2
            exit 1
        fi
        destination="$RUNTIME_SECRET_DIR/$(echo "$variable_name" | tr 'A-Z' 'a-z')"
        cp "$source_path" "$destination"
        chown app:app "$destination"
        chmod 0400 "$destination"
        export "$variable_name=$destination"
    done
}

prepare_runtime_data_directories() {
    for directory in $RUNTIME_DATA_DIRS; do
        mkdir -p "$directory"
        chown app:app "$directory"
        chmod 0750 "$directory"
    done
}

if [ "$(id -u)" = "0" ]; then
    prepare_runtime_data_directories
    copy_file_backed_settings
    exec su-exec app "$@"
fi

exec "$@"
