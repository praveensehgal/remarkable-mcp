"""
reMarkable Cloud API client helpers.
"""

import json as json_module
import os
from pathlib import Path
from typing import Any, Dict, List

# Configuration - check env var first, then fall back to file
REMARKABLE_TOKEN = os.environ.get("REMARKABLE_TOKEN")
REMARKABLE_USE_SSH = os.environ.get("REMARKABLE_USE_SSH", "").lower() in (
    "1",
    "true",
    "yes",
)
REMARKABLE_USE_USB_WEB = os.environ.get("REMARKABLE_USE_USB_WEB", "").lower() in (
    "1",
    "true",
    "yes",
)
REMARKABLE_CONFIG_DIR = Path.home() / ".remarkable"
REMARKABLE_TOKEN_FILE = REMARKABLE_CONFIG_DIR / "token"
CACHE_DIR = REMARKABLE_CONFIG_DIR / "cache"


def get_rmapi():
    """
    Get or initialize the reMarkable API client.

    Priority order:
    1. USB web interface (if REMARKABLE_USE_USB_WEB=1)
    2. SSH (if REMARKABLE_USE_SSH=1)
    3. Cloud API (default, requires token)

    Returns RemarkableClient, SSHClient, or USBWebClient (all have compatible interfaces).
    """
    # Try USB web interface first (no auth required)
    if REMARKABLE_USE_USB_WEB:
        from remarkable_mcp.usb_web import create_usb_web_client

        return create_usb_web_client()

    # Check if SSH mode is enabled
    if REMARKABLE_USE_SSH:
        from remarkable_mcp.ssh import create_ssh_client

        return create_ssh_client()

    # Cloud API mode
    from remarkable_mcp.sync import load_client_from_token

    # If token is provided via environment, use it
    if REMARKABLE_TOKEN:
        # Also save to ~/.rmapi for compatibility
        rmapi_file = Path.home() / ".rmapi"
        rmapi_file.write_text(REMARKABLE_TOKEN)
        return load_client_from_token(REMARKABLE_TOKEN)

    # Load from file
    rmapi_file = Path.home() / ".rmapi"
    if not rmapi_file.exists():
        raise RuntimeError(
            "No reMarkable token found. Register first:\n"
            "  uvx remarkable-mcp --register <code>\n\n"
            "Get a code from: https://my.remarkable.com/device/desktop/connect\n\n"
            "Or use USB web interface (no dev mode required):\n"
            "  uvx remarkable-mcp --usb-web\n\n"
            "Or use SSH mode (requires USB connection + developer mode):\n"
            "  uvx remarkable-mcp --ssh"
        )

    try:
        token_json = rmapi_file.read_text()
        return load_client_from_token(token_json)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize reMarkable client: {e}")


def ensure_config_dir():
    """Ensure configuration directory exists."""
    REMARKABLE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def register_and_get_token(one_time_code: str) -> str:
    """
    Register with reMarkable using a one-time code and return the token.

    Get a code from: https://my.remarkable.com/device/desktop/connect
    """
    from remarkable_mcp.sync import register_device

    try:
        token_data = register_device(one_time_code)

        # Save to ~/.rmapi for compatibility
        rmapi_file = Path.home() / ".rmapi"
        token_json = json_module.dumps(token_data)
        rmapi_file.write_text(token_json)

        return token_json
    except Exception as e:
        raise RuntimeError(str(e))


def get_items_by_id(collection) -> Dict[str, Any]:
    """Build a lookup dict of items by ID."""
    return {item.ID: item for item in collection}


def get_items_by_parent(collection) -> Dict[str, List]:
    """Build a lookup dict of items grouped by parent ID."""
    items_by_parent: Dict[str, List] = {}
    for item in collection:
        parent = item.Parent if hasattr(item, "Parent") else ""
        if parent not in items_by_parent:
            items_by_parent[parent] = []
        items_by_parent[parent].append(item)
    return items_by_parent


def get_item_path(item, items_by_id: Dict[str, Any]) -> str:
    """Get the full path of an item."""
    path_parts = [item.VissibleName]
    parent_id = item.Parent if hasattr(item, "Parent") else ""
    while parent_id and parent_id in items_by_id:
        parent = items_by_id[parent_id]
        path_parts.insert(0, parent.VissibleName)
        parent_id = parent.Parent if hasattr(parent, "Parent") else ""
    return "/" + "/".join(path_parts)


def resolve_path_to_item(path: str, collection) -> Any:
    """Resolve a human-readable path like '/Work/Projects/Doc' to an item.

    Args:
        path: Absolute path starting with /
        collection: List of items from client.get_meta_items()

    Returns:
        The matching item

    Raises:
        FileNotFoundError: If path doesn't exist
    """
    path = path.strip("/")
    if not path:
        raise FileNotFoundError("Cannot resolve empty path")

    parts = path.split("/")
    current_parent = ""

    for i, part in enumerate(parts):
        found = None
        for item in collection:
            parent = item.Parent if hasattr(item, "Parent") else ""
            if parent == current_parent and item.VissibleName == part:
                found = item
                break
        if found is None:
            raise FileNotFoundError(f"Path not found: /{'/'.join(parts[: i + 1])}")
        if i < len(parts) - 1:
            current_parent = found.ID
        else:
            return found

    raise FileNotFoundError(f"Path not found: /{path}")


def resolve_path_to_parent_id(path: str, collection) -> str:
    """Resolve a folder path to its GUID. Returns '' for root '/'.

    Args:
        path: Folder path like '/Work/Projects' or '/'
        collection: List of items from client.get_meta_items()

    Returns:
        The folder's GUID, or '' for root
    """
    path = path.strip("/")
    if not path:
        return ""
    item = resolve_path_to_item("/" + path, collection)
    if not item.is_folder:
        raise ValueError(f"Path is not a folder: /{path}")
    return item.ID


def download_raw_file(client, doc, extension: str):
    """
    Download a raw file (PDF or EPUB) for a document.

    Args:
        client: The reMarkable API client (SSH or Cloud)
        doc: The document to download
        extension: File extension without dot (e.g., 'pdf', 'epub')

    Returns:
        Raw file bytes, or None if file doesn't exist or not supported
    """
    # SSH client has direct download_raw_file method
    if hasattr(client, "download_raw_file"):
        return client.download_raw_file(doc, extension)

    # Cloud client - raw files are not available via API
    # The cloud API only returns the notebook annotations, not source PDFs/EPUBs
    return None


def get_file_type(client, doc) -> str:
    """
    Get the file type (pdf, epub, notebook) for a document.

    Args:
        client: The reMarkable API client (SSH or Cloud)
        doc: The document to check

    Returns:
        File type string: 'pdf', 'epub', or 'notebook'
    """
    # SSH client has direct get_file_type method
    if hasattr(client, "get_file_type"):
        file_type = client.get_file_type(doc)
        if file_type:
            return file_type

    # Infer from document name
    name = doc.VissibleName.lower()
    if name.endswith(".pdf"):
        return "pdf"
    elif name.endswith(".epub"):
        return "epub"

    return "notebook"


def upload_document(file_path: str, destination: str = "/") -> Dict[str, Any]:
    """Upload a local file to the tablet.

    Args:
        file_path: Local file path (PDF or EPUB)
        destination: Folder path on tablet (e.g., '/Work/Projects')

    Returns:
        Dict with upload result info
    """
    import os as _os

    client = get_rmapi()
    collection = client.get_meta_items()

    parent_id = resolve_path_to_parent_id(destination, collection)

    if not _os.path.isfile(file_path):
        raise FileNotFoundError(f"Local file not found: {file_path}")

    filename = _os.path.basename(file_path)
    ext = _os.path.splitext(filename)[1].lower()
    if ext not in (".pdf", ".epub"):
        raise ValueError(f"Unsupported file type: {ext}. Only PDF and EPUB are supported.")

    with open(file_path, "rb") as f:
        file_data = f.read()

    doc = client.upload(file_data, filename, parent_id=parent_id)
    return {
        "name": doc.name,
        "destination": destination,
        "size_bytes": len(file_data),
        "type": ext.lstrip("."),
    }


def create_folder_path(path: str) -> Dict[str, Any]:
    """Create a folder, including intermediate folders (mkdir -p).

    Args:
        path: Full folder path (e.g., '/Work/Projects/Alpha')

    Returns:
        Dict with created folder info
    """
    client = get_rmapi()
    path = path.strip("/")
    if not path:
        raise ValueError("Cannot create root folder")

    parts = path.split("/")
    current_parent = ""
    created = []

    for part in parts:
        collection = client.get_meta_items()
        existing = None
        for item in collection:
            parent = item.Parent if hasattr(item, "Parent") else ""
            if parent == current_parent and item.VissibleName == part and item.is_folder:
                existing = item
                break

        if existing:
            current_parent = existing.ID
        else:
            doc = client.create_folder(part, parent_id=current_parent)
            created.append(part)
            current_parent = doc.ID

    # Restart UI once after all folders are created
    if created and hasattr(client, "restart_ui"):
        client.restart_ui()

    return {
        "path": "/" + "/".join(parts),
        "created_folders": created,
        "already_existed": len(parts) - len(created),
    }


def delete_item_by_path(path: str, doc_id: str = None) -> bool:
    """Delete a document or folder by path or ID.

    Args:
        path: Full path (e.g., '/Work/Old Doc')
        doc_id: Direct document ID (skips path resolution if provided)

    Returns:
        True if deleted
    """
    client = get_rmapi()
    if not doc_id:
        collection = client.get_meta_items()
        item = resolve_path_to_item(path, collection)
        doc_id = item.ID
    return client.delete_item(doc_id)


def move_item_by_path(
    source: str,
    destination: str,
    new_name: str = None,
    source_id: str = None,
    dest_id: str = None,
) -> Dict[str, Any]:
    """Move or rename a document/folder.

    Args:
        source: Current path (e.g., '/Work/Old Doc')
        destination: New parent folder path (e.g., '/Archive')
        new_name: New name (optional)
        source_id: Direct source ID (skips path resolution)
        dest_id: Direct destination folder ID (skips path resolution)

    Returns:
        Dict with move result info
    """
    client = get_rmapi()
    collection = client.get_meta_items()

    if not source_id:
        source_item = resolve_path_to_item(source, collection)
        source_id = source_item.ID
        source_name = source_item.VissibleName
    else:
        source_name = source.rsplit("/", 1)[-1]

    if not dest_id:
        dest_parent_id = resolve_path_to_parent_id(destination, collection)
    else:
        dest_parent_id = dest_id

    client.move_item(source_id, new_parent_id=dest_parent_id, new_name=new_name)

    return {
        "name": new_name or source_name,
        "from": source,
        "to": destination,
    }
