"""Manifest of ontology entity types vs labels actually loaded into Neo4j.

This module is the single documented source for which ontology classes are
operational in the graph vs documentation-only. It does NOT make the ontology
an operational reasoning layer (see schema/ONTOLOGY_DECISION.md — Option B).
"""

from __future__ import annotations

from schema.ontology import ONTOLOGY_ENTITY_TYPES

# Labels created by graph/load_graph.py (and present in live Neo4j).
LOADED_ENTITY_TYPES: tuple[str, ...] = (
    "Customer",
    "Order",
    "Product",
    "SupportTicket",
)

# Ontology classes with no nodes in Neo4j for this demo dataset.
UNLOADED_ONTOLOGY_ENTITY_TYPES: tuple[str, ...] = tuple(
    label
    for label in ONTOLOGY_ENTITY_TYPES
    if label not in LOADED_ENTITY_TYPES
)


def unloaded_labels_sentence() -> str:
    names = ", ".join(UNLOADED_ONTOLOGY_ENTITY_TYPES)
    return f"{names} nodes are documented in the ontology but not loaded in this database."


def unloaded_labels_rule_line() -> str:
    """Schema-prompt bullet for NL→Cypher (documentation alignment, not runtime reasoning)."""
    if not UNLOADED_ONTOLOGY_ENTITY_TYPES:
        return ""
    if len(UNLOADED_ONTOLOGY_ENTITY_TYPES) == 1:
        names = UNLOADED_ONTOLOGY_ENTITY_TYPES[0]
    elif len(UNLOADED_ONTOLOGY_ENTITY_TYPES) == 2:
        names = f"{UNLOADED_ONTOLOGY_ENTITY_TYPES[0]} and {UNLOADED_ONTOLOGY_ENTITY_TYPES[1]}"
    else:
        head = ", ".join(UNLOADED_ONTOLOGY_ENTITY_TYPES[:-1])
        names = f"{head}, and {UNLOADED_ONTOLOGY_ENTITY_TYPES[-1]}"
    return f"- {names} nodes are not loaded in this database."


def validate_manifest() -> None:
    """Raise if ontology and loaded manifest drift apart."""
    loaded_set = set(LOADED_ENTITY_TYPES)
    ontology_set = set(ONTOLOGY_ENTITY_TYPES)
    if not loaded_set <= ontology_set:
        unknown = loaded_set - ontology_set
        raise ValueError(f"Loaded labels not in ontology: {sorted(unknown)}")
    if UNLOADED_ONTOLOGY_ENTITY_TYPES != tuple(
        label for label in ONTOLOGY_ENTITY_TYPES if label not in loaded_set
    ):
        raise ValueError("UNLOADED_ONTOLOGY_ENTITY_TYPES out of sync")
