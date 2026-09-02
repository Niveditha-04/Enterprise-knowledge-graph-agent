from agent.orchestrator import HybridOrchestrator

def test_orchestrator_routes_correctly():
    orchestrator = HybridOrchestrator()
    graph_q = orchestrator.answer("How many orders has customer ALFKI placed?")
    assert graph_q["route"] in ("GRAPH", "BOTH")

    ticket_q = orchestrator.answer("Which tickets mention damaged products?")
    assert ticket_q["route"] in ("TICKETS", "BOTH")
    orchestrator.close()
