#!/bin/bash
# Push any markdown or PDF to reMarkable tablet
# Usage: push-to-remarkable.sh <file> [--title "Title"] [--folder "folder-uuid"]
#
# Examples:
#   push-to-remarkable.sh digest.md --title "Morning Digest - March 18"
#   push-to-remarkable.sh report.pdf --title "Weekly Insights"
#   push-to-remarkable.sh notes.md --folder "some-uuid-here"
#
# Default folder: 05 Personal/Daily Briefs

set -e

# Config
RM_HOST="${REMARKABLE_SSH_HOST:-192.168.50.143}"
RM_PASS="${REMARKABLE_SSH_PASSWORD:-GvNM9CADOF}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
XDIR="/home/root/.local/share/remarkable/xochitl"
DEFAULT_FOLDER="466523f0-5c97-4655-b49c-9f02443ed77b"  # 05 Personal/Daily Briefs

# Parse args
INPUT_FILE=""
TITLE=""
FOLDER="$DEFAULT_FOLDER"

while [ $# -gt 0 ]; do
    case "$1" in
        --title) TITLE="$2"; shift 2 ;;
        --folder) FOLDER="$2"; shift 2 ;;
        *) INPUT_FILE="$1"; shift ;;
    esac
done

if [ -z "$INPUT_FILE" ] || [ ! -f "$INPUT_FILE" ]; then
    echo "Usage: push-to-remarkable.sh <file.md|file.pdf> [--title \"Title\"] [--folder uuid]"
    exit 1
fi

# Default title from filename
if [ -z "$TITLE" ]; then
    TITLE=$(basename "$INPUT_FILE" | sed 's/\.[^.]*$//' | tr '_-' ' ')
fi

EXT="${INPUT_FILE##*.}"
PDF_FILE=""
CLEANUP=""

# Convert markdown to color PDF if needed
if [ "$EXT" = "md" ] || [ "$EXT" = "markdown" ]; then
    echo "Converting markdown to color PDF..."
    PDF_FILE="/tmp/rm-push-$(date +%s).pdf"
    cd "$PROJECT_DIR"
    uv run python3 scripts/journal_to_pdf.py "$INPUT_FILE" "$PDF_FILE"
    CLEANUP="$PDF_FILE ${PDF_FILE%.pdf}.html"
elif [ "$EXT" = "pdf" ]; then
    PDF_FILE="$INPUT_FILE"
else
    echo "Unsupported file type: .$EXT (use .md or .pdf)"
    exit 1
fi

# Check SSH connectivity
if ! sshpass -p "$RM_PASS" ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${RM_HOST}" 'echo ok' >/dev/null 2>&1; then
    echo "Cannot reach reMarkable at ${RM_HOST}. Is it awake and on WiFi?"
    [ -n "$CLEANUP" ] && rm -f $CLEANUP
    exit 1
fi

# Generate document ID
DOC_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
NOW=$(date +%s)000

echo "Uploading: ${TITLE}..."

# Upload PDF
cat "$PDF_FILE" | sshpass -p "$RM_PASS" ssh "root@${RM_HOST}" "cat > ${XDIR}/${DOC_ID}.pdf"

# Upload metadata
cat <<EOF | sshpass -p "$RM_PASS" ssh "root@${RM_HOST}" "cat > ${XDIR}/${DOC_ID}.metadata"
{
    "deleted": false,
    "lastModified": "${NOW}",
    "metadatamodified": true,
    "modified": true,
    "parent": "${FOLDER}",
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

# Cleanup temp files
[ -n "$CLEANUP" ] && rm -f $CLEANUP

echo "Done! '${TITLE}' → reMarkable"
