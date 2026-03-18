"""Tests for write API functions and MCP tool registration."""

import os
from unittest.mock import MagicMock, patch

import pytest


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


class TestToolRegistration:
    """Verify all write tools are registered on the MCP server."""

    def test_upload_tool_registered(self):
        from remarkable_mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "remarkable_upload" in tool_names

    def test_mkdir_tool_registered(self):
        from remarkable_mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "remarkable_mkdir" in tool_names

    def test_delete_tool_registered(self):
        from remarkable_mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "remarkable_delete" in tool_names

    def test_move_tool_registered(self):
        from remarkable_mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "remarkable_move" in tool_names


class TestWriteAPIFunctions:
    """Test the write API functions in api.py."""

    @patch("remarkable_mcp.api.get_rmapi")
    def test_delete_item_by_path(self, mock_rmapi):
        from remarkable_mcp.api import delete_item_by_path

        work = _make_doc("f1", "Work", "", "CollectionType")
        doc = _make_doc("d1", "Old Doc", "f1", "DocumentType")
        client = MagicMock()
        client.get_meta_items.return_value = [work, doc]
        client.delete_item.return_value = True
        mock_rmapi.return_value = client

        result = delete_item_by_path("/Work/Old Doc")
        assert result is True
        client.delete_item.assert_called_once_with("d1")

    @patch("remarkable_mcp.api.get_rmapi")
    def test_move_item_by_path(self, mock_rmapi):
        from remarkable_mcp.api import move_item_by_path

        work = _make_doc("f1", "Work", "", "CollectionType")
        archive = _make_doc("f2", "Archive", "", "CollectionType")
        doc = _make_doc("d1", "Report", "f1", "DocumentType")
        client = MagicMock()
        client.get_meta_items.return_value = [work, archive, doc]
        client.move_item.return_value = True
        mock_rmapi.return_value = client

        result = move_item_by_path("/Work/Report", "/Archive")
        assert result["from"] == "/Work/Report"
        assert result["to"] == "/Archive"
        client.move_item.assert_called_once_with("d1", new_parent_id="f2", new_name=None)

    @patch("remarkable_mcp.api.get_rmapi")
    def test_create_folder_path_new(self, mock_rmapi):
        from remarkable_mcp.api import create_folder_path

        client = MagicMock()
        # First call: empty collection, second call: has the new folder
        new_folder = _make_doc("f1", "Work", "", "CollectionType")
        client.get_meta_items.side_effect = [[], [new_folder]]
        client.create_folder.return_value = new_folder
        mock_rmapi.return_value = client

        result = create_folder_path("/Work")
        assert "Work" in result["created_folders"]

    @patch("remarkable_mcp.api.get_rmapi")
    def test_create_folder_path_exists(self, mock_rmapi):
        from remarkable_mcp.api import create_folder_path

        client = MagicMock()
        existing = _make_doc("f1", "Work", "", "CollectionType")
        client.get_meta_items.return_value = [existing]
        mock_rmapi.return_value = client

        result = create_folder_path("/Work")
        assert result["created_folders"] == []
        assert result["already_existed"] == 1

    @patch("remarkable_mcp.api.get_rmapi")
    def test_upload_document_not_found(self, mock_rmapi):
        from remarkable_mcp.api import upload_document

        client = MagicMock()
        client.get_meta_items.return_value = []
        mock_rmapi.return_value = client

        with pytest.raises(FileNotFoundError, match="Local file not found"):
            upload_document("/nonexistent/file.pdf")

    @patch("remarkable_mcp.api.get_rmapi")
    def test_upload_document_wrong_type(self, mock_rmapi):
        from remarkable_mcp.api import upload_document

        client = MagicMock()
        client.get_meta_items.return_value = []
        mock_rmapi.return_value = client

        # Create a temp txt file
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            temp_path = f.name
        try:
            with pytest.raises(ValueError, match="Unsupported file type"):
                upload_document(temp_path)
        finally:
            os.unlink(temp_path)
