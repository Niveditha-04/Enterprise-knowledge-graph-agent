import chromadb
import pandas as pd
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.csv_utils import read_orders

def build_flat_baseline_index(reset: bool = True):
    client = chromadb.PersistentClient(path="./chroma_db_baseline")
    if reset:
        try:
            client.delete_collection("flat_baseline")
        except Exception:
            pass
    collection = client.get_or_create_collection("flat_baseline")

    orders = read_orders()

    docs, ids = [], []
    for _, row in orders.iterrows():
        doc = f"Order {row['orderID']} placed by customer {row['customerID']} on {row.get('orderDate', 'unknown date')}."
        docs.append(doc)
        ids.append(f"order-{row['orderID']}")

    collection.add(ids=ids, documents=docs)
    return collection

def query_baseline(question, n_results=3):
    client = chromadb.PersistentClient(path="./chroma_db_baseline")
    collection = client.get_collection("flat_baseline")
    return collection.query(query_texts=[question], n_results=n_results)
