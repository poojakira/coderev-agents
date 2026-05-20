"""LangGraph state machine for multi-agent code review."""

from typing import TypedDict

from langgraph.graph import StateGraph, END

from coderev.agents.nodes import (
    orchestrator_node,
    security_node,
    style_node,
    complexity_node,
    summarizer_node,
)


class ReviewState(TypedDict):
    diff: str
    language: str
    # Agent outputs
    security_review: str
    style_review: str
    complexity_review: str
    # Routing decisions
    run_security: bool
    run_complexity: bool
    # Final
    summary: str


def route_after_orchestrator(state: ReviewState) -> list[str]:
    """Conditional routing — skip agents based on diff characteristics."""
    targets = ["style_agent"]  # Always run style
    if state.get("run_security", True):
        targets.append("security_agent")
    if state.get("run_complexity", True):
        targets.append("complexity_agent")
    return targets


def build_graph() -> StateGraph:
    """Construct the multi-agent review graph."""
    graph = StateGraph(ReviewState)

    # Add nodes
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("security_agent", security_node)
    graph.add_node("style_agent", style_node)
    graph.add_node("complexity_agent", complexity_node)
    graph.add_node("summarizer", summarizer_node)

    # Entry point
    graph.set_entry_point("orchestrator")

    # Conditional fan-out from orchestrator
    graph.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "security_agent": "security_agent",
            "style_agent": "style_agent",
            "complexity_agent": "complexity_agent",
        },
    )

    # All agents converge to summarizer
    graph.add_edge("security_agent", "summarizer")
    graph.add_edge("style_agent", "summarizer")
    graph.add_edge("complexity_agent", "summarizer")

    # Summarizer ends
    graph.add_edge("summarizer", END)

    return graph


def compile_graph():
    """Compile the graph for execution."""
    return build_graph().compile()
