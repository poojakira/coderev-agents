"""FastAPI serving endpoint for multi-agent code review."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from coderev.agents.graph import compile_graph

app = FastAPI(
    title="CodeRev Agents",
    description="Multi-agent code review powered by fine-tuned CodeLlama + LangGraph",
    version="0.3.1",
)

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = compile_graph()
    return _graph


class ReviewRequest(BaseModel):
    diff: str = Field(..., min_length=5, max_length=50000)
    language: str = Field(default="", max_length=50)


class ReviewResponse(BaseModel):
    summary: str
    security_review: str
    style_review: str
    complexity_review: str
    agents_invoked: list[str]


@app.post("/v1/review", response_model=ReviewResponse)
async def review_code(request: ReviewRequest) -> ReviewResponse:
    """Submit a code diff for multi-agent review."""
    graph = get_graph()

    initial_state = {
        "diff": request.diff,
        "language": request.language,
        "security_review": "",
        "style_review": "",
        "complexity_review": "",
        "run_security": True,
        "run_complexity": True,
        "summary": "",
    }

    try:
        result = await graph.ainvoke(initial_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {str(e)}")

    agents = ["style_agent"]
    if result.get("run_security"):
        agents.append("security_agent")
    if result.get("run_complexity"):
        agents.append("complexity_agent")

    return ReviewResponse(
        summary=result.get("summary", ""),
        security_review=result.get("security_review", ""),
        style_review=result.get("style_review", ""),
        complexity_review=result.get("complexity_review", ""),
        agents_invoked=agents,
    )


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.3.1"}
