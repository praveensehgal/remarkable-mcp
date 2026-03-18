#!/bin/bash
# Push daily journal to reMarkable tablet as color-highlighted PDF
# Usage: push-journal.sh [YYYY-MM-DD]
# Defaults to yesterday if no date given

set -e

# Config
RM_HOST="${REMARKABLE_SSH_HOST:-192.168.50.143}"
RM_PASS="${REMARKABLE_SSH_PASSWORD:-GvNM9CADOF}"
JOURNAL_DIR="$HOME/clawd/journal"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
XDIR="/home/root/.local/share/remarkable/xochitl"
BRIEF_FOLDER="466523f0-5c97-4655-b49c-9f02443ed77b"  # 05 Personal/Daily Briefs

# Date (yesterday by default)
if [ -n "$1" ]; then
    DATE="$1"
else
    DATE=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)
fi

JOURNAL_FILE="$JOURNAL_DIR/${DATE}.md"

if [ ! -f "$JOURNAL_FILE" ]; then
    echo "No journal found: $JOURNAL_FILE"
    exit 1
fi

echo "Converting ${DATE} journal to color PDF..."
PDF_FILE="/tmp/journal-${DATE}.pdf"

# Use color-highlighted PDF converter
cd "$PROJECT_DIR"
uv run python3 scripts/journal_to_pdf.py "$JOURNAL_FILE" "$PDF_FILE"

# Generate document ID and timestamp
DOC_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
NOW=$(date +%s)000
DISPLAY_DATE=$(date -jf "%Y-%m-%d" "$DATE" "+%B %d, %Y" 2>/dev/null || date -d "$DATE" "+%B %d, %Y")
TITLE="Journal - ${DISPLAY_DATE}"

echo "Uploading to reMarkable: ${TITLE}..."

# Check SSH connectivity
if ! sshpass -p "$RM_PASS" ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${RM_HOST}" 'echo ok' >/dev/null 2>&1; then
    echo "Cannot reach reMarkable at ${RM_HOST}. Is it awake and on WiFi?"
    exit 1
fi

# Upload PDF
cat "$PDF_FILE" | sshpass -p "$RM_PASS" ssh "root@${RM_HOST}" "cat > ${XDIR}/${DOC_ID}.pdf"

# Upload metadata
cat <<EOF | sshpass -p "$RM_PASS" ssh "root@${RM_HOST}" "cat > ${XDIR}/${DOC_ID}.metadata"
{
    "deleted": false,
    "lastModified": "${NOW}",
    "metadatamodified": true,
    "modified": true,
    "parent": "${BRIEF_FOLDER}",
    "pinned": false,
    "synced": false,
    "type": "DocumentType",
    "version": 1,
    "visibleName": "${TITLE}"
}
EOF

# Upload content descriptor
cat <<EOF | sshpass -p "$RM_PASS" ssh "root@${RM_HOST}" "cat > ${XDIR}/${DOC_ID}.content"
{
    "dummyDocument": false,
    "extraMetadata": {},
    "fileType": "pdf",
    "fontName": "",
    "lastOpenedPage": 0,
    "legacyEpub": false,
    "lineHeight": -1,
    "margins": 100,
    "orientation": "portrait",
    "pageCount": 0,
    "textScale": 1,
    "transform": {}
}
EOF

# Cleanup
rm -f "$PDF_FILE" "/tmp/journal-${DATE}.html"

echo "Done! '${TITLE}' is on your reMarkable in 05 Personal/Daily Briefs"
