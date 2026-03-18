#!/usr/bin/env python3
"""
Organize reMarkable tablet: create Archive folder, move all existing root items into it.
Uses reMarkable Cloud API v3 sync protocol.
"""

import base64
import hashlib
import http.client
import json
import ssl
import struct
import time
import urllib.request
import uuid
from pathlib import Path

TOKEN_FILE = Path.home() / ".remarkable" / "token"
BASE_HOST = "internal.cloud.remarkable.com"
BASE_PATH = "/sync/v3"


def crc32c(data: bytes) -> str:
    """Compute CRC32C (Castagnoli) and return base64-encoded value."""
    # Use crcmod if available, otherwise fallback
    try:
        import crcmod
        crc_fn = crcmod.predefined.mkCrcFun("crc-32c")
        crc_val = crc_fn(data)
    except ImportError:
        # Pure Python CRC32C
        crc_val = _crc32c_pure(data)
    return base64.b64encode(struct.pack(">I", crc_val)).decode()


def _crc32c_pure(data: bytes) -> int:
    """Pure Python CRC32C implementation."""
    CRC32C_TABLE = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x82F63B78
            else:
                crc >>= 1
        CRC32C_TABLE.append(crc)

    crc = 0xFFFFFFFF
    for byte in data:
        crc = CRC32C_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_user_token() -> str:
    """Exchange device token for user token."""
    device_token = TOKEN_FILE.read_text().strip()
    req = urllib.request.Request(
        "https://webapp-prod.cloud.remarkable.engineering/token/json/2/user/new",
        method="POST",
        headers={"Authorization": f"Bearer {device_token}"},
    )
    return urllib.request.urlopen(req, timeout=15).read().decode().strip()


def api_get(token: str, path: str, timeout: int = 15) -> bytes:
    """GET from Cloud API."""
    req = urllib.request.Request(
        f"https://{BASE_HOST}{BASE_PATH}/{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return urllib.request.urlopen(req, timeout=timeout).read()


def api_put_blob(token: str, blob_hash: str, data: bytes, rm_filename: str = "") -> int:
    """PUT a blob to Cloud API v3 with required headers.

    rm_filename is only sent for actual files (with extensions like .metadata, .content, .pdf).
    Index files (no extension) must NOT have the Rm-Filename header.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(len(data)),
        "X-Goog-Hash": f"crc32c={crc32c(data)}",
    }
    # Rm-Filename is always required. For index files, use the hash itself.
    headers["Rm-Filename"] = rm_filename if rm_filename else blob_hash

    context = ssl.create_default_context()
    conn = http.client.HTTPSConnection(BASE_HOST, context=context, timeout=30)
    conn.request("PUT", f"{BASE_PATH}/files/{blob_hash}", body=data, headers=headers)
    resp = conn.getresponse()
    status = resp.status
    body = resp.read().decode()
    conn.close()
    if status >= 400:
        raise RuntimeError(f"PUT /files/{blob_hash[:16]}... failed: {status} {body}")
    return status


def api_put_root(token: str, new_hash: str, generation: int) -> int:
    """Update root pointer atomically."""
    payload = json.dumps({
        "hash": new_hash,
        "generation": generation,
        "schemaVersion": 4,
    }).encode()
    context = ssl.create_default_context()
    conn = http.client.HTTPSConnection(BASE_HOST, context=context, timeout=15)
    conn.request(
        "PUT",
        f"{BASE_PATH}/root",
        body=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        },
    )
    resp = conn.getresponse()
    status = resp.status
    body = resp.read().decode()
    conn.close()
    if status >= 400:
        raise RuntimeError(f"PUT /root failed: {status} {body}")
    return status


def parse_index(data: str) -> list[dict]:
    """Parse a sync v3 index file into entries."""
    lines = data.strip().split("\n")
    entries = []
    for line in lines[2:]:  # skip version + root header
        parts = line.split(":")
        if len(parts) >= 4:
            entries.append({
                "hash": parts[0],
                "subfiles": parts[1],
                "id": parts[2],
                "type": int(parts[3]),
                "size": int(parts[4]) if len(parts) >= 5 else 0,
                "raw": line,
            })
    return entries


def get_metadata(token: str, entry_hash: str) -> tuple[dict, str, str]:
    """Fetch metadata for an entry. Returns (metadata_dict, meta_blob_hash, entry_index_text)."""
    idx_data = api_get(token, f"files/{entry_hash}").decode()
    for line in idx_data.strip().split("\n"):
        if ".metadata:" in line:
            meta_hash = line.split(":")[0]
            meta_json = api_get(token, f"files/{meta_hash}").decode()
            return json.loads(meta_json), meta_hash, idx_data
    return {}, "", idx_data


def main():
    print("Getting user token...")
    token = get_user_token()

    print("Fetching root index...")
    root_info = json.loads(api_get(token, "root"))
    root_hash = root_info["hash"]
    generation = root_info["generation"]
    print(f"  Root hash: {root_hash[:16]}...  Generation: {generation}")

    root_idx_bytes = api_get(token, f"files/{root_hash}")
    root_idx = root_idx_bytes.decode()
    entries = parse_index(root_idx)
    print(f"  Total cloud entries: {len(entries)}")

    # Scan for root-level items
    print("\nScanning for root-level items...")
    root_items = []
    for i, entry in enumerate(entries):
        try:
            meta, meta_hash, idx_text = get_metadata(token, entry["hash"])
            if meta.get("parent") == "" and not meta.get("deleted", False):
                root_items.append({
                    "name": meta.get("visibleName", "?"),
                    "id": entry["id"],
                    "entry": entry,
                    "meta": meta,
                    "meta_hash": meta_hash,
                    "idx_text": idx_text,
                })
                tp = "F" if meta.get("type") == "CollectionType" else "d"
                print(f"  [{tp}] {meta.get('visibleName', '?')}")
        except Exception:
            continue
        if (i + 1) % 30 == 0:
            print(f"  ... scanned {i + 1}/{len(entries)}")

    print(f"\nFound {len(root_items)} root-level items to archive")

    # --- Step 1: Create Archive folder ---
    archive_id = str(uuid.uuid4())
    now_ms = str(int(time.time() * 1000))
    print(f"\nCreating Archive folder (ID: {archive_id})...")

    archive_meta = json.dumps({
        "deleted": False,
        "lastModified": now_ms,
        "metadatamodified": True,
        "modified": True,
        "parent": "",
        "pinned": False,
        "synced": False,
        "type": "CollectionType",
        "version": 1,
        "visibleName": "00 Archive",
    }, indent=4).encode()

    archive_content = json.dumps({
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
        "transform": {},
    }, indent=4).encode()

    meta_hash = sha256(archive_meta)
    content_hash = sha256(archive_content)

    # Build folder index
    folder_idx = (
        f"4\n"
        f"0:{archive_id}:2:{len(archive_meta) + len(archive_content)}\n"
        f"{content_hash}:0:{archive_id}.content:0:{len(archive_content)}\n"
        f"{meta_hash}:0:{archive_id}.metadata:0:{len(archive_meta)}\n"
    ).encode()
    folder_idx_hash = sha256(folder_idx)

    # Upload all 3 blobs for Archive folder
    print("  Uploading Archive metadata...")
    api_put_blob(token, meta_hash, archive_meta, f"{archive_id}.metadata")
    print("  Uploading Archive content...")
    api_put_blob(token, content_hash, archive_content, f"{archive_id}.content")
    print("  Uploading Archive index...")
    api_put_blob(token, folder_idx_hash, folder_idx, archive_id)
    print("  Archive folder created!")

    # --- Step 2: Move each root item's parent to Archive ---
    print(f"\nMoving {len(root_items)} items into Archive...")
    new_entry_lines = {}  # old_raw_line -> new_raw_line

    for item in root_items:
        name = item["name"]
        print(f"  Moving: {name}")

        # Update metadata: set parent to archive_id
        new_meta = item["meta"].copy()
        new_meta["parent"] = archive_id
        new_meta["metadatamodified"] = True
        new_meta["modified"] = True
        new_meta["lastModified"] = now_ms
        new_meta_bytes = json.dumps(new_meta, indent=4).encode()
        new_meta_hash = sha256(new_meta_bytes)

        # Upload new metadata blob
        api_put_blob(token, new_meta_hash, new_meta_bytes, f"{item['id']}.metadata")

        # Rebuild entry index with new metadata hash
        old_idx = item["idx_text"]
        new_idx_lines = []
        for line in old_idx.strip().split("\n"):
            if ".metadata:" in line:
                parts = line.split(":")
                parts[0] = new_meta_hash
                parts[4] = str(len(new_meta_bytes))
                new_idx_lines.append(":".join(parts))
            else:
                new_idx_lines.append(line)
        new_idx = "\n".join(new_idx_lines) + "\n"
        new_idx_bytes = new_idx.encode()
        new_idx_hash = sha256(new_idx_bytes)

        # Upload new entry index
        api_put_blob(token, new_idx_hash, new_idx_bytes, item["id"])

        # Track the root index line replacement
        old_line = item["entry"]["raw"]
        parts = old_line.split(":")
        parts[0] = new_idx_hash
        parts[4] = str(len(new_idx_bytes))
        new_entry_lines[old_line] = ":".join(parts)

    # --- Step 3: Rebuild root index ---
    print("\nRebuilding root index...")
    lines = root_idx.strip().split("\n")

    # Replace modified entry lines
    new_lines = []
    for line in lines:
        if line in new_entry_lines:
            new_lines.append(new_entry_lines[line])
        else:
            new_lines.append(line)

    # Add Archive folder entry
    archive_entry = f"{folder_idx_hash}:0:{archive_id}:2:{len(folder_idx)}"
    new_lines.append(archive_entry)

    # Update root header (line index 1): count and total size
    header_parts = new_lines[1].split(":")
    entry_count = len(new_lines) - 2  # minus version + header
    total_size = 0
    for line in new_lines[2:]:
        p = line.split(":")
        if len(p) >= 5:
            total_size += int(p[4])
    header_parts[2] = str(entry_count)
    header_parts[3] = str(total_size)
    new_lines[1] = ":".join(header_parts)

    new_root_idx = "\n".join(new_lines) + "\n"
    new_root_bytes = new_root_idx.encode()
    new_root_hash = sha256(new_root_bytes)

    # Upload new root index
    print(f"  Uploading new root index ({new_root_hash[:16]}...)...")
    api_put_blob(token, new_root_hash, new_root_bytes, "root")

    # --- Step 4: Atomic commit ---
    print("Committing changes (updating root pointer)...")
    new_generation = generation + 1
    api_put_root(token, new_root_hash, new_generation)

    print(f"\nDone! Created '00 Archive' and moved {len(root_items)} items into it.")
    print("Pull down to refresh on your reMarkable tablet.")


if __name__ == "__main__":
    main()
