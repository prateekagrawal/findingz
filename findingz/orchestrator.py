from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .analysis import ExecutionResult, execute_plan
from .knowledge import search_course_notes
from .models import ModelBackend, get_backend
from .schemas import AnalysisPlan


@dataclass
class AnswerBundle:
    question: str
    backend_name: str
    plan: AnalysisPlan
    execution: ExecutionResult | None
    excerpts: list[dict[str, str]]
    explanation: str | None


class FindingZAgent:
    def __init__(self, backend: ModelBackend | None = None, data_dir: Path | None = None) -> None:
        self.backend = backend or get_backend()
        self.data_dir = data_dir

    def plan(self, question: str) -> AnalysisPlan:
        return self.backend.create_plan(question)

    def run(self, question: str, plan: AnalysisPlan) -> AnswerBundle:
        if not plan.execute:
            return AnswerBundle(
                question=question,
                backend_name=self.backend.name,
                plan=plan,
                execution=None,
                excerpts=[],
                explanation=plan.clarification,
            )
        execution = execute_plan(plan, self.data_dir)
        retrieval_query = " ".join([question, *plan.explanation_topics])
        excerpts = search_course_notes(retrieval_query)
        explanation = self.backend.explain(question, plan, execution.summary, excerpts)
        return AnswerBundle(
            question=question,
            backend_name=self.backend.name,
            plan=plan,
            execution=execution,
            excerpts=excerpts,
            explanation=explanation,
        )
