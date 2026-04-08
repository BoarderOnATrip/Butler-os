import React, { useEffect, useState } from "react";
import {
  LayoutChangeEvent,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

export interface ContextMapNode {
  id: string;
  ref?: string;
  title: string;
  subtitle?: string;
  summary?: string;
  kind: string;
  lane: string;
  accent: string;
  pinned?: boolean;
  priority?: string;
  score?: number;
  due_label?: string;
  meta?: Record<string, unknown>;
}

export interface ContextMapEdge {
  id: string;
  source: string;
  target: string;
  kind?: string;
  label?: string;
}

export interface ContextMapSnapshot {
  generated_at?: string;
  focus_ref?: string;
  spotlight?: string;
  stats?: {
    pinned?: number;
    relationships?: number;
    linked_entities?: number;
    linked_organizations?: number;
    linked_places?: number;
    linked_conversations?: number;
    pending?: number;
    signals?: number;
    overdue?: number;
  };
  nodes: ContextMapNode[];
  edges: ContextMapEdge[];
}

interface Props {
  snapshot: ContextMapSnapshot | null;
  busy: boolean;
  pinBusyRef?: string;
  onRefresh: () => void;
  onTogglePin: (ref: string, pinned: boolean, label: string) => void;
}

const ACCENT_COLORS: Record<string, { border: string; fill: string; text: string; line: string }> = {
  mint: { border: "#8ef0b3", fill: "#173124", text: "#ebfff3", line: "#2c5d42" },
  amber: { border: "#ffd86b", fill: "#372b11", text: "#fff5cf", line: "#6b5321" },
  rose: { border: "#ff8ca1", fill: "#3a1720", text: "#ffe7eb", line: "#6b2a39" },
  gold: { border: "#f7c766", fill: "#342610", text: "#fff3d3", line: "#6e5320" },
  sky: { border: "#7fd0ff", fill: "#132939", text: "#ebf8ff", line: "#214e69" },
  slate: { border: "#8ea0bf", fill: "#182131", text: "#eef4fc", line: "#2b3d57" },
};

function lerp(start: number, end: number, progress: number): number {
  return start + (end - start) * progress;
}

function radialPosition(
  index: number,
  count: number,
  radius: number,
  startAngle: number,
  endAngle: number,
  centerX: number,
  centerY: number
) {
  const progress = count <= 1 ? 0.5 : index / (count - 1);
  const angle = (lerp(startAngle, endAngle, progress) * Math.PI) / 180;
  return {
    x: centerX + Math.cos(angle) * radius,
    y: centerY + Math.sin(angle) * radius,
  };
}

function nodeSize(node: ContextMapNode): number {
  if (node.kind === "hub") {
    return 98;
  }
  if (node.kind === "person") {
    return node.pinned ? 78 : 70;
  }
  if (node.kind === "organization") {
    return node.pinned ? 72 : 64;
  }
  if (node.kind === "place") {
    return node.pinned ? 68 : 60;
  }
  if (node.kind === "conversation") {
    return node.pinned ? 68 : 60;
  }
  if (node.kind === "pending") {
    return 66;
  }
  if (node.kind === "signal") {
    return 56;
  }
  return 62;
}

function layoutForLane(
  lane: string,
  index: number,
  count: number,
  width: number,
  height: number
) {
  const centerX = width / 2;
  const centerY = height / 2;

  if (lane === "anchors") {
    return radialPosition(index, count, Math.min(width * 0.19, 74), 220, 320, centerX, centerY - 4);
  }
  if (lane === "linked") {
    return radialPosition(index, count, Math.min(width * 0.42, 156), 146, 34, centerX, centerY - 2);
  }
  if (lane === "relationships") {
    return radialPosition(index, count, Math.min(width * 0.33, 128), 214, 326, centerX, centerY - 6);
  }
  if (lane === "pending") {
    return radialPosition(index, count, Math.min(width * 0.34, 132), 104, 188, centerX, centerY + 2);
  }
  if (lane === "signals") {
    return radialPosition(index, count, Math.min(width * 0.34, 132), -8, 76, centerX, centerY + 2);
  }
  return radialPosition(index, count, Math.min(width * 0.24, 92), 0, 360, centerX, centerY);
}

function formatNodeMeta(node: ContextMapNode): string {
  const parts = [
    node.kind,
    node.priority,
    node.due_label,
    typeof node.score === "number" && node.score > 0 ? `${node.score} score` : "",
  ]
    .filter(Boolean)
    .map((part) => String(part));

  return parts.join(" | ");
}

export default function ContextMapCard({
  snapshot,
  busy,
  pinBusyRef,
  onRefresh,
  onTogglePin,
}: Props) {
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [canvasWidth, setCanvasWidth] = useState(0);

  useEffect(() => {
    if (!snapshot?.nodes?.length) {
      setSelectedNodeId("");
      return;
    }
    const preferredId =
      snapshot.focus_ref && snapshot.nodes.some((node) => node.id === snapshot.focus_ref)
        ? snapshot.focus_ref
        : snapshot.nodes.find((node) => node.kind !== "hub")?.id || snapshot.nodes[0]?.id || "";
    setSelectedNodeId(preferredId);
  }, [snapshot]);

  const canvasHeight = 320;
  const effectiveWidth = Math.max(canvasWidth, 300);
  const laneCounts: Record<string, number> = {};
  const laneIndexes: Record<string, number> = {};
  for (const node of snapshot?.nodes || []) {
    laneCounts[node.lane] = (laneCounts[node.lane] || 0) + 1;
  }

  const positions: Record<string, { x: number; y: number; size: number }> = {};
  for (const node of snapshot?.nodes || []) {
    const laneIndex = laneIndexes[node.lane] || 0;
    laneIndexes[node.lane] = laneIndex + 1;
    if (node.kind === "hub") {
      positions[node.id] = {
        x: effectiveWidth / 2,
        y: canvasHeight / 2,
        size: nodeSize(node),
      };
      continue;
    }

    const point = layoutForLane(node.lane, laneIndex, laneCounts[node.lane] || 1, effectiveWidth, canvasHeight);
    positions[node.id] = {
      x: point.x,
      y: point.y,
      size: nodeSize(node),
    };
  }

  const selectedNode =
    snapshot?.nodes.find((node) => node.id === selectedNodeId) ||
    snapshot?.nodes.find((node) => node.kind !== "hub") ||
    snapshot?.nodes[0] ||
    null;

  const stats = snapshot?.stats || {};
  const detailRef = selectedNode?.ref || "";
  const canPin = Boolean(detailRef) && detailRef !== "hub::today" && !selectedNode?.id.startsWith("signal::");

  function handleCanvasLayout(event: LayoutChangeEvent) {
    setCanvasWidth(event.nativeEvent.layout.width);
  }

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Context map</Text>
      <Text style={styles.cardBody}>
        The map is the fast visual projection of your Butler memory: live relationship pressure, unresolved captures, and recent signals tied together.
      </Text>

      <View style={styles.metricRow}>
        <View style={styles.metricChip}>
          <Text style={styles.metricLabel}>Relationships</Text>
          <Text style={styles.metricValue}>{stats.relationships || 0}</Text>
        </View>
        <View style={styles.metricChip}>
          <Text style={styles.metricLabel}>Pending</Text>
          <Text style={styles.metricValue}>{stats.pending || 0}</Text>
        </View>
        <View style={styles.metricChip}>
          <Text style={styles.metricLabel}>Pinned</Text>
          <Text style={styles.metricValue}>{stats.pinned || 0}</Text>
        </View>
        <View style={styles.metricChip}>
          <Text style={styles.metricLabel}>Linked</Text>
          <Text style={styles.metricValue}>{stats.linked_entities || 0}</Text>
        </View>
        <View style={styles.metricChip}>
          <Text style={styles.metricLabel}>Signals</Text>
          <Text style={styles.metricValue}>{stats.signals || 0}</Text>
        </View>
      </View>

      <View style={styles.spotlightCard}>
        <Text style={styles.spotlightLabel}>Spotlight</Text>
        <Text style={styles.spotlightText}>
          {snapshot?.spotlight || "Log interactions and capture artifacts to start building your map."}
        </Text>
      </View>

      <View style={styles.canvasShell} onLayout={handleCanvasLayout}>
        <View style={styles.ringOuter} />
        <View style={styles.ringMiddle} />
        <View style={styles.ringInner} />

        {snapshot?.edges.map((edge) => {
          const source = positions[edge.source];
          const target = positions[edge.target];
          if (!source || !target) {
            return null;
          }
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const length = Math.sqrt(dx * dx + dy * dy);
          const angle = Math.atan2(dy, dx);
          return (
            <View
              key={edge.id}
              style={[
                styles.edge,
                {
                  width: length,
                  left: (source.x + target.x) / 2 - length / 2,
                  top: (source.y + target.y) / 2 - 1,
                  transform: [{ rotateZ: `${angle}rad` }],
                  backgroundColor:
                    ACCENT_COLORS[
                      edge.kind === "pending"
                        ? "gold"
                        : edge.kind === "signal"
                        ? "sky"
                        : edge.kind === "pin"
                        ? "mint"
                        : "slate"
                    ].line,
                },
              ]}
            />
          );
        })}

        {snapshot?.nodes.map((node) => {
          const position = positions[node.id];
          if (!position) {
            return null;
          }
          const accent = ACCENT_COLORS[node.accent] || ACCENT_COLORS.slate;
          const size = position.size;
          const isSelected = selectedNodeId === node.id;

          return (
            <TouchableOpacity
              key={node.id}
              style={[
                styles.node,
                {
                  width: size,
                  height: size,
                  left: position.x - size / 2,
                  top: position.y - size / 2,
                  borderColor: accent.border,
                  backgroundColor: accent.fill,
                },
                isSelected && styles.nodeSelected,
              ]}
              activeOpacity={0.88}
              onPress={() => setSelectedNodeId(node.id)}
            >
              <Text
                style={[
                  styles.nodeTitle,
                  {
                    color: accent.text,
                    fontSize: node.kind === "hub" ? 16 : 12,
                  },
                ]}
                numberOfLines={2}
              >
                {node.title}
              </Text>
              {node.kind !== "hub" ? (
                <Text style={[styles.nodeSubtitle, { color: accent.text }]} numberOfLines={2}>
                  {node.subtitle || node.kind}
                </Text>
              ) : null}
            </TouchableOpacity>
          );
        })}
      </View>

      <View style={styles.legendRow}>
        <Text style={styles.legendChip}>Mint = pinned anchors</Text>
        <Text style={styles.legendChip}>Amber = hot relationships</Text>
        <Text style={styles.legendChip}>Slate = linked context</Text>
        <Text style={styles.legendChip}>Gold = pending review</Text>
        <Text style={styles.legendChip}>Sky = recent signals</Text>
      </View>

      <View style={styles.buttonRow}>
        <TouchableOpacity style={[styles.primaryButton, busy && styles.buttonDisabled]} disabled={busy} onPress={onRefresh}>
          <Text style={styles.primaryButtonText}>{busy ? "Refreshing..." : "Refresh Map"}</Text>
        </TouchableOpacity>
      </View>

      {selectedNode ? (
        <View style={styles.detailCard}>
          <View style={styles.detailTopRow}>
            <View style={styles.detailTitleWrap}>
              <Text style={styles.detailTitle}>{selectedNode.title}</Text>
              {selectedNode.subtitle ? <Text style={styles.detailSubtitle}>{selectedNode.subtitle}</Text> : null}
            </View>
            {canPin ? (
              <TouchableOpacity
                style={[
                  styles.pinButton,
                  selectedNode.pinned && styles.pinButtonActive,
                  pinBusyRef === detailRef && styles.buttonDisabled,
                ]}
                disabled={pinBusyRef === detailRef}
                onPress={() => onTogglePin(detailRef, Boolean(selectedNode.pinned), selectedNode.title)}
              >
                <Text style={[styles.pinButtonText, selectedNode.pinned && styles.pinButtonTextActive]}>
                  {pinBusyRef === detailRef ? "..." : selectedNode.pinned ? "Unpin" : "Pin"}
                </Text>
              </TouchableOpacity>
            ) : null}
          </View>
          {formatNodeMeta(selectedNode) ? <Text style={styles.detailMeta}>{formatNodeMeta(selectedNode)}</Text> : null}
          {selectedNode.summary ? <Text style={styles.detailSummary}>{selectedNode.summary}</Text> : null}
          {selectedNode.ref ? <Text style={styles.detailRef}>{selectedNode.ref}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#0f1420",
    borderRadius: 18,
    padding: 18,
    borderWidth: 1,
    borderColor: "#1b2232",
    gap: 12,
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
  metricRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  metricChip: {
    minWidth: 72,
    borderRadius: 12,
    backgroundColor: "#121a29",
    borderWidth: 1,
    borderColor: "#23304a",
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 2,
  },
  metricLabel: {
    color: "#7f8ba1",
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  metricValue: {
    color: "#f2f5fb",
    fontSize: 15,
    fontWeight: "800",
  },
  spotlightCard: {
    borderRadius: 14,
    backgroundColor: "#132217",
    borderWidth: 1,
    borderColor: "#24422d",
    padding: 12,
    gap: 4,
  },
  spotlightLabel: {
    color: "#8ef0b3",
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  spotlightText: {
    color: "#edf9f1",
    fontSize: 14,
    lineHeight: 20,
  },
  canvasShell: {
    minHeight: 320,
    borderRadius: 18,
    overflow: "hidden",
    backgroundColor: "#0a1019",
    borderWidth: 1,
    borderColor: "#1a2639",
    position: "relative",
  },
  ringOuter: {
    position: "absolute",
    width: 278,
    height: 278,
    borderRadius: 139,
    borderWidth: 1,
    borderColor: "#162033",
    top: 20,
    left: "50%",
    marginLeft: -139,
  },
  ringMiddle: {
    position: "absolute",
    width: 198,
    height: 198,
    borderRadius: 99,
    borderWidth: 1,
    borderColor: "#1b2a40",
    top: 60,
    left: "50%",
    marginLeft: -99,
  },
  ringInner: {
    position: "absolute",
    width: 118,
    height: 118,
    borderRadius: 59,
    borderWidth: 1,
    borderColor: "#20324d",
    top: 100,
    left: "50%",
    marginLeft: -59,
  },
  edge: {
    position: "absolute",
    height: 2,
    borderRadius: 999,
    opacity: 0.95,
  },
  node: {
    position: "absolute",
    borderRadius: 999,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 8,
    gap: 2,
  },
  nodeSelected: {
    shadowColor: "#8ef0b3",
    shadowOpacity: 0.35,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 0 },
  },
  nodeTitle: {
    textAlign: "center",
    fontWeight: "800",
  },
  nodeSubtitle: {
    textAlign: "center",
    fontSize: 10,
    opacity: 0.88,
  },
  legendRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  legendChip: {
    color: "#8ea0bf",
    fontSize: 12,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#23304a",
    backgroundColor: "#111826",
    paddingHorizontal: 10,
    paddingVertical: 6,
    overflow: "hidden",
  },
  buttonRow: {
    flexDirection: "row",
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
  buttonDisabled: {
    opacity: 0.6,
  },
  detailCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#23304a",
    backgroundColor: "#111826",
    padding: 12,
    gap: 6,
  },
  detailTopRow: {
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
  },
  detailTitleWrap: {
    flex: 1,
    gap: 4,
  },
  detailTitle: {
    color: "#eef4fc",
    fontSize: 15,
    fontWeight: "800",
  },
  detailSubtitle: {
    color: "#98a6c1",
    fontSize: 13,
  },
  detailMeta: {
    color: "#8ef0b3",
    fontSize: 12,
    textTransform: "capitalize",
  },
  detailSummary: {
    color: "#d7deea",
    fontSize: 13,
    lineHeight: 19,
  },
  detailRef: {
    color: "#6d7c95",
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
});
