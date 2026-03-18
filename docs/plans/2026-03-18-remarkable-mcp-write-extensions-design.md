# remarkable-mcp Write Extensions Design

**Date:** 2026-03-18
**Status:** Approved
**Author:** Praveen Sehgal

## Overview

Fork [SamMorrowDrums/remarkable-mcp](https://github.com/SamMorrowDrums/remarkable-mcp) and extend it with write capabilities for the reMarkable Paper Pro Color tablet. Connection via WiFi (USB Web interface over local network).

## Goals

- Full CRUD operations on reMarkable tablet from Claude Code
- WiFi-first connection (no USB cable required)
- Keep all existing read/OCR functionality intact
- Ship as `uvx` installable MCP server

## Connection Layer

- `REMARKABLE_HOST` env var sets tablet's WiFi IP (e.g., `192.168.1.50`)
- Falls back to `10.11.99.1` (USB default) if not set
- `remarkable_status` tool enhanced to show connection info and IP

## New Write Methods on USBWebClient (`usb_web.py`)

```python
def upload(self, file_path: str, parent_id: str = "") -> Document
def create_folder(self, name: str, parent_id: str = "") -> Document
def delete(self, doc_id: str) -> bool
def move(self, doc_id: str, new_parent_id: str = None, new_name: str = None) -> Document
```

### USB Web API Endpoints Used

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Upload PDF/EPUB | POST | `/upload` (multipart form) |
| Create folder | POST | `/upload` with CollectionType |
| Delete | DELETE/POST | `/documents/{guid}` |
| Move/Rename | PUT | `/documents/{guid}` metadata update |

## New MCP Tools

### `remarkable_upload`
- **Input:** `file_path` (local Mac path), `destination` (folder path on tablet)
- **Behavior:** Resolves folder path to parent GUID, uploads via multipart POST
- **Output:** Confirmation with document name and location

### `remarkable_mkdir`
- **Input:** `path` (e.g., "/01 Work/NN Inc/Galaxy")
- **Behavior:** Creates nested folders (mkdir -p), creates intermediates if missing
- **Output:** Created folder info

### `remarkable_delete`
- **Input:** `path` (exact path to document/folder)
- **Behavior:** Resolves path to GUID, deletes
- **Output:** Confirmation of deletion

### `remarkable_move`
- **Input:** `source` (path), `destination` (path), optional `new_name`
- **Behavior:** Handles move-to-folder and rename operations
- **Output:** Updated document info

## API Layer (`api.py`)

Write-side functions that mirror existing read pattern:

```python
def upload_document(file_path, destination_folder) -> dict
def create_folder(path) -> dict
def delete_item(path) -> bool
def move_item(source, destination, new_name=None) -> dict
```

All functions resolve human-readable paths to GUIDs internally.

## Tool Annotations

```python
# Write tools
annotations=ToolAnnotations(destructiveHint=False)   # upload, mkdir, move
annotations=ToolAnnotations(destructiveHint=True)     # delete
```

## Claude Code Integration

```json
{
  "mcpServers": {
    "remarkable": {
      "command": "uvx",
      "args": ["remarkable-mcp", "--usb"],
      "env": {
        "REMARKABLE_HOST": "TABLET_WIFI_IP"
      }
    }
  }
}
```

## Testing Strategy

- Unit tests with mocked HTTP responses for all write endpoints
- Path-to-GUID resolution logic tested thoroughly
- Integration test script (opt-in, requires real tablet)

## Out of Scope (YAGNI)

- Cloud API write support (USB Web only for writes)
- Batch operations (one at a time)
- Notebook creation (upload existing PDFs/EPUBs only)
- Content editing (upload files, not edit pages)
- mDNS auto-discovery (just set the IP)
