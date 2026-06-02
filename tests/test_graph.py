"""Tests for the multi-agent code review graph."""

from coderev.agents.graph import ReviewState, route_after_orchestrator


def test_route_all_agents_for_large_diff():
    state: ReviewState = {
        "diff": "x\n" * 50,
        "language": "python",
        "security_review": "",
        "style_review": "",
        "complexity_review": "",
        "run_security": True,
        "run_complexity": True,
        "summary": "",
    }
    targets = route_after_orchestrator(state)
    assert "style_agent" in targets
    assert "security_agent" in targets
    assert "complexity_agent" in targets


def test_route_skips_security_for_small_diff():
    state: ReviewState = {
        "diff": "x\n" * 5,
        "language": "python",
        "security_review": "",
        "style_review": "",
        "complexity_review": "",
        "run_security": False,
        "run_complexity": True,
        "summary": "",
    }
    targets = route_after_orchestrator(state)
    assert "style_agent" in targets
    assert "security_agent" not in targets


def test_route_skips_complexity_for_trivial_diff():
    state: ReviewState = {
        "diff": "x\n" * 5,
        "language": "python",
        "security_review": "",
        "style_review": "",
        "complexity_review": "",
        "run_security": True,
        "run_complexity": False,
        "summary": "",
    }
    targets = route_after_orchestrator(state)
    assert "complexity_agent" not in targets
    assert "style_agent" in targets


def test_route_always_includes_style():
    state: ReviewState = {
        "diff": "x",
        "language": "python",
        "security_review": "",
        "style_review": "",
        "complexity_review": "",
        "run_security": False,
        "run_complexity": False,
        "summary": "",
    }
    targets = route_after_orchestrator(state)
    assert targets == ["style_agent"]


def test_orchestrator_node_detects_python():
    from coderev.agents.nodes import orchestrator_node

    state = {"diff": "def hello():\n    pass\n" * 15, "language": ""}
    result = orchestrator_node(state)
    assert result["language"] == "python"
    assert result["run_security"] is True
    assert result["run_complexity"] is True


def test_orchestrator_node_skips_security_for_short():
    from coderev.agents.nodes import orchestrator_node

    state = {"diff": "x = 1\n", "language": "python"}
    result = orchestrator_node(state)
    assert result["run_security"] is False
