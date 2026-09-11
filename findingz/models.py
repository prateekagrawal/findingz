from __future__ import annotations

import json
import os
import re
import urllib.request
from abc import ABC, abstractmethod

from .schemas import AnalysisFilter, AnalysisPlan, AnalysisSummary

SYSTEM_PROMPT = """You are the planning component of Finding Z, a bounded dilepton
analysis assistant. Return only an AnalysisPlan matching the supplied JSON schema. Never invent
columns or tools. Use execute=false with a concise clarification when the request is ambiguous
or outside the supported neutral-current Drell-Yan scope. The deterministic tool layer, not you, computes
all numbers."""


class ModelBackend(ABC):
    name: str

    @abstractmethod
    def create_plan(self, question: str) -> AnalysisPlan: ...

    @abstractmethod
    def explain(
        self,
        question: str,
        plan: AnalysisPlan,
        summary: AnalysisSummary,
        excerpts: list[dict[str, str]],
    ) -> str: ...


class ReplayBackend(ModelBackend):
    """Deterministic offline fixture used for development and common demos."""

    name = "replay"

    def create_plan(self, question: str) -> AnalysisPlan:
        lower = question.lower()
        if "identify the incoming quark" in lower or "which proton had the quark" in lower:
            return AnalysisPlan(
                execute=False,
                clarification=(
                    "A proton-proton dilepton event does not determine the incoming quark "
                    "direction event by event. A PDF-based probabilistic inference would need "
                    "a documented model beyond this prepared dataset."
                ),
            )
        if re.fullmatch(r"\s*show me (the )?(z|drell[- ]yan) events[.!]?\s*", lower):
            return AnalysisPlan(
                execute=False,
                clarification=(
                    "Do you mean the simulated Drell-Yan component or collision-like data, and "
                    "should the selection use a Z-mass window or a particular dilepton channel?"
                ),
            )

        samples: list[str] = []
        if "signal" in lower:
            samples.append("signal")
        if "background" in lower:
            samples.append("background")
        if "collision" in lower or "data" in lower:
            samples.append("collision")
        if not samples:
            samples = ["signal", "background"] if "compare" in lower else ["collision"]

        channels = []
        if re.search(r"\bee\b|dielectron", lower):
            channels.append("ee")
        if re.search(r"\bmumu\b|dimuon|muon pair", lower):
            channels.append("mumu")
        filters: list[AnalysisFilter] = []
        pt_match = re.search(r"p[_ ]?t\s*(?:above|>|greater than)\s*(\d+(?:\.\d+)?)", lower)
        if pt_match:
            filters.append(
                AnalysisFilter(
                    variable="min_lepton_pt", operator=">", value=float(pt_match.group(1))
                )
            )
        mass_match = re.search(
            r"(?:between|from)\s*(\d+(?:\.\d+)?)\s*(?:and|to|-)\s*(\d+(?:\.\d+)?)\s*(?:gev)?",
            lower,
        )
        if mass_match:
            filters.append(
                AnalysisFilter(
                    variable="mll",
                    operator="between",
                    value=[float(mass_match.group(1)), float(mass_match.group(2))],
                )
            )
        observable = "mll"
        if "collins" in lower or "cos theta" in lower or "angular" in lower:
            observable = "cos_theta_cs"
        elif "rapidity" in lower or "yll" in lower:
            observable = "rapidity_ll"
        elif "dilepton pt" in lower or "ptll" in lower:
            observable = "ptll"
        return AnalysisPlan(
            samples=samples,
            channels=channels,
            filters=filters,
            observable=observable,
            plot="overlay" if len(samples) > 1 or len(channels) > 1 else "histogram",
            explanation_topics=[
                "dilepton invariant mass",
                "Drell-Yan",
                "Collins-Soper angle",
                "data provenance",
            ],
        )

    def explain(
        self,
        question: str,
        plan: AnalysisPlan,
        summary: AnalysisSummary,
        excerpts: list[dict[str, str]],
    ) -> str:
        sources = ", ".join(sorted({item["source"] for item in excerpts})) or "no note match"
        caution = ""
        if "collision" in plan.samples and summary.z_window_counts.get("collision", 0):
            caution = (
                " Events in the Z window are candidates, not individually proven Drell-Yan "
                "events; other processes can produce the same reconstructed final state."
            )
        return (
            f"The deterministic tools selected {summary.selected_events} and reconstructed "
            f"{summary.observable} from the two lepton momenta. The dilepton invariant mass "
            "comes from the Minkowski norm of the summed four-momentum, so it is unchanged by a "
            f"common Lorentz transformation.{caution} Grounding sources: {sources}."
        )


class _HTTPBackend(ModelBackend):
    def _post(
        self, url: str, payload: dict[str, object], headers: dict[str, str] | None = None
    ) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))


class OllamaBackend(_HTTPBackend):
    name = "ollama"

    def __init__(self) -> None:
        self.base_url = os.environ.get("FINDINGZ_OLLAMA_URL", "http://localhost:11434")
        self.model = os.environ.get("FINDINGZ_OLLAMA_MODEL", "")
        if not self.model:
            raise ValueError("Set FINDINGZ_OLLAMA_MODEL before using the Ollama backend")

    def create_plan(self, question: str) -> AnalysisPlan:
        response = self._post(
            f"{self.base_url}/api/chat",
            {
                "model": self.model,
                "stream": False,
                "format": AnalysisPlan.model_json_schema(),
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
            },
        )
        return AnalysisPlan.model_validate_json(response["message"]["content"])

    def explain(self, question, plan, summary, excerpts) -> str:
        response = self._post(
            f"{self.base_url}/api/chat",
            {
                "model": self.model,
                "stream": False,
                "options": {"temperature": 0.2},
                "messages": [
                    {
                        "role": "system",
                        "content": "Explain only from the supplied tool results and excerpts.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "plan": plan.model_dump(),
                                "tool_results": summary.model_dump(),
                                "course_excerpts": excerpts,
                            }
                        ),
                    },
                ],
            },
        )
        return response["message"]["content"]


class CourseServerBackend(_HTTPBackend):
    name = "course_server"

    def __init__(self) -> None:
        self.base_url = os.environ.get("FINDINGZ_COURSE_BASE_URL", "http://localhost:8000/v1")
        self.api_key = os.environ.get("FINDINGZ_COURSE_API_KEY", "course-key")
        self.model = os.environ.get("FINDINGZ_COURSE_MODEL", "course-model")

    def _chat(self, messages: list[dict[str, str]], structured: bool = False) -> str:
        payload: dict[str, object] = {"model": self.model, "messages": messages, "temperature": 0}
        if structured:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "analysis_plan",
                    "strict": True,
                    "schema": AnalysisPlan.model_json_schema(),
                },
            }
        response = self._post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            payload,
            {"Authorization": f"Bearer {self.api_key}"},
        )
        return response["choices"][0]["message"]["content"]

    def create_plan(self, question: str) -> AnalysisPlan:
        content = self._chat(
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}],
            structured=True,
        )
        return AnalysisPlan.model_validate_json(content)

    def explain(self, question, plan, summary, excerpts) -> str:
        return self._chat(
            [
                {
                    "role": "system",
                    "content": "Explain only from supplied tool results and course excerpts.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": question,
                            "plan": plan.model_dump(),
                            "tool_results": summary.model_dump(),
                            "course_excerpts": excerpts,
                        }
                    ),
                },
            ]
        )


def get_backend(name: str | None = None) -> ModelBackend:
    backend = name or os.environ.get("FINDINGZ_MODEL_BACKEND", "replay")
    if backend == "replay":
        return ReplayBackend()
    if backend == "ollama":
        return OllamaBackend()
    if backend == "course_server":
        return CourseServerBackend()
    raise ValueError(f"Unknown model backend: {backend}")
