#!/bin/bash
# Encrypt sprout.db and push to Codeberg
# Usage: ./sync-memory.sh

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

if [ ! -f "$DB_PATH" ]; then
    echo "No sprout.db found at $DB_PATH"
    exit 1
fi

# Encrypt (overwrite existing)
gpg --batch --yes --symmetric --cipher-algo AES256 \
    --passphrase "$PASSPHRASE" \
    --output "$ENCRYPTED" "$DB_PATH"

cd "$SCRIPT_DIR"

# Commit and push if changed
if git diff --quiet "$ENCRYPTED" 2>/dev/null && git ls-files --error-unmatch sprout.db.gpg &>/dev/null; then
    echo "No changes to sprout.db"
    exit 0
fi

git add sprout.db.gpg
git commit -m "sync: encrypted memory $(date +%Y-%m-%d_%H:%M)"
git push codeberg main

echo "Memory synced to Codeberg at $(date)"
