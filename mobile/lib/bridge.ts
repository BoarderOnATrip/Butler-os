/**
 * Desktop bridge client — proxies tool calls from mobile to the desktop runtime.
 *
 * The desktop bridge server runs at aibutler.local:8765 (mDNS) or a manually
 * configured IP. Mobile tools that require local Mac access (computer use, file
 * ops) are proxied here. Tools that don't need the Mac run in-app or are
 * handled by ElevenLabs directly.
 */

const BRIDGE_PORT = 8765;
const BRIDGE_MDNS = "aibutler.local";

let bridgeUrl: string | null = null;
let bridgeToken: string | null = null;

export interface ContextCaptureRequest {
  capture_kind: string;
  title: string;
  content: string;
  file_name: string;
  mime_type: string;
  data_base64: string;
  source_surface: string;
  source_device: string;
  source_app: string;
}

export function setBridgeUrl(url: string) {
  const trimmed = url.trim();
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    bridgeUrl = trimmed.replace(/\/+$/, "");
    return;
  }
  bridgeUrl = `http://${trimmed.replace(/\/+$/, "")}`;
}

export function clearBridgePairing() {
  bridgeUrl = null;
  bridgeToken = null;
}

function bridgeHeaders(includeJson = true): Record<string, string> {
  const headers: Record<string, string> = {};
  if (includeJson) {
    headers["Content-Type"] = "application/json";
  }
  if (bridgeToken) {
    headers.Authorization = `Bearer ${bridgeToken}`;
    headers["X-AIBUTLER-Token"] = bridgeToken;
  }
  return headers;
}

export async function discoverDesktop(): Promise<string | null> {
  // Try mDNS hostname first
  const mdnsUrl = `http://${BRIDGE_MDNS}:${BRIDGE_PORT}`;
  try {
    const res = await fetch(`${mdnsUrl}/health`, { signal: AbortSignal.timeout(2000) });
    if (res.ok) {
      return mdnsUrl;
    }
  } catch {
    // mDNS not available, need manual pairing
  }
  return null;
}

export async function pairDesktop(url: string, token: string): Promise<unknown> {
  setBridgeUrl(url);
  bridgeToken = token.trim();

  const res = await fetch(`${bridgeUrl}/session`, {
    headers: bridgeHeaders(false),
  });

  if (!res.ok) {
    const text = await res.text();
    clearBridgePairing();
    throw new Error(`Pairing failed ${res.status}: ${text}`);
  }

  return res.json();
}

export async function executeTool(toolName: string, args: Record<string, unknown>): Promise<unknown> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected. Pair with your Mac first.");
  }

  const res = await fetch(`${bridgeUrl}/execute`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify({ tool: toolName, args }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Bridge error ${res.status}: ${text}`);
  }

  return res.json();
}

export async function runAgentic(objective: string): Promise<unknown> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const res = await fetch(`${bridgeUrl}/agentic`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify({ objective }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Agentic error ${res.status}: ${text}`);
  }

  return res.json();
}

export async function runCoreAgent(prompt: string, limit = 5): Promise<unknown> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const res = await fetch(`${bridgeUrl}/assist`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify({ prompt, limit }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Core agent error ${res.status}: ${text}`);
  }

  return res.json();
}

export async function captureContext(payload: ContextCaptureRequest): Promise<unknown> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const res = await fetch(`${bridgeUrl}/context/capture`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Context capture error ${res.status}: ${text}`);
  }

  return res.json();
}

export function isConnected(): boolean {
  return bridgeUrl !== null && bridgeToken !== null;
}
