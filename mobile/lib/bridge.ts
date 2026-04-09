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
  room_id?: string | null;
  artifact_id?: string | null;
  version_id?: string | null;
  refs?: string[];
  lease_owner?: string;
  lease_expires_at?: string | null;
  consumed_at?: string | null;
  expires_at?: string | null;
  session_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ButlerRoom {
  id: string;
  room_id: string;
  kind: string;
  title: string;
  status?: string;
  metadata?: Record<string, unknown>;
  source_refs?: string[];
  current_draft_version?: string | null;
  current_published_version?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ButlerRoomArtifact {
  id: string;
  artifact_id: string;
  room_id: string;
  artifact_kind: string;
  artifact_url: string;
  mime_type?: string;
  metadata?: Record<string, unknown>;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ButlerRoomVersion {
  id: string;
  version_id: string;
  room_id: string;
  state_kind: string;
  payload?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  parent_version_id?: string | null;
  created_by?: string;
  status?: string;
  created_at?: string;
  published_at?: string | null;
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
  room_id?: string;
  artifact_id?: string;
  version_id?: string;
  refs?: string[];
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

export async function listRooms(kind?: string, limit = 12): Promise<ButlerRoom[]> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const params = new URLSearchParams({ limit: String(limit) });
  if (kind) {
    params.set("kind", kind);
  }
  const res = await fetch(`${bridgeUrl}/rooms?${params.toString()}`, {
    headers: bridgeHeaders(false),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Room list error ${res.status}: ${text}`);
  }
  const payload = (await res.json()) as { rooms?: ButlerRoom[] };
  return Array.isArray(payload.rooms) ? payload.rooms : [];
}

export async function createRoom(payload: {
  kind: string;
  title: string;
  status?: string;
  metadata?: Record<string, unknown>;
  source_refs?: string[];
  initial_payload?: Record<string, unknown>;
  created_by?: string;
}): Promise<{ room?: ButlerRoom; draft?: ButlerRoomVersion | null }> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }

  const res = await fetch(`${bridgeUrl}/rooms`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Room create error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getRoom(roomId: string): Promise<ButlerRoom | null> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }
  const res = await fetch(`${bridgeUrl}/rooms/${encodeURIComponent(roomId)}`, {
    headers: bridgeHeaders(false),
  });
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Room fetch error ${res.status}: ${text}`);
  }
  const payload = (await res.json()) as { room?: ButlerRoom };
  return payload.room ?? null;
}

export async function listRoomArtifacts(roomId: string, limit = 25): Promise<ButlerRoomArtifact[]> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${bridgeUrl}/rooms/${encodeURIComponent(roomId)}/artifacts?${params.toString()}`, {
    headers: bridgeHeaders(false),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Room artifact list error ${res.status}: ${text}`);
  }
  const payload = (await res.json()) as { artifacts?: ButlerRoomArtifact[] };
  return Array.isArray(payload.artifacts) ? payload.artifacts : [];
}

export async function attachRoomArtifact(payload: {
  roomId: string;
  artifact_kind: string;
  artifact_url: string;
  mime_type?: string;
  metadata?: Record<string, unknown>;
  created_by?: string;
}): Promise<{ artifact?: ButlerRoomArtifact }> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }
  const { roomId, ...body } = payload;
  const res = await fetch(`${bridgeUrl}/rooms/${encodeURIComponent(roomId)}/artifacts`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Room artifact attach error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getCurrentRoomDraft(
  roomId: string
): Promise<{ room?: ButlerRoom | null; draft?: ButlerRoomVersion | null }> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }
  const res = await fetch(`${bridgeUrl}/rooms/${encodeURIComponent(roomId)}/draft`, {
    headers: bridgeHeaders(false),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Room draft fetch error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function listRoomVersions(roomId: string, limit = 25): Promise<ButlerRoomVersion[]> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${bridgeUrl}/rooms/${encodeURIComponent(roomId)}/versions?${params.toString()}`, {
    headers: bridgeHeaders(false),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Room version list error ${res.status}: ${text}`);
  }
  const payload = (await res.json()) as { versions?: ButlerRoomVersion[] };
  return Array.isArray(payload.versions) ? payload.versions : [];
}

export async function saveRoomDraft(payload: {
  roomId: string;
  payload: Record<string, unknown>;
  parent_version_id?: string | null;
  state_kind?: string;
  metadata?: Record<string, unknown>;
  created_by?: string;
}): Promise<{ room?: ButlerRoom | null; version?: ButlerRoomVersion }> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }
  const { roomId, ...body } = payload;
  const res = await fetch(`${bridgeUrl}/rooms/${encodeURIComponent(roomId)}/drafts`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Room draft save error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function publishRoomVersion(
  versionId: string,
  createdBy = "mobile"
): Promise<{ room?: ButlerRoom | null; version?: ButlerRoomVersion }> {
  if (!bridgeUrl || !bridgeToken) {
    throw new Error("Desktop bridge not connected.");
  }
  const res = await fetch(`${bridgeUrl}/versions/${encodeURIComponent(versionId)}/publish`, {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify({ created_by: createdBy }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Room publish error ${res.status}: ${text}`);
  }
  return res.json();
}

export function isConnected(): boolean {
  return bridgeUrl !== null && bridgeToken !== null;
}
