# remarkable-mcp Write Extensions — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fork SamMorrowDrums/remarkable-mcp and add write capabilities (upload, mkdir, delete, move) with WiFi connection support.

**Architecture:** Extend the existing USBWebClient with write HTTP methods, add 4 new MCP tools that resolve human-readable paths to GUIDs, and update the CLI/server to support WiFi host configuration.

**Tech Stack:** Python 3.10+, mcp SDK (FastMCP), requests, pytest, pytest-asyncio

---

### Task 1: Fork Upstream and Set Up Project

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`

**Step 1: Fork and pull upstream code**

```bash
cd /Users/praveensehgal/Dropbox/Work/PERSONAL_PROJECTS/remarkable
git remote add upstream https://github.com/SamMorrowDrums/remarkable-mcp.git
git fetch upstream
git merge upstream/main --allow-unrelated-histories
```

If conflicts with existing files (folder-structure.md, docs/plans/), keep ours:
```bash
git checkout --ours docs/plans/ folder-structure.md
git add .
git commit -m "chore: merge upstream remarkable-mcp"
```

**Step 2: Update pyproject.toml**

Change project name and author:
```python
[project]
name = "remarkable-mcp-rw"
description = "MCP server for reMarkable — read, write, and manage your tablet"
authors = [
    { name = "Praveen Sehgal" },
    { name = "Sam Morrow" }
]
```

**Step 3: Verify upstream tests pass**

Run: `uv sync --all-extras && uv run pytest test_server.py -v`
Expected: All existing tests pass

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: fork remarkable-mcp, update project metadata"
```

---

### Task 2: Add WiFi Host Support to USBWebClient

**Files:**
- Modify: `remarkable_mcp/usb_web.py`
- Modify: `remarkable_mcp/cli.py`
- Create: `tests/test_usb_web_write.py`

**Step 1: Write failing test for REMARKABLE_HOST env var**

```python
# tests/test_usb_web_write.py
import os
import pytest
from remarkable_mcp.usb_web import create_usb_web_client, DEFAULT_USB_HOST


def test_default_host():
    """Default host is USB address."""
    os.environ.pop("REMARKABLE_HOST", None)
    os.environ.pop("REMARKABLE_USB_HOST", None)
    client = create_usb_web_client()
    assert client.host == DEFAULT_USB_HOST


def test_remarkable_host_env_var():
    """REMARKABLE_HOST env var overrides default."""
    os.environ["REMARKABLE_HOST"] = "http://192.168.1.50"
    try:
        client = create_usb_web_client()
        assert client.host == "http://192.168.1.50"
    finally:
        del os.environ["REMARKABLE_HOST"]


def test_remarkable_host_takes_priority():
    """REMARKABLE_HOST takes priority over REMARKABLE_USB_HOST."""
    os.environ["REMARKABLE_HOST"] = "http://192.168.1.50"
    os.environ["REMARKABLE_USB_HOST"] = "http://10.11.99.1"
    try:
        client = create_usb_web_client()
        assert client.host == "http://192.168.1.50"
    finally:
        del os.environ["REMARKABLE_HOST"]
        del os.environ["REMARKABLE_USB_HOST"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_usb_web_write.py -v`
Expected: FAIL — `REMARKABLE_HOST` not recognized yet

**Step 3: Update `create_usb_web_client` in `usb_web.py`**

```python
def create_usb_web_client(
    host: Optional[str] = None, timeout: Optional[int] = None
) -> USBWebClient:
    import os
    return USBWebClient(
        host=host
        or os.environ.get("REMARKABLE_HOST")
        or os.environ.get("REMARKABLE_USB_HOST", DEFAULT_USB_HOST),
        timeout=timeout or int(os.environ.get("REMARKABLE_USB_TIMEOUT", "10")),
    )
```

**Step 4: Add `--wifi` CLI flag to `cli.py`**

Add to argparse:
```python
parser.add_argument(
    "--wifi",
    action="store_true",
    help="Use WiFi connection (set REMARKABLE_HOST to tablet IP)",
)
```

Add handler (same as `--usb` but semantically clearer):
```python
elif args.wifi:
    os.environ["REMARKABLE_USE_USB_WEB"] = "1"
    from remarkable_mcp.server import run
    run()
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_usb_web_write.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add remarkable_mcp/usb_web.py remarkable_mcp/cli.py tests/test_usb_web_write.py
git commit -m "feat: add REMARKABLE_HOST env var and --wifi CLI flag"
```

---

### Task 3: Add Path Resolution Helpers to `api.py`

**Files:**
- Modify: `remarkable_mcp/api.py`
- Create: `tests/test_path_resolution.py`

**Step 1: Write failing tests for path resolution**

```python
# tests/test_path_resolution.py
import pytest
from unittest.mock import MagicMock
from remarkable_mcp.api import resolve_path_to_item, resolve_path_to_parent_id


def _make_doc(doc_id, name, parent="", doc_type="DocumentType"):
    """Create a mock document."""
    doc = MagicMock()
    doc.ID = doc_id
    doc.id = doc_id
    doc.VissibleName = name
    doc.name = name
    doc.Parent = parent
    doc.parent = parent
    doc.Type = doc_type
    doc.doc_type = doc_type
    doc.is_folder = doc_type == "CollectionType"
    doc.tags = []
    return doc


def _make_collection():
    """Create a mock folder structure: /Work/Projects/Alpha"""
    root_folder = _make_doc("f1", "Work", "", "CollectionType")
    sub_folder = _make_doc("f2", "Projects", "f1", "CollectionType")
    deep_folder = _make_doc("f3", "Alpha", "f2", "CollectionType")
    doc1 = _make_doc("d1", "Meeting Notes", "f2", "DocumentType")
    return [root_folder, sub_folder, deep_folder, doc1]


def test_resolve_root():
    collection = _make_collection()
    item = resolve_path_to_item("/Work", collection)
    assert item.ID == "f1"


def test_resolve_nested_path():
    collection = _make_collection()
    item = resolve_path_to_item("/Work/Projects", collection)
    assert item.ID == "f2"


def test_resolve_deep_path():
    collection = _make_collection()
    item = resolve_path_to_item("/Work/Projects/Alpha", collection)
    assert item.ID == "f3"


def test_resolve_document():
    collection = _make_collection()
    item = resolve_path_to_item("/Work/Projects/Meeting Notes", collection)
    assert item.ID == "d1"


def test_resolve_nonexistent_raises():
    collection = _make_collection()
    with pytest.raises(FileNotFoundError):
        resolve_path_to_item("/Nonexistent", collection)


def test_resolve_parent_id_root():
    collection = _make_collection()
    parent_id = resolve_path_to_parent_id("/", collection)
    assert parent_id == ""


def test_resolve_parent_id_folder():
    collection = _make_collection()
    parent_id = resolve_path_to_parent_id("/Work/Projects", collection)
    assert parent_id == "f2"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_path_resolution.py -v`
Expected: FAIL — functions don't exist

**Step 3: Implement `resolve_path_to_item` and `resolve_path_to_parent_id` in `api.py`**

```python
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
    items_by_id = get_items_by_id(collection)
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
            raise FileNotFoundError(f"Path not found: /{'/'.join(parts[:i+1])}")
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
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_path_resolution.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add remarkable_mcp/api.py tests/test_path_resolution.py
git commit -m "feat: add path-to-GUID resolution helpers"
```

---

### Task 4: Add Write Methods to USBWebClient

**Files:**
- Modify: `remarkable_mcp/usb_web.py`
- Modify: `tests/test_usb_web_write.py`

**Step 1: Write failing tests for upload, create_folder, delete, move**

```python
# Append to tests/test_usb_web_write.py
from unittest.mock import patch, MagicMock
import json


class TestUSBWebUpload:
    """Test upload functionality."""

    @patch("remarkable_mcp.usb_web.requests.request")
    def test_upload_pdf(self, mock_request):
        """Upload a PDF returns a Document."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"ID": "new-guid", "VissibleName": "test.pdf", "Type": "DocumentType"}
        ]
        mock_request.return_value = mock_response

        client = create_usb_web_client()
        # upload expects file bytes and filename
        result = client.upload(b"%PDF-fake", "test.pdf", parent_id="")
        assert result is not None
        assert mock_request.called

    @patch("remarkable_mcp.usb_web.requests.request")
    def test_create_folder(self, mock_request):
        """Create folder sends POST and returns Document."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"ID": "folder-guid", "VissibleName": "New Folder", "Type": "CollectionType"}
        ]
        mock_request.return_value = mock_response

        client = create_usb_web_client()
        result = client.create_folder("New Folder", parent_id="")
        assert result is not None

    @patch("remarkable_mcp.usb_web.requests.request")
    def test_delete_document(self, mock_request):
        """Delete sends DELETE request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        client = create_usb_web_client()
        result = client.delete_item("some-guid")
        assert result is True

    @patch("remarkable_mcp.usb_web.requests.request")
    def test_move_document(self, mock_request):
        """Move sends PUT with updated parent."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        client = create_usb_web_client()
        result = client.move_item("doc-guid", new_parent_id="folder-guid")
        assert result is True
```

**Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_usb_web_write.py -v`
Expected: FAIL — methods don't exist

**Step 3: Implement write methods on USBWebClient**

Add to `usb_web.py`:

```python
# New endpoints
UPLOAD_URL = "/upload"
DOCUMENT_URL = "/documents/{guid}"

class USBWebClient:
    # ... existing methods ...

    def upload(self, file_data: bytes, filename: str, parent_id: str = "") -> Optional[Document]:
        """Upload a PDF or EPUB to the tablet.

        Args:
            file_data: Raw file bytes
            filename: Original filename (e.g., 'report.pdf')
            parent_id: Parent folder GUID ('' for root)

        Returns:
            Document object for the uploaded file
        """
        url = f"{self.host}{UPLOAD_URL}"
        files = {"file": (filename, file_data)}
        data = {}
        if parent_id:
            data["parent"] = parent_id

        try:
            response = requests.post(url, files=files, data=data, timeout=self.DOWNLOAD_TIMEOUT)
            response.raise_for_status()
            # Invalidate cache
            self._documents = []
            self._documents_by_id = {}
            return self._parse_upload_response(response, filename, parent_id)
        except requests.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to reMarkable at {self.host}. "
                "Check WiFi connection and tablet IP."
            )
        except requests.HTTPError as e:
            raise RuntimeError(f"Upload failed: {e}")

    def _parse_upload_response(self, response, filename: str, parent_id: str) -> Document:
        """Parse upload response into a Document."""
        try:
            data = response.json()
            if isinstance(data, list) and data:
                return self._parse_document_entry(data[0], parent=parent_id)
        except Exception:
            pass
        # Fallback: return minimal document
        return Document(
            id="uploaded",
            hash="",
            name=filename,
            doc_type="DocumentType",
            parent=parent_id,
        )

    def create_folder(self, name: str, parent_id: str = "") -> Document:
        """Create a new folder on the tablet.

        Args:
            name: Folder name
            parent_id: Parent folder GUID ('' for root)

        Returns:
            Document object for the created folder
        """
        url = f"{self.host}{UPLOAD_URL}"
        # reMarkable USB web uses multipart upload with special content type
        import io
        import json as json_mod
        import zipfile

        # Create a minimal .content file for a folder
        content_data = json_mod.dumps({
            "dummyDocument": False,
            "extraMetadata": {},
            "fileType": "",
            "fontName": "",
            "lastOpenedPage": 0,
            "legacyEpub": False,
            "lineHeight": -1,
            "margins": 100,
            "orientation": "portrait",
            "pageCount": 0,
            "textScale": 1,
            "transform": {}
        })

        # Build metadata
        metadata = json_mod.dumps({
            "type": "CollectionType",
            "visibleName": name,
            "parent": parent_id,
        })

        files = {"file": (f"{name}.metadata", metadata.encode(), "application/json")}
        data = {"parent": parent_id}

        try:
            response = requests.post(url, files=files, data=data, timeout=self.timeout)
            response.raise_for_status()
            self._documents = []
            self._documents_by_id = {}
            return Document(
                id="pending",
                hash="",
                name=name,
                doc_type="CollectionType",
                parent=parent_id,
            )
        except requests.HTTPError as e:
            raise RuntimeError(f"Failed to create folder '{name}': {e}")

    def delete_item(self, doc_id: str) -> bool:
        """Delete a document or folder from the tablet.

        Args:
            doc_id: Document/folder GUID

        Returns:
            True if deleted successfully
        """
        url = f"{self.host}/documents/{doc_id}"
        try:
            response = requests.delete(url, timeout=self.timeout)
            response.raise_for_status()
            self._documents = []
            self._documents_by_id = {}
            return True
        except requests.HTTPError as e:
            raise RuntimeError(f"Failed to delete {doc_id}: {e}")

    def move_item(self, doc_id: str, new_parent_id: str = None, new_name: str = None) -> bool:
        """Move or rename a document/folder.

        Args:
            doc_id: Document/folder GUID
            new_parent_id: New parent folder GUID (None to keep current)
            new_name: New name (None to keep current)

        Returns:
            True if moved successfully
        """
        url = f"{self.host}/documents/{doc_id}"
        payload = {}
        if new_parent_id is not None:
            payload["parent"] = new_parent_id
        if new_name is not None:
            payload["VissibleName"] = new_name

        try:
            response = requests.put(
                url, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
            self._documents = []
            self._documents_by_id = {}
            return True
        except requests.HTTPError as e:
            raise RuntimeError(f"Failed to move/rename {doc_id}: {e}")
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_usb_web_write.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add remarkable_mcp/usb_web.py tests/test_usb_web_write.py
git commit -m "feat: add upload, create_folder, delete, move to USBWebClient"
```

---

### Task 5: Add Write API Functions to `api.py`

**Files:**
- Modify: `remarkable_mcp/api.py`
- Create: `tests/test_write_api.py`

**Step 1: Write failing tests**

```python
# tests/test_write_api.py
import pytest
from unittest.mock import patch, MagicMock
from remarkable_mcp.api import (
    upload_document,
    create_folder_path,
    delete_item_by_path,
    move_item_by_path,
)


def _make_doc(doc_id, name, parent="", doc_type="DocumentType"):
    doc = MagicMock()
    doc.ID = doc_id
    doc.id = doc_id
    doc.VissibleName = name
    doc.name = name
    doc.Parent = parent
    doc.parent = parent
    doc.Type = doc_type
    doc.doc_type = doc_type
    doc.is_folder = doc_type == "CollectionType"
    doc.tags = []
    return doc


@patch("remarkable_mcp.api.get_rmapi")
def test_create_folder_path_nested(mock_rmapi):
    """create_folder_path creates intermediate folders."""
    client = MagicMock()
    # Empty collection — no folders exist yet
    client.get_meta_items.return_value = []
    client.create_folder.return_value = _make_doc("f1", "Work", "", "CollectionType")
    mock_rmapi.return_value = client

    result = create_folder_path("/Work")
    assert client.create_folder.called


@patch("remarkable_mcp.api.get_rmapi")
def test_delete_item_by_path(mock_rmapi):
    """delete_item_by_path resolves path and deletes."""
    work = _make_doc("f1", "Work", "", "CollectionType")
    doc = _make_doc("d1", "Old Doc", "f1", "DocumentType")
    client = MagicMock()
    client.get_meta_items.return_value = [work, doc]
    client.delete_item.return_value = True
    mock_rmapi.return_value = client

    result = delete_item_by_path("/Work/Old Doc")
    assert result is True
    client.delete_item.assert_called_once_with("d1")
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_write_api.py -v`
Expected: FAIL

**Step 3: Implement write API functions in `api.py`**

```python
def upload_document(file_path: str, destination: str = "/") -> Dict[str, Any]:
    """Upload a local file to the tablet.

    Args:
        file_path: Local file path (PDF or EPUB)
        destination: Folder path on tablet (e.g., '/Work/Projects')

    Returns:
        Dict with upload result info
    """
    import os
    client = get_rmapi()
    collection = client.get_meta_items()

    # Resolve destination folder
    parent_id = resolve_path_to_parent_id(destination, collection)

    # Read local file
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Local file not found: {file_path}")

    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()
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
        # Check if this folder already exists
        existing = None
        for item in collection:
            parent = item.Parent if hasattr(item, "Parent") else ""
            if (parent == current_parent
                    and item.VissibleName == part
                    and item.is_folder):
                existing = item
                break

        if existing:
            current_parent = existing.ID
        else:
            doc = client.create_folder(part, parent_id=current_parent)
            created.append(part)
            # Refresh to get the new folder's ID
            collection = client.get_meta_items()
            for item in collection:
                parent_attr = item.Parent if hasattr(item, "Parent") else ""
                if parent_attr == current_parent and item.VissibleName == part:
                    current_parent = item.ID
                    break

    return {
        "path": "/" + path,
        "created_folders": created,
        "already_existed": len(parts) - len(created),
    }


def delete_item_by_path(path: str) -> bool:
    """Delete a document or folder by path.

    Args:
        path: Full path (e.g., '/Work/Old Doc')

    Returns:
        True if deleted
    """
    client = get_rmapi()
    collection = client.get_meta_items()
    item = resolve_path_to_item(path, collection)
    return client.delete_item(item.ID)


def move_item_by_path(
    source: str, destination: str, new_name: str = None
) -> Dict[str, Any]:
    """Move or rename a document/folder.

    Args:
        source: Current path (e.g., '/Work/Old Doc')
        destination: New parent folder path (e.g., '/Archive')
        new_name: New name (optional)

    Returns:
        Dict with move result info
    """
    client = get_rmapi()
    collection = client.get_meta_items()

    source_item = resolve_path_to_item(source, collection)
    dest_parent_id = resolve_path_to_parent_id(destination, collection)

    client.move_item(source_item.ID, new_parent_id=dest_parent_id, new_name=new_name)

    return {
        "name": new_name or source_item.VissibleName,
        "from": source,
        "to": destination,
    }
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_write_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add remarkable_mcp/api.py tests/test_write_api.py
git commit -m "feat: add write API functions (upload, mkdir, delete, move)"
```

---

### Task 6: Add MCP Write Tools to `tools.py`

**Files:**
- Modify: `remarkable_mcp/tools.py`
- Create: `tests/test_write_tools.py`

**Step 1: Write failing tests for MCP tool registration**

```python
# tests/test_write_tools.py
import pytest


def test_tools_registered():
    """All write tools are registered on the MCP server."""
    from remarkable_mcp.server import mcp

    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "remarkable_upload" in tool_names
    assert "remarkable_mkdir" in tool_names
    assert "remarkable_delete" in tool_names
    assert "remarkable_move" in tool_names
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_write_tools.py -v`
Expected: FAIL

**Step 3: Add 4 write tools to `tools.py`**

Add these imports at the top of `tools.py`:
```python
from remarkable_mcp.api import (
    upload_document,
    create_folder_path,
    delete_item_by_path,
    move_item_by_path,
)
```

Add these tool functions at the end of `tools.py`:

```python
@mcp.tool(
    annotations=ToolAnnotations(
        title="Upload Document",
        readOnlyHint=False,
        destructiveHint=False,
    )
)
def remarkable_upload(file_path: str, destination: str = "/") -> str:
    """
    <usecase>Upload a PDF or EPUB file to your reMarkable tablet.</usecase>
    <instructions>
    Uploads a local file from your computer to the tablet.
    Only PDF and EPUB formats are supported.

    The destination is a folder path on the tablet where the file will be placed.
    If the destination folder doesn't exist, use remarkable_mkdir first.
    </instructions>
    <parameters>
    - file_path: Absolute path to the local PDF or EPUB file
    - destination: Folder path on tablet (default: "/" for root)
    </parameters>
    <examples>
    - remarkable_upload("/Users/praveen/report.pdf", "/01 Work/USMS-JPATS")
    - remarkable_upload("/tmp/ebook.epub", "/05 Personal/Reading")
    - remarkable_upload("/Users/praveen/notes.pdf")  # uploads to root
    </examples>
    """
    try:
        result = upload_document(file_path, destination)
        return make_response(
            result,
            f"Uploaded '{result['name']}' to {result['destination']}."
        )
    except FileNotFoundError as e:
        return make_error("not_found", str(e), "Check the file path exists on your Mac.")
    except ValueError as e:
        return make_error("invalid_type", str(e), "Only .pdf and .epub files are supported.")
    except Exception as e:
        return make_error("upload_failed", str(e), "Check tablet connection with remarkable_status().")


@mcp.tool(
    annotations=ToolAnnotations(
        title="Create Folder",
        readOnlyHint=False,
        destructiveHint=False,
    )
)
def remarkable_mkdir(path: str) -> str:
    """
    <usecase>Create a folder (or nested folders) on your reMarkable tablet.</usecase>
    <instructions>
    Creates the folder at the given path. If intermediate folders don't exist,
    they are created automatically (like mkdir -p).

    Use this to set up your folder structure before uploading documents.
    </instructions>
    <parameters>
    - path: Full folder path to create (e.g., "/01 Work/NN Inc/Galaxy")
    </parameters>
    <examples>
    - remarkable_mkdir("/01 Work")
    - remarkable_mkdir("/01 Work/USMS-JPATS/JMISFIN")  # creates all levels
    - remarkable_mkdir("/05 Personal/Reading")
    </examples>
    """
    try:
        result = create_folder_path(path)
        if result["created_folders"]:
            msg = f"Created: {', '.join(result['created_folders'])}."
        else:
            msg = f"All folders in '{path}' already exist."
        return make_response(result, msg)
    except ValueError as e:
        return make_error("invalid_path", str(e), "Provide a path like '/Folder/Subfolder'.")
    except Exception as e:
        return make_error("mkdir_failed", str(e), "Check tablet connection with remarkable_status().")


@mcp.tool(
    annotations=ToolAnnotations(
        title="Delete Document or Folder",
        readOnlyHint=False,
        destructiveHint=True,
    )
)
def remarkable_delete(path: str) -> str:
    """
    <usecase>Delete a document or folder from your reMarkable tablet.</usecase>
    <instructions>
    Permanently deletes the item at the given path. This cannot be undone.

    For folders, all contents are deleted recursively.
    Use remarkable_browse to verify the path before deleting.
    </instructions>
    <parameters>
    - path: Exact path to the document or folder to delete
    </parameters>
    <examples>
    - remarkable_delete("/01 Work/Old Project")
    - remarkable_delete("/05 Personal/Reading/finished-book.pdf")
    </examples>
    """
    try:
        result = delete_item_by_path(path)
        return make_response(
            {"deleted": path, "success": result},
            f"Deleted '{path}'."
        )
    except FileNotFoundError:
        return make_error(
            "not_found",
            f"Path not found: {path}",
            "Use remarkable_browse() to find the correct path."
        )
    except Exception as e:
        return make_error("delete_failed", str(e), "Check tablet connection with remarkable_status().")


@mcp.tool(
    annotations=ToolAnnotations(
        title="Move or Rename",
        readOnlyHint=False,
        destructiveHint=False,
    )
)
def remarkable_move(source: str, destination: str, new_name: Optional[str] = None) -> str:
    """
    <usecase>Move or rename a document/folder on your reMarkable tablet.</usecase>
    <instructions>
    Move a document or folder to a new location, optionally renaming it.

    To rename without moving, set destination to the current parent folder.
    To move without renaming, omit new_name.
    </instructions>
    <parameters>
    - source: Current path of the item
    - destination: New parent folder path
    - new_name: Optional new name for the item
    </parameters>
    <examples>
    - remarkable_move("/Meeting Notes", "/01 Work/USMS-JPATS")
    - remarkable_move("/old-name.pdf", "/", new_name="new-name.pdf")
    - remarkable_move("/01 Work/Doc", "/02 Archive", new_name="2026-Doc")
    </examples>
    """
    try:
        result = move_item_by_path(source, destination, new_name)
        return make_response(
            result,
            f"Moved '{result['name']}' from {result['from']} to {result['to']}."
        )
    except FileNotFoundError as e:
        return make_error(
            "not_found", str(e),
            "Use remarkable_browse() to verify source and destination paths."
        )
    except Exception as e:
        return make_error("move_failed", str(e), "Check tablet connection with remarkable_status().")
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_write_tools.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add remarkable_mcp/tools.py tests/test_write_tools.py
git commit -m "feat: add 4 MCP write tools (upload, mkdir, delete, move)"
```

---

### Task 7: Update Server Instructions and README

**Files:**
- Modify: `remarkable_mcp/server.py` (instructions string)
- Modify: `README.md`

**Step 1: Update `_build_instructions()` in `server.py`**

Add write tools section to the instructions string:
```python
instructions += """
## Write Tools

- `remarkable_upload(file_path, destination)` - Upload a PDF/EPUB to a folder
- `remarkable_mkdir(path)` - Create folders (supports nested creation)
- `remarkable_delete(path)` - Delete a document or folder
- `remarkable_move(source, destination, new_name)` - Move or rename items

### Uploading Documents
1. Use `remarkable_mkdir("/Folder/Sub")` to create the destination folder first
2. Use `remarkable_upload("/local/path/file.pdf", "/Folder/Sub")` to upload

### Organizing Library
1. Use `remarkable_browse("/")` to see current structure
2. Use `remarkable_move(source, destination)` to reorganize
3. Use `remarkable_delete(path)` to remove unwanted items
"""
```

Remove the "All operations are read-only" line from the existing instructions.

**Step 2: Update README.md**

Add write tools to the Tools table. Add WiFi connection section. Add Claude Code configuration example.

**Step 3: Commit**

```bash
git add remarkable_mcp/server.py README.md
git commit -m "docs: update server instructions and README with write tools"
```

---

### Task 8: Integration Test and Claude Code Config

**Files:**
- Create: `tests/test_integration.py`
- Modify: Claude Code settings (manual)

**Step 1: Create opt-in integration test**

```python
# tests/test_integration.py
"""
Integration tests — run against a real reMarkable tablet.
Skip by default. Run with: REMARKABLE_HOST=<ip> pytest tests/test_integration.py -v
"""
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("REMARKABLE_HOST"),
    reason="Set REMARKABLE_HOST to run integration tests"
)


def test_status():
    from remarkable_mcp.usb_web import create_usb_web_client
    client = create_usb_web_client()
    assert client.check_connection() is True


def test_list_documents():
    from remarkable_mcp.usb_web import create_usb_web_client
    client = create_usb_web_client()
    docs = client.get_meta_items()
    assert isinstance(docs, list)


def test_create_and_delete_folder():
    from remarkable_mcp.api import create_folder_path, delete_item_by_path
    result = create_folder_path("/Test-MCP-Integration")
    assert "Test-MCP-Integration" in result["created_folders"]
    # Clean up
    delete_item_by_path("/Test-MCP-Integration")
```

**Step 2: Document Claude Code config**

Add to README:
```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "remarkable": {
      "command": "uvx",
      "args": ["remarkable-mcp-rw", "--wifi"],
      "env": {
        "REMARKABLE_HOST": "http://YOUR_TABLET_IP"
      }
    }
  }
}
```

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add opt-in integration tests for real tablet"
```

**Step 4: Push to GitHub**

```bash
git push -u origin main
```

---

## Summary

| Task | Description | Files | Est. |
|------|-------------|-------|------|
| 1 | Fork upstream, set up project | pyproject.toml | Setup |
| 2 | WiFi host support | usb_web.py, cli.py | Small |
| 3 | Path resolution helpers | api.py | Small |
| 4 | Write methods on USBWebClient | usb_web.py | Medium |
| 5 | Write API functions | api.py | Medium |
| 6 | MCP write tools | tools.py | Medium |
| 7 | Server instructions + README | server.py, README.md | Small |
| 8 | Integration tests + config | tests/ | Small |

**Dependencies:** Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7 → Task 8 (sequential — each builds on previous)
