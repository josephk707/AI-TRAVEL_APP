import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { ApiError } from "../api/client";
import { fetchWeather, Weather } from "../api/weather";
import { useTranslation } from "../i18n";
import { colors, radius, spacing, typography } from "../theme/tokens";
import { Card } from "./Card";
import { LoadingView } from "./LoadingView";

type State =
  | { status: "loading" }
  | { status: "success"; weather: Weather }
  | { status: "error"; message: string };

// A representative subset of WMO codes -> Ionicons, matching
// backend/app/services/open_meteo_client.py's own code grouping.
function iconForCondition(code: number): keyof typeof Ionicons.glyphMap {
  if (code === 0 || code === 1) return "sunny-outline";
  if (code === 2 || code === 3) return "partly-sunny-outline";
  if (code === 45 || code === 48) return "cloud-outline";
  if (code >= 51 && code <= 67) return "rainy-outline";
  if (code >= 71 && code <= 77) return "snow-outline";
  if (code >= 80 && code <= 82) return "rainy-outline";
  if (code >= 85 && code <= 86) return "snow-outline";
  if (code >= 95) return "thunderstorm-outline";
  return "partly-sunny-outline";
}

/** Maps Integration phase — real, live Open-Meteo current + forecast
 * weather for a place's real coordinates (GET /v1/weather). Self-contained
 * (fetches on mount given lat/lng) so any screen that already has a
 * location can drop this in — used first by PoiDetailScreen. */
export function WeatherCard({ lat, lng }: { lat: number; lng: number }): React.JSX.Element {
  const { t } = useTranslation();
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    // Resolves the next state without setting it synchronously in the
    // effect body (react-hooks/set-state-in-effect) — matches this
    // codebase's established resolveX/loadState split (see
    // PoiDetailScreen.tsx's resolveDetail).
    const resolveWeather = async (): Promise<State> => {
      try {
        const weather = await fetchWeather(lat, lng);
        return { status: "success", weather };
      } catch (error) {
        const message = error instanceof ApiError ? error.message : t("weather.couldntLoad");
        return { status: "error", message };
      }
    };
    resolveWeather().then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, [lat, lng, t]);

  return (
    <Card style={styles.card} testID="weather-card">
      <Text style={styles.title}>{t("weather.title")}</Text>

      {state.status === "loading" && <LoadingView label={t("weather.loading")} />}

      {state.status === "error" && (
        <Text style={styles.errorText} testID="weather-error">
          {state.message}
        </Text>
      )}

      {state.status === "success" && (
        <View>
          <View style={styles.currentRow}>
            <Ionicons
              name={iconForCondition(state.weather.current.condition_code)}
              size={40}
              color={colors.primary}
            />
            <View style={styles.currentTextGroup}>
              <Text style={styles.temperature}>
                {Math.round(state.weather.current.temperature_c)}°C
              </Text>
              <Text style={styles.condition}>{state.weather.current.condition}</Text>
            </View>
          </View>

          <View style={styles.statsRow}>
            {state.weather.current.humidity_percent != null && (
              <Text style={styles.statText}>
                {t("weather.humidity")}: {Math.round(state.weather.current.humidity_percent)}%
              </Text>
            )}
            {state.weather.current.wind_speed_kmh != null && (
              <Text style={styles.statText}>
                {t("weather.wind")}: {Math.round(state.weather.current.wind_speed_kmh)} km/h
              </Text>
            )}
          </View>

          {state.weather.daily.length > 0 && (
            <View style={styles.forecastRow}>
              {state.weather.daily.slice(0, 5).map((day, index) => (
                <View key={day.date} style={styles.forecastDay} testID={`weather-day-${day.date}`}>
                  <Text style={styles.forecastLabel}>
                    {index === 0 ? t("weather.today") : day.date.slice(5)}
                  </Text>
                  <Ionicons
                    name={iconForCondition(day.condition_code)}
                    size={20}
                    color={colors.textMuted}
                  />
                  <Text style={styles.forecastTemp}>
                    {Math.round(day.temperature_max_c)}°/{Math.round(day.temperature_min_c)}°
                  </Text>
                </View>
              ))}
            </View>
          )}
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.sm },
  title: { ...typography.subtitle, color: colors.text },
  errorText: { ...typography.caption, color: colors.textMuted },
  currentRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  currentTextGroup: { gap: 2 },
  temperature: { ...typography.title, color: colors.text },
  condition: { ...typography.body, color: colors.textMuted },
  statsRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.xs },
  statText: { ...typography.caption, color: colors.textMuted },
  forecastRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: spacing.md,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  forecastDay: { alignItems: "center", gap: 2, borderRadius: radius.sm },
  forecastLabel: { ...typography.micro, color: colors.textMuted },
  forecastTemp: { ...typography.caption, color: colors.text },
});
