import chromadb

def query_tickets(question: str, n_results: int = 3):
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_collection("support_tickets")
    results = collection.query(query_texts=[question], n_results=n_results)
    return results
