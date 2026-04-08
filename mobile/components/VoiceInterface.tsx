import React, { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  Animated,
  StyleSheet,
} from "react-native";

interface Props {
  status: "idle" | "listening" | "thinking" | "speaking" | "error";
  onPress: () => void;
  lastUtterance?: string;
  lastResponse?: string;
}

export default function VoiceInterface({
  status,
  onPress,
  lastUtterance,
  lastResponse,
}: Props) {
  const pulseAnim = React.useRef(new Animated.Value(1)).current;

  React.useEffect(() => {
    if (status === "listening") {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.15, duration: 600, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
        ])
      ).start();
    } else {
      pulseAnim.setValue(1);
    }
  }, [status, pulseAnim]);

  const statusColors: Record<string, string> = {
    idle: "#333",
    listening: "#00ff9d",
    thinking: "#00d4ff",
    speaking: "#c084fc",
    error: "#ff4444",
  };

  const statusLabels: Record<string, string> = {
    idle: "Tap to speak",
    listening: "Listening...",
    thinking: "Thinking...",
    speaking: "Speaking...",
    error: "Error — tap to retry",
  };

  return (
    <View style={styles.container}>
      <Text style={styles.logo}>🫅</Text>
      <Text style={styles.title}>aiButler</Text>
      <Text style={styles.subtitle}>Your executive assistant</Text>

      <Animated.View
        style={[
          styles.micRing,
          { borderColor: statusColors[status], transform: [{ scale: pulseAnim }] },
        ]}
      >
        <TouchableOpacity
          style={[styles.micButton, { backgroundColor: statusColors[status] + "22" }]}
          onPress={onPress}
          activeOpacity={0.7}
        >
          <Text style={[styles.micIcon, { color: statusColors[status] }]}>
            {status === "speaking" ? "🔊" : status === "thinking" ? "🤔" : "🎤"}
          </Text>
        </TouchableOpacity>
      </Animated.View>

      <Text style={[styles.statusLabel, { color: statusColors[status] }]}>
        {statusLabels[status]}
      </Text>

      {lastUtterance ? (
        <View style={styles.utteranceBox}>
          <Text style={styles.utteranceLabel}>You said</Text>
          <Text style={styles.utteranceText}>{lastUtterance}</Text>
        </View>
      ) : null}

      {lastResponse ? (
        <View style={styles.responseBox}>
          <Text style={styles.responseLabel}>Butler</Text>
          <Text style={styles.responseText}>{lastResponse}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 32,
    backgroundColor: "#0a0a0f",
  },
  logo: { fontSize: 56, marginBottom: 8 },
  title: { fontSize: 36, fontWeight: "700", color: "#e8e8f0", marginBottom: 4 },
  subtitle: { fontSize: 16, color: "#666", marginBottom: 48 },
  micRing: {
    width: 140,
    height: 140,
    borderRadius: 70,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 24,
  },
  micButton: {
    width: 120,
    height: 120,
    borderRadius: 60,
    alignItems: "center",
    justifyContent: "center",
  },
  micIcon: { fontSize: 52 },
  statusLabel: { fontSize: 16, fontWeight: "500", marginBottom: 32 },
  utteranceBox: {
    width: "100%",
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  utteranceLabel: { fontSize: 11, color: "#555", marginBottom: 4, textTransform: "uppercase" },
  utteranceText: { fontSize: 16, color: "#aaa" },
  responseBox: {
    width: "100%",
    backgroundColor: "#0f2318",
    borderRadius: 12,
    padding: 16,
    borderLeftWidth: 3,
    borderLeftColor: "#00ff9d",
  },
  responseLabel: { fontSize: 11, color: "#00c87a", marginBottom: 4, textTransform: "uppercase" },
  responseText: { fontSize: 16, color: "#e8e8f0" },
});
