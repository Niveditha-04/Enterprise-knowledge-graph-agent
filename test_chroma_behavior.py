"""ChromaDB duplicate/update/delete behavior (Section 17 audit tests).

Uses isolated temp directories — never mutates ./chroma_db.
"""

import shutil
import tempfile

import chromadb


def _temp_client():
    path = tempfile.mkdtemp(prefix="chroma_behavior_")
    client = chromadb.PersistentClient(path=path)
    return client, path


def test_duplicate_add_keeps_original_document():
    client, path = _temp_client()
    try:
        col = client.get_or_create_collection("dup_test")
        col.add(ids=["TCK-DUP"], documents=["original text"], metadatas=[{"v": 1}])
        col.add(ids=["TCK-DUP"], documents=["replacement text"], metadatas=[{"v": 2}])
        assert col.count() == 1
        got = col.get(ids=["TCK-DUP"], include=["documents", "metadatas"])
        assert got["documents"] == ["original text"]
        assert got["metadatas"] == [{"v": 1}]
    finally:
        shutil.rmtree(path)


def test_upsert_replaces_document_and_metadata():
    client, path = _temp_client()
    try:
        col = client.get_or_create_collection("upsert_test")
        col.add(ids=["TCK-1"], documents=["version A"], metadatas=[{"v": 1}])
        col.upsert(ids=["TCK-1"], documents=["version B"], metadatas=[{"v": 2}])
        got = col.get(ids=["TCK-1"], include=["documents", "metadatas"])
        assert got["documents"] == ["version B"]
        assert got["metadatas"] == [{"v": 2}]
    finally:
        shutil.rmtree(path)


def test_update_and_delete_single_ticket():
    client, path = _temp_client()
    try:
        col = client.get_or_create_collection("mut_test")
        col.add(ids=["TCK-1"], documents=["before"], metadatas=[{"v": 1}])
        col.update(ids=["TCK-1"], documents=["after"], metadatas=[{"v": 2}])
        got = col.get(ids=["TCK-1"], include=["documents"])
        assert got["documents"] == ["after"]
        col.delete(ids=["TCK-1"])
        assert col.count() == 0
    finally:
        shutil.rmtree(path)


def test_rebuild_without_reset_leaves_stale_document():
    """Mirrors build_index(reset=False) — duplicate ids do not refresh embeddings."""
    client, path = _temp_client()
    try:
        col = client.get_or_create_collection("rebuild_test")
        col.add(ids=["TCK-1"], documents=["version A"], metadatas=[{"v": 1}])
        col = client.get_or_create_collection("rebuild_test")
        col.add(ids=["TCK-1"], documents=["version B"], metadatas=[{"v": 2}])
        got = col.get(ids=["TCK-1"], include=["documents", "metadatas"])
        assert got["documents"] == ["version A"]
        assert got["metadatas"] == [{"v": 1}]
    finally:
        shutil.rmtree(path)
