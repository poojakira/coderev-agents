"""Agent node implementations for the code review graph."""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from coderev.config import Settings

_settings = Settings()
_llm = ChatOpenAI(
    model=_settings.llm_model,
    api_key=_settings.llm_api_key or "sk-placeholder",
    base_url=_settings.llm_base_url or None,
    temperature=_settings.llm_temperature,
)


def orchestrator_node(state: dict) -> dict:
    """Route decision — analyze diff and decide which agents to invoke."""
    diff = state["diff"]
    lines = diff.strip().split("\n")
    num_lines = len(lines)

    # Heuristic routing: skip security for trivial diffs, skip complexity for short ones
    run_security = num_lines >= _settings.security_scan_threshold
    run_complexity = num_lines >= 20

    # Detect language if not provided
    language = state.get("language", "")
    if not language:
        if any(kw in diff for kw in ["def ", "import ", "class "]):
            language = "python"
        elif any(kw in diff for kw in ["function ", "const ", "=>"]):
            language = "javascript"
        else:
            language = "unknown"

    return {"run_security": run_security, "run_complexity": run_complexity, "language": language}


def security_node(state: dict) -> dict:
    """Security-focused code review agent."""
    response = _llm.invoke([
        SystemMessage(content=(
            "You are a security-focused code reviewer. Identify: SQL injection, XSS, "
            "hardcoded secrets, insecure deserialization, path traversal, SSRF, "
            "and authentication/authorization flaws. Be concise."
        )),
        HumanMessage(content=f"Review this diff for security issues:\n```\n{state['diff']}\n```"),
    ])
    return {"security_review": response.content}


def style_node(state: dict) -> dict:
    """Style and best practices review agent."""
    response = _llm.invoke([
        SystemMessage(content=(
            "You are a code style reviewer. Check: naming conventions, function length, "
            "dead code, missing type hints, unclear variable names, and violations of "
            "language-specific idioms. Be concise and actionable."
        )),
        HumanMessage(content=f"Review this {state.get('language', '')} diff for style:\n```\n{state['diff']}\n```"),
    ])
    return {"style_review": response.content}


def complexity_node(state: dict) -> dict:
    """Complexity analysis agent."""
    response = _llm.invoke([
        SystemMessage(content=(
            "You are a code complexity analyst. Evaluate: cyclomatic complexity, "
            "nesting depth, function length, coupling between modules, and suggest "
            "refactoring opportunities. Be concise."
        )),
        HumanMessage(content=f"Analyze complexity of this diff:\n```\n{state['diff']}\n```"),
    ])
    return {"complexity_review": response.content}


def summarizer_node(state: dict) -> dict:
    """Aggregate all agent reviews into a final summary."""
    parts = []
    if state.get("security_review"):
        parts.append(f"## Security\n{state['security_review']}")
    if state.get("style_review"):
        parts.append(f"## Style\n{state['style_review']}")
    if state.get("complexity_review"):
        parts.append(f"## Complexity\n{state['complexity_review']}")

    combined = "\n\n".join(parts) if parts else "No issues found."

    response = _llm.invoke([
        SystemMessage(content=(
            "Summarize these code review findings into a concise, prioritized review. "
            "Start with critical issues, then warnings, then suggestions. "
            "Use markdown formatting."
        )),
        HumanMessage(content=combined),
    ])
    return {"summary": response.content}
