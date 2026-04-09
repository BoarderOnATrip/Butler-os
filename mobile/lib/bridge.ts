/**
 * Desktop bridge client — proxies tool calls from mobile to the desktop runtime.
 *
 * The desktop bridge server runs at aibutler.local:8765 (mDNS) or a manually
 * configured IP. Mobile tools that require local Mac access (computer use, file
 * ops) are proxied here. Tools that don't need the Mac run in-app or are
 * handled by ElevenLabs directly.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

const BRIDGE_PORT = 8765;
const BRIDGE_MDNS = "aibutler.local";
const BRIDGE_STORAGE_KEY = "aibutler.mobile.bridge-pairing";

let bridgeUrl: string | null = null;
let bridgeToken: string | null = null;

export interface BridgePairingState {
  url: string;
  token: string;
}

export interface ContinuityPacket {
  id: string;
  kind: string;
  title: string;
  content?: string;
  source_device?: string;
  target_device?: string;
  source_surface?: string;
  status?: string;
  metadata?: Record<string, unknown>;
  lease_owner?: string;
  lease_expires_at?: string | null;
  consumed_at?: string | null;
  expires_at?: string | null;
  session_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

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
  AsyncStorage.removeItem(BRIDGE_STORAGE_KEY).catch(() => {});
}

async function persistBridgePairing() {
  if (!bridgeUrl || !bridgeToken) {
    return;
  }
  await AsyncStorage.setItem(
    BRIDGE_STORAGE_KEY,
    JSON.stringify({
      url: bridgeUrl,
      token: bridgeToken,
    } satisfies BridgePairingState)
  );
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

  const payload = await res.json();
  await persistBridgePairing();
  return payload;
}

export async function restoreBridgePairing(): Promise<BridgePairingState | null> {
  const raw = await AsyncStorage.getItem(BRIDGE_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<BridgePairingState>;
    if (!parsed.url || !parsed.token) {
      clearBridgePairing();
      return null;
    }

    setBridgeUrl(parsed.url);
    bridgeToken = parsed.token;

    const res = await fetch(`${bridgeUrl}/session`, {
      headers: bridgeHeaders(false),
    });
    if (!res.ok) {
      clearBridgePairing();
      return null;
    }

    return { url: bridgeUrl, token: bridgeToken };
  } catch {
    clearBridgePairing();
    return null;
  }
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

export async function listContinuityInbox(
  targetDevice = "phone",
  status?: string,
  limit = 12,
  includeConsumed = false
): Promise<ContinuityPacket[]> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const params = new URLSearchParams({
    target_device: targetDevice,
    limit: String(limit),
    include_consumed: includeConsumed ? "true" : "false",
  });
  if (status) {
    params.set("status", status);
  }
  const res = await fetch(`${bridgeUrl}/continuity/inbox?${params.toString()}`, {
    headers: bridgeHeaders(false),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Continuity inbox error ${res.status}: ${text}`);
  }
  const payload = (await res.json()) as { ok?: boolean; packets?: ContinuityPacket[] };
  return Array.isArray(payload.packets) ? payload.packets : [];
}

export async function pushContinuityPacket(payload: {
  kind?: string;
  title: string;
  content?: string;
  target_device: string;
  source_device?: string;
  source_surface?: string;
  metadata?: Record<string, unknown>;
  expires_in_minutes?: number;
}): Promise<unknown> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const res = await fetch(`${bridgeUrl}/continuity/push`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Continuity push error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function acknowledgeContinuityPacket(
  packetId: string,
  actorDevice = "phone",
  note = ""
): Promise<unknown> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const res = await fetch(`${bridgeUrl}/continuity/ack`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify({ packet_id: packetId, actor_device: actorDevice, note }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Continuity ack error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function claimContinuityPacket(
  packetId: string,
  actorDevice = "phone",
  leaseMinutes = 15
): Promise<unknown> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const res = await fetch(`${bridgeUrl}/continuity/claim`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify({ packet_id: packetId, actor_device: actorDevice, lease_minutes: leaseMinutes }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Continuity claim error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getDesktopClipboard(): Promise<{ content: string; preview?: string; has_content?: boolean }> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const res = await fetch(`${bridgeUrl}/clipboard/desktop`, {
    headers: bridgeHeaders(false),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Desktop clipboard error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function setDesktopClipboard(content: string, sourceDevice = "phone"): Promise<unknown> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const res = await fetch(`${bridgeUrl}/clipboard/desktop`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify({
      content,
      source_device: sourceDevice,
      source_surface: "mobile.continuity",
      create_packet: true,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Desktop clipboard write error ${res.status}: ${text}`);
  }
  return res.json();
}

export function isConnected(): boolean {
  return bridgeUrl !== null && bridgeToken !== null;
}
