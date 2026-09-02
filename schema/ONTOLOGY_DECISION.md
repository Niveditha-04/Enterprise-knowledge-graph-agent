# Section 15 — Ontology decision: Option B (formal artifact only)

## Decision

**Keep the ontology as a formal domain model and documentation artifact. Do not integrate it as an operational reasoning layer at runtime.**

The running application does **not** consult `schema/ontology.ttl`, RDF triples, or OWL classes when routing, generating Cypher, retrieving tickets, or synthesizing answers. Reasoning uses hand-written prompts (`agent/nl_to_cypher.py` `SCHEMA_CONTEXT`) and application-layer guards (`agent/synthesis.py`).

## What the audit found

| Layer | Role today |
|-------|------------|
| `schema/ontology.md`, `schema/ontology.ttl` | Documents 6 entity types and 6 relationships for the O2C domain |
| `graph/load_graph.py` | Loads **4** node types: Customer, Order, Product, SupportTicket |
| `agent/nl_to_cypher.py` | Hand-written schema prompt; includes a bullet that unloaded labels are not in Neo4j |
| `agent/synthesis.py` | Application-layer guard for misleading zero-count / proxy answers on unloaded concepts |
| Live Neo4j | 91 Customer, 830 Order, 77 Product, 200 SupportTicket — **no Employee or Invoice nodes** |

The **Employee/Invoice bug** (Section 12) is a direct consequence of this split:

1. The ontology documents Employee and Invoice as first-class entities.
2. The loader never creates those nodes.
3. NL→Cypher **already warned** in `SCHEMA_CONTEXT` that Employee and Invoice are not loaded.
4. The model still generated `MATCH (e:Employee) RETURN count(e)` for `unsupported_employee_count`.
5. Neo4j returned `count = 0` (valid Cypher, empty label).
6. Synthesis treated zero as a factual answer until the **synthesis guard** was added.

The bug is **not** “the ontology was wrong.” It is **documentation vs. loaded graph drift**, combined with LLM non-compliance with schema text and synthesis treating empty-query results as ground truth.

## Option A considered — and rejected

**Option A** would mean integrating the ontology meaningfully at runtime (e.g. validating the loader against ontology classes, refusing queries against documented-but-unloaded labels, deriving behavior from OWL).

### Low-effort integrations evaluated

| Idea | Effort | Would it have prevented the Employee/Invoice bug **without** the synthesis guard? |
|------|--------|-------------------------------------------------------------------------------------|
| Startup check: ontology classes vs Neo4j labels | Low | **No** — catches deploy-time drift; does not stop runtime NL→Cypher from targeting `:Employee` |
| Derive unloaded-label list from ontology − loaded manifest | Low | **Partially** — DRY for the label list only; still need guard **logic** |
| Block Cypher containing `:Employee` / `:Invoice` before execution | Low–medium | **Partial** — would block the Employee case; **not** the Invoice **proxy** case (`count(o)` relabeled as invoices) |
| Full ontology-driven query validation | High | Uncertain — proxy and keyword mismatches need question-level checks anyway |

**Critical evidence:** `SCHEMA_CONTEXT` already stated that Employee and Invoice are not loaded. The model ignored it. A startup validation step would not have changed runtime behavior. A Cypher blocklist derived from the ontology would have caught `MATCH (e:Employee)` but **not** `MATCH (o:Order) RETURN count(o) AS invoice_count` when the user asked about invoices.

The **invoice proxy** case required **question-keyword vs Cypher-label mismatch** detection in synthesis — logic that cannot be derived automatically from the ontology alone.

Therefore Option A does **not** justify itself on the audit’s central failure. The fix that restored synthesis to **22/23** was an **application-layer synthesis guard**, not ontology integration.

## What we did instead (still Option B)

`schema/graph_manifest.py` records which ontology classes are loaded vs documentation-only. It is used to:

- Keep `SCHEMA_CONTEXT` and the synthesis guard’s label list **aligned** with the ontology (avoid three divergent hardcoded lists).
- Support **tests** that fail if ontology, loader, and manifest drift apart.

This is **documentation hygiene**, not operational ontology reasoning. The guard’s **behavior** (zero-count refusal, invoice proxy detection, question keywords) remains explicit application code.

## When Option A would be worth revisiting

Revisit meaningful ontology integration only if the project gains requirements such as:

- Multiple loaders or environments where manifest drift is frequent and must be enforced at deploy time.
- SHACL/OWL validation of incoming data before graph load.
- Federated graphs where the ontology is the contract between teams.

For this demo’s scope, those costs exceed the benefit.

## Summary

- **Ontology:** formal domain model + RDF export + human-readable docs.
- **Runtime:** Neo4j labels + hand-written schema prompt + hybrid orchestration.
- **Employee/Invoice safety:** synthesis guard (application patch), aligned with but not **derived from** ontology inference.
