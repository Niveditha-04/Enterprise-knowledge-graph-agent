"""Hallucination-resistance tests for grounded answer synthesis.

These tests run first in Section 7 because synthesis must refuse to guess
when retrieval misses the relevant evidence (see order 10864 in Section 6).
"""

import json
from pathlib import Path

import pytest

from agent.synthesis import (
    indicates_insufficient_evidence,
    indicates_order_10864_fabrication,
    synthesize_answer,
)

TICKETS_PATH = Path(__file__).parent / "data" / "support_tickets.json"

# Actual bad Chroma retrieval for "What happened with order 10864?" (Section 6).
# Ground-truth ticket TCK-1002 is absent; nearby order numbers create a hallucination trap.
BAD_ORDER_10864_RETRIEVAL_IDS = [
    "TCK-1156",
    "TCK-1135",
    "TCK-1029",
    "TCK-1107",
    "TCK-1077",
    "TCK-1122",
    "TCK-1024",
    "TCK-1087",
    "TCK-1124",
    "TCK-1105",
]

QUESTION_ORDER_10864 = "What happened with order 10864?"


@pytest.fixture(scope="module")
def tickets_by_id():
    tickets = json.loads(TICKETS_PATH.read_text())
    return {t["ticket_id"]: t for t in tickets}


@pytest.fixture(scope="module")
def bad_order_10864_ticket_chunks(tickets_by_id):
    chunks = []
    for ticket_id in BAD_ORDER_10864_RETRIEVAL_IDS:
        ticket = tickets_by_id[ticket_id]
        chunks.append(
            {
                "ticket_id": ticket["ticket_id"],
                "text": ticket["text"],
                "customer_id": ticket["customer_id"],
                "order_id": ticket["order_id"],
            }
        )
    return chunks


def test_synthesis_refuses_to_hallucinate_on_missed_order_10864_retrieval(
    bad_order_10864_ticket_chunks,
):
    """Feed synthesis the real bad Chroma output — it must not invent an answer."""
    result = synthesize_answer(
        question=QUESTION_ORDER_10864,
        graph_result=None,
        ticket_chunks=bad_order_10864_ticket_chunks,
    )

    print(
        "\n--- Hallucination-resistance test (order 10864 bad retrieval) ---\n"
        f"Question: {QUESTION_ORDER_10864}\n"
        f"Retrieved ticket IDs: {BAD_ORDER_10864_RETRIEVAL_IDS}\n"
        f"Missing ground-truth ticket: TCK-1002\n"
        f"Synthesis answer:\n{result['answer']}\n"
        f"insufficient_evidence={result['insufficient_evidence']}\n"
        f"evidence_sufficient={result['evidence_sufficient']}"
    )

    assert result["insufficient_evidence"] or not result["evidence_sufficient"], (
        "Expected synthesis to flag insufficient evidence, got:\n"
        f"{result['answer']}"
    )
    assert indicates_insufficient_evidence(result["answer"]), (
        "Answer should explicitly state insufficient evidence:\n"
        f"{result['answer']}"
    )
    assert not indicates_order_10864_fabrication(result["answer"]), (
        "Answer fabricated the true issue (damaged product on order 10864):\n"
        f"{result['answer']}"
    )

    lowered = result["answer"].lower()
    assert "no response after 3 business days" not in lowered or "10864" not in lowered, (
        "Answer incorrectly attributed a nearby-order status complaint to order 10864:\n"
        f"{result['answer']}"
    )
