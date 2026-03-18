"""
Integration tests — run against a real reMarkable tablet.
Skipped by default. Run with: REMARKABLE_HOST=http://<ip> pytest tests/test_integration.py -v
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("REMARKABLE_HOST"),
    reason="Set REMARKABLE_HOST to run integration tests"
)


def test_status():
    """Can connect to the tablet."""
    from remarkable_mcp.usb_web import create_usb_web_client
    client = create_usb_web_client()
    assert client.check_connection() is True


def test_list_documents():
    """Can list documents."""
    from remarkable_mcp.usb_web import create_usb_web_client
    client = create_usb_web_client()
    docs = client.get_meta_items()
    assert isinstance(docs, list)


def test_create_and_delete_folder():
    """Can create and delete a test folder."""
    from remarkable_mcp.api import create_folder_path, delete_item_by_path
    result = create_folder_path("/MCP-Integration-Test")
    assert "MCP-Integration-Test" in result["created_folders"]
    # Clean up
    delete_item_by_path("/MCP-Integration-Test")
