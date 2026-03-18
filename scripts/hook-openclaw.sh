#!/bin/bash
# Hook into OpenClaw jobs to push output to reMarkable
# Add to OpenClaw job payloads or call from post-delivery hooks
#
# This script monitors the journal directory and auto-pushes new entries.
# Run via cron at 5 AM and 7 PM daily to catch morning digest and evening brief.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JOURNAL_DIR="$HOME/clawd/journal"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)

# Track what we've already pushed (avoid duplicates)
PUSH_LOG="$HOME/.remarkable/push-log.txt"
mkdir -p "$(dirname "$PUSH_LOG")"
touch "$PUSH_LOG"

push_if_new() {
    local file="$1"
    local title="$2"

    if [ ! -f "$file" ]; then
        return
    fi

    # Skip if already pushed
    if grep -q "$file" "$PUSH_LOG" 2>/dev/null; then
        echo "Already pushed: $title"
        return
    fi

    echo "Pushing: $title"
    "$SCRIPT_DIR/push-to-remarkable.sh" "$file" --title "$title"

    # Log it
    echo "$file" >> "$PUSH_LOG"
}

# Push today's journal if it exists (evening brief creates it)
DISPLAY_TODAY=$(date "+%B %d, %Y")
push_if_new "$JOURNAL_DIR/${TODAY}.md" "Journal - ${DISPLAY_TODAY}"

# Push yesterday's journal if not yet pushed (morning catch-up)
DISPLAY_YESTERDAY=$(date -v-1d "+%B %d, %Y" 2>/dev/null || date -d "yesterday" "+%B %d, %Y")
push_if_new "$JOURNAL_DIR/${YESTERDAY}.md" "Journal - ${DISPLAY_YESTERDAY}"

echo "Done."
