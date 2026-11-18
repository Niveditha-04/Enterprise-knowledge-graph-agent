from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal

EX = Namespace("http://example.org/o2c#")

ONTOLOGY_ENTITY_TYPES: tuple[str, ...] = (
    "Customer",
    "Order",
    "Product",
    "Employee",
    "Invoice",
    "SupportTicket",
)

def build_ontology():
    g = Graph()
    g.bind("o2c", EX)

    for cls in ONTOLOGY_ENTITY_TYPES:
        g.add((EX[cls], RDF.type, OWL.Class))

    relationships = [
        ("PLACED", "Customer", "Order"),
        ("CONTAINS", "Order", "Product"),
        ("HANDLED", "Employee", "Order"),
        ("BILLED_AS", "Order", "Invoice"),
        ("FILED", "Customer", "SupportTicket"),
        ("REFERENCES", "SupportTicket", "Order"),
    ]
    for rel, domain, range_ in relationships:
        g.add((EX[rel], RDF.type, OWL.ObjectProperty))
        g.add((EX[rel], RDFS.domain, EX[domain]))
        g.add((EX[rel], RDFS.range, EX[range_]))

    return g

if __name__ == "__main__":
    g = build_ontology()
    g.serialize(destination="schema/ontology.ttl", format="turtle")
    print(f"Ontology written with {len(g)} triples")
