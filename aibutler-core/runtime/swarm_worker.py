#!/usr/bin/env python3
"""
Starter Butler swarm worker.

This is intentionally pragmatic:
  - load a persisted swarm contract/run
  - execute agent objectives in dependency order
  - use the existing Butler agentic loop as the first worker brain
  - persist lifecycle state, tasks, room draft snapshots, and continuity escalations
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import deque

from runtime.agentic import AgenticOrchestrator
from runtime.engine import ButlerRuntime
from runtime.models import utc_now


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a persisted Butler swarm contract")
    parser.add_argument("--contract-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runtime-dir", default="")
    parser.add_argument("--actor", default="swarm-worker")
    return parser


def _topological_order(contract) -> list:
    by_id = {agent.id: agent for agent in contract.agents}
    indegree: dict[str, int] = {agent.id: 0 for agent in contract.agents}
    adjacency: dict[str, list[str]] = {agent.id: [] for agent in contract.agents}
    for agent in contract.agents:
        for dep in agent.depends_on:
            if dep not in by_id:
                continue
            indegree[agent.id] += 1
            adjacency[dep].append(agent.id)

    queue = deque([agent_id for agent_id, degree in indegree.items() if degree == 0])
    ordered_ids: list[str] = []
    while queue:
        current = queue.popleft()
        ordered_ids.append(current)
        for child in adjacency[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(ordered_ids) != len(contract.agents):
        raise ValueError("Swarm contract contains a dependency cycle.")
    return [by_id[agent_id] for agent_id in ordered_ids]


def _finalize_run(
    runtime: ButlerRuntime,
    run_id: str,
    contract,
    *,
    actor: str,
    status: str,
    note: str = "",
    session_id: str | None = None,
) -> None:
    completed_at = utc_now()
    final_summary = note.strip() or f"Swarm {status} for {contract.title}"
    runtime.update_swarm_run(
        run_id,
        status=status,
        completed_at=completed_at,
        summary=final_summary,
        metadata_patch={"final_note": final_summary, "completed_by": actor},
    )
    run = runtime.get_swarm_run(run_id)
    artifact_id = ""
    if run:
        report_path, artifact = runtime._persist_swarm_report(run, session_id=session_id)
        artifact_id = artifact.id if artifact else ""
        runtime.update_swarm_run(
            run_id,
            report_path=report_path,
            metadata_patch={"report_artifact_id": artifact_id} if artifact_id else {},
        )
    if status != "completed":
        runtime.create_continuity_packet(
            kind="swarm_status",
            title=f"Swarm needs oversight: {contract.title}",
            content=final_summary,
            source_device="swarm-worker",
            target_device="desktop",
            source_surface="swarm",
            room_id=contract.room_id,
            artifact_id=artifact_id or None,
            refs=[f"swarm/contracts/{contract.id}", f"rooms/{contract.room_id}", f"swarm/runs/{run_id}"],
            metadata={"contract_id": contract.id, "run_id": run_id, "status": status},
        )


def _summarize_agent_result(result: dict) -> str:
    review_summary = ""
    history = result.get("history", []) or []
    if history:
        last_review = history[-1].get("review", {}) or {}
        review_summary = str(last_review.get("summary", "")).strip()
    if review_summary:
        return review_summary[:280]

    final_result = result.get("final_result")
    if final_result:
        rendered = json.dumps(final_result, default=str)
        return rendered[:280]

    status = result.get("status", "unknown")
    iterations = result.get("iterations", 0)
    return f"status={status}; iterations={iterations}"


def _default_tool_args(contract, agent, tool_name: str) -> dict:
    objective = contract.objective.strip() or agent.objective.strip() or contract.title
    launcher_config = dict(contract.deployment_policy.launcher_config or {})
    if tool_name == "butler_memory_search":
        return {"query": objective, "limit": 6}
    if tool_name == "context_graph_snapshot":
        return {"relationship_limit": 8 if contract.template == "relationship" else 6, "pending_limit": 6, "signal_limit": 5, "pin_limit": 4}
    if tool_name == "context_activity_feed":
        return {"limit": 8}
    if tool_name == "list_pending_context":
        return {"limit": 8}
    if tool_name == "relationship_get_briefing":
        return {"limit": 5}
    if tool_name == "relationship_list_followups":
        return {"limit": 8}
    if tool_name == "build_swarm_vpn_bootstrap":
        return {
            "ssh_target": launcher_config.get("vpn_ssh_target", ""),
            "remote_workdir": launcher_config.get("remote_workdir", "~/Butler-os/aibutler-core"),
            "repo_url": launcher_config.get("repo_url", "https://github.com/BoarderOnATrip/Butler-os.git"),
            "branch": launcher_config.get("branch", "main"),
            "remote_python": launcher_config.get("remote_python", "python3"),
            "execute": False,
        }
    return {}


def _tool_result_preview(tool_name: str, tool_result: dict) -> str:
    if not tool_result.get("ok", True):
        approval_id = tool_result.get("approval_request_id")
        if approval_id:
            return f"{tool_name} needs approval ({approval_id})"
        return f"{tool_name} failed: {tool_result.get('error') or 'unknown error'}"

    output = tool_result.get("output")
    if tool_name == "context_graph_snapshot" and isinstance(output, dict):
        stats = dict(output.get("stats") or {})
        spotlight = (output.get("spotlight") or "Context snapshot ready.").strip()
        return f"{spotlight} relationships={stats.get('relationships', 0)}, pending={stats.get('pending', 0)}"
    if tool_name == "context_activity_feed" and isinstance(output, list):
        if not output:
            return "Recent activity is quiet."
        lead = output[0]
        return f"{len(output)} recent activity item(s); latest: {lead.get('title') or lead.get('summary') or 'activity'}"
    if tool_name == "list_pending_context" and isinstance(output, list):
        if not output:
            return "No pending review items."
        return f"{len(output)} pending review item(s); newest: {output[0].get('title') or 'pending'}"
    if tool_name == "relationship_get_briefing" and isinstance(output, dict):
        return (output.get("briefing_text") or f"{len(output.get('priority_followups') or [])} priority follow-up(s) ready.").strip()[:240]
    if tool_name == "relationship_list_followups":
        items = list(output or []) if isinstance(output, list) else list((output or {}).get("items") or [])
        if not items:
            return "No relationship follow-ups due."
        lead = items[0]
        return f"{len(items)} follow-up(s); top: {lead.get('full_name') or lead.get('person_name') or 'unknown'}"
    if tool_name == "butler_memory_search" and isinstance(output, dict):
        if output.get("skipped"):
            return output.get("summary") or "Semantic recall skipped because the local memory index is cold."
        results = list(output.get("results") or [])
        if not results:
            return "No strong Butler memory matches."
        top = results[0]
        return f"Top memory match: {top.get('title') or top.get('ref') or 'unknown'}"
    if tool_name == "secret_recovery_status" and isinstance(output, dict):
        missing = list(output.get("missing") or [])
        recoverable = list(output.get("recoverable_missing") or [])
        if not missing:
            return "Secrets look online."
        if recoverable:
            return f"Missing secrets: {', '.join(missing)}; recoverable: {', '.join(recoverable)}"
        return f"Missing secrets: {', '.join(missing)}"
    if tool_name == "openclaw_status" and isinstance(output, dict):
        gateway = dict(output.get("gateway") or {})
        mode = output.get("mode") or "unknown"
        return f"OpenClaw installed={bool(output.get('openclaw_installed'))}; mode={mode}; gateway_running={bool(gateway.get('running'))}"
    if tool_name == "rtk_status" and isinstance(output, dict):
        return f"RTK installed={bool(output.get('rtk_installed'))}; plugin_installed={bool(output.get('plugin_installed'))}"
    if tool_name == "build_swarm_vpn_bootstrap" and isinstance(output, dict):
        return f"VPN bootstrap ready for {output.get('remote_workdir') or '~'}"

    rendered = json.dumps(output, default=str)
    return rendered[:240]


def _execute_agent_tool_hints(runtime: ButlerRuntime, session_id: str, contract, agent) -> list[dict]:
    tool_results: list[dict] = []
    memory_ready: bool | None = None
    for tool_name in agent.tool_hints:
        args = _default_tool_args(contract, agent, tool_name)
        try:
            if tool_name == "butler_memory_search":
                if memory_ready is None:
                    status = runtime.execute_tool(
                        session_id=session_id,
                        tool_name="butler_memory_status",
                        args={},
                        actor="swarm-worker",
                        note="Swarm worker checked semantic memory readiness before search",
                    )
                    output = status.get("output") or {}
                    memory_ready = bool(status.get("ok")) and int(output.get("total_drawers", 0) or 0) > 0
                if not memory_ready:
                    tool_results.append(
                        {
                            "tool": tool_name,
                            "args": args,
                            "result": {
                                "ok": True,
                                "output": {
                                    "skipped": True,
                                    "reason": "semantic_memory_cold",
                                    "summary": "Semantic recall skipped because the local memory index is cold.",
                                },
                                "error": None,
                            },
                        }
                    )
                    continue
            result = runtime.execute_tool(
                session_id=session_id,
                tool_name=tool_name,
                args=args,
                actor="swarm-worker",
                note=f"Swarm worker executed hinted tool {tool_name}",
            )
            tool_results.append({"tool": tool_name, "args": args, "result": result})
        except Exception as exc:
            tool_results.append({"tool": tool_name, "args": args, "error": str(exc)})
    return tool_results


def _summarize_tool_execution(tool_results: list[dict]) -> str:
    previews: list[str] = []
    for item in tool_results:
        if item.get("error"):
            previews.append(f"{item['tool']} failed: {item['error']}")
            continue
        previews.append(_tool_result_preview(item["tool"], item.get("result") or {}))
    return "; ".join(previews[:3])[:280] if previews else "No tool output recorded."


def _compact_tool_results(tool_results: list[dict]) -> list[dict]:
    compacted: list[dict] = []
    for item in tool_results:
        tool_name = item.get("tool", "")
        if item.get("error"):
            compacted.append(
                {
                    "tool": tool_name,
                    "args": dict(item.get("args") or {}),
                    "ok": False,
                    "preview": f"{tool_name} failed: {item['error']}",
                    "error": item["error"],
                }
            )
            continue

        result = dict(item.get("result") or {})
        compacted.append(
            {
                "tool": tool_name,
                "args": dict(item.get("args") or {}),
                "ok": bool(result.get("ok")),
                "preview": _tool_result_preview(tool_name, result),
                "error": result.get("error"),
                "approval_request_id": result.get("approval_request_id"),
            }
        )
    return compacted


def main() -> int:
    args = _build_parser().parse_args()
    runtime = ButlerRuntime(args.runtime_dir) if args.runtime_dir else ButlerRuntime()
    contract = runtime.get_swarm_contract(args.contract_id)
    run = runtime.get_swarm_run(args.run_id)
    if not contract:
        raise SystemExit(f"Unknown swarm contract: {args.contract_id}")
    if not run:
        raise SystemExit(f"Unknown swarm run: {args.run_id}")

    session = runtime.get_or_create_session(
        session_id=f"swarm-{run.id}",
        user_id="swarm-runner",
        surface="swarm-worker",
        metadata={"contract_id": contract.id, "run_id": run.id, "room_id": contract.room_id},
    )
    runtime.update_swarm_run(
        run.id,
        status="running",
        pid=None,
        launched_at=run.launched_at or utc_now(),
        metadata_patch={"worker_started_at": utc_now(), "actor": args.actor},
        session_id=session.id,
    )

    finalized = False
    try:
        ordered_agents = _topological_order(contract)
    except Exception as exc:
        _finalize_run(runtime, run.id, contract, actor=args.actor, status="failed", note=str(exc), session_id=session.id)
        return 1

    try:
        orchestrator = AgenticOrchestrator(runtime)
        final_status = "completed"
        final_note = ""

        for agent in ordered_agents:
            dependency_states = {
                state.agent_id: state.status
                for state in (runtime.get_swarm_run(run.id) or run).agent_states
            }
            unmet = [dep for dep in agent.depends_on if dependency_states.get(dep) not in {"completed"}]
            if unmet:
                runtime.update_swarm_agent_state(
                    run.id,
                    agent.id,
                    status="blocked",
                    error=f"Waiting on dependencies: {', '.join(unmet)}",
                    metadata_patch={"blocked_by": unmet},
                    session_id=session.id,
                )
                final_status = "blocked"
                final_note = f"{agent.title} is blocked by unresolved dependencies."
                break

            task = runtime.create_task(
                session.id,
                f"{contract.title} · {agent.title}",
                kind="swarm_agent",
                payload={
                    "contract_id": contract.id,
                    "run_id": run.id,
                    "room_id": contract.room_id,
                    "agent_id": agent.id,
                    "role": agent.role,
                    "objective": agent.objective,
                },
            )
            runtime.update_task(task.id, status="running")
            runtime.update_swarm_agent_state(
                run.id,
                agent.id,
                status="running",
                task_id=task.id,
                started_at=utc_now(),
                session_id=session.id,
            )

            try:
                tool_results = _execute_agent_tool_hints(runtime, session.id, contract, agent)
                successful_tool_results = [
                    item for item in tool_results if item.get("result", {}).get("ok", False)
                ]
                if successful_tool_results:
                    result_summary = _summarize_tool_execution(tool_results)
                    compact_tool_results = _compact_tool_results(tool_results)
                    agent_payload = {
                        "status": "complete",
                        "mode": "tool_hints",
                        "tool_results": compact_tool_results,
                        "summary": result_summary,
                    }
                    runtime.update_task(task.id, status="completed", result=agent_payload)
                    runtime.save_draft_version(
                        contract.room_id,
                        payload={
                            "contract_id": contract.id,
                            "run_id": run.id,
                            "template": contract.template,
                            "agent": {
                                "id": agent.id,
                                "title": agent.title,
                                "role": agent.role,
                            },
                            "summary": result_summary,
                            "tool_results": compact_tool_results,
                        },
                        state_kind="swarm_agent_output",
                        metadata={
                            "swarm_contract_id": contract.id,
                            "swarm_run_id": run.id,
                            "agent_id": agent.id,
                        },
                        created_by="swarm-worker",
                        session_id=session.id,
                    )
                    runtime.update_swarm_agent_state(
                        run.id,
                        agent.id,
                        status="completed",
                        result_summary=result_summary,
                        completed_at=utc_now(),
                        metadata_patch={
                            "execution_mode": "tool_hints",
                            "tool_count": len(compact_tool_results),
                            "tool_results": compact_tool_results,
                        },
                        session_id=session.id,
                    )
                else:
                    result = asyncio.run(orchestrator.run(agent.objective, max_iterations=agent.max_iterations))
                    result_summary = _summarize_agent_result(result)
                    result_metadata = {
                        "history_length": len(result.get("history", [])),
                        "iterations": result.get("iterations", 0),
                        "result_status": result.get("status", "unknown"),
                        "execution_mode": "agentic_fallback",
                    }
                    if result.get("status") == "complete":
                        runtime.update_task(task.id, status="completed", result=result)
                        runtime.update_swarm_agent_state(
                            run.id,
                            agent.id,
                            status="completed",
                            result_summary=result_summary,
                            completed_at=utc_now(),
                            metadata_patch=result_metadata,
                            session_id=session.id,
                        )
                    else:
                        runtime.update_task(task.id, status="max_iterations", result=result)
                        runtime.update_swarm_agent_state(
                            run.id,
                            agent.id,
                            status="awaiting_oversight",
                            result_summary=result_summary,
                            completed_at=utc_now(),
                            metadata_patch=result_metadata,
                            session_id=session.id,
                        )
                        final_status = "awaiting_oversight"
                        final_note = f"{agent.title} reached max iterations and needs human review. {result_summary}"
                        break
            except Exception as exc:
                runtime.update_task(task.id, status="failed", error=str(exc))
                runtime.update_swarm_agent_state(
                    run.id,
                    agent.id,
                    status="failed",
                    error=str(exc),
                    completed_at=utc_now(),
                    session_id=session.id,
                )
                final_status = "failed"
                final_note = f"{agent.title} failed: {exc}"
                break

        if final_status == "completed":
            completed_run = runtime.get_swarm_run(run.id)
            if completed_run:
                agent_summaries = [state.result_summary for state in completed_run.agent_states if state.result_summary]
                if agent_summaries:
                    final_note = " | ".join(agent_summaries[:3])

        _finalize_run(runtime, run.id, contract, actor=args.actor, status=final_status, note=final_note, session_id=session.id)
        finalized = True
        return 0 if final_status == "completed" else 1
    except Exception as exc:
        if not finalized:
            try:
                _finalize_run(
                    runtime,
                    run.id,
                    contract,
                    actor=args.actor,
                    status="failed",
                    note=f"Unhandled worker failure: {exc}",
                    session_id=session.id,
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
