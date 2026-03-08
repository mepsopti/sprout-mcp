#!/bin/bash
# Pull and decrypt sprout.db from Codeberg
# Usage: ./pull-memory.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_PATH="$HOME/.sprout/sprout.db"
ENCRYPTED="$SCRIPT_DIR/sprout.db.gpg"
PASSPHRASE_FILE="$SCRIPT_DIR/.sprout-passphrase"
if [ ! -f "$PASSPHRASE_FILE" ]; then
    echo "No passphrase file found. Run: echo 'YOUR_PASSPHRASE' > $PASSPHRASE_FILE"
    exit 1
fi
PASSPHRASE="$(cat "$PASSPHRASE_FILE")"

cd "$SCRIPT_DIR"
git pull codeberg main

if [ ! -f "$ENCRYPTED" ]; then
    echo "No encrypted DB found"
    exit 1
fi

mkdir -p "$(dirname "$DB_PATH")"

gpg --batch --yes --decrypt \
    --passphrase "$PASSPHRASE" \
    --output "$DB_PATH" "$ENCRYPTED"

echo "Memory restored to $DB_PATH"
