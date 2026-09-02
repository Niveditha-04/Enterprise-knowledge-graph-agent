"""Ticket-only RAG baseline using the same Chroma index as the hybrid system."""

from __future__ import annotations

from rag.query_index import query_tickets


def query_ticket_baseline(question: str, n_results: int = 3) -> dict:
    return query_tickets(question, n_results=n_results)
