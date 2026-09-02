import chromadb
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()


def build_ticket_index(reset: bool = True):
    client = chromadb.PersistentClient(path="./chroma_db")
    if reset:
        try:
            client.delete_collection("support_tickets")
        except Exception:
            pass
    collection = client.get_or_create_collection("support_tickets")

    tickets = pd.read_json("data/support_tickets.json")

    collection.add(
        ids=tickets["ticket_id"].tolist(),
        documents=tickets["text"].tolist(),
        metadatas=[
            {"customer_id": row["customer_id"], "order_id": str(row["order_id"])}
            for _, row in tickets.iterrows()
        ]
    )
    print(f"Indexed {len(tickets)} tickets")
    return collection


if __name__ == "__main__":
    build_ticket_index()
