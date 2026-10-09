from __future__ import annotations

from src.contracts import Architecture, ProcurementDecision
from src.agent_single import SingleProcurementAgent
from src.agent_staged import StagedProcurementSystem


def handle_request(request_id: str, architecture: Architecture = "single") -> ProcurementDecision:
    """Assessment adapter.

    Keep this function callable by the public/hidden evaluation harness.
    Your internal implementation may use any framework, modules, agents, tools,
    deterministic checks, or orchestration strategy.
    """
    if architecture == "single":
        agent = SingleProcurementAgent()
        return agent.run(request_id)
    elif architecture == "staged":
        staged_system = StagedProcurementSystem()
        return staged_system.run(request_id)
    else:
        raise ValueError(f"Unknown architecture: {architecture}")
