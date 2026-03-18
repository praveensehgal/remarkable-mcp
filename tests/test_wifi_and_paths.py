"""Tests for WiFi host support and path resolution."""

import os
from unittest.mock import MagicMock, patch

import pytest

from remarkable_mcp.usb_web import DEFAULT_USB_HOST, USBWebClient, create_usb_web_client

# --- WiFi Host Tests ---


class TestWiFiHost:
    def setup_method(self):
        """Clean env before each test."""
        os.environ.pop("REMARKABLE_HOST", None)
        os.environ.pop("REMARKABLE_USB_HOST", None)

    def teardown_method(self):
        """Clean env after each test."""
        os.environ.pop("REMARKABLE_HOST", None)
        os.environ.pop("REMARKABLE_USB_HOST", None)

    def test_default_host(self):
        client = create_usb_web_client()
        assert client.host == DEFAULT_USB_HOST

    def test_remarkable_host_env_var(self):
        os.environ["REMARKABLE_HOST"] = "http://192.168.1.50"
        client = create_usb_web_client()
        assert client.host == "http://192.168.1.50"

    def test_remarkable_host_takes_priority(self):
        os.environ["REMARKABLE_HOST"] = "http://192.168.1.50"
        os.environ["REMARKABLE_USB_HOST"] = "http://10.11.99.1"
        client = create_usb_web_client()
        assert client.host == "http://192.168.1.50"

    def test_usb_host_fallback(self):
        os.environ["REMARKABLE_USB_HOST"] = "http://10.11.99.2"
        client = create_usb_web_client()
        assert client.host == "http://10.11.99.2"


# --- Path Resolution Tests ---


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


def _make_collection():
    """Create: /Work/Projects/Alpha + /Work/Projects/Meeting Notes"""
    return [
        _make_doc("f1", "Work", "", "CollectionType"),
        _make_doc("f2", "Projects", "f1", "CollectionType"),
        _make_doc("f3", "Alpha", "f2", "CollectionType"),
        _make_doc("d1", "Meeting Notes", "f2", "DocumentType"),
    ]


class TestPathResolution:
    def test_resolve_root_folder(self):
        from remarkable_mcp.api import resolve_path_to_item

        item = resolve_path_to_item("/Work", _make_collection())
        assert item.ID == "f1"

    def test_resolve_nested_path(self):
        from remarkable_mcp.api import resolve_path_to_item

        item = resolve_path_to_item("/Work/Projects", _make_collection())
        assert item.ID == "f2"

    def test_resolve_deep_path(self):
        from remarkable_mcp.api import resolve_path_to_item

        item = resolve_path_to_item("/Work/Projects/Alpha", _make_collection())
        assert item.ID == "f3"

    def test_resolve_document(self):
        from remarkable_mcp.api import resolve_path_to_item

        item = resolve_path_to_item("/Work/Projects/Meeting Notes", _make_collection())
        assert item.ID == "d1"

    def test_resolve_nonexistent_raises(self):
        from remarkable_mcp.api import resolve_path_to_item

        with pytest.raises(FileNotFoundError):
            resolve_path_to_item("/Nonexistent", _make_collection())

    def test_resolve_parent_id_root(self):
        from remarkable_mcp.api import resolve_path_to_parent_id

        assert resolve_path_to_parent_id("/", _make_collection()) == ""

    def test_resolve_parent_id_folder(self):
        from remarkable_mcp.api import resolve_path_to_parent_id

        assert resolve_path_to_parent_id("/Work/Projects", _make_collection()) == "f2"

    def test_resolve_parent_id_not_folder_raises(self):
        from remarkable_mcp.api import resolve_path_to_parent_id

        with pytest.raises(ValueError):
            resolve_path_to_parent_id("/Work/Projects/Meeting Notes", _make_collection())


# --- USB Web Write Method Tests ---


class TestUSBWebUpload:
    @patch("remarkable_mcp.usb_web.requests.post")
    def test_upload_pdf(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"ID": "new-guid", "VissibleName": "test.pdf", "Type": "DocumentType"}
        ]
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = USBWebClient(host="http://fake")
        result = client.upload(b"%PDF-fake", "test.pdf", parent_id="")
        assert result.name == "test.pdf"
        assert mock_post.called

    @patch("remarkable_mcp.usb_web.requests.post")
    def test_upload_with_parent(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = USBWebClient(host="http://fake")
        result = client.upload(b"%PDF-fake", "test.pdf", parent_id="folder-123")
        assert result.parent == "folder-123"

    @patch("remarkable_mcp.usb_web.requests.post")
    def test_upload_clears_cache(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = USBWebClient(host="http://fake")
        client._documents = [MagicMock()]  # fake cached docs
        client.upload(b"%PDF-fake", "test.pdf")
        assert client._documents == []


class TestUSBWebCreateFolder:
    @patch("remarkable_mcp.usb_web.requests.post")
    def test_create_folder(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = USBWebClient(host="http://fake")
        result = client.create_folder("New Folder", parent_id="")
        assert result.name == "New Folder"
        assert result.is_folder

    @patch("remarkable_mcp.usb_web.requests.post")
    def test_create_folder_with_parent(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = USBWebClient(host="http://fake")
        result = client.create_folder("Sub", parent_id="parent-id")
        assert result.parent == "parent-id"


class TestUSBWebDelete:
    @patch("remarkable_mcp.usb_web.requests.delete")
    def test_delete_item(self, mock_delete):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_delete.return_value = mock_response

        client = USBWebClient(host="http://fake")
        assert client.delete_item("some-guid") is True

    @patch("remarkable_mcp.usb_web.requests.delete")
    def test_delete_clears_cache(self, mock_delete):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_delete.return_value = mock_response

        client = USBWebClient(host="http://fake")
        client._documents = [MagicMock()]
        client.delete_item("some-guid")
        assert client._documents == []


class TestUSBWebMove:
    @patch("remarkable_mcp.usb_web.requests.put")
    def test_move_item(self, mock_put):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_put.return_value = mock_response

        client = USBWebClient(host="http://fake")
        assert client.move_item("doc-guid", new_parent_id="folder-guid") is True

    @patch("remarkable_mcp.usb_web.requests.put")
    def test_rename_item(self, mock_put):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_put.return_value = mock_response

        client = USBWebClient(host="http://fake")
        assert client.move_item("doc-guid", new_name="New Name") is True
        call_kwargs = mock_put.call_args
        assert "New Name" in str(call_kwargs)

    @patch("remarkable_mcp.usb_web.requests.put")
    def test_move_clears_cache(self, mock_put):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_put.return_value = mock_response

        client = USBWebClient(host="http://fake")
        client._documents = [MagicMock()]
        client.move_item("doc-guid", new_parent_id="folder-guid")
        assert client._documents == []
