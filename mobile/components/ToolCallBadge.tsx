import React from "react";
import { View, Text, StyleSheet } from "react-native";

interface Props {
  toolName: string;
  status: "running" | "success" | "error";
  result?: string;
}

const riskColors: Record<string, string> = {
  computer_use: "#ff9944",
  file_ops: "#44aaff",
  secrets: "#ff4488",
  context: "#8ef0b3",
  relationship: "#ffd86b",
  general: "#888",
};

export default function ToolCallBadge({ toolName, status, result }: Props) {
  const category = toolName.includes("click") || toolName.includes("mouse") || toolName.includes("type") || toolName.includes("key")
    ? "computer_use"
    : toolName.includes("secret") || toolName.includes("clipboard")
    ? "secrets"
    : toolName.includes("convert") || toolName.includes("image") || toolName.includes("video") || toolName.includes("file")
    ? "file_ops"
    : toolName.includes("relationship") || toolName.includes("followup")
    ? "relationship"
    : toolName.includes("context") || toolName.includes("pending")
    ? "context"
    : "general";

  const color = riskColors[category];

  const statusIcon = status === "running" ? "⏳" : status === "success" ? "✅" : "❌";

  return (
    <View style={[styles.badge, { borderLeftColor: color }]}>
      <View style={styles.header}>
        <Text style={[styles.toolName, { color }]}>{toolName}</Text>
        <Text style={styles.statusIcon}>{statusIcon}</Text>
      </View>
      {result ? (
        <Text style={styles.result} numberOfLines={2}>
          {result}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    backgroundColor: "#111",
    borderRadius: 8,
    padding: 10,
    borderLeftWidth: 3,
    marginVertical: 4,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  toolName: { fontSize: 13, fontWeight: "600", fontFamily: "monospace" },
  statusIcon: { fontSize: 14 },
  result: { fontSize: 12, color: "#666", marginTop: 4 },
});
