#!/usr/bin/env python3
"""
aiButler core agent.

This is intentionally small and deterministic. It keeps Butler's core surface
closer to pi's minimal wrapper philosophy: route a prompt to the right Butler
tooling, summarize the result, and leave heavier orchestration as an optional
layer above it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from runtime.models import utc_now


@dataclass
class CoreAgentResponse:
    prompt: str
    mode: str
    summary: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    session_id: str = ""
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ButlerCoreAgent:
    """Thin Butler wrapper that routes prompts into the right context tools."""

    DEFAULT_SESSION_ID = "core-agent"

    def __init__(self, runtime: "ButlerRuntime"):  # type: ignore[name-defined]
        self.runtime = runtime

    def run(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        normalized_prompt = (prompt or "").strip()
        if not normalized_prompt:
            return {"ok": False, "output": "", "error": "prompt is required"}

        session = self.runtime.get_or_create_session(
            session_id=session_id or self.DEFAULT_SESSION_ID,
            user_id="butler-core-agent",
            surface="core-agent",
            metadata={"core_agent": True},
        )
        plan = self._plan(normalized_prompt, limit=max(1, min(limit, 8)))
        tool_results: list[dict[str, Any]] = []

        for call in plan["tool_calls"]:
            result = self.runtime.execute_tool(
                session_id=session.id,
                tool_name=call["tool"],
                args=call.get("args", {}),
                actor="butler-core-agent",
                note=f"Core agent routed prompt via {call['tool']}",
            )
            tool_results.append(
                {
                    "tool": call["tool"],
                    "args": call.get("args", {}),
                    "result": result,
                }
            )

        summary, citations = self._summarize(
            mode=plan["mode"],
            prompt=normalized_prompt,
            tool_results=tool_results,
        )

        response = CoreAgentResponse(
            prompt=normalized_prompt,
            mode=plan["mode"],
            summary=summary,
            citations=citations,
            tool_results=tool_results,
            session_id=session.id,
        )

        self.runtime.write_memory(
            session_id=session.id,
            kind="core_agent_turn",
            content=summary,
            tags=["core-agent", plan["mode"]],
            metadata={
                "prompt": normalized_prompt,
                "mode": plan["mode"],
                "tool_results": tool_results,
            },
        )

        return {
            "ok": True,
            "output": response.to_dict(),
            "error": None,
        }

    def _plan(self, prompt: str, limit: int) -> dict[str, Any]:
        prompt_lower = prompt.lower()

        if any(
            phrase in prompt_lower
            for phrase in (
                "bring butler back online",
                "bring intelligence back online",
                "restore intelligence",
                "rehydrate secret",
                "recover secret",
                "recover api key",
                "restore api key",
            )
        ):
            return {
                "mode": "secret_recovery",
                "tool_calls": [
                    {"tool": "secret_recovery_status", "args": {}},
                    {"tool": "rehydrate_missing_secrets", "args": {}},
                ],
            }

        if any(
            phrase in prompt_lower
            for phrase in (
                "secret status",
                "api key",
                "credentials",
                "credential",
                "what is offline",
                "what's offline",
                "why is butler offline",
                "intelligence offline",
                "keychain",
            )
        ):
            return {
                "mode": "secret_status",
                "tool_calls": [
                    {"tool": "secret_recovery_status", "args": {}},
                ],
            }

        if any(
            phrase in prompt_lower
            for phrase in (
                "owe a reply",
                "follow up",
                "follow-up",
                "relationship",
                "outreach",
                "who should i reply",
                "who do i owe",
            )
        ):
            return {
                "mode": "relationship_briefing",
                "tool_calls": [
                    {"tool": "relationship_get_briefing", "args": {"limit": limit}},
                ],
            }

        if any(phrase in prompt_lower for phrase in ("graph", "map", "network", "context map")):
            return {
                "mode": "context_map",
                "tool_calls": [
                    {
                        "tool": "context_graph_snapshot",
                        "args": {
                            "relationship_limit": min(limit, 6),
                            "pending_limit": 4,
                            "signal_limit": 5,
                            "pin_limit": 4,
                        },
                    }
                ],
            }

        if any(phrase in prompt_lower for phrase in ("journal", "recent activity", "what happened", "timeline")):
            return {
                "mode": "activity_feed",
                "tool_calls": [
                    {"tool": "context_activity_feed", "args": {"limit": max(limit, 8)}},
                ],
            }

        if any(phrase in prompt_lower for phrase in ("pending", "unclear", "uncertain", "needs review")):
            return {
                "mode": "pending_review",
                "tool_calls": [
                    {"tool": "list_pending_context", "args": {"limit": max(limit, 8)}},
                ],
            }

        return {
            "mode": "memory_search",
            "tool_calls": [
                {"tool": "butler_memory_search", "args": {"query": prompt, "limit": limit}},
            ],
        }

    def _summarize(
        self,
        *,
        mode: str,
        prompt: str,
        tool_results: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        primary = tool_results[0]["result"] if tool_results else {}
        if primary and not primary.get("ok", True):
            return (primary.get("error") or "The core agent run failed.", [])

        output = primary.get("output") if isinstance(primary, dict) else {}

        if mode == "secret_status":
            status = dict(output or {})
            missing = list(status.get("missing") or [])
            recoverable = list(status.get("recoverable_missing") or [])
            citations = [
                {
                    "ref": f"secret/{item.get('name')}",
                    "title": item.get("name"),
                    "subtitle": "ready" if item.get("ready") else ("recoverable from Maccy" if item.get("recoverable_from_maccy") else "missing"),
                    "similarity": None,
                }
                for item in list(status.get("statuses") or [])[:4]
            ]
            if not missing:
                return "Butler's main intelligence providers are online. Stored credentials are present for the current core set.", citations
            if recoverable:
                recoverable_text = ", ".join(recoverable)
                return f"Butler is missing {len(missing)} core credential(s). {recoverable_text} can be restored from Maccy now.", citations
            return f"Butler is missing {len(missing)} core credential(s), and none of them look recoverable from Maccy yet.", citations

        if mode == "secret_recovery":
            recovery = tool_results[1]["result"] if len(tool_results) > 1 else {}
            if recovery and not recovery.get("ok", True):
                approval_id = recovery.get("approval_request_id")
                if approval_id:
                    return (
                        f"Recovery is staged. Approve `rehydrate_missing_secrets` to restore missing credentials from Maccy. Approval id: {approval_id}.",
                        [],
                    )
                return (recovery.get("error") or "Secret recovery failed.", [])

            recovery_output = recovery.get("output") if isinstance(recovery, dict) else {}
            restored = list((recovery_output or {}).get("restored") or [])
            already_ready = list((recovery_output or {}).get("already_ready") or [])
            still_missing = list((recovery_output or {}).get("still_missing") or [])
            if restored and not still_missing:
                restored_text = ", ".join(restored)
                return f"Butler is back online. Restored {restored_text} from Maccy into Keychain.", []
            if restored:
                return (
                    f"Recovered {', '.join(restored)}, but Butler is still missing {', '.join(still_missing)}.",
                    [],
                )
            if still_missing:
                return (
                    f"Butler still cannot recover {', '.join(still_missing)} from Maccy. Paste fresh keys on the Mac or save them explicitly.",
                    [],
                )
            if already_ready:
                return "Butler is online. Existing stored credentials were re-injected into the runtime.", []
            return "No missing intelligence secrets needed recovery.", []

        if mode == "relationship_briefing":
            priorities = list((output or {}).get("priority_followups") or [])
            citations = [
                {
                    "ref": item.get("person_ref"),
                    "title": item.get("full_name") or item.get("person_name"),
                    "subtitle": item.get("next_action"),
                    "similarity": None,
                }
                for item in priorities[:3]
            ]
            summary = (output or {}).get("briefing_text") or "No relationship briefing is available yet."
            return summary, citations

        if mode == "context_map":
            stats = dict((output or {}).get("stats") or {})
            spotlight = (output or {}).get("spotlight") or "The context map is ready."
            summary = (
                f"{spotlight} "
                f"{stats.get('relationships', 0)} live relationship nodes, "
                f"{stats.get('linked_entities', 0)} linked entities, "
                f"{stats.get('pending', 0)} pending review."
            )
            return summary, []

        if mode == "activity_feed":
            items = list(output or [])
            citations = [
                {
                    "ref": item.get("ref"),
                    "title": item.get("title"),
                    "subtitle": item.get("summary"),
                    "similarity": None,
                }
                for item in items[:3]
            ]
            if not items:
                return "The journal is quiet right now. Capture or log something to build the timeline.", citations
            headline = items[0].get("title") or "Recent activity"
            summary = f"Latest signal: {headline}. Showing the most recent context activity in LIFO order."
            return summary, citations

        if mode == "pending_review":
            items = list(output or [])
            citations = [
                {
                    "ref": f"pending/{item.get('id')}",
                    "title": item.get("title"),
                    "subtitle": item.get("capture_kind"),
                    "similarity": None,
                }
                for item in items[:3]
            ]
            if not items:
                return "Nothing is sitting in pending review right now.", citations
            summary = f"{len(items)} pending item{'s' if len(items) != 1 else ''} need review. Start with {items[0].get('title') or 'the newest item'}."
            return summary, citations

        results = list((output or {}).get("results") or [])
        citations = [
            {
                "ref": item.get("ref"),
                "title": item.get("title") or item.get("ref"),
                "subtitle": item.get("text"),
                "similarity": item.get("similarity"),
            }
            for item in results[:3]
        ]
        if not results:
            return (
                "I did not find a strong memory match yet. Try a more specific prompt or index more context first.",
                citations,
            )

        top = results[0]
        title = top.get("title") or top.get("ref") or "Top match"
        similarity = top.get("similarity")
        similarity_text = f" ({int(float(similarity) * 100)}% match)" if similarity is not None else ""
        summary = f"Best memory match for '{prompt}' is {title}{similarity_text}."
        return summary, citations
