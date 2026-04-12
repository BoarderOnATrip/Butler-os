#!/usr/bin/env python3
"""
Small CLI for the open-source Butler runtime.
"""
from __future__ import annotations

import argparse
import json
import time

from runtime.engine import ButlerRuntime


def _print(data) -> None:
    print(json.dumps(data, indent=2, default=str))


_TERMINAL_SWARM_STATUSES = {"completed", "failed", "blocked", "awaiting_oversight"}


def _swarm_observation(run) -> dict:
    return {
        "run_id": run.id,
        "status": run.status,
        "summary": run.summary,
        "updated_at": run.updated_at,
        "agents": [
            {
                "agent_id": state.agent_id,
                "title": state.title,
                "status": state.status,
                "result_summary": state.result_summary,
                "error": state.error,
            }
            for state in run.agent_states
        ],
    }


def _watch_swarm_run(
    runtime: ButlerRuntime,
    run_id: str,
    *,
    interval_seconds: float = 1.0,
    timeout_seconds: float = 60.0,
    show_report: bool = False,
) -> dict:
    deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None
    last_signature = ""
    observations: list[dict] = []

    while True:
        run = runtime.get_swarm_run(run_id)
        if not run:
            return {"error": "not found", "run_id": run_id, "observations": observations}

        observation = _swarm_observation(run)
        signature = json.dumps(observation, sort_keys=True, default=str)
        if signature != last_signature:
            print(json.dumps({"watch": observation}, indent=2, default=str))
            observations.append(observation)
            last_signature = signature

        if run.status in _TERMINAL_SWARM_STATUSES:
            return {
                "timed_out": False,
                "run": run.to_dict(),
                "report": runtime.get_swarm_run_report(run.id) if show_report else None,
                "observations": observations,
            }

        if deadline is not None and time.monotonic() >= deadline:
            return {
                "timed_out": True,
                "run": run.to_dict(),
                "report": runtime.get_swarm_run_report(run.id) if show_report and run.report_path else None,
                "observations": observations,
            }

        time.sleep(max(0.1, interval_seconds))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="aiButler runtime CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    create_session = sub.add_parser("session-create")
    create_session.add_argument("--user-id", default="local-user")
    create_session.add_argument("--surface", default="local")
    create_session.add_argument("--metadata", default="{}")

    list_sessions = sub.add_parser("session-list")
    list_sessions.add_argument("--limit", type=int, default=20)

    close_session = sub.add_parser("session-close")
    close_session.add_argument("session_id")

    permission_get = sub.add_parser("permission-get")
    permission_get.add_argument("session_id")

    permission_set = sub.add_parser("permission-set")
    permission_set.add_argument("session_id")
    permission_set.add_argument("mode", choices=["locked", "standard", "full-access"])
    permission_set.add_argument("--actor", default="user")
    permission_set.add_argument("--note", default="")
    permission_set.add_argument("--duration-minutes", type=int)
    permission_set.add_argument("--arm-token")

    full_access_arm = sub.add_parser("full-access-arm")
    full_access_arm.add_argument("--actor", default="user")
    full_access_arm.add_argument("--note", default="")
    full_access_arm.add_argument("--duration-minutes", type=int)

    create_task = sub.add_parser("task-create")
    create_task.add_argument("session_id")
    create_task.add_argument("title")
    create_task.add_argument("--kind", default="general")
    create_task.add_argument("--payload", default="{}")

    list_tasks = sub.add_parser("task-list")
    list_tasks.add_argument("--session-id")
    list_tasks.add_argument("--limit", type=int, default=50)

    memory_add = sub.add_parser("memory-add")
    memory_add.add_argument("session_id")
    memory_add.add_argument("kind")
    memory_add.add_argument("content")
    memory_add.add_argument("--tags", default="")
    memory_add.add_argument("--metadata", default="{}")

    memory_list = sub.add_parser("memory-list")
    memory_list.add_argument("--session-id")
    memory_list.add_argument("--limit", type=int, default=50)

    approval_list = sub.add_parser("approval-list")
    approval_list.add_argument("--session-id")
    approval_list.add_argument("--status")

    approval_resolve = sub.add_parser("approval-resolve")
    approval_resolve.add_argument("approval_id")
    approval_resolve.add_argument("--approved", action="store_true")
    approval_resolve.add_argument("--actor", default="user")
    approval_resolve.add_argument("--note", default="")

    tool_list = sub.add_parser("tool-list")

    tool_run = sub.add_parser("tool-run")
    tool_run.add_argument("--session-id", default="cli-session")
    tool_run.add_argument("--tool-name", required=True)
    tool_run.add_argument("--args", default="{}")
    tool_run.add_argument("--approved", action="store_true")
    tool_run.add_argument("--actor", default="runtime")
    tool_run.add_argument("--note", default="")

    agentic_run = sub.add_parser("agentic-run")
    agentic_run.add_argument("--objective", required=True)
    agentic_run.add_argument("--max-iterations", type=int, default=8)

    core_agent_run = sub.add_parser("core-agent-run")
    core_agent_run.add_argument("--prompt", required=True)
    core_agent_run.add_argument("--limit", type=int, default=5)

    receipt_list = sub.add_parser("receipt-list")
    receipt_list.add_argument("--session-id")
    receipt_list.add_argument("--limit", type=int, default=50)

    security_events = sub.add_parser("security-events")
    security_events.add_argument("--limit", type=int, default=50)

    context_init = sub.add_parser("context-init")

    context_event_add = sub.add_parser("context-event-add")
    context_event_add.add_argument("--event-type", required=True)
    context_event_add.add_argument("--summary", required=True)
    context_event_add.add_argument("--payload", default="{}")
    context_event_add.add_argument("--source", default="{}")
    context_event_add.add_argument("--entity-refs", default="")
    context_event_add.add_argument("--session-id")

    context_event_list = sub.add_parser("context-event-list")
    context_event_list.add_argument("--limit", type=int, default=50)

    context_sheet_create = sub.add_parser("context-sheet-create")
    context_sheet_create.add_argument("kind")
    context_sheet_create.add_argument("name")
    context_sheet_create.add_argument("--slug")
    context_sheet_create.add_argument("--body", default="")
    context_sheet_create.add_argument("--links", default="")
    context_sheet_create.add_argument("--source-refs", default="")
    context_sheet_create.add_argument("--metadata", default="{}")
    context_sheet_create.add_argument("--status", default="active")
    context_sheet_create.add_argument("--confidence", type=float, default=1.0)

    context_sheet_list = sub.add_parser("context-sheet-list")
    context_sheet_list.add_argument("--kind")
    context_sheet_list.add_argument("--limit", type=int, default=50)

    context_pending_add = sub.add_parser("context-pending-add")
    context_pending_add.add_argument("capture_kind")
    context_pending_add.add_argument("title")
    context_pending_add.add_argument("--content", default="")
    context_pending_add.add_argument("--metadata", default="{}")
    context_pending_add.add_argument("--source", default="{}")
    context_pending_add.add_argument("--confidence", type=float, default=0.0)
    context_pending_add.add_argument("--session-id")

    context_pending_list = sub.add_parser("context-pending-list")
    context_pending_list.add_argument("--limit", type=int, default=50)

    swarm_contract_create = sub.add_parser("swarm-contract-create")
    swarm_contract_create.add_argument("--title", required=True)
    swarm_contract_create.add_argument("--objective", required=True)
    swarm_contract_create.add_argument("--template", default="")
    swarm_contract_create.add_argument("--room-id", default="")
    swarm_contract_create.add_argument("--room-kind", default="project")
    swarm_contract_create.add_argument("--target", default="")
    swarm_contract_create.add_argument("--launcher", default="")
    swarm_contract_create.add_argument("--agents-json", default="")
    swarm_contract_create.add_argument("--deployment-policy", default="")
    swarm_contract_create.add_argument("--metadata", default="{}")
    swarm_contract_create.add_argument("--source-refs", default="")
    swarm_contract_create.add_argument("--created-by", default="cli")
    swarm_contract_create.add_argument("--session-id")

    swarm_start = sub.add_parser("swarm-start")
    swarm_start.add_argument("--title", required=True)
    swarm_start.add_argument("--objective", required=True)
    swarm_start.add_argument("--template", default="")
    swarm_start.add_argument("--room-id", default="")
    swarm_start.add_argument("--room-kind", default="project")
    swarm_start.add_argument("--target", default="")
    swarm_start.add_argument("--launcher", default="")
    swarm_start.add_argument("--agents-json", default="")
    swarm_start.add_argument("--deployment-policy", default="")
    swarm_start.add_argument("--metadata", default="{}")
    swarm_start.add_argument("--source-refs", default="")
    swarm_start.add_argument("--created-by", default="cli")
    swarm_start.add_argument("--session-id")
    swarm_start.add_argument("--vpn-ssh-target", default="")
    swarm_start.add_argument("--remote-workdir", default="")
    swarm_start.add_argument("--remote-python", default="python3")
    swarm_start.add_argument("--dry-run", action="store_true")
    swarm_start.add_argument("--watch", action="store_true")
    swarm_start.add_argument("--watch-interval", type=float, default=1.0)
    swarm_start.add_argument("--watch-timeout", type=float, default=60.0)
    swarm_start.add_argument("--show-report", action="store_true")

    swarm_contract_get = sub.add_parser("swarm-contract-get")
    swarm_contract_get.add_argument("contract_id")

    swarm_contract_list = sub.add_parser("swarm-contract-list")
    swarm_contract_list.add_argument("--room-id")
    swarm_contract_list.add_argument("--status")
    swarm_contract_list.add_argument("--limit", type=int, default=20)

    swarm_launch = sub.add_parser("swarm-launch")
    swarm_launch.add_argument("contract_id")
    swarm_launch.add_argument("--target")
    swarm_launch.add_argument("--launcher")
    swarm_launch.add_argument("--vpn-ssh-target", default="")
    swarm_launch.add_argument("--remote-workdir", default="")
    swarm_launch.add_argument("--remote-python", default="python3")
    swarm_launch.add_argument("--dry-run", action="store_true")
    swarm_launch.add_argument("--created-by", default="cli")
    swarm_launch.add_argument("--session-id")
    swarm_launch.add_argument("--watch", action="store_true")
    swarm_launch.add_argument("--watch-interval", type=float, default=1.0)
    swarm_launch.add_argument("--watch-timeout", type=float, default=60.0)
    swarm_launch.add_argument("--show-report", action="store_true")

    swarm_run_list = sub.add_parser("swarm-run-list")
    swarm_run_list.add_argument("--contract-id")
    swarm_run_list.add_argument("--room-id")
    swarm_run_list.add_argument("--status")
    swarm_run_list.add_argument("--limit", type=int, default=20)

    swarm_run_get = sub.add_parser("swarm-run-get")
    swarm_run_get.add_argument("run_id")

    swarm_run_report = sub.add_parser("swarm-run-report")
    swarm_run_report.add_argument("run_id")

    swarm_run_watch = sub.add_parser("swarm-run-watch")
    swarm_run_watch.add_argument("run_id")
    swarm_run_watch.add_argument("--interval", type=float, default=1.0)
    swarm_run_watch.add_argument("--timeout", type=float, default=60.0)
    swarm_run_watch.add_argument("--show-report", action="store_true")

    swarm_vpn_bootstrap = sub.add_parser("swarm-vpn-bootstrap")
    swarm_vpn_bootstrap.add_argument("--ssh-target", default="")
    swarm_vpn_bootstrap.add_argument("--remote-workdir", default="~/Butler-os/aibutler-core")
    swarm_vpn_bootstrap.add_argument("--repo-url", default="https://github.com/BoarderOnATrip/Butler-os.git")
    swarm_vpn_bootstrap.add_argument("--branch", default="main")
    swarm_vpn_bootstrap.add_argument("--remote-python", default="python3")
    swarm_vpn_bootstrap.add_argument("--execute", action="store_true")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    runtime = ButlerRuntime()

    if args.command == "session-create":
        result = runtime.create_session(
            user_id=args.user_id,
            surface=args.surface,
            metadata=json.loads(args.metadata),
        ).to_dict()
    elif args.command == "session-list":
        result = [session.to_dict() for session in runtime.list_sessions(limit=args.limit)]
    elif args.command == "session-close":
        session = runtime.close_session(args.session_id)
        result = session.to_dict() if session else {"error": "not found"}
    elif args.command == "permission-get":
        result = runtime.get_permission_state(args.session_id)
    elif args.command == "permission-set":
        try:
            session = runtime.set_permission_mode(
                args.session_id,
                args.mode,
                actor=args.actor,
                note=args.note,
                duration_minutes=args.duration_minutes,
                arm_token=args.arm_token,
            )
            result = session.to_dict() if session else {"error": "not found"}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
    elif args.command == "full-access-arm":
        result = runtime.arm_full_access(
            actor=args.actor,
            note=args.note,
            duration_minutes=args.duration_minutes,
        )
    elif args.command == "task-create":
        result = runtime.create_task(
            session_id=args.session_id,
            title=args.title,
            kind=args.kind,
            payload=json.loads(args.payload),
        ).to_dict()
    elif args.command == "task-list":
        result = [task.to_dict() for task in runtime.list_tasks(session_id=args.session_id, limit=args.limit)]
    elif args.command == "memory-add":
        tags = [tag for tag in args.tags.split(",") if tag]
        result = runtime.write_memory(
            session_id=args.session_id,
            kind=args.kind,
            content=args.content,
            tags=tags,
            metadata=json.loads(args.metadata),
        ).to_dict()
    elif args.command == "memory-list":
        result = [memory.to_dict() for memory in runtime.list_memories(session_id=args.session_id, limit=args.limit)]
    elif args.command == "approval-list":
        result = [approval.to_dict() for approval in runtime.list_approvals(session_id=args.session_id, status=args.status)]
    elif args.command == "approval-resolve":
        approval = runtime.resolve_approval(
            args.approval_id,
            approved=args.approved,
            actor=args.actor,
            note=args.note,
        )
        result = approval.to_dict() if approval else {"error": "not found"}
    elif args.command == "tool-list":
        result = [spec.to_dict() for spec in runtime.tool_specs.values()]
    elif args.command == "tool-run":
        session_id = args.session_id
        tool_name = args.tool_name
        session = runtime.get_or_create_session(session_id=session_id, user_id="local-user", surface="cli")
        result = runtime.execute_tool(
            session_id=session.id,
            tool_name=tool_name,
            args=json.loads(args.args),
            approved=args.approved,
            actor=args.actor,
            note=args.note,
        )
    elif args.command == "agentic-run":
        import asyncio
        from runtime.agentic import AgenticOrchestrator
        orchestrator = AgenticOrchestrator(runtime)
        result = asyncio.run(orchestrator.run(args.objective, args.max_iterations))
    elif args.command == "core-agent-run":
        from runtime.core_agent import ButlerCoreAgent

        agent = ButlerCoreAgent(runtime)
        result = agent.run(args.prompt, limit=args.limit)
    elif args.command == "receipt-list":
        result = [receipt.to_dict() for receipt in runtime.list_receipts(session_id=args.session_id, limit=args.limit)]
    elif args.command == "security-events":
        result = runtime.list_security_events(limit=args.limit)
    elif args.command == "context-init":
        result = runtime.init_context_repo()
    elif args.command == "context-event-add":
        entity_refs = [ref for ref in args.entity_refs.split(",") if ref]
        result = runtime.append_context_event(
            event_type=args.event_type,
            summary=args.summary,
            payload=json.loads(args.payload),
            source=json.loads(args.source),
            entity_refs=entity_refs,
            session_id=args.session_id,
        ).to_dict()
    elif args.command == "context-event-list":
        result = [event.to_dict() for event in runtime.list_context_events(limit=args.limit)]
    elif args.command == "context-sheet-create":
        links = [ref for ref in args.links.split(",") if ref]
        source_refs = [ref for ref in args.source_refs.split(",") if ref]
        result = runtime.create_context_sheet(
            kind=args.kind,
            name=args.name,
            slug=args.slug,
            body=args.body,
            links=links,
            source_refs=source_refs,
            metadata=json.loads(args.metadata),
            status=args.status,
            confidence=args.confidence,
        ).to_dict()
    elif args.command == "context-sheet-list":
        result = [sheet.to_dict() for sheet in runtime.list_context_sheets(kind=args.kind, limit=args.limit)]
    elif args.command == "context-pending-add":
        result = runtime.capture_pending_context(
            capture_kind=args.capture_kind,
            title=args.title,
            content=args.content,
            metadata=json.loads(args.metadata),
            source=json.loads(args.source),
            confidence=args.confidence,
            session_id=args.session_id,
        ).to_dict()
    elif args.command == "context-pending-list":
        result = [item.to_dict() for item in runtime.list_pending_context(limit=args.limit)]
    elif args.command == "swarm-contract-create":
        agents = json.loads(args.agents_json) if args.agents_json else None
        deployment_policy = json.loads(args.deployment_policy) if args.deployment_policy else None
        source_refs = [ref for ref in args.source_refs.split(",") if ref]
        result = runtime.create_swarm_contract(
            title=args.title,
            objective=args.objective,
            template=args.template,
            room_id=args.room_id or None,
            room_kind=args.room_kind,
            target=args.target,
            launcher=args.launcher,
            agents=agents,
            deployment_policy=deployment_policy,
            metadata=json.loads(args.metadata),
            source_refs=source_refs,
            created_by=args.created_by,
            session_id=args.session_id,
        ).to_dict()
    elif args.command == "swarm-start":
        agents = json.loads(args.agents_json) if args.agents_json else None
        deployment_policy = json.loads(args.deployment_policy) if args.deployment_policy else None
        source_refs = [ref for ref in args.source_refs.split(",") if ref]
        contract = runtime.create_swarm_contract(
            title=args.title,
            objective=args.objective,
            template=args.template,
            room_id=args.room_id or None,
            room_kind=args.room_kind,
            target=args.target,
            launcher=args.launcher,
            agents=agents,
            deployment_policy=deployment_policy,
            metadata=json.loads(args.metadata),
            source_refs=source_refs,
            created_by=args.created_by,
            session_id=args.session_id,
        )
        launch = runtime.launch_swarm_contract(
            contract.id,
            target=args.target or None,
            launcher=args.launcher or None,
            vpn_ssh_target=args.vpn_ssh_target,
            remote_workdir=args.remote_workdir,
            remote_python=args.remote_python,
            dry_run=args.dry_run,
            created_by=args.created_by,
            session_id=args.session_id,
        )
        result = launch
        if args.watch and launch.get("launch_ready") and launch.get("run", {}).get("run_id"):
            watch = _watch_swarm_run(
                runtime,
                launch["run"]["run_id"],
                interval_seconds=args.watch_interval,
                timeout_seconds=args.watch_timeout,
                show_report=args.show_report,
            )
            result = {
                **launch,
                "run": watch.get("run", launch.get("run")),
                "watch": watch,
            }
    elif args.command == "swarm-contract-get":
        contract = runtime.get_swarm_contract(args.contract_id)
        result = contract.to_dict() if contract else {"error": "not found"}
    elif args.command == "swarm-contract-list":
        result = [
            contract.to_dict()
            for contract in runtime.list_swarm_contracts(
                room_id=args.room_id,
                status=args.status,
                limit=args.limit,
            )
        ]
    elif args.command == "swarm-launch":
        result = runtime.launch_swarm_contract(
            args.contract_id,
            target=args.target,
            launcher=args.launcher,
            vpn_ssh_target=args.vpn_ssh_target,
            remote_workdir=args.remote_workdir,
            remote_python=args.remote_python,
            dry_run=args.dry_run,
            created_by=args.created_by,
            session_id=args.session_id,
        )
        if args.watch and result.get("launch_ready") and result.get("run", {}).get("run_id"):
            watch = _watch_swarm_run(
                runtime,
                result["run"]["run_id"],
                interval_seconds=args.watch_interval,
                timeout_seconds=args.watch_timeout,
                show_report=args.show_report,
            )
            result = {
                **result,
                "run": watch.get("run", result.get("run")),
                "watch": watch,
            }
    elif args.command == "swarm-run-list":
        result = [
            run.to_dict()
            for run in runtime.list_swarm_runs(
                contract_id=args.contract_id,
                room_id=args.room_id,
                status=args.status,
                limit=args.limit,
            )
        ]
    elif args.command == "swarm-run-get":
        run = runtime.get_swarm_run(args.run_id)
        result = run.to_dict() if run else {"error": "not found"}
    elif args.command == "swarm-run-report":
        report = runtime.get_swarm_run_report(args.run_id)
        result = report or {"error": "not found"}
    elif args.command == "swarm-run-watch":
        result = _watch_swarm_run(
            runtime,
            args.run_id,
            interval_seconds=args.interval,
            timeout_seconds=args.timeout,
            show_report=args.show_report,
        )
    elif args.command == "swarm-vpn-bootstrap":
        result = runtime.build_swarm_vpn_bootstrap(
            ssh_target=args.ssh_target,
            remote_workdir=args.remote_workdir,
            repo_url=args.repo_url,
            branch=args.branch,
            remote_python=args.remote_python,
            execute=args.execute,
        )
    else:
        result = {"error": f"Unknown command: {args.command}"}

    _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
