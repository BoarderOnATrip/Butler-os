#!/usr/bin/env python3
"""
aiButler swarm tools.

These are the first user-facing wrappers around Butler's persisted swarm
deployment contract and run launcher.
"""
from __future__ import annotations

from typing import Any


def _get_runtime():
    from runtime.engine import get_default_runtime

    return get_default_runtime()


def create_swarm_contract(
    title: str,
    objective: str,
    template: str = "",
    room_id: str = "",
    room_kind: str = "project",
    target: str = "local_desktop",
    launcher: str = "desktop",
    agents: list[dict[str, Any]] | None = None,
    deployment_policy: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
    created_by: str = "tool",
    session_id: str = "",
) -> dict:
    runtime = _get_runtime()
    contract = runtime.create_swarm_contract(
        title=title,
        objective=objective,
        template=template,
        room_id=room_id or None,
        room_kind=room_kind,
        target=target,
        launcher=launcher,
        agents=agents,
        deployment_policy=deployment_policy,
        metadata=metadata,
        source_refs=source_refs,
        created_by=created_by,
        session_id=session_id or None,
    )
    return {"ok": True, "output": contract.to_dict(), "error": None}


def get_swarm_contract(contract_id: str) -> dict:
    runtime = _get_runtime()
    contract = runtime.get_swarm_contract(contract_id)
    if not contract:
        return {"ok": False, "output": None, "error": "not found"}
    return {"ok": True, "output": contract.to_dict(), "error": None}


def list_swarm_contracts(
    room_id: str = "",
    status: str = "",
    limit: int = 20,
) -> dict:
    runtime = _get_runtime()
    contracts = runtime.list_swarm_contracts(
        room_id=room_id or None,
        status=status or None,
        limit=limit,
    )
    return {"ok": True, "output": [contract.to_dict() for contract in contracts], "error": None}


def launch_swarm_contract(
    contract_id: str,
    target: str = "",
    launcher: str = "",
    vpn_ssh_target: str = "",
    remote_workdir: str = "",
    remote_python: str = "python3",
    dry_run: bool = False,
    created_by: str = "tool",
    session_id: str = "",
) -> dict:
    runtime = _get_runtime()
    output = runtime.launch_swarm_contract(
        contract_id,
        target=target or None,
        launcher=launcher or None,
        vpn_ssh_target=vpn_ssh_target,
        remote_workdir=remote_workdir,
        remote_python=remote_python,
        dry_run=dry_run,
        created_by=created_by,
        session_id=session_id or None,
    )
    return {"ok": True, "output": output, "error": None}


def get_swarm_run(run_id: str) -> dict:
    runtime = _get_runtime()
    run = runtime.get_swarm_run(run_id)
    if not run:
        return {"ok": False, "output": None, "error": "not found"}
    return {"ok": True, "output": run.to_dict(), "error": None}


def list_swarm_runs(
    contract_id: str = "",
    room_id: str = "",
    status: str = "",
    limit: int = 20,
) -> dict:
    runtime = _get_runtime()
    runs = runtime.list_swarm_runs(
        contract_id=contract_id or None,
        room_id=room_id or None,
        status=status or None,
        limit=limit,
    )
    return {"ok": True, "output": [run.to_dict() for run in runs], "error": None}


def get_swarm_run_report(run_id: str) -> dict:
    runtime = _get_runtime()
    report = runtime.get_swarm_run_report(run_id)
    if not report:
        return {"ok": False, "output": None, "error": "not found"}
    return {"ok": True, "output": report, "error": None}


def build_swarm_vpn_bootstrap(
    ssh_target: str = "",
    remote_workdir: str = "~/Butler-os/aibutler-core",
    repo_url: str = "https://github.com/BoarderOnATrip/Butler-os.git",
    branch: str = "main",
    remote_python: str = "python3",
    execute: bool = False,
) -> dict:
    runtime = _get_runtime()
    output = runtime.build_swarm_vpn_bootstrap(
        ssh_target=ssh_target,
        remote_workdir=remote_workdir,
        repo_url=repo_url,
        branch=branch,
        remote_python=remote_python,
        execute=execute,
    )
    return {"ok": True, "output": output, "error": None}


TOOLS = {
    "create_swarm_contract": {
        "fn": create_swarm_contract,
        "description": "Create a persisted Butler swarm deployment contract bound to a canonical room.",
        "params": {
            "title": "str",
            "objective": "str",
            "template": "str=",
            "room_id": "str=",
            "room_kind": "str=project",
            "target": "str=local_desktop",
            "launcher": "str=desktop",
            "agents": "list[dict]=",
            "deployment_policy": "dict=",
            "metadata": "dict=",
            "source_refs": "list[str]=",
            "created_by": "str=tool",
            "session_id": "str=",
        },
    },
    "get_swarm_contract": {
        "fn": get_swarm_contract,
        "description": "Fetch one persisted Butler swarm contract.",
        "params": {
            "contract_id": "str",
        },
    },
    "list_swarm_contracts": {
        "fn": list_swarm_contracts,
        "description": "List persisted Butler swarm contracts.",
        "params": {
            "room_id": "str=",
            "status": "str=",
            "limit": "int=20",
        },
    },
    "launch_swarm_contract": {
        "fn": launch_swarm_contract,
        "description": "Launch a persisted swarm contract locally or through a VPN SSH target.",
        "params": {
            "contract_id": "str",
            "target": "str=",
            "launcher": "str=",
            "vpn_ssh_target": "str=",
            "remote_workdir": "str=",
            "remote_python": "str=python3",
            "dry_run": "bool=False",
            "created_by": "str=tool",
            "session_id": "str=",
        },
    },
    "get_swarm_run": {
        "fn": get_swarm_run,
        "description": "Fetch one persisted Butler swarm run.",
        "params": {
            "run_id": "str",
        },
    },
    "list_swarm_runs": {
        "fn": list_swarm_runs,
        "description": "List persisted Butler swarm runs and their statuses.",
        "params": {
            "contract_id": "str=",
            "room_id": "str=",
            "status": "str=",
            "limit": "int=20",
        },
    },
    "get_swarm_run_report": {
        "fn": get_swarm_run_report,
        "description": "Fetch the human-readable swarm report for a completed or staged run.",
        "params": {
            "run_id": "str",
        },
    },
    "build_swarm_vpn_bootstrap": {
        "fn": build_swarm_vpn_bootstrap,
        "description": "Generate or execute a VPN worker bootstrap script for Butler swarm runs.",
        "params": {
            "ssh_target": "str=",
            "remote_workdir": "str=~/Butler-os/aibutler-core",
            "repo_url": "str=https://github.com/BoarderOnATrip/Butler-os.git",
            "branch": "str=main",
            "remote_python": "str=python3",
            "execute": "bool=False",
        },
    },
}
