"""Tests for WiFi host support and path resolution."""
import os
import pytest
from unittest.mock import MagicMock
from remarkable_mcp.usb_web import create_usb_web_client, DEFAULT_USB_HOST


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
