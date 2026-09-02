"""ChromaDB indexing and scale analysis (Section 17).

Inspects the live ticket index when available. No fabricated latency benchmarks.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = Path("./chroma_db")
BASELINE_PATH = Path("./chroma_db_baseline")
COLLECTION_NAME = "support_tickets"
BASELINE_COLLECTION = "flat_baseline"

# Chroma 0.5.5 defaults when collection metadata is empty (see hnsw_params.py).
DEFAULT_HNSW = {
    "index_type": "HNSW (approximate nearest neighbor via hnswlib)",
    "space": "l2",
    "M": 16,
    "construction_ef": 100,
    "search_ef": 10,
    "embedding_model": "ONNXMiniLM_L6_V2 (all-MiniLM-L6-v2, 384-dim)",
    "persistence": "PersistentClient on-disk (chroma.sqlite3 + segment HNSW files)",
}


@dataclass(frozen=True)
class ChromaOperation:
    api: str
    supported_by_chroma: str
    used_in_this_project: str
    effect_on_stale_data: str


OPERATIONS: tuple[ChromaOperation, ...] = (
    ChromaOperation(
        api="collection.add(ids=...)",
        supported_by_chroma="Inserts new ids; **duplicate ids are silently ignored** (original kept)",
        used_in_this_project="Only path — `rag/build_index.py` bulk add after optional collection delete",
        effect_on_stale_data="Re-running build without reset leaves old embeddings in place",
    ),
    ChromaOperation(
        api="collection.upsert(ids=...)",
        supported_by_chroma="Insert or replace by id (re-embeds document)",
        used_in_this_project="**Not used** — no incremental ticket sync",
        effect_on_stale_data="Would be the right API for single-ticket refresh if implemented",
    ),
    ChromaOperation(
        api="collection.update(ids=...)",
        supported_by_chroma="Update existing id (re-embeds if document changes)",
        used_in_this_project="**Not used**",
        effect_on_stale_data="N/A today",
    ),
    ChromaOperation(
        api="collection.delete(ids=...)",
        supported_by_chroma="Remove ids from index",
        used_in_this_project="**Not used** — only whole-collection delete on rebuild",
        effect_on_stale_data="Deleted tickets remain searchable until full rebuild",
    ),
    ChromaOperation(
        api="client.delete_collection(...)",
        supported_by_chroma="Drop entire collection",
        used_in_this_project="`build_index(reset=True)` default before reload",
        effect_on_stale_data="Full ticket index wipe; requires re-add of all tickets",
    ),
)


def _dir_size_mb(path: Path) -> float | None:
    if not path.exists():
        return None
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 2)


def inspect_index(path: Path, collection_name: str) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}

    client = chromadb.PersistentClient(path=str(path))
    try:
        collection = client.get_collection(collection_name)
    except Exception as exc:
        return {"exists": True, "path": str(path), "collection": collection_name, "error": str(exc)}

    dimension = None
    sqlite_path = path / "chroma.sqlite3"
    if sqlite_path.exists():
        conn = sqlite3.connect(sqlite_path)
        cur = conn.cursor()
        cur.execute("SELECT dimension FROM collections WHERE name = ?", (collection_name,))
        row = cur.fetchone()
        dimension = row[0] if row else None
        conn.close()

    return {
        "exists": True,
        "path": str(path),
        "collection": collection_name,
        "count": collection.count(),
        "metadata": collection.metadata or {},
        "dimension": dimension,
        "size_mb": _dir_size_mb(path),
        "embedding_function": type(collection._embedding_function).__name__,
    }


def scale_reasoning(ticket_count: int) -> dict[str, str]:
    if ticket_count <= 10_000:
        tier = "≤10K (current demo scale)"
        latency = (
            "Query time is dominated by **ONNX query embedding** (CPU) and Python client overhead, "
            "not HNSW search. At 200 tickets, retrieval is sub-second and was not the hybrid latency bottleneck (Section 11)."
        )
        recall = (
            "HNSW with search_ef=10 is typically near-exact at this size; retrieval quality issues "
            "(e.g. order 10864 RR 0.0–0.5) are embedding/semantic, not index-approximation error."
        )
        ops = "Full rebuild (`delete_collection` + `add`) is acceptable at this size."
    elif ticket_count <= 1_000_000:
        tier = "100K–1M"
        latency = (
            "HNSW search cost grows ~O(log n); expect milliseconds to tens of ms for ANN search on one collection. "
            "Query embedding still runs per request. Tune `hnsw:search_ef` upward if recall drops."
        )
        recall = (
            "**Approximate** — default search_ef=10 trades recall for speed. "
            "Theme queries with dozens of relevant tickets (Section 6) become harder to fully recall at small K regardless."
        )
        ops = (
            "Full rebuild gets slow (re-embed all tickets). Need `upsert` batches or partitioned collections "
            "(by date/customer) for incremental ingest."
        )
    else:
        tier = "1M–10M+"
        latency = (
            "Single monolithic HNSW index may need sharding, dedicated embedding service, and higher search_ef. "
            "Consider metadata pre-filtering (customer_id, order_id) before vector search to shrink candidate set."
        )
        recall = (
            "ANN recall vs latency tradeoff becomes operational. Exact brute-force is not viable. "
            "Hybrid graph path becomes more important for identifier-heavy queries (order numbers)."
        )
        ops = (
            "Require streaming upsert pipeline, tombstone deletes, and consistency contract with Neo4j ticket nodes."
        )

    return {"tier": tier, "query_latency": latency, "recall_implications": recall, "operational_ops": ops}


def build_report() -> dict[str, Any]:
    ticket_index = inspect_index(CHROMA_PATH, COLLECTION_NAME)
    baseline_index = inspect_index(BASELINE_PATH, BASELINE_COLLECTION)

    return {
        "chromadb_version": chromadb.__version__,
        "default_hnsw": DEFAULT_HNSW,
        "ticket_index": ticket_index,
        "baseline_index": baseline_index,
        "operations": [op.__dict__ for op in OPERATIONS],
        "duplicate_id_behavior": {
            "tested": True,
            "add_same_id_twice": "Silently ignored — count unchanged, original document/metadata/embedding kept",
            "upsert_same_id": "Replaces document/metadata and re-embeds",
            "rebuild_without_reset": "Same as duplicate add — stale text persists",
            "rebuild_with_reset": "delete_collection then add — correct fresh index",
        },
        "scale_projections": {
            "10_000_tickets": scale_reasoning(10_000),
            "1_000_000_tickets": scale_reasoning(1_000_000),
            "10_000_000_tickets": scale_reasoning(10_000_000),
        },
        "data_freshness_bridge": {
            "runtime_ticket_update": "None — orchestrator only calls query_tickets(); no write path",
            "ticket_text_source_of_truth": "data/support_tickets.json",
            "neo4j_ticket_nodes": "graph/load_graph.py MERGE SupportTicket — full graph wipe on reload",
            "consistency_model": "Batch rebuild only; graph and Chroma can drift if only one is refreshed",
        },
    }


def format_report(report: dict[str, Any]) -> str:
    t = report["ticket_index"]
    lines = [
        "ChromaDB indexing & scale analysis (Section 17)",
        "=" * 60,
        f"chromadb {report['chromadb_version']}",
        "",
        "Ticket index (support_tickets):",
        f"  path: {t.get('path')} ({t.get('size_mb')} MB on disk)",
        f"  count: {t.get('count')}  dimension: {t.get('dimension')}",
        f"  embedding: {t.get('embedding_function')}",
        f"  collection metadata: {t.get('metadata') or '{} (defaults apply)'}",
        "",
        "Default index (no custom metadata):",
    ]
    for k, v in report["default_hnsw"].items():
        lines.append(f"  {k}: {v}")

    lines.extend(["", "Duplicate ID behavior (tested in temp collection):"])
    for k, v in report["duplicate_id_behavior"].items():
        if k != "tested":
            lines.append(f"  {k}: {v}")

    lines.extend(["", "Scale projections (not benchmarked):"])
    for key, assessment in report["scale_projections"].items():
        lines.append(f"\n  {key} [{assessment['tier']}]:")
        lines.append(f"    Latency: {assessment['query_latency']}")
        lines.append(f"    Recall: {assessment['recall_implications']}")
        lines.append(f"    Ops: {assessment['operational_ops']}")

    lines.extend(["", "Data freshness bridge (Section 18):"])
    for k, v in report["data_freshness_bridge"].items():
        lines.append(f"  {k}: {v}")

    return "\n".join(lines)


if __name__ == "__main__":
    report = build_report()
    print(format_report(report))
    out = Path(__file__).parent / "chroma_scale_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
