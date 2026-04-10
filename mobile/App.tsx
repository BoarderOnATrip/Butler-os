/**
 * aiButler Mobile — phone-first Butler surface.
 *
 * This screen is intentionally product-shaped:
 * your phone is where you review relationship context, pair to your Mac,
 * trigger outreach follow-ups, and launch the voice layer.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Image,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Clipboard from "expo-clipboard";
import * as ImagePicker from "expo-image-picker";

import ContextMapCard, { ContextMapSnapshot } from "./components/ContextMapCard";
import ToolCallBadge from "./components/ToolCallBadge";
import {
  loadPhoneMetadataSnapshot,
  loadPhoneMetadataStatus,
  requestPhoneMetadataPermissions,
  type AndroidPhoneMetadataItem,
  type AndroidPhoneMetadataSnapshot,
  type AndroidPhoneMetadataStatus,
} from "./lib/androidPhoneMetadata";
import { availableModuleIds, modesForModuleIds } from "./lib/modules";
import { RECIPES } from "./lib/recipes";
import { TOOL_DEFINITIONS } from "./lib/tools";
import { DEFAULT_PHONE_SKIN, PHONE_MODE_META, PHONE_SKINS, type PhoneMode, type QuickActionRecipe } from "./lib/skins";
import {
  acknowledgeContinuityPacket,
  captureContext,
  claimContinuityPacket,
  clearBridgePairing,
  createRoom,
  discoverDesktop,
  executeTool,
  getDesktopClipboard,
  listRooms,
  isConnected,
  listContinuityInbox,
  pairDesktop,
  publishRoomVersion,
  pushContinuityPacket,
  resolveRoom,
  restoreBridgePairing,
  runCoreAgent,
  runAgentic,
  setDesktopClipboard,
  type ButlerRoom,
  type ContinuityPacket,
} from "./lib/bridge";

const AGENT_ID = process.env.EXPO_PUBLIC_ELEVENLABS_AGENT_ID ?? "";
const PHONE_SKIN_STORAGE_KEY = "aibutler.mobile.active-skin";

type VoiceStatus = "idle" | "listening" | "thinking" | "speaking" | "error";

interface ToolCall {
  id: string;
  toolName: string;
  status: "running" | "success" | "error";
  result?: string;
}

interface PendingItem {
  id: string;
  capture_kind: string;
  title: string;
  content?: string;
  confidence?: number;
  created_at?: string;
  status?: string;
  path?: string;
  source?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

interface FollowupItem {
  id: string;
  person_ref?: string;
  full_name?: string;
  person_name?: string;
  name?: string;
  company?: string;
  role?: string;
  channel?: string;
  direction?: string;
  relationship_type?: string;
  stage?: string;
  priority?: string;
  next_action?: string;
  next_action_due_at?: string;
  due_label?: string;
  score?: number;
  overdue?: boolean;
  thread_summary?: string;
  open_loop?: string;
  last_touch_at?: string;
  pinned?: boolean;
}

interface ActivityItem {
  id: string;
  ref?: string;
  kind?: string;
  title?: string;
  summary?: string;
  path?: string;
  created_at?: string;
  updated_at?: string;
  event_type?: string;
  pinned?: boolean;
  pin_label?: string;
  pin_note?: string;
}

interface OpenClawGatewayState {
  ok?: boolean;
  running?: boolean;
  summary?: string;
  raw?: string;
  payload?: Record<string, unknown> | null;
}

interface OpenClawStatusSnapshot {
  openclaw_installed?: boolean;
  openclaw_path?: string;
  openclaw_version?: string;
  node_installed?: boolean;
  node_version?: string;
  npm_installed?: boolean;
  npm_version?: string;
  npm_global_prefix?: string;
  npm_global_bin?: string;
  npm_global_bin_on_path?: boolean;
  operator_mode?: string;
  ready?: boolean;
  gateway?: OpenClawGatewayState;
  remote?: {
    configured?: boolean;
    endpoint?: string;
    label?: string;
    vpn_required?: boolean;
    reachable?: boolean;
    probe?: {
      summary?: string;
      error?: string;
    };
  };
  openclaw_user_dir?: string;
  extensions_dir?: string;
  rtk_plugin_installed?: boolean;
  rtk_plugin_dir?: string;
  suggested_steps?: string[];
}

type CaptureKind = "receipt" | "note" | "person" | "artifact";
type ReviewStatus = "new" | "deferred" | "dismissed" | "promoted";

interface SelectedCapture {
  uri: string;
  fileName: string;
  mimeType: string;
  base64: string;
  source: "camera" | "library";
  width?: number;
  height?: number;
}

const SOURCE_APP = "aiButler mobile";
const SOURCE_DEVICE = "phone";
const SOURCE_HARDWARE = "android-phone";
const SOURCE_SURFACE = "mobile.capture_tray";

const RELATIONSHIP_CHANNELS = ["call", "text", "email", "in-person", "voice"];
const RELATIONSHIP_DIRECTIONS = ["outbound", "inbound", "two-way"];
const RELATIONSHIP_TYPES = ["lead", "customer", "partner", "advisor", "investor", "friend", "vendor", "other"];
const RELATIONSHIP_STAGES = ["new", "contacted", "warm", "replied", "qualified", "active", "closed"];
const RELATIONSHIP_PRIORITIES = ["low", "medium", "high", "critical"];
const METADATA_INGEST_TOOL_NAMES = new Set([
  "capture_pending_context",
  "relationship_log_interaction",
  "relationship_ingest_phone_metadata",
  "relationship_import_contacts",
  "promote_pending_context",
  "defer_pending_context",
  "dismiss_pending_context",
  "restore_pending_context",
  "list_pending_context",
]);

function prettifyFileStem(fileName: string): string {
  return fileName
    .replace(/\.[^.]+$/, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function buildDefaultCaptureTitle(kind: CaptureKind, fileName?: string): string {
  const label = kind.charAt(0).toUpperCase() + kind.slice(1);
  const stem = fileName ? prettifyFileStem(fileName) : "";
  return stem ? `${label}: ${stem}` : `${label} capture`;
}

function compactText(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function stringValue(value: unknown): string {
  if (typeof value === "string") {
    return compactText(value);
  }
  if (typeof value === "number") {
    return String(value);
  }
  return "";
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return undefined;
}

function summarizeBridgeOutput(result: unknown): string {
  if (typeof result === "string") {
    return result;
  }
  if (!result || typeof result !== "object") {
    return String(result);
  }
  const payload = result as Record<string, unknown>;
  if (typeof payload.output === "string") {
    return payload.output;
  }
  if (payload.output !== undefined) {
    try {
      return JSON.stringify(payload.output, null, 2);
    } catch {
      return String(payload.output);
    }
  }
  if (typeof payload.message === "string") {
    return payload.message;
  }
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}

function stripPendingPrefix(value: string): string {
  return value.replace(/^(receipt|note|person|artifact)\s*[:\-]\s*/i, "").trim();
}

function normalizeTagsCsv(value: string): string {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)
    .join(", ");
}

function getFollowupName(item: FollowupItem): string {
  return item.person_name || item.full_name || item.name || "Untitled relationship";
}

function formatFeedTimestamp(value?: string): string {
  if (!value) {
    return "No timestamp";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatMetadataTimestamp(value?: string): string {
  return formatFeedTimestamp(value);
}

function inferRoomKindFromRef(ref: string): string {
  const prefix = compactText(ref).split("/", 1)[0].toLowerCase();
  switch (prefix) {
    case "people":
      return "person";
    case "organizations":
      return "organization";
    case "places":
      return "place";
    case "conversations":
      return "conversation";
    case "projects":
      return "project";
    case "tasks":
      return "task";
    case "pending":
      return "pending";
    default:
      return prefix.replace(/s$/, "") || "general";
  }
}

function humanizeRef(ref: string): string {
  const suffix = compactText(ref).split("/").slice(-1)[0] || ref;
  return suffix
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function contextDirectoryForKind(kind: string): string {
  switch (compactText(kind).toLowerCase()) {
    case "person":
      return "people";
    case "organization":
      return "organizations";
    case "place":
      return "places";
    case "conversation":
      return "conversations";
    case "task":
      return "tasks";
    case "project":
      return "projects";
    case "artifact":
      return "artifacts";
    case "secret":
      return "secrets";
    default:
      return compactText(kind).toLowerCase() || "items";
  }
}

function refFromContextSheet(sheet: Record<string, unknown> | null | undefined): string {
  if (!sheet) {
    return "";
  }
  const kind = compactText(String(sheet.kind || ""));
  const slug = compactText(String(sheet.slug || ""));
  if (!kind || !slug) {
    return "";
  }
  return `${contextDirectoryForKind(kind)}/${slug}`;
}

function buildPhoneMetadataReviewContent(item: AndroidPhoneMetadataItem): string {
  const source = item.source ? JSON.stringify(item.source, null, 2) : "";
  return [
    `Kind: ${item.kind}`,
    item.timestamp_iso ? `Timestamp: ${item.timestamp_iso}` : "",
    item.summary ? `Summary: ${item.summary}` : "",
    source ? `Source: ${source}` : "",
  ]
    .filter(Boolean)
    .join("\n\n");
}

function reviewStatusFromPending(item: PendingItem, localStatuses: Record<string, ReviewStatus>): ReviewStatus {
  const normalizedStatus = compactText(item.status || "").toLowerCase();
  if (normalizedStatus === "deferred" || normalizedStatus === "dismissed" || normalizedStatus === "promoted") {
    return normalizedStatus as ReviewStatus;
  }
  return localStatuses[item.id] || "new";
}

function phoneDirection(item: AndroidPhoneMetadataItem): string {
  const sourceType = compactText(stringValue(item.source?.type)).toLowerCase();
  if (item.kind === "sms_thread") {
    if (sourceType === "inbox") return "inbound";
    if (sourceType === "sent" || sourceType === "outbox" || sourceType === "queued") return "outbound";
    return "two-way";
  }
  if (sourceType === "incoming" || sourceType === "missed" || sourceType === "rejected" || sourceType === "blocked" || sourceType === "voicemail") {
    return "inbound";
  }
  if (sourceType === "outgoing") {
    return "outbound";
  }
  return "two-way";
}

function phoneNextAction(item: AndroidPhoneMetadataItem): string {
  const sourceType = compactText(stringValue(item.source?.type)).toLowerCase();
  if (item.kind === "sms_thread") {
    if ((item.unread_count || 0) > 0 || sourceType === "inbox") {
      return "Reply to text thread";
    }
    return "";
  }
  if (sourceType === "missed") {
    return "Return missed call";
  }
  if (sourceType === "voicemail") {
    return "Check voicemail and reply";
  }
  return "";
}

function phonePriority(item: AndroidPhoneMetadataItem, nextAction: string): string {
  if (!nextAction) {
    return "medium";
  }
  if (item.kind === "sms_thread" && (item.unread_count || 0) > 0) {
    return "high";
  }
  const sourceType = compactText(stringValue(item.source?.type)).toLowerCase();
  return sourceType === "missed" ? "high" : "medium";
}

function phoneExternalEventId(item: AndroidPhoneMetadataItem): string {
  const explicit = stringValue(item.record_id) || stringValue(item.source?.record_id);
  if (explicit) {
    return explicit;
  }
  return [
    item.kind,
    String(item.timestamp_ms),
    compactText(item.title),
    stringValue(item.source?.number || item.source?.address),
    stringValue(item.thread_id || item.source?.thread_id),
  ]
    .filter(Boolean)
    .join("|");
}

function buildPhoneMetadataIngestArgs(item: AndroidPhoneMetadataItem): Record<string, unknown> {
  const phoneNumber = stringValue(item.source?.number || item.source?.address);
  const rawTitle = compactText(item.title);
  const personName =
    /^unknown caller$/i.test(rawTitle) && phoneNumber
      ? phoneNumber
      : /^sms thread\b/i.test(rawTitle) && phoneNumber
      ? phoneNumber
      : rawTitle || phoneNumber || "Unknown phone contact";
  const summaryBits = [compactText(item.summary), stringValue(item.source?.body_preview)].filter(Boolean);
  const summary = summaryBits.length ? summaryBits.join(" • ") : `${item.kind === "sms_thread" ? "SMS thread" : "Phone call"} with ${personName}`;
  const nextAction = phoneNextAction(item);
  const threadId = stringValue(item.thread_id || item.source?.thread_id);
  const durationSeconds = numberValue(item.source?.duration_seconds);

  return {
    person_name: personName,
    channel: item.kind === "sms_thread" ? "text" : "call",
    direction: phoneDirection(item),
    phone_number: phoneNumber,
    summary,
    relationship_type: "contact",
    stage: "active",
    priority: phonePriority(item, nextAction),
    next_action: nextAction,
    due_date: nextAction ? "today" : "",
    occurred_at: item.timestamp_iso || "",
    duration_seconds: durationSeconds,
    thread_id: threadId,
    external_event_id: phoneExternalEventId(item),
    call_status: item.kind === "call" ? stringValue(item.source?.type) : "",
    snippet: stringValue(item.source?.body_preview),
    conversation_label: item.kind === "sms_thread" ? rawTitle : "",
    source_app: SOURCE_APP,
    source_device: SOURCE_DEVICE,
    source_hardware: SOURCE_HARDWARE,
    source_surface: item.kind === "sms_thread" ? "android.sms" : "android.call_log",
  };
}

export default function App() {
  const [activeSkinId, setActiveSkinId] = useState(DEFAULT_PHONE_SKIN.id);
  const currentSkin = useMemo(
    () => PHONE_SKINS.find((skin) => skin.id === activeSkinId) ?? DEFAULT_PHONE_SKIN,
    [activeSkinId]
  );
  const [skinHydrated, setSkinHydrated] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("idle");
  const [activeMode, setActiveMode] = useState<PhoneMode>(DEFAULT_PHONE_SKIN.defaultMode);
  const [lastUtterance, setLastUtterance] = useState("");
  const [lastResponse, setLastResponse] = useState("");
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [desktopPaired, setDesktopPaired] = useState(false);
  const [pairingHost, setPairingHost] = useState("");
  const [pairingToken, setPairingToken] = useState("");
  const [pairingBusy, setPairingBusy] = useState(false);
  const [discoveredHost, setDiscoveredHost] = useState("");
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [captureKind, setCaptureKind] = useState<CaptureKind>("receipt");
  const [captureTitle, setCaptureTitle] = useState("");
  const [captureContent, setCaptureContent] = useState("");
  const [selectedCapture, setSelectedCapture] = useState<SelectedCapture | null>(null);
  const [pendingItems, setPendingItems] = useState<PendingItem[]>([]);
  const [pendingBusy, setPendingBusy] = useState(false);
  const [captureBusy, setCaptureBusy] = useState(false);
  const [reviewStatuses, setReviewStatuses] = useState<Record<string, ReviewStatus>>({});
  const [reviewInsights, setReviewInsights] = useState<Record<string, string>>({});
  const [reviewBusyId, setReviewBusyId] = useState("");
  const [relationshipName, setRelationshipName] = useState("");
  const [relationshipCompany, setRelationshipCompany] = useState("");
  const [relationshipRole, setRelationshipRole] = useState("");
  const [relationshipPlaceName, setRelationshipPlaceName] = useState("");
  const [relationshipConversationLabel, setRelationshipConversationLabel] = useState("");
  const [relationshipChannel, setRelationshipChannel] = useState("call");
  const [relationshipDirection, setRelationshipDirection] = useState("outbound");
  const [relationshipType, setRelationshipType] = useState("lead");
  const [relationshipStage, setRelationshipStage] = useState("new");
  const [relationshipPriority, setRelationshipPriority] = useState("medium");
  const [relationshipPhone, setRelationshipPhone] = useState("");
  const [relationshipEmail, setRelationshipEmail] = useState("");
  const [relationshipSummary, setRelationshipSummary] = useState("");
  const [relationshipNextAction, setRelationshipNextAction] = useState("");
  const [relationshipDueAt, setRelationshipDueAt] = useState("");
  const [relationshipFollowUpInDays, setRelationshipFollowUpInDays] = useState("");
  const [relationshipOpenLoop, setRelationshipOpenLoop] = useState("");
  const [relationshipNotes, setRelationshipNotes] = useState("");
  const [relationshipTagsCsv, setRelationshipTagsCsv] = useState("");
  const [relationshipBusy, setRelationshipBusy] = useState(false);
  const [contactImportBusy, setContactImportBusy] = useState(false);
  const [followups, setFollowups] = useState<FollowupItem[]>([]);
  const [followupsBusy, setFollowupsBusy] = useState(false);
  const [activityItems, setActivityItems] = useState<ActivityItem[]>([]);
  const [activityBusy, setActivityBusy] = useState(false);
  const [contextMap, setContextMap] = useState<ContextMapSnapshot | null>(null);
  const [contextMapBusy, setContextMapBusy] = useState(false);
  const [pinBusyRef, setPinBusyRef] = useState("");
  const [phoneMetadataStatus, setPhoneMetadataStatus] = useState<AndroidPhoneMetadataStatus | null>(null);
  const [phoneMetadataSnapshot, setPhoneMetadataSnapshot] = useState<AndroidPhoneMetadataSnapshot | null>(null);
  const [phoneMetadataBusy, setPhoneMetadataBusy] = useState(false);
  const [phoneMetadataRefreshBusy, setPhoneMetadataRefreshBusy] = useState(false);
  const [phoneMetadataPromoteBusy, setPhoneMetadataPromoteBusy] = useState("");
  const [phoneMetadataSyncBusy, setPhoneMetadataSyncBusy] = useState("");
  const [openclawStatus, setOpenclawStatus] = useState<OpenClawStatusSnapshot | null>(null);
  const [openclawBusy, setOpenclawBusy] = useState(false);
  const [openclawActionBusy, setOpenclawActionBusy] = useState("");
  const [openclawRemoteRpcUrl, setOpenclawRemoteRpcUrl] = useState("");
  const [openclawRemoteLabel, setOpenclawRemoteLabel] = useState("Shared VPN operator");
  const [continuityItems, setContinuityItems] = useState<ContinuityPacket[]>([]);
  const [continuityBusy, setContinuityBusy] = useState(false);
  const [continuityActionBusy, setContinuityActionBusy] = useState("");
  const [continuityTitle, setContinuityTitle] = useState("Quick handoff");
  const [continuityNote, setContinuityNote] = useState("");
  const [activeContinuityPacketId, setActiveContinuityPacketId] = useState("");
  const [rooms, setRooms] = useState<ButlerRoom[]>([]);
  const [roomsBusy, setRoomsBusy] = useState(false);
  const [roomActionBusy, setRoomActionBusy] = useState("");
  const [roomTitle, setRoomTitle] = useState("");
  const [roomKind, setRoomKind] = useState("project");
  const [roomSeedNote, setRoomSeedNote] = useState("");
  const [activeRoomId, setActiveRoomId] = useState("");
  const conversationRef = useRef<any>(null);

  const spotlightContinuityPacket = useCallback((packet?: ContinuityPacket | null) => {
    if (!packet?.id) {
      return;
    }
    setActiveContinuityPacketId(packet.id);
    if (packet.room_id) {
      setActiveRoomId(packet.room_id);
    }
  }, []);

  const spotlightRoom = useCallback((room?: ButlerRoom | null) => {
    if (!room?.room_id) {
      return;
    }
    setActiveRoomId(room.room_id);
  }, []);

  useEffect(() => {
    discoverDesktop().then((url) => {
      if (!url) {
        return;
      }
      setDiscoveredHost(url);
      setPairingHost((current) => current || url);
      setLastResponse("Desktop discovered on your local network. Add the pairing token from your Mac to unlock secure control.");
    });
  }, []);

  useEffect(() => {
    let cancelled = false;

    restoreBridgePairing()
      .then((pairing) => {
        if (cancelled || !pairing) {
          return;
        }
        setPairingHost(pairing.url);
        setPairingToken(pairing.token);
        setDesktopPaired(true);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    AsyncStorage.getItem(PHONE_SKIN_STORAGE_KEY)
      .then((storedSkinId) => {
        if (cancelled || !storedSkinId) {
          return;
        }
        if (PHONE_SKINS.some((skin) => skin.id === storedSkinId)) {
          setActiveSkinId(storedSkinId);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSkinHydrated(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!skinHydrated) {
      return;
    }
    AsyncStorage.setItem(PHONE_SKIN_STORAGE_KEY, activeSkinId).catch(() => {});
  }, [activeSkinId, skinHydrated]);

  const unwrapToolResult = useCallback((result: unknown): { ok: boolean; output?: unknown; error?: string } => {
    if (!result || typeof result !== "object") {
      return { ok: false, error: "Unexpected tool result." };
    }
    const payload = result as { ok?: boolean; output?: unknown; error?: string };
    return {
      ok: Boolean(payload.ok),
      output: payload.output,
      error: payload.error,
    };
  }, []);

  const handleToolCall = useCallback(
    async (toolName: string, args: Record<string, unknown>): Promise<unknown> => {
      const callId = Math.random().toString(36).slice(2);

      setToolCalls((prev) => [
        { id: callId, toolName, status: "running" },
        ...prev.slice(0, 11),
      ]);

      try {
        let result: unknown;

        if (isConnected()) {
          result = await executeTool(toolName, args);
        } else {
          result = {
            ok: false,
            error: "Desktop bridge not paired. Pair with your Mac to unlock computer use and local tools.",
          };
        }

        const resultStr = typeof result === "string" ? result : JSON.stringify(result);

        setToolCalls((prev) =>
          prev.map((call) =>
            call.id === callId ? { ...call, status: "success", result: resultStr } : call
          )
        );

        return result;
      } catch (error: unknown) {
        const errMsg = error instanceof Error ? error.message : String(error);
        setToolCalls((prev) =>
          prev.map((call) =>
            call.id === callId ? { ...call, status: "error", result: errMsg } : call
          )
        );
        return { ok: false, error: errMsg };
      }
    },
    []
  );

  const focusMode = useCallback((mode: PhoneMode, response?: string) => {
    setActiveMode(mode);
    if (response) {
      setLastResponse(response);
    }
  }, []);

  const handleSkinChange = useCallback((skinId: string) => {
    const nextSkin = PHONE_SKINS.find((skin) => skin.id === skinId);
    if (!nextSkin) {
      return;
    }
    const availableModes = modesForModuleIds(
      availableModuleIds(nextSkin.moduleIds, { desktopPaired, platformOS: Platform.OS })
    );
    const nextMode = availableModes.includes(nextSkin.defaultMode) ? nextSkin.defaultMode : availableModes[0] ?? "home";
    setActiveSkinId(nextSkin.id);
    setActiveMode(nextMode);
    setLastResponse(`${nextSkin.name} skin loaded. Butler shifted emphasis without changing your underlying context.`);
  }, [desktopPaired]);

  const handlePairDesktop = useCallback(async () => {
    if (!pairingHost.trim()) {
      Alert.alert("Mac address missing", "Enter your Mac hostname or local IP first.");
      return;
    }
    if (!pairingToken.trim()) {
      Alert.alert("Pairing token missing", "Open the bridge on your Mac and paste the pairing token shown there.");
      return;
    }

    setPairingBusy(true);
    try {
      await pairDesktop(pairingHost.trim(), pairingToken.trim());
      setDesktopPaired(true);
      focusMode("home", "Your Mac is paired. Butler can now act on your behalf with local approvals and receipts.");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      Alert.alert("Pairing failed", message);
      setDesktopPaired(false);
    } finally {
      setPairingBusy(false);
    }
  }, [focusMode, pairingHost, pairingToken]);

  const handleDisconnectDesktop = useCallback(() => {
    clearBridgePairing();
    setDesktopPaired(false);
    focusMode("act", "Desktop pairing cleared. Voice remains available, but local desktop actions are offline.");
  }, [focusMode]);

  const handleVoiceToggle = useCallback(() => {
    if (!AGENT_ID) {
      Alert.alert(
        "Agent Not Configured",
        "Set EXPO_PUBLIC_ELEVENLABS_AGENT_ID before starting voice. The phone app is ready for pairing and quick actions now."
      );
      setVoiceStatus("error");
      return;
    }

    if (voiceStatus === "idle" || voiceStatus === "error") {
      setVoiceStatus("listening");
      setLastUtterance("Voice session starting...");
      setLastResponse("Voice transport is scaffolded. Pairing, quick actions, and desktop delegation are ready now.");
      // ElevenLabs SDK session start belongs here once the mobile voice transport is wired.
      // conversationRef.current?.startSession()
      return;
    }

    setVoiceStatus("idle");
    // conversationRef.current?.endSession()
  }, [voiceStatus]);

  const handleQuickAction = useCallback(async (action: QuickActionRecipe) => {
    if (action.requiresPairing && !desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac to run Butler quick actions against your local runtime.");
      return;
    }

    setActionBusy(action.label);
    try {
      setActiveMode("act");
      setLastUtterance(action.label);

      if (action.mode === "assist") {
        const result = await runCoreAgent(action.prompt, 6);
        const payload = result && typeof result === "object" ? (result as Record<string, unknown>) : null;
        const output = payload?.output && typeof payload.output === "object" ? (payload.output as Record<string, unknown>) : null;
        const summary = typeof output?.summary === "string" ? output.summary : JSON.stringify(result);
        setLastResponse(summary);
      } else {
        const result = await runAgentic(action.objective);
        setLastResponse(typeof result === "string" ? result : JSON.stringify(result));
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Quick action failed", message);
    } finally {
      setActionBusy(null);
    }
  }, [desktopPaired]);

  const refreshPendingQueue = useCallback(async () => {
    if (!desktopPaired) {
      setPendingItems([]);
      return;
    }

    setPendingBusy(true);
    try {
      const result = await handleToolCall("list_pending_context", { limit: 12 });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to load pending queue.");
      }
      setPendingItems(Array.isArray(parsed.output) ? (parsed.output as PendingItem[]) : []);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
    } finally {
      setPendingBusy(false);
    }
  }, [desktopPaired, handleToolCall, unwrapToolResult]);

  const refreshFollowupQueue = useCallback(async () => {
    if (!desktopPaired) {
      setFollowups([]);
      return;
    }

    setFollowupsBusy(true);
    try {
      const result = await handleToolCall("relationship_list_followups", { limit: 8 });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to load follow-up queue.");
      }
      setFollowups(Array.isArray(parsed.output) ? (parsed.output as FollowupItem[]) : []);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
    } finally {
      setFollowupsBusy(false);
    }
  }, [desktopPaired, handleToolCall, unwrapToolResult]);

  const refreshActivityFeed = useCallback(async () => {
    if (!desktopPaired) {
      setActivityItems([]);
      return;
    }

    setActivityBusy(true);
    try {
      const result = await handleToolCall("context_activity_feed", { limit: 14 });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to load activity feed.");
      }
      setActivityItems(Array.isArray(parsed.output) ? (parsed.output as ActivityItem[]) : []);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
    } finally {
      setActivityBusy(false);
    }
  }, [desktopPaired, handleToolCall, unwrapToolResult]);

  const refreshContextMap = useCallback(async () => {
    if (!desktopPaired) {
      setContextMap(null);
      return;
    }

    setContextMapBusy(true);
    try {
      const result = await handleToolCall("context_graph_snapshot", {
        relationship_limit: 6,
        pending_limit: 4,
        signal_limit: 5,
        pin_limit: 4,
      });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to load context map.");
      }
      const snapshot = parsed.output && typeof parsed.output === "object" ? (parsed.output as ContextMapSnapshot) : null;
      setContextMap(snapshot);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
    } finally {
      setContextMapBusy(false);
    }
  }, [desktopPaired, handleToolCall, unwrapToolResult]);

  const refreshOpenClawStatus = useCallback(
    async (options?: { silent?: boolean }) => {
      if (!desktopPaired) {
        setOpenclawStatus(null);
        return;
      }

      setOpenclawBusy(true);
      try {
        const result = await handleToolCall("openclaw_status", {});
        const parsed = unwrapToolResult(result);
        if (!parsed.ok) {
          throw new Error(parsed.error || "Failed to inspect the operator stack.");
        }
        const snapshot =
          parsed.output && typeof parsed.output === "object"
            ? (parsed.output as OpenClawStatusSnapshot)
            : null;
        setOpenclawStatus(snapshot);
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        setLastResponse(message);
        if (!options?.silent) {
          Alert.alert("OpenClaw check failed", message);
        }
      } finally {
        setOpenclawBusy(false);
      }
    },
    [desktopPaired, handleToolCall, unwrapToolResult]
  );

  const runOpenClawAction = useCallback(
    async (
      busyKey: string,
      toolName: string,
      args: Record<string, unknown>,
      {
        successTitle,
        failureTitle,
      }: {
        successTitle: string;
        failureTitle: string;
      }
    ) => {
      if (!desktopPaired) {
        Alert.alert("Mac not paired", "Pair your Mac first so Butler can manage the operator stack.");
        return;
      }

      setOpenclawActionBusy(busyKey);
      try {
        const result = await handleToolCall(toolName, args);
        const parsed = unwrapToolResult(result);
        const payload = result && typeof result === "object" ? (result as Record<string, unknown>) : {};
        const approvalId = stringValue(payload.approval_request_id);

        if (!parsed.ok) {
          if (approvalId) {
            const stagedMessage = `${parsed.error || "Approval required."} Approval id: ${approvalId}.`;
            setLastResponse(stagedMessage);
            Alert.alert("Approval staged", stagedMessage);
            await refreshOpenClawStatus({ silent: true });
            return;
          }
          throw new Error(parsed.error || `${failureTitle} failed.`);
        }

        const output = parsed.output && typeof parsed.output === "object" ? (parsed.output as Record<string, unknown>) : {};
        const nextSteps = Array.isArray(output.next_steps) ? output.next_steps.map((step) => stringValue(step)).filter(Boolean) : [];
        const successMessage =
          stringValue(output.message) ||
          (nextSteps.length ? `${successTitle}. Next: ${nextSteps[0]}` : `${successTitle}.`);
        setLastResponse(successMessage);
        await refreshOpenClawStatus({ silent: true });
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        setLastResponse(message);
        Alert.alert(failureTitle, message);
      } finally {
        setOpenclawActionBusy("");
      }
    },
    [desktopPaired, handleToolCall, refreshOpenClawStatus, unwrapToolResult]
  );

  const handleConfigureOpenClawRemote = useCallback(() => {
    const rpcUrl = compactText(openclawRemoteRpcUrl);
    const label = compactText(openclawRemoteLabel) || "Shared VPN operator";
    if (!rpcUrl) {
      Alert.alert("Remote endpoint needed", "Paste the VPN-reachable OpenClaw RPC URL first.");
      return;
    }

    runOpenClawAction(
      "remote-config",
      "configure_openclaw_remote_endpoint",
      {
        rpc_url: rpcUrl,
        label,
        vpn_required: true,
      },
      {
        successTitle: "Remote OpenClaw endpoint saved",
        failureTitle: "Remote OpenClaw setup failed",
      }
    );
  }, [openclawRemoteLabel, openclawRemoteRpcUrl, runOpenClawAction]);

  const handleClearOpenClawRemote = useCallback(() => {
    runOpenClawAction(
      "remote-clear",
      "clear_openclaw_remote_endpoint",
      {},
      {
        successTitle: "Remote OpenClaw endpoint cleared",
        failureTitle: "Remote OpenClaw clear failed",
      }
    );
  }, [runOpenClawAction]);

  const refreshContinuityInbox = useCallback(async (options?: { silent?: boolean }) => {
    if (!desktopPaired) {
      setContinuityItems([]);
      return;
    }

    setContinuityBusy(true);
    try {
      const packets = await listContinuityInbox("phone", undefined, 10, false);
      setContinuityItems(packets);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      if (!options?.silent) {
        Alert.alert("Continuity refresh failed", message);
      }
    } finally {
      setContinuityBusy(false);
    }
  }, [desktopPaired]);

  const handleSendPhoneClipboardToMac = useCallback(async () => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can hand off your clipboard.");
      return;
    }
    setContinuityActionBusy("push-clipboard");
    try {
      const content = await Clipboard.getStringAsync();
      if (!compactText(content)) {
        throw new Error("Phone clipboard is empty.");
      }
      await setDesktopClipboard(content, "phone");
      setLastResponse("Phone clipboard sent to your Mac.");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Clipboard handoff failed", message);
    } finally {
      setContinuityActionBusy("");
    }
  }, [desktopPaired]);

  const handlePullMacClipboardToPhone = useCallback(async () => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can pull the Mac clipboard.");
      return;
    }
    setContinuityActionBusy("pull-clipboard");
    try {
      const payload = await getDesktopClipboard();
      const content = typeof payload.content === "string" ? payload.content : "";
      if (!compactText(content)) {
        throw new Error("The Mac clipboard is empty.");
      }
      await Clipboard.setStringAsync(content);
      setLastResponse("Mac clipboard copied onto your phone.");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Clipboard pull failed", message);
    } finally {
      setContinuityActionBusy("");
    }
  }, [desktopPaired]);

  const handleSendContinuityNote = useCallback(async () => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can hand off notes.");
      return;
    }
    const title = compactText(continuityTitle) || "Quick handoff";
    const content = continuityNote.trim();
    if (!content) {
      Alert.alert("Nothing to hand off", "Add a quick note or draft before sending it to the Mac.");
      return;
    }

    setContinuityActionBusy("send-note");
    try {
      const result = await pushContinuityPacket({
        kind: "text",
        title,
        content,
        target_device: "desktop",
        source_device: "phone",
        source_surface: "mobile.act.continuity",
        metadata: { lane: "quick_handoff" },
        expires_in_minutes: 180,
      });
      spotlightContinuityPacket(result.packet);
      setContinuityNote("");
      setLastResponse(`Continuity handoff queued for your Mac: ${title}.`);
      await refreshContinuityInbox({ silent: true });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Handoff failed", message);
    } finally {
      setContinuityActionBusy("");
    }
  }, [continuityNote, continuityTitle, desktopPaired, refreshContinuityInbox, spotlightContinuityPacket]);

  const handleClaimContinuityPacket = useCallback(async (packetId: string) => {
    setContinuityActionBusy(`claim:${packetId}`);
    try {
      const result = await claimContinuityPacket(packetId, "phone", 15);
      spotlightContinuityPacket(result.packet);
      await refreshContinuityInbox({ silent: true });
      setLastResponse("Continuity packet claimed on this phone.");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Claim failed", message);
    } finally {
      setContinuityActionBusy("");
    }
  }, [refreshContinuityInbox, spotlightContinuityPacket]);

  const handleCopyContinuityPacket = useCallback(async (packet: ContinuityPacket) => {
    setContinuityActionBusy(`copy:${packet.id}`);
    try {
      await Clipboard.setStringAsync(packet.content || "");
      await acknowledgeContinuityPacket(packet.id, "phone", "Copied into phone clipboard.");
      await refreshContinuityInbox({ silent: true });
      setLastResponse(`Copied "${packet.title}" into your phone clipboard.`);
      if (activeContinuityPacketId === packet.id) {
        setActiveContinuityPacketId("");
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Copy failed", message);
    } finally {
      setContinuityActionBusy("");
    }
  }, [activeContinuityPacketId, refreshContinuityInbox]);

  const refreshRooms = useCallback(async (options?: { silent?: boolean }) => {
    if (!desktopPaired) {
      setRooms([]);
      return;
    }

    setRoomsBusy(true);
    try {
      const nextRooms = await listRooms(undefined, 8);
      setRooms(nextRooms);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      if (!options?.silent) {
        Alert.alert("Room refresh failed", message);
      }
    } finally {
      setRoomsBusy(false);
    }
  }, [desktopPaired]);

  const handleCreateRoom = useCallback(async () => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can create canonical rooms.");
      return;
    }
    const title = compactText(roomTitle);
    if (!title) {
      Alert.alert("Missing room title", "Give this room a short title first.");
      return;
    }

    setRoomActionBusy("create-room");
    try {
      const result = await createRoom({
        kind: roomKind,
        title,
        metadata: {
          source_surface: "mobile.act.rooms",
          seeded_from_phone: true,
        },
        initial_payload: {
          title,
          kind: roomKind,
          note: roomSeedNote.trim(),
        },
        created_by: "mobile",
      });
      const createdRoom = result.room;
      const createdDraft = result.draft;
      if (createdDraft?.version_id) {
        await publishRoomVersion(createdDraft.version_id, "mobile");
      }
      setRoomTitle("");
      setRoomSeedNote("");
      spotlightRoom(createdRoom ?? null);
      setLastResponse(createdRoom?.title ? `Canonical room ready: ${createdRoom.title}.` : "Canonical room created.");
      await refreshRooms({ silent: true });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Room creation failed", message);
    } finally {
      setRoomActionBusy("");
    }
  }, [createRoom, desktopPaired, publishRoomVersion, refreshRooms, roomKind, roomSeedNote, roomTitle, spotlightRoom]);

  const handleSendRoomToMac = useCallback(async (room: ButlerRoom) => {
    setRoomActionBusy(`handoff-room:${room.room_id}`);
    try {
      const result = await pushContinuityPacket({
        kind: "room_ref",
        title: `Open room: ${room.title}`,
        content: room.title,
        target_device: "desktop",
        source_device: "phone",
        source_surface: "mobile.act.rooms",
        room_id: room.room_id,
        refs: [`rooms/${room.room_id}`, ...(room.source_refs ?? [])],
        metadata: {
          action: "open_room",
          room_kind: room.kind,
          room_title: room.title,
        },
        expires_in_minutes: 240,
      });
      spotlightRoom(room);
      spotlightContinuityPacket(result.packet);
      setLastResponse(`Room queued for your Mac: ${room.title}.`);
      await refreshContinuityInbox({ silent: true });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Room handoff failed", message);
    } finally {
      setRoomActionBusy("");
    }
  }, [refreshContinuityInbox, spotlightContinuityPacket, spotlightRoom]);

  const handleFocusRoom = useCallback((roomId: string, title: string) => {
    if (!compactText(roomId)) {
      return;
    }
    setActiveRoomId(roomId);
    setLastResponse(`Focused room: ${title}.`);
  }, []);

  const resolveCanonicalRoomForRef = useCallback(async (
    sourceRef: string,
    title: string,
    kind?: string,
    metadata?: Record<string, unknown>
  ) => {
    const result = await resolveRoom({
      source_ref: sourceRef,
      title: compactText(title) || humanizeRef(sourceRef),
      kind: compactText(kind || "") || inferRoomKindFromRef(sourceRef),
      metadata: {
        source_surface: "mobile.ref-resolution",
        ...metadata,
      },
      created_by: "mobile",
    });
    if (!result.room) {
      throw new Error(`Unable to resolve room for ${sourceRef}.`);
    }
    await refreshRooms({ silent: true });
    return result.room;
  }, [refreshRooms]);

  const queueRefForMac = useCallback(async (
    sourceRef: string,
    title: string,
    options?: {
      kind?: string;
      summary?: string;
      metadata?: Record<string, unknown>;
      activateAct?: boolean;
      alertOnError?: boolean;
      setStatusMessage?: boolean;
    }
  ) => {
    const actionKey = `handoff-ref:${sourceRef}`;
    setRoomActionBusy(actionKey);
    try {
      const normalizedRef = compactText(sourceRef);
      if (!normalizedRef) {
        throw new Error("Missing context ref.");
      }

      let roomId = "";
      let packetKind = "room_ref";
      let resolvedRoom: ButlerRoom | null = null;
      if (!normalizedRef.startsWith("pending/")) {
        const room = await resolveCanonicalRoomForRef(
          normalizedRef,
          title,
          options?.kind,
          options?.metadata
        );
        resolvedRoom = room;
        roomId = room.room_id;
      } else {
        packetKind = "pending_ref";
      }

      const result = await pushContinuityPacket({
        kind: packetKind,
        title: `Open on Mac: ${title}`,
        content: options?.summary || title,
        target_device: "desktop",
        source_device: "phone",
        source_surface: "mobile.context-handoff",
        room_id: roomId || undefined,
        refs: [normalizedRef],
        metadata: {
          action: roomId ? "open_room" : "open_ref",
          source_ref: normalizedRef,
          room_kind: options?.kind || inferRoomKindFromRef(normalizedRef),
          title,
          ...options?.metadata,
        },
        expires_in_minutes: 240,
      });
      spotlightContinuityPacket(result.packet);
      if (resolvedRoom) {
        spotlightRoom(resolvedRoom);
      }
      if (options?.setStatusMessage !== false) {
        setLastResponse(`Queued "${title}" for your Mac.`);
      }
      await refreshContinuityInbox({ silent: true });
      if (options?.activateAct !== false) {
        setActiveMode("act");
      }
      return true;
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      if (options?.setStatusMessage !== false) {
        setLastResponse(message);
      }
      if (options?.alertOnError !== false) {
        Alert.alert("Context handoff failed", message);
      }
      return false;
    } finally {
      setRoomActionBusy("");
    }
  }, [refreshContinuityInbox, resolveCanonicalRoomForRef, spotlightContinuityPacket, spotlightRoom]);

  const handleSendRefToMac = useCallback(async (
    sourceRef: string,
    title: string,
    options?: {
      kind?: string;
      summary?: string;
      metadata?: Record<string, unknown>;
    }
  ) => {
    await queueRefForMac(sourceRef, title, {
      ...options,
      activateAct: true,
      alertOnError: true,
      setStatusMessage: true,
    });
  }, [queueRefForMac]);

  const refreshPhoneMetadataStatus = useCallback(async () => {
    try {
      const status = await loadPhoneMetadataStatus();
      setPhoneMetadataStatus(status);
      return status;
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setPhoneMetadataStatus({
        ready: false,
        permissions: {
          read_call_log: "unavailable",
          read_sms: "unavailable",
        },
        missing_permissions: ["READ_CALL_LOG", "READ_SMS"],
        status_label: "Unavailable",
      });
      setLastResponse(message);
      return null;
    }
  }, []);

  const refreshPhoneMetadataSnapshot = useCallback(async () => {
    setPhoneMetadataRefreshBusy(true);
    try {
      const snapshot = await loadPhoneMetadataSnapshot({ limitCalls: 8, limitSms: 8 });
      setPhoneMetadataSnapshot(snapshot);
      setPhoneMetadataStatus({
        ready: snapshot.ready,
        permissions: snapshot.permissions,
        missing_permissions: snapshot.missing_permissions,
        status_label: snapshot.status_label,
      });
      return snapshot;
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      setPhoneMetadataSnapshot(null);
      return null;
    } finally {
      setPhoneMetadataRefreshBusy(false);
    }
  }, []);

  const handleRequestPhoneMetadataPermissions = useCallback(async () => {
    setPhoneMetadataBusy(true);
    try {
      const status = await requestPhoneMetadataPermissions();
      setPhoneMetadataStatus(status);
      setLastResponse(
        status.ready
          ? "Android call log and SMS permissions granted. Butler can now inspect phone metadata."
          : "Permission request completed. Grant call log and SMS access to enable metadata ingest."
      );
      if (status.ready) {
        await refreshPhoneMetadataSnapshot();
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Permission request failed", message);
    } finally {
      setPhoneMetadataBusy(false);
    }
  }, [refreshPhoneMetadataSnapshot]);

  const handlePromotePhoneMetadataItem = useCallback(
    async (item: AndroidPhoneMetadataItem) => {
      if (!desktopPaired) {
        Alert.alert("Mac not paired", "Pair your Mac first so Butler can promote phone metadata into the review queue.");
        return;
      }

      const promoteKey = `${item.kind}:${item.timestamp_ms}:${item.title}`;
      setPhoneMetadataPromoteBusy(promoteKey);
      try {
        const result = await handleToolCall("capture_pending_context", {
          capture_kind: item.kind === "sms_thread" ? "sms_thread" : "call_log",
          title: item.title,
          content: buildPhoneMetadataReviewContent(item),
          confidence: item.kind === "sms_thread" ? 0.7 : 0.78,
          source_app: SOURCE_APP,
          source_device: SOURCE_DEVICE,
          source_hardware: SOURCE_HARDWARE,
          source_surface: item.kind === "sms_thread" ? "android.sms.review" : "android.call_log.review",
        });
        const parsed = unwrapToolResult(result);
        if (!parsed.ok) {
          throw new Error(parsed.error || "Failed to promote phone metadata.");
        }
        const output =
          parsed.output && typeof parsed.output === "object"
            ? (parsed.output as Record<string, unknown>)
            : {};
        const pendingId = compactText(String(output.id || ""));
        const queuedForMac = pendingId
          ? await queueRefForMac(`pending/${pendingId}`, item.title, {
              kind: "pending",
              summary: item.summary || item.title,
              metadata: {
                lane: "phone_metadata_promote",
                capture_kind: item.kind,
              },
              activateAct: false,
              alertOnError: false,
              setStatusMessage: false,
            })
          : false;
        focusMode(
          "review",
          queuedForMac
            ? `Promoted ${item.title} into pending review and queued it for your Mac.`
            : `Promoted ${item.title} into pending review.`
        );
        await refreshPendingQueue();
        await refreshActivityFeed();
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        setLastResponse(message);
        Alert.alert("Promotion failed", message);
      } finally {
        setPhoneMetadataPromoteBusy("");
      }
    },
    [desktopPaired, focusMode, handleToolCall, queueRefForMac, refreshActivityFeed, refreshPendingQueue, unwrapToolResult]
  );

  const handleSyncPhoneMetadata = useCallback(
    async (scope: "calls" | "sms" | "all") => {
      if (!desktopPaired) {
        Alert.alert("Mac not paired", "Pair your Mac first so Butler can write phone metadata into the trusted CRM graph.");
        return;
      }
      if (!phoneMetadataSnapshot?.ready) {
        Alert.alert("Metadata not ready", "Grant Android call log and SMS permissions first.");
        return;
      }

      const items =
        scope === "calls"
          ? phoneMetadataSnapshot.call_log
          : scope === "sms"
          ? phoneMetadataSnapshot.sms_threads
          : [...phoneMetadataSnapshot.call_log, ...phoneMetadataSnapshot.sms_threads];

      if (!items.length) {
        setLastResponse("No phone metadata items are available to sync yet.");
        return;
      }

      setPhoneMetadataSyncBusy(scope);
      try {
        let ingested = 0;
        let skipped = 0;
        let failed = 0;

        for (const item of items) {
          const result = await handleToolCall("relationship_ingest_phone_metadata", buildPhoneMetadataIngestArgs(item));
          const parsed = unwrapToolResult(result);
          if (!parsed.ok) {
            failed += 1;
            continue;
          }

          const output = parsed.output && typeof parsed.output === "object" ? (parsed.output as Record<string, unknown>) : {};
          if (output.skipped === true) {
            skipped += 1;
          } else {
            ingested += 1;
          }
        }

        setLastResponse(
          `Synced ${items.length} phone signals. Ingested ${ingested}, skipped ${skipped}, failed ${failed}.`
        );
        setActiveMode("review");
        await refreshFollowupQueue();
        await refreshPendingQueue();
        await refreshActivityFeed();
        await refreshContextMap();
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        setLastResponse(message);
        Alert.alert("Phone metadata sync failed", message);
      } finally {
        setPhoneMetadataSyncBusy("");
      }
    },
    [
      desktopPaired,
      handleToolCall,
      phoneMetadataSnapshot,
      refreshActivityFeed,
      refreshContextMap,
      refreshFollowupQueue,
      refreshPendingQueue,
      unwrapToolResult,
    ]
  );

  const handleTogglePin = useCallback(async (ref: string, pinned: boolean, label: string) => {
    if (!desktopPaired || !ref) {
      return;
    }

    setPinBusyRef(ref);
    try {
      const result = await handleToolCall("pin_context_ref", {
        ref,
        pinned: !pinned,
        label,
      });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to update pin.");
      }
      await refreshActivityFeed();
      await refreshFollowupQueue();
      await refreshContextMap();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Pin update failed", message);
    } finally {
      setPinBusyRef("");
    }
  }, [desktopPaired, handleToolCall, refreshActivityFeed, refreshContextMap, refreshFollowupQueue, unwrapToolResult]);

  const updateReviewStatus = useCallback((itemId: string, status: ReviewStatus) => {
    setReviewStatuses((prev) => ({
      ...prev,
      [itemId]: status,
    }));
  }, []);

  const prefillRelationshipFromPending = useCallback((item: PendingItem) => {
    const cleanedTitle = stripPendingPrefix(compactText(item.title));
    const cleanedContent = compactText(item.content || "");
    const inferredName =
      item.capture_kind === "person"
        ? cleanedTitle
        : cleanedTitle || cleanedContent.split(/[.?!\n]/, 1)[0] || item.capture_kind;
    const relationshipSeed = inferredName || "Pending review item";

    setRelationshipName((current) => current || relationshipSeed);
    setRelationshipConversationLabel((current) => current || cleanedTitle || item.capture_kind);
    setRelationshipSummary((current) => current || cleanedContent || item.title);
    setRelationshipNextAction((current) => current || `Confirm ${relationshipSeed} and decide the next step.`);
    setRelationshipOpenLoop((current) => current || `Promoted from pending review item ${item.id}.`);
  }, []);

  const movePendingIntoPeople = useCallback((item: PendingItem, message?: string) => {
    prefillRelationshipFromPending(item);
    focusMode(
      "people",
      message || `Prefilled ${item.title} into the People mode so you can finish the relationship record.`,
    );
  }, [focusMode, prefillRelationshipFromPending]);

  const handleReviewAnalyze = useCallback(async (item: PendingItem) => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can analyze pending items with the trusted desktop core.");
      return;
    }

    setReviewBusyId(item.id);
    try {
      const prompt = [
        "You are reviewing a pending Butler context item.",
        `Title: ${item.title}`,
        `Kind: ${item.capture_kind}`,
        item.confidence !== undefined ? `Confidence: ${Math.round(item.confidence * 100)}%` : "",
        item.content ? `Content: ${item.content}` : "",
        "",
        "Return a short correction recommendation with:",
        "- likely category",
        "- whether to promote, defer, dismiss, or pin",
        "- one sentence explaining why",
      ]
        .filter(Boolean)
        .join("\n");
      const result = await runCoreAgent(prompt, 4);
      const summary = summarizeBridgeOutput(result);
      setReviewInsights((prev) => ({
        ...prev,
        [item.id]: summary,
      }));
      updateReviewStatus(item.id, "new");
      setLastResponse(summary);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Review analysis failed", message);
    } finally {
      setReviewBusyId("");
    }
  }, [desktopPaired, updateReviewStatus]);

  const handleReviewPromote = useCallback(async (item: PendingItem) => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can promote reviewed context into the trusted repo.");
      return;
    }

    setReviewBusyId(item.id);
    try {
      const result = await handleToolCall("promote_pending_context", {
        pending_id: item.id,
      });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to promote pending item.");
      }
      const output =
        parsed.output && typeof parsed.output === "object"
          ? (parsed.output as Record<string, unknown>)
          : {};
      const sheet =
        output.sheet && typeof output.sheet === "object"
          ? (output.sheet as Record<string, unknown>)
          : null;
      const promotedRef = refFromContextSheet(sheet);
      const queuedForMac = promotedRef
        ? await queueRefForMac(promotedRef, item.title, {
            kind: inferRoomKindFromRef(promotedRef),
            summary: item.content || item.title,
            metadata: {
              lane: "review_promote",
              pending_id: item.id,
            },
            activateAct: false,
            alertOnError: false,
            setStatusMessage: false,
          })
        : false;
      movePendingIntoPeople(
        item,
        queuedForMac
          ? `Promoted "${item.title}" into canonical context, queued it for your Mac, and moved it into People so you can finish the relationship record.`
          : `Promoted "${item.title}" into canonical context and moved it into People so you can finish the relationship record.`
      );
      updateReviewStatus(item.id, "promoted");
      await refreshPendingQueue();
      await refreshActivityFeed();
      await refreshContextMap();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Promotion failed", message);
    } finally {
      setReviewBusyId("");
    }
  }, [
    desktopPaired,
    handleToolCall,
    movePendingIntoPeople,
    queueRefForMac,
    refreshActivityFeed,
    refreshContextMap,
    refreshPendingQueue,
    unwrapToolResult,
    updateReviewStatus,
  ]);

  const handleReviewDefer = useCallback(async (item: PendingItem) => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can defer the review item safely.");
      return;
    }

    setReviewBusyId(item.id);
    try {
      const result = await handleToolCall("defer_pending_context", {
        pending_id: item.id,
        defer_for_days: 3,
        note: "Deferred from mobile review lane.",
      });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to defer pending item.");
      }
      updateReviewStatus(item.id, "deferred");
      setReviewInsights((prev) => ({
        ...prev,
        [item.id]: prev[item.id] || "Deferred for three days from the mobile review lane.",
      }));
      setLastResponse(`Deferred "${item.title}" for later review.`);
      await refreshPendingQueue();
      await refreshActivityFeed();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Defer failed", message);
    } finally {
      setReviewBusyId("");
    }
  }, [desktopPaired, handleToolCall, refreshActivityFeed, refreshPendingQueue, unwrapToolResult, updateReviewStatus]);

  const handleReviewDismiss = useCallback(async (item: PendingItem) => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can dismiss the review item safely.");
      return;
    }

    setReviewBusyId(item.id);
    try {
      const result = await handleToolCall("dismiss_pending_context", {
        pending_id: item.id,
        note: "Dismissed from mobile review lane.",
      });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to dismiss pending item.");
      }
      updateReviewStatus(item.id, "dismissed");
      setReviewInsights((prev) => ({
        ...prev,
        [item.id]: prev[item.id] || "Dismissed from the mobile review lane.",
      }));
      setLastResponse(`Dismissed "${item.title}" from active review.`);
      await refreshPendingQueue();
      await refreshActivityFeed();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Dismiss failed", message);
    } finally {
      setReviewBusyId("");
    }
  }, [desktopPaired, handleToolCall, refreshActivityFeed, refreshPendingQueue, unwrapToolResult, updateReviewStatus]);

  const handleReviewRestore = useCallback(async (item: PendingItem) => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can restore the review item.");
      return;
    }

    setReviewBusyId(item.id);
    try {
      const result = await handleToolCall("restore_pending_context", {
        pending_id: item.id,
        note: "Restored from mobile review lane.",
      });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to restore pending item.");
      }
      updateReviewStatus(item.id, "new");
      setReviewInsights((prev) => ({
        ...prev,
        [item.id]: prev[item.id] || "Restored to the active review lane.",
      }));
      setLastResponse(`Restored "${item.title}" to active review.`);
      await refreshPendingQueue();
      await refreshActivityFeed();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Restore failed", message);
    } finally {
      setReviewBusyId("");
    }
  }, [desktopPaired, handleToolCall, refreshActivityFeed, refreshPendingQueue, unwrapToolResult, updateReviewStatus]);

  const handleRelationshipFieldPick = useCallback((kind: "channel" | "direction" | "type" | "stage" | "priority", value: string) => {
    if (kind === "channel") setRelationshipChannel(value);
    if (kind === "direction") setRelationshipDirection(value);
    if (kind === "type") setRelationshipType(value);
    if (kind === "stage") setRelationshipStage(value);
    if (kind === "priority") setRelationshipPriority(value);
  }, []);

  useEffect(() => {
    if (!desktopPaired) {
      setPendingItems([]);
      setFollowups([]);
      setActivityItems([]);
      setContextMap(null);
      setOpenclawStatus(null);
      setContinuityItems([]);
      setRooms([]);
      return;
    }
    refreshPendingQueue();
    refreshFollowupQueue();
    refreshActivityFeed();
    refreshContextMap();
    refreshOpenClawStatus({ silent: true });
    refreshContinuityInbox({ silent: true });
    refreshRooms({ silent: true });
  }, [desktopPaired, refreshPendingQueue, refreshFollowupQueue, refreshActivityFeed, refreshContextMap, refreshOpenClawStatus, refreshContinuityInbox, refreshRooms]);

  useEffect(() => {
    refreshPhoneMetadataStatus().then((status) => {
      if (status?.ready) {
        refreshPhoneMetadataSnapshot();
      }
    });
  }, [refreshPhoneMetadataSnapshot, refreshPhoneMetadataStatus]);

  const handleRelationshipLog = useCallback(async () => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can write trusted relationship records.");
      return;
    }

    const personName = compactText(relationshipName);
    const company = compactText(relationshipCompany);
    const role = compactText(relationshipRole);
    const placeName = compactText(relationshipPlaceName);
    const conversationLabel = compactText(relationshipConversationLabel);
    const channel = compactText(relationshipChannel) || "call";
    const direction = compactText(relationshipDirection) || "outbound";
    const relationshipTypeValue = compactText(relationshipType) || "lead";
    const stage = compactText(relationshipStage) || "new";
    const priority = compactText(relationshipPriority) || "medium";
    const phone = compactText(relationshipPhone);
    const email = compactText(relationshipEmail);
    const summary = compactText(relationshipSummary);
    const nextAction = compactText(relationshipNextAction);
    const nextActionDueAt = compactText(relationshipDueAt);
    const followUpInDays = compactText(relationshipFollowUpInDays);
    const openLoop = compactText(relationshipOpenLoop);
    const notes = compactText(relationshipNotes);
    const tagsCsv = normalizeTagsCsv(relationshipTagsCsv);

    if (!personName) {
      Alert.alert("Name missing", "Enter the person's name before logging the interaction.");
      return;
    }
    if (!summary) {
      Alert.alert("Summary missing", "Add a short summary so the CRM record is trustworthy later.");
      return;
    }
    if (!nextAction) {
      Alert.alert("Next action missing", "Add the next action so the follow-up queue stays useful.");
      return;
    }

    setRelationshipBusy(true);
    try {
      const result = await handleToolCall("relationship_log_interaction", {
        person_name: personName,
        company,
        role,
        place_name: placeName,
        conversation_label: conversationLabel,
        channel,
        phone,
        email,
        relationship_type: relationshipTypeValue,
        stage,
        priority,
        direction,
        summary,
        next_action: nextAction,
        next_action_due_at: nextActionDueAt,
        follow_up_in_days: followUpInDays !== "" ? Number(followUpInDays) : undefined,
        open_loop: openLoop,
        notes,
        tags_csv: tagsCsv,
        source_app: SOURCE_APP,
        source_device: SOURCE_DEVICE,
        source_surface: SOURCE_SURFACE,
      });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to log relationship interaction.");
      }
      const output =
        parsed.output && typeof parsed.output === "object"
          ? (parsed.output as Record<string, unknown>)
          : {};
      const followup =
        output.followup && typeof output.followup === "object"
          ? (output.followup as Record<string, unknown>)
          : null;
      const personSheet =
        output.person_sheet && typeof output.person_sheet === "object"
          ? (output.person_sheet as Record<string, unknown>)
          : null;
      const personRef =
        compactText(String((followup && followup.person_ref) || "")) || refFromContextSheet(personSheet);
      const queuedForMac = personRef
        ? await queueRefForMac(personRef, personName, {
            kind: "person",
            summary,
            metadata: {
              lane: "relationship_log",
              next_action: nextAction,
              place_ref: compactText(String((followup && followup.place_ref) || "")),
              conversation_ref: compactText(String((followup && followup.conversation_ref) || "")),
            },
            activateAct: false,
            alertOnError: false,
            setStatusMessage: false,
          })
        : false;

      setRelationshipName("");
      setRelationshipCompany("");
      setRelationshipRole("");
      setRelationshipPlaceName("");
      setRelationshipConversationLabel("");
      setRelationshipChannel("call");
      setRelationshipDirection("outbound");
      setRelationshipType("lead");
      setRelationshipStage("new");
      setRelationshipPriority("medium");
      setRelationshipPhone("");
      setRelationshipEmail("");
      setRelationshipSummary("");
      setRelationshipNextAction("");
      setRelationshipDueAt("");
      setRelationshipFollowUpInDays("");
      setRelationshipOpenLoop("");
      setRelationshipNotes("");
      setRelationshipTagsCsv("");
      setLastUtterance(`Relationship: ${personName}`);
      focusMode(
        "people",
        queuedForMac
          ? `Logged ${personName}, refreshed the follow-up queue, and queued the relationship room for your Mac.`
          : `Logged ${personName} and refreshed the follow-up queue.`
      );
      await refreshFollowupQueue();
      await refreshActivityFeed();
      await refreshContextMap();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Relationship log failed", message);
    } finally {
      setRelationshipBusy(false);
    }
  }, [
    desktopPaired,
    handleToolCall,
    relationshipChannel,
    relationshipCompany,
    relationshipConversationLabel,
    relationshipName,
    relationshipDirection,
    relationshipPlaceName,
    relationshipType,
    relationshipStage,
    relationshipPriority,
    relationshipPhone,
    relationshipEmail,
    relationshipNextAction,
    relationshipRole,
    relationshipDueAt,
    relationshipFollowUpInDays,
    relationshipOpenLoop,
    relationshipSummary,
    relationshipNotes,
    relationshipTagsCsv,
    focusMode,
    queueRefForMac,
    refreshActivityFeed,
    refreshContextMap,
    refreshFollowupQueue,
    unwrapToolResult,
  ]);

  const handleImportContacts = useCallback(async () => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so Butler can import trusted contacts from the desktop.");
      return;
    }

    setContactImportBusy(true);
    try {
      const result = await handleToolCall("relationship_import_contacts", { limit: 200 });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to import contacts.");
      }

      const output = (parsed.output && typeof parsed.output === "object") ? (parsed.output as Record<string, unknown>) : {};
      const importedCount = Number(output.imported_count || 0);
      const created = Number(output.created || 0);
      const updated = Number(output.updated || 0);
      setLastUtterance("Import contacts");
      focusMode("people", `Imported ${importedCount} desktop contacts into the CRM graph. Created ${created}, updated ${updated}.`);
      await refreshFollowupQueue();
      await refreshActivityFeed();
      await refreshContextMap();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Contact import failed", message);
    } finally {
      setContactImportBusy(false);
    }
  }, [desktopPaired, focusMode, handleToolCall, refreshActivityFeed, refreshContextMap, refreshFollowupQueue, unwrapToolResult]);

  const selectCaptureMedia = useCallback(
    async (source: "camera" | "library") => {
      if (!desktopPaired) {
        Alert.alert("Mac not paired", "Pair your Mac first so the phone can write into the trusted context repository.");
        return;
      }

      const permissionResult =
        source === "camera"
          ? await ImagePicker.requestCameraPermissionsAsync()
          : await ImagePicker.requestMediaLibraryPermissionsAsync();

      if (!permissionResult.granted) {
        Alert.alert(
          source === "camera" ? "Camera permission needed" : "Photo library permission needed",
          "Butler needs access to your photos so receipts and artifacts can be turned into pending context captures."
        );
        return;
      }

      const pickerResult =
        source === "camera"
          ? await ImagePicker.launchCameraAsync({
              mediaTypes: ImagePicker.MediaTypeOptions.Images,
              allowsEditing: false,
              quality: 0.85,
              base64: true,
            })
          : await ImagePicker.launchImageLibraryAsync({
              mediaTypes: ImagePicker.MediaTypeOptions.Images,
              allowsEditing: false,
              quality: 0.85,
              base64: true,
            });

      if (pickerResult.canceled || !pickerResult.assets?.length) {
        return;
      }

      const asset = pickerResult.assets[0];
      if (!asset.base64) {
        Alert.alert("Capture missing data", "The selected image did not include upload data. Try another photo or capture again.");
        return;
      }

      const fileName = asset.fileName || `capture-${Date.now()}.jpg`;
      const mimeType = asset.mimeType || "image/jpeg";
      setSelectedCapture({
        uri: asset.uri,
        fileName,
        mimeType,
        base64: asset.base64,
        source,
        width: asset.width,
        height: asset.height,
      });
      setCaptureTitle((current) => current.trim() || buildDefaultCaptureTitle(captureKind, fileName));
      setLastResponse(
        source === "camera"
          ? "Photo captured. Add a title or note, then send it to pending review."
          : "Photo selected from your library. Add a title or note, then send it to pending review."
      );
    },
    [captureKind, desktopPaired]
  );

  const handleCapturePending = useCallback(async () => {
    if (!desktopPaired) {
      Alert.alert("Mac not paired", "Pair your Mac first so the phone can write into the trusted context repository.");
      return;
    }
    const title = captureTitle.trim() || (selectedCapture ? buildDefaultCaptureTitle(captureKind, selectedCapture.fileName) : "");
    const content = captureContent.trim();

    if (!title) {
      Alert.alert("Title missing", "Give this capture a short label so it is easy to review later.");
      return;
    }

    if (!selectedCapture && !content) {
      Alert.alert(
        "Add context",
        "Take a photo, pick a photo, or add a note so this pending item has something useful to review later."
      );
      return;
    }

    setCaptureBusy(true);
    try {
      const captureOrigin = selectedCapture ? selectedCapture.source : "manual note";
      const result = await captureContext({
        capture_kind: captureKind,
        title,
        content,
        file_name: selectedCapture?.fileName || "",
        mime_type: selectedCapture?.mimeType || "",
        data_base64: selectedCapture?.base64 || "",
        source_app: SOURCE_APP,
        source_device: SOURCE_DEVICE,
        source_surface: SOURCE_SURFACE,
      });
      const parsed = unwrapToolResult(result);
      if (!parsed.ok) {
        throw new Error(parsed.error || "Failed to capture pending context.");
      }
      const output =
        parsed.output && typeof parsed.output === "object"
          ? (parsed.output as Record<string, unknown>)
          : {};
      const pendingItem =
        output.pending_item && typeof output.pending_item === "object"
          ? (output.pending_item as Record<string, unknown>)
          : null;
      const pendingId = compactText(String((pendingItem && pendingItem.id) || ""));
      const queuedForMac = pendingId
        ? await queueRefForMac(`pending/${pendingId}`, title, {
            kind: "pending",
            summary: content || title,
            metadata: {
              lane: "capture_pending",
              capture_kind: captureKind,
              capture_source: captureOrigin,
            },
            activateAct: false,
            alertOnError: false,
            setStatusMessage: false,
          })
        : false;

      setCaptureTitle("");
      setCaptureContent("");
      setSelectedCapture(null);
      setLastUtterance(`Capture: ${captureKind}`);
      const baseMessage =
        typeof result === "string"
          ? result
          : `Saved "${title}" to pending review from ${captureOrigin}.`;
      focusMode(
        "review",
        queuedForMac ? `${baseMessage} Queued it for your Mac.` : baseMessage
      );
      await refreshPendingQueue();
      await refreshActivityFeed();
      await refreshContextMap();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLastResponse(message);
      Alert.alert("Capture failed", message);
    } finally {
      setCaptureBusy(false);
    }
  }, [
    captureContent,
    captureKind,
    captureTitle,
    desktopPaired,
    focusMode,
    refreshActivityFeed,
    refreshContextMap,
    queueRefForMac,
    selectedCapture,
    refreshPendingQueue,
    unwrapToolResult,
  ]);

  const clearSelectedCapture = useCallback(() => {
    setSelectedCapture(null);
    setLastResponse("Attachment cleared. You can take a new photo or keep this as a note.");
  }, []);

  const statusColor =
    voiceStatus === "listening"
      ? "#00e39a"
      : voiceStatus === "thinking"
      ? "#00d4ff"
      : voiceStatus === "speaking"
      ? "#f4b7ff"
      : voiceStatus === "error"
      ? "#ff5d73"
      : "#7f8ba1";

  const liveContinuityItems = useMemo(
    () => continuityItems.filter((item) => item.status !== "consumed"),
    [continuityItems]
  );

  const continuitySpotlightItem = useMemo(
    () => liveContinuityItems.find((item) => item.id === activeContinuityPacketId) ?? liveContinuityItems[0] ?? null,
    [activeContinuityPacketId, liveContinuityItems]
  );

  const focusedRoom = useMemo(
    () => rooms.find((room) => room.room_id === activeRoomId) ?? rooms[0] ?? null,
    [activeRoomId, rooms]
  );

  const reviewPendingItems = [...pendingItems].sort((left, right) => {
    const rank = (status?: ReviewStatus) => {
      switch (status) {
        case "promoted":
          return 3;
        case "deferred":
          return 2;
        case "dismissed":
          return 1;
        default:
          return 0;
      }
    };
    const leftRank = rank(reviewStatusFromPending(left, reviewStatuses));
    const rightRank = rank(reviewStatusFromPending(right, reviewStatuses));
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return (right.created_at || "").localeCompare(left.created_at || "");
  });

  const metadataIngestCalls = toolCalls.filter((call) => METADATA_INGEST_TOOL_NAMES.has(call.toolName));
  const activePendingCount = reviewPendingItems.filter((item) => reviewStatusFromPending(item, reviewStatuses) === "new").length;
  const promotedCount = reviewPendingItems.filter((item) => reviewStatusFromPending(item, reviewStatuses) === "promoted").length;
  const visibleModuleIds = useMemo(
    () => availableModuleIds(currentSkin.moduleIds, { desktopPaired, platformOS: Platform.OS }),
    [currentSkin.moduleIds, desktopPaired]
  );
  const enabledModules = useMemo(() => new Set(visibleModuleIds), [visibleModuleIds]);
  const availableModes = useMemo(() => modesForModuleIds(visibleModuleIds), [visibleModuleIds]);
  const activeRecipes = useMemo(
    () =>
      currentSkin.recipeIds
        .map((id) => RECIPES[id])
        .filter((recipe) => !recipe.requiresPairing || desktopPaired),
    [currentSkin.recipeIds, desktopPaired]
  );
  const activeModeMeta = PHONE_MODE_META[activeMode];
  const openclawGatewayRunning = Boolean(openclawStatus?.gateway?.running);
  const openclawRemoteActive = Boolean(openclawStatus?.remote?.configured);
  const openclawReady =
    typeof openclawStatus?.ready === "boolean"
      ? openclawStatus.ready
      : Boolean(openclawStatus?.openclaw_installed) && openclawGatewayRunning;

  useEffect(() => {
    const remote = openclawStatus?.remote;
    if (!remote?.configured) {
      return;
    }
    if (remote.endpoint) {
      setOpenclawRemoteRpcUrl(remote.endpoint);
    }
    if (remote.label) {
      setOpenclawRemoteLabel(remote.label);
    }
  }, [openclawStatus]);

  useEffect(() => {
    if (!availableModes.length || availableModes.includes(activeMode)) {
      return;
    }
    const fallbackMode = availableModes.includes(currentSkin.defaultMode) ? currentSkin.defaultMode : availableModes[0];
    setActiveMode(fallbackMode);
  }, [activeMode, availableModes, currentSkin.defaultMode]);
  const homeHeadline =
    followups.length > 0
      ? `${getFollowupName(followups[0])} is the strongest next relationship move.`
      : activePendingCount > 0
      ? `${activePendingCount} item${activePendingCount === 1 ? "" : "s"} still need review before Butler should learn from them.`
      : "The lane is clear right now. Capture something or run a recipe to keep Butler useful.";
  const homeSecondary =
    phoneMetadataSnapshot?.review_queue?.length
      ? `${phoneMetadataSnapshot.review_queue.length} phone-native metadata items are waiting to be promoted into the main review lane.`
      : desktopPaired
      ? "Your Mac is paired, so the phone can stay lightweight while the desktop remains the trusted execution arm."
      : "Pair your Mac to unlock the trusted execution plane and turn the phone into a real operator surface.";

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <View style={styles.heroCard}>
          <Text style={styles.eyebrow}>aiButler mobile</Text>
          <Text style={styles.title}>Your CRM AI companion in your pocket</Text>
          <Text style={styles.subtitle}>
            Keep relationship context close, trigger follow-ups from your phone, and hand work off to your trusted desktop Butler when it is time to act.
          </Text>
          <View style={styles.metaRow}>
            <Text style={[styles.metaBadge, desktopPaired ? styles.metaBadgeReady : styles.metaBadgeBlocked]}>
              {desktopPaired ? "Mac paired" : "Mac not paired"}
            </Text>
            <Text style={styles.metaText}>
              {discoveredHost ? `Found: ${discoveredHost}` : "Looking for your Mac on the local network"}
            </Text>
          </View>
        </View>

        <View style={styles.modeRail}>
          {availableModes.map((typedMode) => {
            const meta = PHONE_MODE_META[typedMode];
            const active = typedMode === activeMode;
            const badgeCount =
              typedMode === "review"
                ? activePendingCount
                : typedMode === "act"
                ? liveContinuityItems.length
                : 0;
            return (
              <TouchableOpacity
                key={typedMode}
                style={[styles.modeChip, active && styles.modeChipActive, active && { borderColor: currentSkin.accent }]}
                onPress={() => setActiveMode(typedMode)}
              >
                <Text style={[styles.modeChipText, active && styles.modeChipTextActive]}>
                  {badgeCount > 0 ? `${meta.label} · ${badgeCount}` : meta.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={styles.card}>
          <Text style={[styles.cardEyebrow, { color: currentSkin.accent }]}>{currentSkin.name} skin</Text>
          <Text style={styles.cardTitle}>{activeModeMeta.title}</Text>
          <Text style={styles.cardBody}>{activeModeMeta.description}</Text>
          <Text style={styles.captureHint}>{currentSkin.tagline}</Text>
          <View style={styles.skinRail}>
            {PHONE_SKINS.map((skin) => {
              const active = skin.id === currentSkin.id;
              return (
                <TouchableOpacity
                  key={skin.id}
                  style={[styles.skinChip, active && styles.skinChipActive, active && { borderColor: skin.accent }]}
                  onPress={() => handleSkinChange(skin.id)}
                >
                  <Text style={[styles.skinChipText, active && styles.skinChipTextActive]}>{skin.name}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {activeMode === "home" && enabledModules.has("hero_brief") ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Today at a glance</Text>
            <Text style={styles.cardBody}>{homeHeadline}</Text>
            <Text style={styles.captureHint}>{homeSecondary}</Text>
            <View style={styles.reviewSummaryRow}>
              <Text style={styles.reviewSummaryPill}>{followups.length} follow-ups</Text>
              <Text style={styles.reviewSummaryText}>{activePendingCount} active review</Text>
              <Text style={styles.reviewSummaryText}>{toolCalls.length} recent actions</Text>
            </View>
          </View>
        ) : null}

        {activeMode === "act" && enabledModules.has("pairing") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Secure Mac pairing</Text>
          <Text style={styles.cardBody}>
            Butler uses a pairing token before your phone can reach the desktop bridge. That keeps phone convenience without turning your Mac into an open API.
          </Text>
          <TextInput
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="http://aibutler.local:8765 or 192.168.1.50:8765"
            placeholderTextColor="#5f6b84"
            style={styles.input}
            value={pairingHost}
            onChangeText={setPairingHost}
          />
          <TextInput
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="Paste pairing token from your Mac"
            placeholderTextColor="#5f6b84"
            secureTextEntry
            style={styles.input}
            value={pairingToken}
            onChangeText={setPairingToken}
          />
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.primaryButton, pairingBusy && styles.buttonDisabled]}
              disabled={pairingBusy}
              onPress={handlePairDesktop}
            >
              <Text style={styles.primaryButtonText}>{pairingBusy ? "Pairing..." : "Pair Mac"}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryButton} onPress={handleDisconnectDesktop}>
              <Text style={styles.secondaryButtonText}>Disconnect</Text>
            </TouchableOpacity>
          </View>
        </View>
        ) : null}

        {activeMode === "act" ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Continuity lane</Text>
          <Text style={styles.cardBody}>
            Hand work between the phone and Mac without losing the thread. Butler keeps a small inbox of packets while giving you direct clipboard handoff when you want zero friction.
          </Text>
          <View style={styles.reviewSummaryRow}>
            <Text style={[styles.metaBadge, desktopPaired ? styles.metaBadgeReady : styles.metaBadgeBlocked]}>
              {desktopPaired ? "Bridge online" : "Bridge offline"}
            </Text>
            <Text style={styles.reviewSummaryText}>
              {liveContinuityItems.length} live packet
              {liveContinuityItems.length === 1 ? "" : "s"}
            </Text>
          </View>
          {continuitySpotlightItem ? (
            <View style={styles.spotlightPanel}>
              <Text style={styles.spotlightLabel}>Current handoff</Text>
              <Text style={styles.spotlightTitle}>{continuitySpotlightItem.title}</Text>
              <Text style={styles.spotlightMeta}>
                {[continuitySpotlightItem.kind, continuitySpotlightItem.status || "pending"].filter(Boolean).join(" • ")}
                {continuitySpotlightItem.updated_at ? ` • ${formatMetadataTimestamp(continuitySpotlightItem.updated_at)}` : ""}
              </Text>
            </View>
          ) : null}
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.secondaryButton, continuityBusy && styles.buttonDisabled]}
              disabled={!desktopPaired || continuityBusy || continuityActionBusy !== ""}
              onPress={() => refreshContinuityInbox()}
            >
              <Text style={styles.secondaryButtonText}>{continuityBusy ? "Refreshing..." : "Refresh Inbox"}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, continuityActionBusy === "push-clipboard" && styles.buttonDisabled]}
              disabled={!desktopPaired || continuityActionBusy !== ""}
              onPress={handleSendPhoneClipboardToMac}
            >
              <Text style={styles.primaryButtonText}>
                {continuityActionBusy === "push-clipboard" ? "Sending..." : "Phone → Mac Clipboard"}
              </Text>
            </TouchableOpacity>
          </View>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.secondaryButton, continuityActionBusy === "pull-clipboard" && styles.buttonDisabled]}
              disabled={!desktopPaired || continuityActionBusy !== ""}
              onPress={handlePullMacClipboardToPhone}
            >
              <Text style={styles.secondaryButtonText}>
                {continuityActionBusy === "pull-clipboard" ? "Pulling..." : "Mac → Phone Clipboard"}
              </Text>
            </TouchableOpacity>
          </View>
          <View style={styles.sectionGroup}>
            <TextInput
              autoCapitalize="sentences"
              autoCorrect
              placeholder="Quick handoff title"
              placeholderTextColor="#5f6b84"
              style={styles.input}
              value={continuityTitle}
              onChangeText={setContinuityTitle}
            />
            <TextInput
              autoCapitalize="sentences"
              autoCorrect
              multiline
              placeholder="Send a note, draft, or breadcrumb to the other device"
              placeholderTextColor="#5f6b84"
              style={[styles.input, styles.textArea]}
              value={continuityNote}
              onChangeText={setContinuityNote}
            />
            <View style={styles.buttonRow}>
              <TouchableOpacity
                style={[styles.primaryButton, continuityActionBusy === "send-note" && styles.buttonDisabled]}
                disabled={!desktopPaired || continuityActionBusy !== ""}
                onPress={handleSendContinuityNote}
              >
                <Text style={styles.primaryButtonText}>
                  {continuityActionBusy === "send-note" ? "Sending..." : "Send Note To Mac"}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
          {!desktopPaired ? (
            <Text style={styles.captureHint}>
              Pair your Mac first. Continuity packets ride over the trusted Butler bridge so the phone and desktop stay in one execution thread.
            </Text>
          ) : null}
          {continuityItems.length ? (
            <View style={styles.pendingList}>
              {continuityItems.map((packet) => (
                <View
                  key={packet.id}
                  style={[styles.pendingRow, activeContinuityPacketId === packet.id && styles.pendingRowActive]}
                >
                  <View style={styles.pendingHeaderRow}>
                    <View style={styles.pendingMeta}>
                      {activeContinuityPacketId === packet.id ? (
                        <Text style={[styles.metaBadge, styles.metaBadgeReady]}>Current handoff</Text>
                      ) : null}
                      <Text style={styles.pendingTitle}>{packet.title}</Text>
                      <Text style={styles.pendingKind}>
                        {[packet.kind, packet.source_device, packet.status].filter(Boolean).join(" • ")}
                        {packet.updated_at ? ` • ${formatMetadataTimestamp(packet.updated_at)}` : ""}
                      </Text>
                    </View>
                  </View>
                  {packet.room_id ? <Text style={styles.feedMeta}>Room {packet.room_id}</Text> : null}
                  {packet.lease_owner ? (
                    <Text style={styles.feedMeta}>
                      Claimed by {packet.lease_owner}
                      {packet.lease_expires_at ? ` until ${formatMetadataTimestamp(packet.lease_expires_at)}` : ""}
                    </Text>
                  ) : null}
                  {packet.refs?.length ? (
                    <Text style={styles.feedMeta}>Refs {packet.refs.slice(0, 3).join(" · ")}</Text>
                  ) : null}
                  {packet.content ? (
                    <Text style={styles.pendingContent} numberOfLines={3}>
                      {packet.content}
                    </Text>
                  ) : null}
                  <View style={styles.buttonRow}>
                    {packet.room_id ? (
                      <TouchableOpacity
                        style={styles.secondaryButton}
                        disabled={continuityActionBusy !== ""}
                        onPress={() => handleFocusRoom(packet.room_id || "", packet.title)}
                      >
                        <Text style={styles.secondaryButtonText}>
                          {activeRoomId === packet.room_id ? "Room Focused" : "Focus Room"}
                        </Text>
                      </TouchableOpacity>
                    ) : null}
                    {packet.status !== "consumed" ? (
                      <TouchableOpacity
                        style={[styles.secondaryButton, continuityActionBusy === `claim:${packet.id}` && styles.buttonDisabled]}
                        disabled={continuityActionBusy !== ""}
                        onPress={() => handleClaimContinuityPacket(packet.id)}
                      >
                        <Text style={styles.secondaryButtonText}>
                          {continuityActionBusy === `claim:${packet.id}` ? "Claiming..." : "Claim"}
                        </Text>
                      </TouchableOpacity>
                    ) : null}
                    <TouchableOpacity
                      style={[styles.secondaryButton, continuityActionBusy === `copy:${packet.id}` && styles.buttonDisabled]}
                      disabled={continuityActionBusy !== ""}
                      onPress={() => handleCopyContinuityPacket(packet)}
                    >
                      <Text style={styles.secondaryButtonText}>
                        {continuityActionBusy === `copy:${packet.id}` ? "Copying..." : "Copy To Phone"}
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.captureHint}>
              No handoff packets yet. Start by sending a clipboard snippet or quick note to your Mac.
            </Text>
          )}
        </View>
        ) : null}

        {activeMode === "act" && enabledModules.has("room_workspace") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Canonical rooms</Text>
          <Text style={styles.cardBody}>
            Rooms are now first-class Butler objects. Create them here, then hand them to the Mac or DewDrops without inventing separate IDs or desktop-only state.
          </Text>
          <View style={styles.reviewSummaryRow}>
            <Text style={[styles.metaBadge, desktopPaired ? styles.metaBadgeReady : styles.metaBadgeBlocked]}>
              {desktopPaired ? "Room API online" : "Pairing required"}
            </Text>
            <Text style={styles.reviewSummaryText}>{rooms.length} recent room{rooms.length === 1 ? "" : "s"}</Text>
          </View>
          {focusedRoom ? (
            <View style={styles.spotlightPanel}>
              <Text style={styles.spotlightLabel}>Focused room</Text>
              <Text style={styles.spotlightTitle}>{focusedRoom.title}</Text>
              <Text style={styles.spotlightMeta}>
                {[focusedRoom.kind, focusedRoom.status, focusedRoom.current_published_version ? "published" : "draft-only"]
                  .filter(Boolean)
                  .join(" • ")}
              </Text>
            </View>
          ) : null}
          <TextInput
            autoCapitalize="sentences"
            autoCorrect
            placeholder="Room title"
            placeholderTextColor="#5f6b84"
            style={styles.input}
            value={roomTitle}
            onChangeText={setRoomTitle}
          />
          <View style={styles.buttonRow}>
            {["project", "person", "conversation"].map((kind) => {
              const active = roomKind === kind;
              return (
                <TouchableOpacity
                  key={kind}
                  style={[styles.secondaryButton, active && { borderColor: currentSkin.accent }]}
                  onPress={() => setRoomKind(kind)}
                >
                  <Text style={styles.secondaryButtonText}>{kind}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          <TextInput
            autoCapitalize="sentences"
            autoCorrect
            multiline
            placeholder="Seed note for the first draft version"
            placeholderTextColor="#5f6b84"
            style={[styles.input, styles.textArea]}
            value={roomSeedNote}
            onChangeText={setRoomSeedNote}
          />
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.secondaryButton, roomsBusy && styles.buttonDisabled]}
              disabled={!desktopPaired || roomsBusy || roomActionBusy !== ""}
              onPress={() => refreshRooms()}
            >
              <Text style={styles.secondaryButtonText}>{roomsBusy ? "Refreshing..." : "Refresh Rooms"}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, roomActionBusy === "create-room" && styles.buttonDisabled]}
              disabled={!desktopPaired || roomActionBusy !== ""}
              onPress={handleCreateRoom}
            >
              <Text style={styles.primaryButtonText}>
                {roomActionBusy === "create-room" ? "Creating..." : "Create Room"}
              </Text>
            </TouchableOpacity>
          </View>
          {rooms.length ? (
            <View style={styles.pendingList}>
              {rooms.map((room) => (
                <View
                  key={room.room_id}
                  style={[styles.pendingRow, activeRoomId === room.room_id && styles.pendingRowActive]}
                >
                  <View style={styles.pendingHeaderRow}>
                    <View style={styles.pendingMeta}>
                      {activeRoomId === room.room_id ? (
                        <Text style={[styles.metaBadge, styles.metaBadgeReady]}>Focused room</Text>
                      ) : null}
                      <Text style={styles.pendingTitle}>{room.title}</Text>
                      <Text style={styles.pendingKind}>
                        {[room.kind, room.status, room.current_published_version ? "published" : "draft-only"].filter(Boolean).join(" • ")}
                      </Text>
                    </View>
                  </View>
                  {room.source_refs?.length ? (
                    <Text style={styles.feedMeta}>Refs {room.source_refs.slice(0, 3).join(" · ")}</Text>
                  ) : null}
                  <Text style={styles.feedMeta}>ID {room.room_id}</Text>
                  <View style={styles.buttonRow}>
                    <TouchableOpacity
                      style={styles.secondaryButton}
                      disabled={!desktopPaired || roomActionBusy !== ""}
                      onPress={() => handleFocusRoom(room.room_id, room.title)}
                    >
                      <Text style={styles.secondaryButtonText}>
                        {activeRoomId === room.room_id ? "Focused" : "Focus"}
                      </Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.secondaryButton, roomActionBusy === `handoff-room:${room.room_id}` && styles.buttonDisabled]}
                      disabled={!desktopPaired || roomActionBusy !== ""}
                      onPress={() => handleSendRoomToMac(room)}
                    >
                      <Text style={styles.secondaryButtonText}>
                        {roomActionBusy === `handoff-room:${room.room_id}` ? "Sending..." : "Send To Mac"}
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.captureHint}>
              No canonical rooms yet. Create one here to start the real Butler/DewDrops seam.
            </Text>
          )}
        </View>
        ) : null}

        {activeMode === "act" && enabledModules.has("operator_stack") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Operator stack</Text>
          <Text style={styles.cardBody}>
            OpenClaw is Butler&apos;s built-in operator layer. The phone stays lightweight while Butler reaches either the paired Mac or a shared VPN-backed operator environment for the heavier agent, gateway, and plugin fabric underneath it.
          </Text>
          <View style={styles.reviewSummaryRow}>
            <Text style={styles.reviewSummaryPill}>
              {openclawStatus?.openclaw_installed ? "OpenClaw ready" : "OpenClaw missing"}
            </Text>
            <Text style={styles.reviewSummaryText}>
              {openclawGatewayRunning ? "Gateway online" : "Gateway not ready"}
            </Text>
            <Text style={styles.reviewSummaryText}>
              {openclawRemoteActive ? "Remote mode" : "Local mode"}
            </Text>
            <Text style={styles.reviewSummaryText}>
              {openclawStatus?.rtk_plugin_installed ? "RTK plugin installed" : "RTK optional"}
            </Text>
          </View>
          <View style={styles.sectionGroup}>
            <Text style={styles.relationshipLabel}>Shared VPN operator</Text>
            <TextInput
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              placeholder="ws://10.0.0.15:18789/rpc"
              placeholderTextColor="#5f6b84"
              style={styles.input}
              value={openclawRemoteRpcUrl}
              onChangeText={setOpenclawRemoteRpcUrl}
            />
            <TextInput
              autoCapitalize="words"
              autoCorrect
              placeholder="Shared VPN operator"
              placeholderTextColor="#5f6b84"
              style={styles.input}
              value={openclawRemoteLabel}
              onChangeText={setOpenclawRemoteLabel}
            />
            <Text style={styles.captureHint}>
              Point Butler at a VPN-reachable OpenClaw RPC endpoint when you want the heavy operator stack to live in one shared private environment.
            </Text>
          </View>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.secondaryButton, openclawBusy && styles.buttonDisabled]}
              disabled={openclawBusy || openclawActionBusy !== ""}
              onPress={() => refreshOpenClawStatus()}
            >
              <Text style={styles.secondaryButtonText}>{openclawBusy ? "Refreshing..." : "Refresh Stack"}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, openclawActionBusy === "install" && styles.buttonDisabled]}
              disabled={openclawActionBusy !== ""}
              onPress={() =>
                runOpenClawAction("install", "install_openclaw", {}, {
                  successTitle: "OpenClaw install completed",
                  failureTitle: "OpenClaw install failed",
                })
              }
            >
              <Text style={styles.primaryButtonText}>
                {openclawActionBusy === "install" ? "Installing..." : "Install OpenClaw"}
              </Text>
            </TouchableOpacity>
          </View>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.primaryButton, openclawActionBusy === "remote-config" && styles.buttonDisabled]}
              disabled={openclawActionBusy !== ""}
              onPress={handleConfigureOpenClawRemote}
            >
              <Text style={styles.primaryButtonText}>
                {openclawActionBusy === "remote-config" ? "Saving..." : "Use VPN Endpoint"}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.secondaryButton, openclawActionBusy === "remote-clear" && styles.buttonDisabled]}
              disabled={openclawActionBusy !== ""}
              onPress={handleClearOpenClawRemote}
            >
              <Text style={styles.secondaryButtonText}>
                {openclawActionBusy === "remote-clear" ? "Clearing..." : "Clear Remote Mode"}
              </Text>
            </TouchableOpacity>
          </View>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.secondaryButton, openclawActionBusy === "gateway" && styles.buttonDisabled]}
              disabled={openclawActionBusy !== ""}
              onPress={() =>
                runOpenClawAction("gateway", "openclaw_gateway_install", {}, {
                  successTitle: "OpenClaw gateway install completed",
                  failureTitle: "Gateway install failed",
                })
              }
            >
              <Text style={styles.secondaryButtonText}>
                {openclawActionBusy === "gateway" ? "Installing..." : "Install Gateway"}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.secondaryButton, openclawActionBusy === "local-mode" && styles.buttonDisabled]}
              disabled={openclawActionBusy !== ""}
              onPress={() =>
                runOpenClawAction("local-mode", "openclaw_configure_local_gateway", {}, {
                  successTitle: "OpenClaw local gateway mode configured",
                  failureTitle: "Local gateway configuration failed",
                })
              }
            >
              <Text style={styles.secondaryButtonText}>
                {openclawActionBusy === "local-mode" ? "Configuring..." : "Set Local Mode"}
              </Text>
            </TouchableOpacity>
          </View>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.secondaryButton, openclawActionBusy === "restart" && styles.buttonDisabled]}
              disabled={openclawActionBusy !== ""}
              onPress={() =>
                runOpenClawAction("restart", "openclaw_gateway_restart", {}, {
                  successTitle: "OpenClaw gateway restart completed",
                  failureTitle: "Gateway restart failed",
                })
              }
            >
              <Text style={styles.secondaryButtonText}>
                {openclawActionBusy === "restart" ? "Restarting..." : "Restart Gateway"}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.secondaryButton, openclawActionBusy === "doctor" && styles.buttonDisabled]}
              disabled={openclawActionBusy !== ""}
              onPress={() =>
                runOpenClawAction("doctor", "openclaw_doctor", { apply_fixes: true }, {
                  successTitle: "OpenClaw doctor completed",
                  failureTitle: "OpenClaw doctor failed",
                })
              }
            >
              <Text style={styles.secondaryButtonText}>
                {openclawActionBusy === "doctor" ? "Running..." : "Run Doctor"}
              </Text>
            </TouchableOpacity>
          </View>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.secondaryButton, openclawActionBusy === "rtk" && styles.buttonDisabled]}
              disabled={openclawActionBusy !== ""}
              onPress={() =>
                runOpenClawAction("rtk", "install_rtk_openclaw_plugin", {}, {
                  successTitle: "RTK plugin install staged",
                  failureTitle: "RTK plugin install failed",
                })
              }
            >
              <Text style={styles.secondaryButtonText}>
                {openclawActionBusy === "rtk" ? "Staging..." : "Install RTK Plugin"}
              </Text>
            </TouchableOpacity>
          </View>
          {openclawStatus ? (
            <View style={styles.sectionGroup}>
              <Text style={styles.feedMeta}>
                {openclawReady
                  ? openclawRemoteActive
                    ? "Butler's operator stack is reachable through the shared private environment."
                    : "Butler's operator stack is online on this Mac."
                  : openclawRemoteActive
                  ? "Butler is pointed at a shared private operator stack, but it is not reachable right now."
                  : openclawStatus.openclaw_installed
                  ? "OpenClaw is installed, but the gateway still needs attention."
                  : "OpenClaw is not installed yet on this Mac."}
              </Text>
              {openclawStatus.remote?.configured ? (
                <Text style={styles.feedMeta}>
                  Remote {openclawStatus.remote.label || "operator stack"}: {openclawStatus.remote.endpoint}
                </Text>
              ) : null}
              {openclawStatus.remote?.probe?.summary ? (
                <Text style={styles.feedMeta}>{openclawStatus.remote.probe.summary}</Text>
              ) : null}
              {openclawStatus.openclaw_version ? (
                <Text style={styles.feedMeta}>CLI {openclawStatus.openclaw_version}</Text>
              ) : null}
              {openclawStatus.node_version ? (
                <Text style={styles.feedMeta}>Node {openclawStatus.node_version}</Text>
              ) : null}
              {openclawStatus.gateway?.summary ? (
                <Text style={styles.feedMeta}>{openclawStatus.gateway.summary}</Text>
              ) : null}
              {!openclawStatus.npm_global_bin_on_path && openclawStatus.npm_global_bin ? (
                <Text style={styles.captureHint}>
                  Add {openclawStatus.npm_global_bin} to PATH if your shell still cannot find `openclaw`.
                </Text>
              ) : null}
              {openclawStatus.suggested_steps?.length ? (
                <View style={styles.pendingList}>
                  {openclawStatus.suggested_steps.map((step) => (
                    <View key={step} style={styles.pendingRow}>
                      <Text style={styles.pendingContent}>{step}</Text>
                    </View>
                  ))}
                </View>
              ) : null}
            </View>
          ) : (
            <Text style={styles.captureHint}>
              Butler will check the stack on the paired Mac and keep the current gateway status here.
            </Text>
          )}
        </View>
        ) : null}

        {activeMode === "act" && enabledModules.has("voice") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Voice layer</Text>
          <Text style={styles.cardBody}>
            Talk naturally, then let Butler route the work to the right surface. Voice transport is scaffolded; the pair-first control plane is ready now.
          </Text>
          <TouchableOpacity
            style={[styles.voiceButton, { borderColor: statusColor, backgroundColor: `${statusColor}18` }]}
            onPress={handleVoiceToggle}
          >
            <Text style={[styles.voiceButtonEmoji, { color: statusColor }]}>🎤</Text>
            <Text style={styles.voiceButtonText}>
              {voiceStatus === "idle" ? "Start voice" : voiceStatus === "error" ? "Retry voice" : "Stop voice"}
            </Text>
          </TouchableOpacity>
          <Text style={[styles.voiceStatus, { color: statusColor }]}>
            {voiceStatus === "idle" && "Idle"}
            {voiceStatus === "listening" && "Listening"}
            {voiceStatus === "thinking" && "Thinking"}
            {voiceStatus === "speaking" && "Speaking"}
            {voiceStatus === "error" && "Configuration needed"}
          </Text>
        </View>
        ) : null}

        {activeMode === "home" && enabledModules.has("recipes") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Recipes</Text>
          <Text style={styles.cardBody}>
            The phone should feel like a layer, not a dashboard. These are the first product-shaped actions in the Raven skin.
          </Text>
          <View style={styles.quickActionGrid}>
            {activeRecipes.map((action) => (
              <TouchableOpacity
                key={action.id}
                style={styles.quickAction}
                disabled={actionBusy !== null}
                onPress={() => handleQuickAction(action)}
              >
                <Text style={styles.quickActionTitle}>
                  {actionBusy === action.label ? `${action.label}...` : action.label}
                </Text>
                <Text style={styles.quickActionBody}>{action.summary}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
        ) : null}

        {activeMode === "review" && enabledModules.has("review_lane") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Review lane</Text>
          <Text style={styles.cardBody}>
            This is the trust layer: new items land here, you can ask Butler to classify them, defer them, dismiss them, or promote them into the relationship flow without losing the original artifact.
          </Text>
          <View style={styles.reviewSummaryRow}>
            <Text style={styles.reviewSummaryPill}>{activePendingCount} active</Text>
            <Text style={styles.reviewSummaryText}>{pendingItems.length} total pending</Text>
            <Text style={styles.reviewSummaryText}>{promotedCount} promoted locally</Text>
          </View>
          <View style={styles.buttonRow}>
            <TouchableOpacity style={styles.secondaryButton} onPress={refreshPendingQueue}>
              <Text style={styles.secondaryButtonText}>Refresh Pending</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryButton} onPress={refreshActivityFeed}>
              <Text style={styles.secondaryButtonText}>Refresh Metadata</Text>
            </TouchableOpacity>
          </View>
          {pendingBusy ? <Text style={styles.queueStatus}>Loading pending review items...</Text> : null}
          {reviewPendingItems.length > 0 ? (
            <View style={styles.reviewList}>
              {reviewPendingItems.map((item) => {
                const reviewStatus = reviewStatusFromPending(item, reviewStatuses);
                const insight = reviewInsights[item.id];
                return (
                  <View key={item.id} style={styles.reviewCard}>
                    <View style={styles.reviewHeaderRow}>
                      <View style={styles.pendingMeta}>
                        <View style={styles.reviewBadgeRow}>
                          <Text style={styles.pendingTitle}>{item.title}</Text>
                          <Text style={styles.reviewStatusBadge}>{reviewStatus}</Text>
                          {item.status && item.status !== "pending" ? (
                            <Text style={styles.reviewSourceBadge}>{item.status}</Text>
                          ) : null}
                        </View>
                        <Text style={styles.pendingKind}>
                          {item.capture_kind}
                          {typeof item.confidence === "number" ? ` • ${Math.round(item.confidence * 100)}% confidence` : ""}
                          {item.created_at ? ` • ${formatFeedTimestamp(item.created_at)}` : ""}
                        </Text>
                      </View>
                    </View>
                    {item.content ? (
                      <Text style={styles.pendingContent} numberOfLines={3}>
                        {item.content}
                      </Text>
                    ) : null}
                    {insight ? (
                      <View style={styles.reviewInsightBlock}>
                        <Text style={styles.reviewInsightLabel}>Butler review</Text>
                        <Text style={styles.reviewInsightText}>{insight}</Text>
                      </View>
                    ) : null}
                    <View style={styles.reviewActionsRow}>
                      <TouchableOpacity
                        style={[styles.reviewActionButton, reviewBusyId === item.id && styles.buttonDisabled]}
                        disabled={reviewBusyId === item.id}
                        onPress={() => handleReviewAnalyze(item)}
                      >
                        <Text style={styles.reviewActionText}>
                          {reviewBusyId === item.id ? "Analyzing..." : "Ask Butler"}
                        </Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={[styles.reviewActionButton, reviewBusyId === item.id && styles.buttonDisabled]}
                        disabled={reviewBusyId === item.id}
                        onPress={() => (reviewStatus === "promoted" ? movePendingIntoPeople(item) : handleReviewPromote(item))}
                      >
                        <Text style={styles.reviewActionText}>
                          {reviewStatus === "promoted" ? "Use in CRM" : "Promote"}
                        </Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={[styles.reviewActionButton, reviewBusyId === item.id && styles.buttonDisabled]}
                        disabled={reviewBusyId === item.id}
                        onPress={() => (reviewStatus === "deferred" ? handleReviewRestore(item) : handleReviewDefer(item))}
                      >
                        <Text style={styles.reviewActionText}>
                          {reviewStatus === "deferred" ? "Undefer" : "Defer"}
                        </Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={[styles.reviewActionButton, reviewBusyId === item.id && styles.buttonDisabled]}
                        disabled={reviewBusyId === item.id}
                        onPress={() => (reviewStatus === "dismissed" ? handleReviewRestore(item) : handleReviewDismiss(item))}
                      >
                        <Text style={styles.reviewActionText}>
                          {reviewStatus === "dismissed" ? "Restore" : "Dismiss"}
                        </Text>
                      </TouchableOpacity>
                    </View>
                    <View style={styles.buttonRow}>
                      <TouchableOpacity
                        style={[
                          styles.secondaryButton,
                          roomActionBusy === `handoff-ref:pending/${item.id}` && styles.buttonDisabled,
                        ]}
                        disabled={roomActionBusy !== ""}
                        onPress={() =>
                          handleSendRefToMac(`pending/${item.id}`, item.title, {
                            kind: "pending",
                            summary: item.content || insight || item.capture_kind,
                            metadata: {
                              lane: "review",
                              review_status: reviewStatus,
                              pending_id: item.id,
                            },
                          })
                        }
                      >
                        <Text style={styles.secondaryButtonText}>
                          {roomActionBusy === `handoff-ref:pending/${item.id}` ? "Sending..." : "Send To Mac"}
                        </Text>
                      </TouchableOpacity>
                    </View>
                    {reviewStatus === "promoted" ? (
                      <Text style={styles.reviewStatusText}>Prefilled into relationship ingest below.</Text>
                    ) : null}
                  </View>
                );
              })}
            </View>
          ) : (
            <Text style={styles.queueStatus}>No pending items yet. Capture a photo, note, or relationship event to start the review lane.</Text>
          )}
        </View>
        ) : null}

        {activeMode === "review" && enabledModules.has("metadata_results") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Metadata ingest results</Text>
          <Text style={styles.cardBody}>
            The newest useful signal from the phone should be visible immediately so you can trust what Butler has ingested and what it still needs you to correct.
          </Text>
          {metadataIngestCalls.length > 0 ? (
            <View style={styles.metadataList}>
              {metadataIngestCalls.map((call) => (
                <View key={call.id} style={styles.metadataItem}>
                  <ToolCallBadge toolName={call.toolName} status={call.status} result={call.result} />
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.queueStatus}>No metadata ingest yet. Relationship logs, contact imports, and capture saves will appear here.</Text>
          )}
        </View>
        ) : null}

        {activeMode === "people" && enabledModules.has("relationship_ingest") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Relationship ingest</Text>
          <Text style={styles.cardBody}>
            Log the interaction once, and Butler should remember the person, the context, and the next move without making you clean it up later.
          </Text>
          <View style={styles.relationshipGrid}>
            <TextInput
              autoCapitalize="words"
              autoCorrect={false}
              placeholder="Person name"
              placeholderTextColor="#5f6b84"
              style={styles.input}
              value={relationshipName}
              onChangeText={setRelationshipName}
            />
            <TextInput
              autoCapitalize="words"
              autoCorrect={false}
              placeholder="Company"
              placeholderTextColor="#5f6b84"
              style={styles.input}
              value={relationshipCompany}
              onChangeText={setRelationshipCompany}
            />
            <TextInput
              autoCapitalize="words"
              autoCorrect={false}
              placeholder="Role or title"
              placeholderTextColor="#5f6b84"
              style={styles.input}
              value={relationshipRole}
              onChangeText={setRelationshipRole}
            />
            <View style={styles.relationshipMetaRow}>
              <TextInput
                autoCapitalize="words"
                autoCorrect={false}
                placeholder="Place name"
                placeholderTextColor="#5f6b84"
                style={styles.relationshipMetaInput}
                value={relationshipPlaceName}
                onChangeText={setRelationshipPlaceName}
              />
              <TextInput
                autoCapitalize="words"
                autoCorrect={false}
                placeholder="Thread or topic label"
                placeholderTextColor="#5f6b84"
                style={styles.relationshipMetaInput}
                value={relationshipConversationLabel}
                onChangeText={setRelationshipConversationLabel}
              />
            </View>
            <View style={styles.relationshipChipGroup}>
              <Text style={styles.relationshipLabel}>Channel</Text>
              <View style={styles.captureKindRow}>
                {RELATIONSHIP_CHANNELS.map((item) => (
                  <TouchableOpacity
                    key={item}
                    style={[
                      styles.captureKindChip,
                      relationshipChannel === item && styles.captureKindChipActive,
                    ]}
                    onPress={() => handleRelationshipFieldPick("channel", item)}
                  >
                    <Text
                      style={[
                        styles.captureKindChipText,
                        relationshipChannel === item && styles.captureKindChipTextActive,
                      ]}
                    >
                      {item}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <View style={styles.relationshipChipGroup}>
              <Text style={styles.relationshipLabel}>Direction</Text>
              <View style={styles.captureKindRow}>
                {RELATIONSHIP_DIRECTIONS.map((item) => (
                  <TouchableOpacity
                    key={item}
                    style={[
                      styles.captureKindChip,
                      relationshipDirection === item && styles.captureKindChipActive,
                    ]}
                    onPress={() => handleRelationshipFieldPick("direction", item)}
                  >
                    <Text
                      style={[
                        styles.captureKindChipText,
                        relationshipDirection === item && styles.captureKindChipTextActive,
                      ]}
                    >
                      {item}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <View style={styles.relationshipChipGroup}>
              <Text style={styles.relationshipLabel}>Type</Text>
              <View style={styles.captureKindRow}>
                {RELATIONSHIP_TYPES.map((item) => (
                  <TouchableOpacity
                    key={item}
                    style={[
                      styles.captureKindChip,
                      relationshipType === item && styles.captureKindChipActive,
                    ]}
                    onPress={() => handleRelationshipFieldPick("type", item)}
                  >
                    <Text
                      style={[
                        styles.captureKindChipText,
                        relationshipType === item && styles.captureKindChipTextActive,
                      ]}
                    >
                      {item}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <View style={styles.relationshipChipGroup}>
              <Text style={styles.relationshipLabel}>Stage</Text>
              <View style={styles.captureKindRow}>
                {RELATIONSHIP_STAGES.map((item) => (
                  <TouchableOpacity
                    key={item}
                    style={[
                      styles.captureKindChip,
                      relationshipStage === item && styles.captureKindChipActive,
                    ]}
                    onPress={() => handleRelationshipFieldPick("stage", item)}
                  >
                    <Text
                      style={[
                        styles.captureKindChipText,
                        relationshipStage === item && styles.captureKindChipTextActive,
                      ]}
                    >
                      {item}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <View style={styles.relationshipChipGroup}>
              <Text style={styles.relationshipLabel}>Priority</Text>
              <View style={styles.captureKindRow}>
                {RELATIONSHIP_PRIORITIES.map((item) => (
                  <TouchableOpacity
                    key={item}
                    style={[
                      styles.captureKindChip,
                      relationshipPriority === item && styles.captureKindChipActive,
                    ]}
                    onPress={() => handleRelationshipFieldPick("priority", item)}
                  >
                    <Text
                      style={[
                        styles.captureKindChipText,
                        relationshipPriority === item && styles.captureKindChipTextActive,
                      ]}
                    >
                      {item}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <View style={styles.relationshipMetaRow}>
              <TextInput
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="Phone"
                placeholderTextColor="#5f6b84"
                style={styles.relationshipMetaInput}
                value={relationshipPhone}
                onChangeText={setRelationshipPhone}
              />
              <TextInput
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="Email"
                placeholderTextColor="#5f6b84"
                style={styles.relationshipMetaInput}
                value={relationshipEmail}
                onChangeText={setRelationshipEmail}
              />
            </View>
            <TextInput
              autoCapitalize="sentences"
              autoCorrect
              multiline
              placeholder="What happened in the interaction?"
              placeholderTextColor="#5f6b84"
              style={[styles.input, styles.textArea]}
              value={relationshipSummary}
              onChangeText={setRelationshipSummary}
            />
            <TextInput
              autoCapitalize="sentences"
              autoCorrect
              multiline
              placeholder="Next action"
              placeholderTextColor="#5f6b84"
              style={[styles.input, styles.textArea]}
              value={relationshipNextAction}
              onChangeText={setRelationshipNextAction}
            />
            <View style={styles.relationshipMetaRow}>
              <TextInput
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="Due date or timing"
                placeholderTextColor="#5f6b84"
                style={styles.relationshipMetaInput}
                value={relationshipDueAt}
                onChangeText={setRelationshipDueAt}
              />
              <TextInput
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="Follow-up in days"
                placeholderTextColor="#5f6b84"
                style={styles.relationshipMetaInput}
                value={relationshipFollowUpInDays}
                onChangeText={setRelationshipFollowUpInDays}
                keyboardType="number-pad"
              />
            </View>
            <TextInput
              autoCapitalize="sentences"
              autoCorrect
              multiline
              placeholder="Open loop"
              placeholderTextColor="#5f6b84"
              style={[styles.input, styles.textArea]}
              value={relationshipOpenLoop}
              onChangeText={setRelationshipOpenLoop}
            />
            <TextInput
              autoCapitalize="sentences"
              autoCorrect
              multiline
              placeholder="Notes"
              placeholderTextColor="#5f6b84"
              style={[styles.input, styles.textArea]}
              value={relationshipNotes}
              onChangeText={setRelationshipNotes}
            />
            <TextInput
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="Tags CSV"
              placeholderTextColor="#5f6b84"
              style={styles.input}
              value={relationshipTagsCsv}
              onChangeText={setRelationshipTagsCsv}
            />
          </View>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.primaryButton, relationshipBusy && styles.buttonDisabled]}
              disabled={relationshipBusy}
              onPress={handleRelationshipLog}
            >
              <Text style={styles.primaryButtonText}>{relationshipBusy ? "Saving..." : "Log Interaction"}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryButton} onPress={refreshFollowupQueue}>
              <Text style={styles.secondaryButtonText}>Refresh Follow-ups</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity
            style={[styles.secondaryGhostButton, contactImportBusy && styles.buttonDisabled]}
            disabled={contactImportBusy}
            onPress={handleImportContacts}
          >
            <Text style={styles.secondaryButtonText}>
              {contactImportBusy ? "Importing desktop contacts..." : "Import Desktop Contacts"}
            </Text>
          </TouchableOpacity>
          <Text style={styles.captureHint}>
            The goal is a trustworthy CRM: record the person, the channel, the summary, and the next action in one pass.
          </Text>
          {followupsBusy ? <Text style={styles.queueStatus}>Loading follow-up queue...</Text> : null}
          {followups.length > 0 && (
            <View style={styles.pendingList}>
              {followups.map((item) => (
                <View key={item.id} style={styles.pendingRow}>
                  <View style={styles.pendingHeaderRow}>
                    <View style={styles.pendingMeta}>
                      <Text style={styles.pendingTitle}>
                        {getFollowupName(item)}
                        {item.pinned ? " • pinned" : ""}
                      </Text>
                      <Text style={styles.pendingKind}>
                        {item.company || item.role ? [item.company, item.role].filter(Boolean).join(" • ") : item.channel || "relationship"}
                        {item.direction ? ` • ${item.direction}` : ""}
                        {typeof item.score === "number" ? ` • ${item.score} score` : ""}
                      </Text>
                    </View>
                    {item.person_ref ? (
                      <TouchableOpacity
                        style={[
                          styles.pinButton,
                          item.pinned && styles.pinButtonActive,
                          pinBusyRef === item.person_ref && styles.buttonDisabled,
                        ]}
                        disabled={pinBusyRef === item.person_ref}
                        onPress={() => handleTogglePin(item.person_ref || "", Boolean(item.pinned), getFollowupName(item))}
                      >
                        <Text style={[styles.pinButtonText, item.pinned && styles.pinButtonTextActive]}>
                          {pinBusyRef === item.person_ref ? "..." : item.pinned ? "Unpin" : "Pin"}
                        </Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                  {item.next_action ? (
                    <Text style={styles.pendingContent}>{item.next_action}</Text>
                  ) : null}
                  {item.due_label || item.next_action_due_at ? (
                    <Text style={styles.relationshipMetaText}>
                      {item.due_label || item.next_action_due_at}
                      {item.overdue ? " • overdue" : ""}
                    </Text>
                  ) : null}
                  {item.thread_summary ? (
                    <Text style={styles.pendingContent} numberOfLines={2}>
                      {item.thread_summary}
                    </Text>
                  ) : null}
                  {item.person_ref ? (
                    <View style={styles.buttonRow}>
                      <TouchableOpacity
                        style={[
                          styles.secondaryButton,
                          roomActionBusy === `handoff-ref:${item.person_ref}` && styles.buttonDisabled,
                        ]}
                        disabled={roomActionBusy !== ""}
                        onPress={() =>
                          handleSendRefToMac(item.person_ref || "", getFollowupName(item), {
                            kind: "person",
                            summary: item.next_action || item.thread_summary || item.company || item.channel || "",
                            metadata: {
                              lane: "followups",
                              score: item.score ?? null,
                              due_label: item.due_label || "",
                              next_action: item.next_action || "",
                            },
                          })
                        }
                      >
                        <Text style={styles.secondaryButtonText}>
                          {roomActionBusy === `handoff-ref:${item.person_ref}` ? "Sending..." : "Send To Mac"}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  ) : null}
                </View>
              ))}
            </View>
          )}
        </View>
        ) : null}

        {activeMode === "capture" && enabledModules.has("phone_metadata") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Android phone metadata</Text>
          <Text style={styles.cardBody}>
            Butler can read call log metadata and SMS thread metadata directly on Android, then promote selected items into review without copying the raw history out of the phone.
          </Text>
          <View style={styles.metaRow}>
            <Text style={[styles.metaBadge, phoneMetadataSnapshot?.ready ? styles.metaBadgeReady : styles.metaBadgeBlocked]}>
              {phoneMetadataSnapshot?.ready ? "Metadata ready" : "Metadata locked"}
            </Text>
            <Text style={styles.metaText}>
              {phoneMetadataStatus?.status_label || "Permissions needed"}
            </Text>
          </View>
          {phoneMetadataStatus?.missing_permissions?.length ? (
            <Text style={styles.captureHint}>
              Missing: {phoneMetadataStatus.missing_permissions.join(", ")}
            </Text>
          ) : null}
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.primaryButton, phoneMetadataBusy && styles.buttonDisabled]}
              disabled={phoneMetadataBusy}
              onPress={handleRequestPhoneMetadataPermissions}
            >
              <Text style={styles.primaryButtonText}>
                {phoneMetadataBusy ? "Requesting..." : "Grant Call + SMS Access"}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.secondaryButton, phoneMetadataRefreshBusy && styles.buttonDisabled]}
              disabled={phoneMetadataRefreshBusy}
              onPress={refreshPhoneMetadataSnapshot}
            >
              <Text style={styles.secondaryButtonText}>
                {phoneMetadataRefreshBusy ? "Refreshing..." : "Refresh Metadata"}
              </Text>
            </TouchableOpacity>
          </View>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.secondaryButton, phoneMetadataSyncBusy === "calls" && styles.buttonDisabled]}
              disabled={phoneMetadataSyncBusy !== ""}
              onPress={() => handleSyncPhoneMetadata("calls")}
            >
              <Text style={styles.secondaryButtonText}>
                {phoneMetadataSyncBusy === "calls" ? "Syncing Calls..." : "Sync Calls"}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.secondaryButton, phoneMetadataSyncBusy === "sms" && styles.buttonDisabled]}
              disabled={phoneMetadataSyncBusy !== ""}
              onPress={() => handleSyncPhoneMetadata("sms")}
            >
              <Text style={styles.secondaryButtonText}>
                {phoneMetadataSyncBusy === "sms" ? "Syncing SMS..." : "Sync SMS"}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, phoneMetadataSyncBusy === "all" && styles.buttonDisabled]}
              disabled={phoneMetadataSyncBusy !== ""}
              onPress={() => handleSyncPhoneMetadata("all")}
            >
              <Text style={styles.primaryButtonText}>
                {phoneMetadataSyncBusy === "all" ? "Syncing..." : "Sync All Visible"}
              </Text>
            </TouchableOpacity>
          </View>
          {phoneMetadataSnapshot?.generated_at ? (
            <Text style={styles.feedTimestamp}>Generated {formatMetadataTimestamp(phoneMetadataSnapshot.generated_at)}</Text>
          ) : null}
          {phoneMetadataSnapshot?.error ? <Text style={styles.queueStatus}>{phoneMetadataSnapshot.error}</Text> : null}
          {phoneMetadataSnapshot?.call_log?.length ? (
            <View style={styles.sectionGroup}>
              <Text style={styles.relationshipLabel}>Recent calls</Text>
              <View style={styles.pendingList}>
                {phoneMetadataSnapshot.call_log.map((item) => (
                  <View key={`${item.kind}:${item.timestamp_ms}:${item.title}`} style={styles.pendingRow}>
                    <View style={styles.pendingHeaderRow}>
                      <View style={styles.pendingMeta}>
                        <Text style={styles.pendingTitle}>{item.title}</Text>
                        <Text style={styles.pendingKind}>
                          {item.summary}
                          {item.timestamp_iso ? ` • ${formatMetadataTimestamp(item.timestamp_iso)}` : ""}
                        </Text>
                      </View>
                    </View>
                    {item.source?.number ? (
                      <Text style={styles.pendingContent}>{String(item.source.number)}</Text>
                    ) : null}
                    {item.source?.cached_name ? (
                      <Text style={styles.feedMeta}>{String(item.source.cached_name)}</Text>
                    ) : null}
                  </View>
                ))}
              </View>
            </View>
          ) : null}
          {phoneMetadataSnapshot?.sms_threads?.length ? (
            <View style={styles.sectionGroup}>
              <Text style={styles.relationshipLabel}>SMS threads</Text>
              <View style={styles.pendingList}>
                {phoneMetadataSnapshot.sms_threads.map((item) => (
                  <View key={`${item.kind}:${item.thread_id ?? item.timestamp_ms}:${item.title}`} style={styles.pendingRow}>
                    <View style={styles.pendingHeaderRow}>
                      <View style={styles.pendingMeta}>
                        <Text style={styles.pendingTitle}>{item.title}</Text>
                        <Text style={styles.pendingKind}>
                          {item.summary}
                          {typeof item.count === "number" ? ` • ${item.count} messages` : ""}
                          {typeof item.unread_count === "number" && item.unread_count > 0 ? ` • ${item.unread_count} unread` : ""}
                        </Text>
                      </View>
                    </View>
                    {item.source?.body_preview ? (
                      <Text style={styles.pendingContent} numberOfLines={2}>
                        {String(item.source.body_preview)}
                      </Text>
                    ) : null}
                    <Text style={styles.feedMeta}>
                      {item.timestamp_iso ? formatMetadataTimestamp(item.timestamp_iso) : "No timestamp"}
                    </Text>
                  </View>
                ))}
              </View>
            </View>
          ) : null}
          {phoneMetadataSnapshot?.review_queue?.length ? (
            <View style={styles.sectionGroup}>
              <Text style={styles.relationshipLabel}>Review queue</Text>
              <Text style={styles.captureHint}>
                Pick a metadata item and promote it into the main pending queue when you want to review or enrich it later.
              </Text>
              <View style={styles.pendingList}>
                {phoneMetadataSnapshot.review_queue.map((item) => {
                  const promoteKey = `${item.kind}:${item.timestamp_ms}:${item.title}`;
                  const busy = phoneMetadataPromoteBusy === promoteKey;
                  return (
                    <View key={promoteKey} style={styles.pendingRow}>
                      <View style={styles.pendingHeaderRow}>
                        <View style={styles.pendingMeta}>
                          <Text style={styles.pendingTitle}>{item.title}</Text>
                          <Text style={styles.pendingKind}>
                            {item.kind}
                            {item.timestamp_iso ? ` • ${formatMetadataTimestamp(item.timestamp_iso)}` : ""}
                          </Text>
                        </View>
                        <TouchableOpacity
                          style={[styles.pinButton, busy && styles.buttonDisabled]}
                          disabled={busy}
                          onPress={() => handlePromotePhoneMetadataItem(item)}
                        >
                          <Text style={styles.pinButtonText}>{busy ? "..." : "Promote"}</Text>
                        </TouchableOpacity>
                      </View>
                      {item.summary ? (
                        <Text style={styles.pendingContent} numberOfLines={2}>
                          {item.summary}
                        </Text>
                      ) : null}
                    </View>
                  );
                })}
              </View>
            </View>
          ) : null}
        </View>
        ) : null}

        {activeMode === "people" && enabledModules.has("context_map") ? (
        <ContextMapCard
          snapshot={contextMap}
          busy={contextMapBusy}
          pinBusyRef={pinBusyRef}
          onRefresh={refreshContextMap}
          onTogglePin={handleTogglePin}
          onSendToMac={(ref, title, summary, kind) =>
            handleSendRefToMac(ref, title, {
              kind,
              summary,
              metadata: { lane: "context_map" },
            })
          }
          sendBusyRef={roomActionBusy.startsWith("handoff-ref:") ? roomActionBusy.replace("handoff-ref:", "") : ""}
        />
        ) : null}

        {activeMode === "home" && enabledModules.has("journal") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Journal</Text>
          <Text style={styles.cardBody}>
            Butler should feel like a diary, not a database. New activity lands at the top, and pinned people or records stay in view until you are done with them.
          </Text>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.primaryButton, activityBusy && styles.buttonDisabled]}
              disabled={activityBusy}
              onPress={refreshActivityFeed}
            >
              <Text style={styles.primaryButtonText}>{activityBusy ? "Refreshing..." : "Refresh Journal"}</Text>
            </TouchableOpacity>
          </View>
          {activityBusy ? <Text style={styles.queueStatus}>Loading journal...</Text> : null}
          {activityItems.length > 0 && (
            <View style={styles.feedList}>
              {activityItems.map((item) => (
                <View key={item.id} style={styles.feedRow}>
                  <View style={styles.feedTopRow}>
                    <View style={styles.feedTitleWrap}>
                      <View style={styles.feedBadgeRow}>
                        <Text style={styles.feedBadge}>{item.kind || "activity"}</Text>
                        {item.pinned ? <Text style={styles.feedBadgePinned}>Pinned</Text> : null}
                      </View>
                      <Text style={styles.feedTitle}>{item.title || item.ref || "Untitled entry"}</Text>
                    </View>
                    {item.ref ? (
                      <TouchableOpacity
                        style={[
                          styles.pinButton,
                          item.pinned && styles.pinButtonActive,
                          pinBusyRef === item.ref && styles.buttonDisabled,
                        ]}
                        disabled={pinBusyRef === item.ref}
                        onPress={() => handleTogglePin(item.ref || "", Boolean(item.pinned), item.title || item.ref || "Pinned item")}
                      >
                        <Text style={[styles.pinButtonText, item.pinned && styles.pinButtonTextActive]}>
                          {pinBusyRef === item.ref ? "..." : item.pinned ? "Unpin" : "Pin"}
                        </Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                  <Text style={styles.feedTimestamp}>
                    {formatFeedTimestamp(item.updated_at || item.created_at)}
                    {item.event_type ? ` • ${item.event_type}` : ""}
                  </Text>
                  {item.summary ? (
                    <Text style={styles.feedSummary} numberOfLines={3}>
                      {item.summary}
                    </Text>
                  ) : null}
                  {item.path ? (
                    <Text style={styles.feedMeta} numberOfLines={1}>
                      {item.path}
                    </Text>
                  ) : null}
                  {item.ref ? (
                    <View style={styles.buttonRow}>
                      <TouchableOpacity
                        style={[
                          styles.secondaryButton,
                          roomActionBusy === `handoff-ref:${item.ref}` && styles.buttonDisabled,
                        ]}
                        disabled={roomActionBusy !== ""}
                        onPress={() =>
                          handleSendRefToMac(item.ref || "", item.title || item.ref || "Journal item", {
                            summary: item.summary || item.event_type || item.kind || "",
                            metadata: {
                              lane: "journal",
                              event_type: item.event_type || "",
                            },
                          })
                        }
                      >
                        <Text style={styles.secondaryButtonText}>
                          {roomActionBusy === `handoff-ref:${item.ref}` ? "Sending..." : "Send To Mac"}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  ) : null}
                </View>
              ))}
            </View>
          )}
        </View>
        ) : null}

        {activeMode === "capture" && enabledModules.has("capture_pending") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Capture to pending</Text>
          <Text style={styles.cardBody}>
            Frictionless capture lands here first. If Butler is not sure yet, it should preserve the item and let you batch review it later instead of filing it incorrectly.
          </Text>
          <View style={styles.captureKindRow}>
            {(["receipt", "note", "person", "artifact"] as CaptureKind[]).map((kind) => (
              <TouchableOpacity
                key={kind}
                style={[
                  styles.captureKindChip,
                  captureKind === kind && styles.captureKindChipActive,
                ]}
                onPress={() => setCaptureKind(kind)}
              >
                <Text
                  style={[
                    styles.captureKindChipText,
                    captureKind === kind && styles.captureKindChipTextActive,
                  ]}
                >
                  {kind}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
          <View style={styles.captureActionRow}>
            <TouchableOpacity style={styles.secondaryButton} onPress={() => selectCaptureMedia("camera")}>
              <Text style={styles.secondaryButtonText}>Take Photo</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryButton} onPress={() => selectCaptureMedia("library")}>
              <Text style={styles.secondaryButtonText}>Choose Library</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.captureHint}>
            Use the camera for receipts and the library for screenshots, artifacts, and anything you want to batch review later.
          </Text>
          {selectedCapture ? (
            <View style={styles.capturePreviewCard}>
              <Image source={{ uri: selectedCapture.uri }} style={styles.capturePreviewImage} />
              <View style={styles.capturePreviewMeta}>
                <Text style={styles.capturePreviewTitle}>{selectedCapture.fileName}</Text>
                <Text style={styles.capturePreviewBody}>
                  {selectedCapture.source === "camera" ? "Captured on camera" : "Picked from library"}
                  {selectedCapture.width && selectedCapture.height ? ` • ${selectedCapture.width} x ${selectedCapture.height}` : ""}
                </Text>
                <Text style={styles.capturePreviewBody}>{selectedCapture.mimeType}</Text>
              </View>
            </View>
          ) : null}
          <TextInput
            autoCapitalize="sentences"
            autoCorrect
            placeholder={selectedCapture ? buildDefaultCaptureTitle(captureKind, selectedCapture.fileName) : "Staples receipt, call with Sarah, note from airport..."}
            placeholderTextColor="#5f6b84"
            style={styles.input}
            value={captureTitle}
            onChangeText={setCaptureTitle}
          />
          <TextInput
            autoCapitalize="sentences"
            autoCorrect
            multiline
            placeholder="Optional details, OCR, or why this might matter later"
            placeholderTextColor="#5f6b84"
            style={[styles.input, styles.textArea]}
            value={captureContent}
            onChangeText={setCaptureContent}
          />
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.primaryButton, captureBusy && styles.buttonDisabled]}
              disabled={captureBusy}
              onPress={handleCapturePending}
            >
              <Text style={styles.primaryButtonText}>{captureBusy ? "Saving..." : "Save To Pending"}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryButton} onPress={clearSelectedCapture}>
              <Text style={styles.secondaryButtonText}>Clear Photo</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity style={styles.secondaryGhostButton} onPress={refreshPendingQueue}>
            <Text style={styles.secondaryButtonText}>Refresh Queue</Text>
          </TouchableOpacity>
          <Text style={styles.captureHint}>
            {pendingItems.length > 0
              ? `${pendingItems.length} items are waiting in the review lane above.`
              : "Nothing is waiting yet. Capture something, then review it above before it becomes a mistake."}
          </Text>
        </View>
        ) : null}

        {activeMode === "act" && enabledModules.has("conversation_memory") ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Conversation memory</Text>
          <Text style={styles.cardBody}>
            Keep enough context on the phone to stay in the flow, while the desktop runtime handles higher-trust actions and writes receipts.
          </Text>
          <View style={styles.memoryPanel}>
            <Text style={styles.memoryLabel}>You</Text>
            <Text style={styles.memoryText}>{lastUtterance || "“Who do I owe a follow-up to today?”"}</Text>
          </View>
          <View style={[styles.memoryPanel, styles.memoryPanelReply]}>
            <Text style={styles.memoryReplyLabel}>Butler</Text>
            <Text style={styles.memoryReplyText}>
              {lastResponse ||
              "I can keep a live relationship queue on your phone, then route outreach and desktop work through the trusted local runtime."}
            </Text>
          </View>
        </View>
        ) : null}

        {activeMode === "act" && enabledModules.has("tool_activity") && toolCalls.length > 0 && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Tool activity</Text>
            <Text style={styles.cardBody}>
              Every delegated action stays legible. This is the surface where people should see what Butler is touching on their behalf.
            </Text>
            {toolCalls.map((call) => (
              <ToolCallBadge
                key={call.id}
                toolName={call.toolName}
                status={call.status}
                result={call.result}
              />
            ))}
          </View>
        )}

        <Text style={styles.footerNote}>
          Current tool contract count: {TOOL_DEFINITIONS.length}. The phone is the companion surface. The Mac stays the high-trust execution surface.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: "#090b13",
  },
  scrollContent: {
    paddingHorizontal: 18,
    paddingVertical: 20,
    gap: 14,
  },
  heroCard: {
    backgroundColor: "#101522",
    borderRadius: 20,
    padding: 22,
    borderWidth: 1,
    borderColor: "#1d2940",
  },
  eyebrow: {
    fontSize: 11,
    letterSpacing: 1.4,
    textTransform: "uppercase",
    color: "#7fa9ff",
    marginBottom: 8,
  },
  title: {
    fontSize: 30,
    lineHeight: 34,
    fontWeight: "800",
    color: "#f2f5fb",
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 15,
    lineHeight: 22,
    color: "#9aa8c4",
  },
  metaRow: {
    marginTop: 18,
    gap: 10,
  },
  metaBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
    fontSize: 12,
    fontWeight: "700",
    overflow: "hidden",
  },
  metaBadgeReady: {
    backgroundColor: "#0f3326",
    color: "#7bf0ba",
  },
  metaBadgeBlocked: {
    backgroundColor: "#2a1d22",
    color: "#ff93ab",
  },
  metaText: {
    color: "#7f8ba1",
    fontSize: 13,
  },
  modeRail: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  modeChip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#24314a",
    backgroundColor: "#0f1420",
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  modeChipActive: {
    backgroundColor: "#162335",
    borderColor: "#7dffd2",
  },
  modeChipText: {
    color: "#9cb0d0",
    fontSize: 12,
    fontWeight: "700",
  },
  modeChipTextActive: {
    color: "#eff4fb",
  },
  skinRail: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  skinChip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#24314a",
    backgroundColor: "#0a0f18",
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  skinChipActive: {
    backgroundColor: "#162335",
  },
  skinChipText: {
    color: "#9cb0d0",
    fontSize: 12,
    fontWeight: "700",
  },
  skinChipTextActive: {
    color: "#eff4fb",
  },
  card: {
    backgroundColor: "#0f1420",
    borderRadius: 18,
    padding: 18,
    borderWidth: 1,
    borderColor: "#1b2232",
    gap: 12,
  },
  cardEyebrow: {
    fontSize: 11,
    letterSpacing: 1.3,
    textTransform: "uppercase",
    color: "#7dffd2",
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: "#f2f5fb",
  },
  cardBody: {
    fontSize: 14,
    lineHeight: 21,
    color: "#93a0ba",
  },
  input: {
    borderWidth: 1,
    borderColor: "#263149",
    backgroundColor: "#0a0f18",
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: "#f2f5fb",
    fontSize: 14,
  },
  buttonRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  captureActionRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  primaryButton: {
    flex: 1,
    borderRadius: 14,
    backgroundColor: "#8ef0b3",
    paddingVertical: 14,
    alignItems: "center",
  },
  primaryButtonText: {
    color: "#08110a",
    fontWeight: "800",
    fontSize: 15,
  },
  secondaryButton: {
    borderRadius: 14,
    backgroundColor: "#171f31",
    paddingVertical: 14,
    paddingHorizontal: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  secondaryButtonText: {
    color: "#b6c2da",
    fontWeight: "700",
  },
  secondaryGhostButton: {
    borderRadius: 14,
    backgroundColor: "#121a29",
    paddingVertical: 14,
    paddingHorizontal: 16,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#23304a",
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  voiceButton: {
    borderWidth: 1,
    borderRadius: 18,
    paddingVertical: 20,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  voiceButtonEmoji: {
    fontSize: 32,
  },
  voiceButtonText: {
    color: "#edf2f9",
    fontWeight: "700",
    fontSize: 16,
  },
  voiceStatus: {
    fontSize: 13,
    fontWeight: "700",
  },
  quickActionGrid: {
    gap: 10,
  },
  captureKindRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  captureKindChip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#23304a",
    backgroundColor: "#111827",
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  captureKindChipActive: {
    backgroundColor: "#173124",
    borderColor: "#8ef0b3",
  },
  captureKindChipText: {
    color: "#a6b4ce",
    fontSize: 12,
    fontWeight: "700",
    textTransform: "capitalize",
  },
  captureKindChipTextActive: {
    color: "#8ef0b3",
  },
  textArea: {
    minHeight: 88,
    textAlignVertical: "top",
  },
  captureHint: {
    color: "#8ea0bf",
    fontSize: 12,
    lineHeight: 18,
  },
  capturePreviewCard: {
    flexDirection: "row",
    gap: 12,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#283654",
    backgroundColor: "#0b111d",
    padding: 12,
    alignItems: "center",
  },
  capturePreviewImage: {
    width: 78,
    height: 78,
    borderRadius: 12,
    backgroundColor: "#182235",
  },
  capturePreviewMeta: {
    flex: 1,
    gap: 3,
  },
  capturePreviewTitle: {
    color: "#edf3fb",
    fontSize: 14,
    fontWeight: "700",
  },
  capturePreviewBody: {
    color: "#94a3be",
    fontSize: 12,
    lineHeight: 17,
  },
  pendingList: {
    gap: 10,
  },
  pendingRow: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#1f2b42",
    backgroundColor: "#121a29",
    padding: 12,
    gap: 4,
  },
  pendingRowActive: {
    borderColor: "#7cf0bb",
    backgroundColor: "#132032",
  },
  pendingMeta: {
    gap: 2,
    flex: 1,
  },
  pendingHeaderRow: {
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
  },
  pendingTitle: {
    color: "#eef4fc",
    fontSize: 14,
    fontWeight: "700",
  },
  pendingKind: {
    color: "#89bfa0",
    fontSize: 12,
    textTransform: "capitalize",
  },
  pendingContent: {
    color: "#93a0ba",
    fontSize: 13,
    lineHeight: 18,
  },
  quickAction: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#23304a",
    padding: 14,
    backgroundColor: "#121a29",
    gap: 6,
  },
  quickActionTitle: {
    color: "#f1f5fc",
    fontWeight: "700",
    fontSize: 15,
  },
  quickActionBody: {
    color: "#90a0bd",
    fontSize: 13,
    lineHeight: 18,
  },
  reviewSummaryRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    alignItems: "center",
  },
  reviewSummaryPill: {
    alignSelf: "flex-start",
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
    backgroundColor: "#173124",
    color: "#8ef0b3",
    fontSize: 12,
    fontWeight: "800",
    overflow: "hidden",
  },
  reviewSummaryText: {
    color: "#93a0ba",
    fontSize: 12,
  },
  reviewList: {
    gap: 10,
  },
  reviewCard: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#273650",
    backgroundColor: "#0d1522",
    padding: 12,
    gap: 10,
  },
  reviewHeaderRow: {
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
  },
  reviewBadgeRow: {
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap",
    alignItems: "center",
  },
  reviewStatusBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: "#182235",
    color: "#9fc4de",
    fontSize: 11,
    fontWeight: "700",
    overflow: "hidden",
    textTransform: "capitalize",
  },
  reviewSourceBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: "#2d2230",
    color: "#ffb3cb",
    fontSize: 11,
    fontWeight: "700",
    overflow: "hidden",
    textTransform: "capitalize",
  },
  reviewActionsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  reviewActionButton: {
    borderRadius: 999,
    backgroundColor: "#172235",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: "#27405c",
  },
  reviewActionText: {
    color: "#dbe6f5",
    fontSize: 12,
    fontWeight: "700",
  },
  reviewInsightBlock: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#243852",
    backgroundColor: "#0a111b",
    padding: 10,
    gap: 4,
  },
  reviewInsightLabel: {
    color: "#7cf0bb",
    fontSize: 11,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  reviewInsightText: {
    color: "#cfd8e7",
    fontSize: 13,
    lineHeight: 18,
  },
  reviewStatusText: {
    color: "#7f8ba1",
    fontSize: 12,
  },
  metadataList: {
    gap: 10,
  },
  metadataItem: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#24314b",
    backgroundColor: "#0d1522",
    padding: 10,
  },
  relationshipGrid: {
    gap: 10,
  },
  relationshipChipGroup: {
    gap: 8,
  },
  relationshipLabel: {
    color: "#7f8ba1",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.6,
    textTransform: "uppercase",
  },
  relationshipMetaRow: {
    flexDirection: "row",
    gap: 10,
  },
  relationshipMetaInput: {
    flex: 1,
    borderWidth: 1,
    borderColor: "#263149",
    backgroundColor: "#0a0f18",
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: "#f2f5fb",
    fontSize: 14,
  },
  queueStatus: {
    color: "#8ea0bf",
    fontSize: 12,
    lineHeight: 18,
  },
  sectionGroup: {
    gap: 10,
    marginTop: 4,
  },
  spotlightPanel: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#29415b",
    backgroundColor: "#111b2a",
    padding: 12,
    gap: 4,
  },
  spotlightLabel: {
    color: "#7cf0bb",
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 0.8,
    textTransform: "uppercase",
  },
  spotlightTitle: {
    color: "#eef4fc",
    fontSize: 15,
    fontWeight: "700",
  },
  spotlightMeta: {
    color: "#8ea0bf",
    fontSize: 12,
    lineHeight: 18,
  },
  relationshipMetaText: {
    color: "#a8b5cc",
    fontSize: 12,
    lineHeight: 18,
  },
  feedList: {
    gap: 10,
  },
  feedRow: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#24314b",
    backgroundColor: "#101725",
    padding: 12,
    gap: 6,
  },
  feedTopRow: {
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
  },
  feedTitleWrap: {
    flex: 1,
    gap: 6,
  },
  feedBadgeRow: {
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap",
  },
  feedBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: "#182235",
    color: "#8dc8ff",
    fontSize: 11,
    fontWeight: "700",
    textTransform: "capitalize",
    overflow: "hidden",
  },
  feedBadgePinned: {
    alignSelf: "flex-start",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: "#173124",
    color: "#8ef0b3",
    fontSize: 11,
    fontWeight: "700",
    overflow: "hidden",
  },
  feedTitle: {
    color: "#eef4fc",
    fontSize: 14,
    fontWeight: "700",
  },
  feedTimestamp: {
    color: "#90a0bd",
    fontSize: 12,
  },
  feedSummary: {
    color: "#d7deea",
    fontSize: 13,
    lineHeight: 19,
  },
  feedMeta: {
    color: "#7f8ba1",
    fontSize: 11,
  },
  pinButton: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#29415b",
    backgroundColor: "#111b2a",
    paddingHorizontal: 12,
    paddingVertical: 7,
    alignItems: "center",
    justifyContent: "center",
  },
  pinButtonActive: {
    borderColor: "#8ef0b3",
    backgroundColor: "#173124",
  },
  pinButtonText: {
    color: "#9fc4de",
    fontSize: 12,
    fontWeight: "700",
  },
  pinButtonTextActive: {
    color: "#8ef0b3",
  },
  memoryPanel: {
    backgroundColor: "#151d2e",
    borderRadius: 14,
    padding: 14,
    gap: 6,
  },
  memoryPanelReply: {
    borderLeftWidth: 3,
    borderLeftColor: "#8ef0b3",
    backgroundColor: "#122017",
  },
  memoryLabel: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1,
    color: "#7f8ba1",
  },
  memoryText: {
    color: "#ced7e7",
    fontSize: 14,
    lineHeight: 20,
  },
  memoryReplyLabel: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1,
    color: "#7cf0bb",
  },
  memoryReplyText: {
    color: "#eaf4ee",
    fontSize: 14,
    lineHeight: 20,
  },
  footerNote: {
    color: "#627089",
    fontSize: 12,
    lineHeight: 18,
    paddingBottom: 18,
  },
});
