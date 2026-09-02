from neo4j import GraphDatabase
import pandas as pd
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.csv_utils import read_orders

load_dotenv()

class GraphLoader:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
        )

    def close(self):
        self.driver.close()

    def clear_graph(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def create_constraints(self):
        constraints = [
            "CREATE CONSTRAINT customer_id IF NOT EXISTS FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE",
            "CREATE CONSTRAINT order_id IF NOT EXISTS FOR (o:Order) REQUIRE o.order_id IS UNIQUE",
            "CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.product_id IS UNIQUE",
            "CREATE CONSTRAINT ticket_id IF NOT EXISTS FOR (t:SupportTicket) REQUIRE t.ticket_id IS UNIQUE",
        ]
        with self.driver.session() as session:
            for c in constraints:
                session.run(c)

    def load_customers(self, df):
        with self.driver.session() as session:
            for _, row in df.iterrows():
                session.run(
                    """
                    MERGE (c:Customer {customer_id: $customer_id})
                    SET c.company_name = $company_name, c.country = $country
                    """,
                    customer_id=row["customerID"],
                    company_name=row.get("companyName", "Unknown"),
                    country=row.get("country", "Unknown"),
                )

    def load_orders_and_relationships(self, orders_df):
        with self.driver.session() as session:
            for _, row in orders_df.iterrows():
                session.run(
                    """
                    MATCH (c:Customer {customer_id: $customer_id})
                    MERGE (o:Order {order_id: $order_id})
                    SET o.order_date = $order_date
                    MERGE (c)-[:PLACED]->(o)
                    """,
                    customer_id=row["customerID"],
                    order_id=int(row["orderID"]),
                    order_date=str(row.get("orderDate", "")),
                )

    def load_products_and_order_lines(self, products_df, order_details_df):
        with self.driver.session() as session:
            for _, row in products_df.iterrows():
                session.run(
                    """
                    MERGE (p:Product {product_id: $product_id})
                    SET p.product_name = $product_name, p.unit_price = $unit_price
                    """,
                    product_id=int(row["productID"]),
                    product_name=row.get("productName", "Unknown"),
                    unit_price=float(row.get("unitPrice", 0)),
                )
            for _, row in order_details_df.iterrows():
                session.run(
                    """
                    MATCH (o:Order {order_id: $order_id})
                    MATCH (p:Product {product_id: $product_id})
                    MERGE (o)-[r:CONTAINS]->(p)
                    SET r.quantity = $quantity
                    """,
                    order_id=int(row["orderID"]),
                    product_id=int(row["productID"]),
                    quantity=int(row.get("quantity", 0)),
                )

    def load_support_tickets(self, tickets_df):
        with self.driver.session() as session:
            for _, row in tickets_df.iterrows():
                session.run(
                    """
                    MATCH (c:Customer {customer_id: $customer_id})
                    MATCH (o:Order {order_id: $order_id})
                    MERGE (t:SupportTicket {ticket_id: $ticket_id})
                    SET t.text = $text
                    MERGE (c)-[:FILED]->(t)
                    MERGE (t)-[:REFERENCES]->(o)
                    """,
                    customer_id=row["customer_id"],
                    order_id=int(row["order_id"]),
                    ticket_id=row["ticket_id"],
                    text=row["text"],
                )


def run_full_load():
    loader = GraphLoader()
    loader.clear_graph()
    loader.create_constraints()

    customers = pd.read_csv("data/customers.csv")
    orders = read_orders()
    products = pd.read_csv("data/products.csv")
    order_details = pd.read_csv("data/order-details.csv")
    tickets = pd.read_json("data/support_tickets.json")

    loader.load_customers(customers)
    loader.load_orders_and_relationships(orders)
    loader.load_products_and_order_lines(products, order_details)
    loader.load_support_tickets(tickets)

    loader.close()
    print("Graph load complete")


if __name__ == "__main__":
    run_full_load()
