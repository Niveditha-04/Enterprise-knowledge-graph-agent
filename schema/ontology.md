# Order-to-Cash Domain Ontology

## Entity Types
- Customer (properties: customer_id, company_name, country)
- Order (properties: order_id, order_date, shipped_date)
- Product (properties: product_id, product_name, unit_price)
- Employee (properties: employee_id, name, title)
- Invoice (properties: invoice_id, amount, status, due_date)
- SupportTicket (properties: ticket_id, text, created_date)

## Relationships
- (Customer)-[:PLACED]->(Order)
- (Order)-[:CONTAINS {quantity, unit_price}]->(Product)
- (Employee)-[:HANDLED]->(Order)
- (Order)-[:BILLED_AS]->(Invoice)
- (Customer)-[:FILED]->(SupportTicket)
- (SupportTicket)-[:REFERENCES]->(Order)
