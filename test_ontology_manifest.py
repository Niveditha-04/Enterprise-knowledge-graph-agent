"""Ontology vs loaded-graph manifest (Section 15 — Option B documentation checks)."""

from schema.graph_manifest import (
    LOADED_ENTITY_TYPES,
    UNLOADED_ONTOLOGY_ENTITY_TYPES,
    unloaded_labels_rule_line,
    validate_manifest,
)
from schema.ontology import ONTOLOGY_ENTITY_TYPES


def test_ontology_entity_types_complete():
    assert set(ONTOLOGY_ENTITY_TYPES) == {
        "Customer",
        "Order",
        "Product",
        "Employee",
        "Invoice",
        "SupportTicket",
    }


def test_loaded_vs_unloaded_partition_ontology():
    assert set(LOADED_ENTITY_TYPES) | set(UNLOADED_ONTOLOGY_ENTITY_TYPES) == set(
        ONTOLOGY_ENTITY_TYPES
    )
    assert set(LOADED_ENTITY_TYPES) & set(UNLOADED_ONTOLOGY_ENTITY_TYPES) == set()


def test_unloaded_labels_are_employee_and_invoice():
    assert UNLOADED_ONTOLOGY_ENTITY_TYPES == ("Employee", "Invoice")


def test_validate_manifest_passes():
    validate_manifest()


def test_schema_rule_line_mentions_unloaded_labels():
    line = unloaded_labels_rule_line()
    assert "Employee" in line
    assert "Invoice" in line
    assert "not loaded" in line
