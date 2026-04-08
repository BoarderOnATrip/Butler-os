#!/usr/bin/env python3
"""
aiButler Desktop Bridge Server

Secure HTTP bridge that lets the mobile app proxy tool calls
to the desktop runtime.

Security:
  - Binds to localhost by default
  - Requires a pairing token for privileged routes
  - Blocks remote full-access elevation
  - All computer_use tools still require AIBUTLER_ENABLE_COMPUTER_USE=1
  - Approval-first policy enforced by the runtime engine

Start:
  cd bridge
  pip install -r requirements.txt
  python server.py
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import sys
import asyncio
from pathlib import Path
from typing import Annotated

# Add aibutler-core to sys.path so runtime/tools are importable.
# Pylance can't resolve dynamic sys.path inserts — that's expected.
_CORE = Path(__file__).parent.parent / "aibutler-core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from fastapi import Depends, FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
import uvicorn  # noqa: E402

from runtime.engine import get_default_runtime  # type: ignore[import]  # noqa: E402

app = FastAPI(title="aiButler Bridge", version="0.2.0")

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "AIBUTLER_BRIDGE_ALLOWED_ORIGINS",
        "http://localhost,http://127.0.0.1",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-AIBUTLER-Token"],
)

runtime = get_default_runtime()
SESSION_ID = os.environ.get("AIBUTLER_BRIDGE_SESSION_ID", "bridge-session")
USER_ID = os.environ.get("AIBUTLER_USER_ID", "local-user")
BRIDGE_STATE_PATH = Path.home() / ".aibutler" / "bridge.json"


def _load_or_create_bridge_state() -> dict:
    if BRIDGE_STATE_PATH.exists():
        try:
            return json.loads(BRIDGE_STATE_PATH.read_text())
        except Exception:
            pass

    state = {
        "pairing_token": secrets.token_urlsafe(32),
    }
    BRIDGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BRIDGE_STATE_PATH.write_text(json.dumps(state, indent=2))
    return state


def _save_bridge_state(state: dict) -> None:
    BRIDGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BRIDGE_STATE_PATH.write_text(json.dumps(state, indent=2))


BRIDGE_STATE = _load_or_create_bridge_state()
LAN_ENABLED = os.environ.get("AIBUTLER_BRIDGE_ALLOW_LAN", os.environ.get("AIBUTLER_BRIDGE_LAN", "0")) == "1"


def _pairing_token() -> str:
    return BRIDGE_STATE["pairing_token"]


def _is_localhost(request: Request) -> bool:
    client = request.client.host if request.client else ""
    return client in {"127.0.0.1", "::1", "localhost"}


def _require_pairing_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_aibutler_token: Annotated[str | None, Header()] = None,
) -> None:
    if _is_localhost(request) and os.environ.get("AIBUTLER_BRIDGE_REQUIRE_LOCAL_TOKEN", "0") != "1":
        return

    raw_token = x_aibutler_token
    if raw_token is None and authorization:
        raw_token = authorization.removeprefix("Bearer ").strip()

    if not raw_token or not hmac.compare_digest(raw_token, _pairing_token()):
        raise HTTPException(
            status_code=401,
            detail="Bridge pairing token required. Pair your phone with the desktop token first.",
        )


def _get_session():
    return runtime.get_or_create_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        surface="mobile-bridge",
        metadata={"bridge": True, "lan_enabled": LAN_ENABLED, "trusted_local": False, "remote_surface": True},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Request / Response models
# ──────────────────────────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)


class AgenticRequest(BaseModel):
    objective: str
    max_iterations: int = 8


class CoreAgentRequest(BaseModel):
    prompt: str
    limit: int = 5


class ContextCaptureRequest(BaseModel):
    capture_kind: str
    title: str
    content: str = ""
    file_name: str = ""
    mime_type: str = ""
    data_base64: str = ""
    source_surface: str = ""
    source_device: str = ""
    source_app: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Heartbeat — mobile uses this to discover the desktop bridge."""
    return {
        "ok": True,
        "service": "aibutler-bridge",
        "version": "0.2.0",
        "pairing_required": True,
        "lan_enabled": LAN_ENABLED,
        "token_hint": f"{_pairing_token()[:6]}...{_pairing_token()[-4:]}",
    }


@app.get("/pairing")
def pairing_info(request: Request):
    """Expose pairing details to local desktop surfaces only."""
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Pairing details are only available on the local desktop.")

    return {
        "ok": True,
        "token": _pairing_token(),
        "state_path": str(BRIDGE_STATE_PATH),
        "lan_enabled": LAN_ENABLED,
        "authorization_header": "X-AIBUTLER-Token",
    }


@app.post("/pairing/regenerate")
def regenerate_pairing_token(request: Request):
    """Rotate the bridge token from the local desktop."""
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Pairing token rotation is local-only.")

    BRIDGE_STATE["pairing_token"] = secrets.token_urlsafe(32)
    _save_bridge_state(BRIDGE_STATE)
    return {"ok": True, "token": _pairing_token()}


@app.get("/tools")
def list_tools(_: None = Depends(_require_pairing_token)):
    """Return all available tool specs."""
    return {"tools": [s.to_dict() for s in runtime.tool_specs.values()]}


@app.post("/execute")
def execute_tool(req: ExecuteRequest, _: None = Depends(_require_pairing_token)):
    """Execute a Butler tool via the runtime engine."""
    session = _get_session()
    try:
        result = runtime.execute_tool(
            session_id=session.id,
            tool_name=req.tool,
            args=req.args,
            actor="mobile-bridge",
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agentic")
async def run_agentic(req: AgenticRequest, _: None = Depends(_require_pairing_token)):
    """Run the agentic orchestrator with an objective."""
    try:
        from runtime.agentic import AgenticOrchestrator  # type: ignore[import]
        orchestrator = AgenticOrchestrator(runtime)
        result = await asyncio.to_thread(
            lambda: asyncio.run(orchestrator.run(req.objective, req.max_iterations))
        )
        return result
    except ImportError:
        raise HTTPException(status_code=501, detail="Agentic runtime not available (Phase 3)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/assist")
def run_core_agent(req: CoreAgentRequest, _: None = Depends(_require_pairing_token)):
    """Run the thin Butler core agent for recall and relationship prompts."""
    try:
        from runtime.core_agent import ButlerCoreAgent  # type: ignore[import]

        agent = ButlerCoreAgent(runtime)
        return agent.run(req.prompt, session_id=_get_session().id, limit=req.limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/context/capture")
def capture_context(req: ContextCaptureRequest, _: None = Depends(_require_pairing_token)):
    """Capture a phone photo or attachment into the canonical context repo."""
    session = _get_session()
    try:
        args = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        result = runtime.execute_tool(
            session_id=session.id,
            tool_name="capture_context_artifact",
            args=args,
            actor="mobile-bridge",
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/session")
def get_session(_: None = Depends(_require_pairing_token)):
    """Return current bridge session state."""
    session = _get_session()
    return session.to_dict()


@app.post("/permission")
def set_permission(request: Request, mode: str, note: str = ""):
    """Change session permission mode (locked | standard)."""
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Bridge permission changes are local-only.")
    if mode == "full-access":
        raise HTTPException(status_code=403, detail="Remote full-access elevation is not allowed.")
    if mode not in {"locked", "standard"}:
        raise HTTPException(status_code=400, detail="Unsupported bridge permission mode.")
    session = _get_session()
    runtime.set_permission_mode(session.id, mode, actor="bridge-user", note=note)
    return {"ok": True, "mode": mode}


if __name__ == "__main__":
    host = os.environ.get("AIBUTLER_BRIDGE_HOST", "0.0.0.0" if LAN_ENABLED else "127.0.0.1")
    port = int(os.environ.get("AIBUTLER_BRIDGE_PORT", "8765"))
    print(f"\n  aiButler Bridge running at http://{host}:{port}")
    print(f"  Pairing token file: {BRIDGE_STATE_PATH}")
    print("  Use AIBUTLER_BRIDGE_ALLOW_LAN=1 only when you intend to pair a phone on your LAN.")
    if LAN_ENABLED:
        print(f"  Mobile app: connect to http://YOUR_MAC_IP:{port} with the stored pairing token.")
    else:
        print("  LAN access is disabled. Bridge is localhost-only.")
    print("")
    uvicorn.run(app, host=host, port=port, log_level="info")
