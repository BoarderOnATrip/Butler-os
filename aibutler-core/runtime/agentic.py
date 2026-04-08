#!/usr/bin/env python3
"""
aiButler Agentic Core — Plan → Execute → Reflect → Iterate loop.

The orchestrator drives multi-step tasks autonomously:
  1. Planner     → decides the next tool call(s) given objective + history
  2. Executor    → runs tool calls through the existing ButlerRuntime (with full approval enforcement)
  3. Reviewer    → evaluates results; decides if the objective is met or needs another iteration
  4. Memory      → writes reflection + result to the runtime store (RAG + structured)
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from runtime.models import utc_now


@dataclass
class AgenticStep:
    step: int
    action: str
    reasoning: str
    tool_calls: list[dict]
    result: Any = None
    review: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        return asdict(self)


class AgenticOrchestrator:
    """
    Multi-agent loop. All tool execution goes through ButlerRuntime.execute_tool
    so the approval-first policy is always enforced.
    """

    MASTER_SESSION_ID = "agentic-master"

    def __init__(self, runtime: "ButlerRuntime"):  # type: ignore[name-defined]
        self.runtime = runtime
        self._ensure_session()

    def _ensure_session(self):
        self.session = self.runtime.get_or_create_session(
            session_id=self.MASTER_SESSION_ID,
            user_id="agentic-orchestrator",
            surface="agentic",
            metadata={"orchestrator": True},
        )

    async def run(self, objective: str, max_iterations: int = 8) -> dict:
        """Run the full agentic loop. Returns final result dict."""
        history: list[AgenticStep] = []
        current_objective = objective

        for iteration in range(max_iterations):
            # 1. Plan
            plan = await self._plan(current_objective, history)

            # 2. Execute
            execution_result = self._execute_plan(plan)

            # 3. Review
            review = await self._review(objective, plan, execution_result, history)

            step = AgenticStep(
                step=iteration + 1,
                action=plan.get("action", "unknown"),
                reasoning=plan.get("reasoning", ""),
                tool_calls=plan.get("tool_calls", []),
                result=execution_result,
                review=review,
            )
            history.append(step)

            # 4. Write to memory
            self.runtime.write_memory(
                session_id=self.session.id,
                kind="agentic_step",
                content=f"Step {iteration + 1} — {review.get('summary', '')}",
                tags=["agentic", "step", f"iteration-{iteration + 1}"],
                metadata={
                    "objective": objective,
                    "step": step.to_dict(),
                },
            )

            if review.get("done"):
                return {
                    "status": "complete",
                    "objective": objective,
                    "iterations": iteration + 1,
                    "final_result": review.get("result"),
                    "history": [s.to_dict() for s in history],
                }

            current_objective = review.get("next_objective", objective)

        return {
            "status": "max_iterations_reached",
            "objective": objective,
            "iterations": max_iterations,
            "history": [s.to_dict() for s in history],
        }

    async def _plan(self, objective: str, history: list[AgenticStep]) -> dict:
        """
        Planner: determines the next action.
        In production, this calls Claude with full context and tool specs.
        Stub implementation uses heuristic routing.
        """
        objective_lower = objective.lower()

        # Heuristic routing for common patterns
        if any(k in objective_lower for k in ("pipeline", "follow-up", "follow up", "relationship", "outreach", "reply")):
            return {
                "action": "relationship_followups",
                "reasoning": "Objective involves relationship management; inspect the live follow-up queue first.",
                "tool_calls": [{"tool": "relationship_list_followups", "args": {"limit": 8}}],
            }
        if any(k in objective_lower for k in ("calendar", "meeting", "schedule", "event")):
            return {
                "action": "list_calendar_events",
                "reasoning": "Objective involves scheduling; inspect upcoming calendar events first.",
                "tool_calls": [{"tool": "calendar_list_events", "args": {"days": 7}}],
            }
        if any(k in objective_lower for k in ("contact", "email", "phone")):
            query = objective.split()[-1]
            return {
                "action": "search_contacts",
                "reasoning": "Objective involves contacts.",
                "tool_calls": [{"tool": "contacts_search", "args": {"query": query}}],
            }
        if any(k in objective_lower for k in ("screenshot", "screen", "capture")):
            return {
                "action": "capture_screen",
                "reasoning": "Objective requires screen inspection.",
                "tool_calls": [{"tool": "capture_screen", "args": {}}],
            }
        if any(k in objective_lower for k in ("briefing", "summary", "status", "today")):
            return {
                "action": "daily_briefing",
                "reasoning": "Generate daily executive overview from calendar plus relationship follow-ups.",
                "tool_calls": [
                    {"tool": "calendar_list_events", "args": {"days": 1}},
                    {"tool": "relationship_get_briefing", "args": {"limit": 5}},
                ],
            }

        # Default: no tool call, respond from memory
        return {
            "action": "respond_from_context",
            "reasoning": f"No specific tool matches '{objective}'. Responding from context.",
            "tool_calls": [],
        }

    def _execute_plan(self, plan: dict) -> list[dict]:
        """Execute each tool call in the plan through the runtime (approval enforced)."""
        results = []
        for call in plan.get("tool_calls", []):
            try:
                result = self.runtime.execute_tool(
                    session_id=self.session.id,
                    tool_name=call["tool"],
                    args=call.get("args", {}),
                    actor="agentic-planner",
                )
                results.append({"tool": call["tool"], "result": result})
            except Exception as e:
                results.append({"tool": call["tool"], "error": str(e)})
        return results

    async def _review(
        self,
        original_objective: str,
        plan: dict,
        execution_result: list[dict],
        history: list[AgenticStep],
    ) -> dict:
        """
        Reviewer: evaluate results and decide if done.
        In production, this calls Claude with the full execution context.
        """
        all_ok = all(r.get("result", {}).get("ok", True) for r in execution_result if "result" in r)

        # Stop if we got good results or have done 3+ iterations on simple tasks
        done = all_ok and (len(history) >= 1 or not execution_result)

        output_summary = json.dumps(execution_result, default=str)[:300]

        return {
            "done": done,
            "summary": f"Action '{plan.get('action')}' completed. Results: {output_summary}",
            "next_objective": original_objective,
            "result": execution_result,
        }
