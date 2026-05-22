"""Live eval runner for document-grounded answers that must update the canvas.

Run from backend:
    uv run python evals/eval_agent_canvas_scalar.py

Use another engineering-document fixture:
    uv run python evals/eval_agent_canvas_scalar.py --suite evals/fixtures/my_doc.json

The benchmark prompts live in eval fixture files, not in the agent prompt. This
runner checks that exact eval prompts are absent from active agent instructions.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.agent import agent
from src.agent.deps import AgentDeps
from src.agent.state import Canvas, CanvasNode


DEFAULT_SUITE = ROOT / "evals" / "fixtures" / "sample_canvas_facts.json"


@dataclass(frozen=True)
class EvalCase:
    name: str
    prompt: str
    expected_node_type: str
    expected_answer_terms: tuple[str, ...]
    expected_canvas_terms: tuple[str, ...]
    expected_page: int


@dataclass(frozen=True)
class EvalSuite:
    document_id: str
    filename: str
    cases: tuple[EvalCase, ...]


def _load_suite(path: Path) -> EvalSuite:
    data = json.loads(path.read_text(encoding="utf-8"))
    document = data["document"]
    cases = tuple(
        EvalCase(
            name=item["name"],
            prompt=item["prompt"],
            expected_node_type=item["expected_node_type"],
            expected_answer_terms=tuple(item.get("expected_answer_terms") or item["expected_terms"]),
            expected_canvas_terms=tuple(item.get("expected_canvas_terms") or item["expected_terms"]),
            expected_page=int(item["expected_page"]),
        )
        for item in data["cases"]
    )
    return EvalSuite(
        document_id=document["id"],
        filename=document["filename"],
        cases=cases,
    )


def _new_state(suite: EvalSuite) -> Canvas:
    return Canvas(
        nodes=[
            CanvasNode(
                id=f"__doc_{suite.document_id}",
                node_type="document",
                title=suite.filename,
                filename=suite.filename,
                status="found",
            )
        ],
        workspace_doc_ids=[suite.document_id],
        active_document_id=suite.document_id,
    )


def _node_text(node: CanvasNode) -> str:
    parts = [node.title, node.text, node.spec_title]
    for section in node.parameter_sections:
        parts.append(section.name)
        for row in section.rows:
            parts.extend([row.parameter, row.value, row.unit, row.source.filename, str(row.source.page)])
    return " ".join(part for part in parts if part)


def _canvas_text(state: Canvas) -> str:
    return " ".join(_node_text(node) for node in state.nodes).lower()


def _fact_has_evidence(state: Canvas, node: CanvasNode, suite: EvalSuite, page: int) -> bool:
    return any(
        rel.from_id == node.id
        and rel.to_id == f"__doc_{suite.document_id}"
        and rel.document_id == suite.document_id
        and rel.page == page
        for rel in state.relations
    )


def _spec_has_sources(node: CanvasNode, suite: EvalSuite, page: int) -> bool:
    rows = [row for section in node.parameter_sections for row in section.rows]
    return bool(rows) and all(
        row.source.filename
        and row.source.filename == suite.filename
        and row.source.page == page
        and len(row.source.bbox) == 4
        for row in rows
    )


def _active_instruction_text() -> str:
    paths = [
        ROOT / "src" / "agent" / "prompts.py",
        ROOT / "src" / "agent" / "capabilities" / "canvas.py",
        ROOT / "src" / "agent" / "capabilities" / "context.py",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths).lower()


def _assert_eval_questions_not_in_agent_instructions(cases: Iterable[EvalCase]) -> None:
    instructions = _active_instruction_text()
    leaked = [case.prompt for case in cases if case.prompt.lower() in instructions]
    if leaked:
        raise AssertionError(f"eval question(s) leaked into active agent instructions: {leaked}")


def _assert_terms_present(terms: Iterable[str], haystack: str, label: str) -> None:
    missing = [term for term in terms if term.lower() not in haystack]
    if missing:
        raise AssertionError(f"{label} missing expected terms: {missing}")


async def _run_case(suite: EvalSuite, case: EvalCase) -> None:
    state = _new_state(suite)
    deps = AgentDeps(state=state)
    result = await agent.run(case.prompt, deps=deps)
    answer = str(getattr(result, "output", result))
    try:
        content_nodes = [node for node in state.nodes if node.node_type in {"fact", "spec"}]
        target_nodes = [node for node in content_nodes if node.node_type == case.expected_node_type]

        if not target_nodes:
            created = [node.node_type for node in content_nodes]
            raise AssertionError(f"{case.name}: expected {case.expected_node_type} node, got {created}")

        canvas_text = _canvas_text(state)
        _assert_terms_present(case.expected_answer_terms, answer.lower(), f"{case.name} answer")
        _assert_terms_present(case.expected_canvas_terms, canvas_text, f"{case.name} canvas")

        if case.expected_node_type == "fact":
            if not any(_fact_has_evidence(state, node, suite, case.expected_page) for node in target_nodes):
                raise AssertionError(f"{case.name}: fact node missing evidence relation to {suite.filename} page {case.expected_page}")
        else:
            if not any(_spec_has_sources(node, suite, case.expected_page) for node in target_nodes):
                raise AssertionError(f"{case.name}: spec node missing row-level sources for {suite.filename} page {case.expected_page}")
    except Exception:
        print(f"ANSWER {case.name}: {answer}")
        print("NODES:")
        for node in state.nodes:
            print(f"  - {node.node_type} {node.id}: {_node_text(node)}")
        print("RELATIONS:")
        for rel in state.relations:
            print(f"  - {rel.from_id} -> {rel.to_id} page={rel.page} doc={rel.document_id} label={rel.label}")
        raise

    print(f"PASS {case.name}: {answer.strip()[:180]}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="JSON eval suite for one engineering document")
    args = parser.parse_args()

    suite = _load_suite(args.suite)
    _assert_eval_questions_not_in_agent_instructions(suite.cases)
    for case in suite.cases:
        try:
            await _run_case(suite, case)
        except Exception as exc:
            print(f"FAIL {case.name}: {exc}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
