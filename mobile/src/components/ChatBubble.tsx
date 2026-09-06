import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { radius, spacing, type Theme, typography, useThemedStyles } from "../theme";

interface Props {
  role: "user" | "assistant";
  text: string;
  testID?: string;
}

/** Shared chat bubble — F5's ChatScreen (MOBILE_ARCHITECTURE.md §2, "the
 * conversational planner — primary interaction surface"). */
export function ChatBubble({ role, text, testID }: Props): React.JSX.Element {
  const styles = useThemedStyles(createStyles);
  const isUser = role === "user";
  return (
    <View style={[styles.row, isUser ? styles.rowUser : styles.rowAssistant]}>
      <View
        style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}
        testID={testID}
      >
        <Text style={[styles.text, isUser ? styles.textUser : styles.textAssistant]}>{text}</Text>
      </View>
    </View>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    row: { flexDirection: "row", marginVertical: spacing.xs },
    rowUser: { justifyContent: "flex-end" },
    rowAssistant: { justifyContent: "flex-start" },
    bubble: {
      maxWidth: "82%",
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.md,
      borderRadius: radius.lg,
    },
    bubbleUser: { backgroundColor: colors.primary, borderBottomRightRadius: radius.sm },
    bubbleAssistant: {
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
      borderBottomLeftRadius: radius.sm,
    },
    text: { ...typography.body },
    textUser: { color: colors.primaryText },
    textAssistant: { color: colors.text },
  });
