import pandas as pd
import random
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.csv_utils import read_orders

random.seed(42)

TICKET_TEMPLATES = [
    "Customer {customer} reported a delay on order {order}. Investigating carrier issue.",
    "Customer {customer} requested invoice correction for order {order} due to pricing discrepancy.",
    "Customer {customer} escalated order {order} — product arrived damaged, replacement requested.",
    "Customer {customer} inquired about order {order} status, no response after 3 business days.",
    "Customer {customer} disputed a charge on order {order}; refund under review.",
]

def generate_tickets(customers_df, orders_df, n=200):
    tickets = []
    for i in range(n):
        order_row = orders_df.sample(1).iloc[0]
        template = random.choice(TICKET_TEMPLATES)
        text = template.format(
            customer=order_row["customerID"],
            order=order_row["orderID"]
        )
        tickets.append({
            "ticket_id": f"TCK-{1000+i}",
            "customer_id": order_row["customerID"],
            "order_id": order_row["orderID"],
            "text": text
        })
    return pd.DataFrame(tickets)

if __name__ == "__main__":
    customers = pd.read_csv("data/customers.csv")
    orders = read_orders()
    tickets = generate_tickets(customers, orders)
    tickets.to_json("data/support_tickets.json", orient="records", indent=2)
    print(f"Generated {len(tickets)} support tickets")
