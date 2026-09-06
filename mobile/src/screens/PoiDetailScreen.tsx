import { Ionicons } from "@expo/vector-icons";
import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { Poi } from "../api/pois";
import { ApiError } from "../api/client";
import { fetchPoi } from "../api/pois";
import { addFavorite, listFavorites, removeFavorite } from "../api/collections";
import { createReview, listPoiReviews, Review } from "../api/reviews";
import { listTrips, Trip } from "../api/trips";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ErrorState } from "../components/ErrorState";
import { LoadingView } from "../components/LoadingView";
import { MapErrorBoundary } from "../components/MapErrorBoundary";
import { MapView, Marker, PROVIDER_GOOGLE } from "../components/PlatformMap";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import { WeatherCard } from "../components/WeatherCard";
import { useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

type LoadState =
  | { status: "loading" }
  | { status: "success"; poi: Poi }
  | { status: "error"; message: string };

type ReviewFormState = { visible: false } | { visible: true; tripId: string | null; rating: number; text: string };

const OPENING_HOURS_DAY_ORDER = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

function formatOpeningHours(hours: Record<string, unknown> | null): string[] {
  if (!hours) return [];
  const entries = Object.entries(hours).filter(([, value]) => typeof value === "string");
  if (entries.length === 0) return [];
  entries.sort(
    ([a], [b]) => OPENING_HOURS_DAY_ORDER.indexOf(a) - OPENING_HOURS_DAY_ORDER.indexOf(b),
  );
  return entries.map(([day, value]) => `${day[0].toUpperCase()}${day.slice(1)}: ${value}`);
}

/** F6 — Maps & Navigation. POI detail: address, category, opening hours
 * (when known — "verify on arrival" otherwise, matching FR-007's
 * exception-flow wording used elsewhere in this product for unconfirmed
 * hours), and a small map centered on the place. */
export function PoiDetailScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList, "PoiDetail">>();
  const route = useRoute<RouteProp<RootStackParamList, "PoiDetail">>();
  const insets = useSafeAreaInsets();
  const { t } = useTranslation();
  const { colors, isDark } = useTheme();
  const styles = useThemedStyles(createStyles);
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [isFavorite, setIsFavorite] = useState(false);
  const [favoriteBusy, setFavoriteBusy] = useState(false);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [reviewForm, setReviewForm] = useState<ReviewFormState>({ visible: false });
  const [completedTrips, setCompletedTrips] = useState<Trip[]>([]);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [submittingReview, setSubmittingReview] = useState(false);

  // Resolves the next LoadState without setting state itself, so the
  // effect below can set state only inside a .then() callback
  // (react-hooks/set-state-in-effect) while the retry button — a real
  // event handler, not an effect — is free to set the "loading" state
  // synchronously before calling this (same split as
  // InterestSelectScreen.tsx's resolveInterests/loadInterests).
  const resolveDetail = useCallback(async (): Promise<LoadState> => {
    try {
      const poi = await fetchPoi(route.params.poiId);
      return { status: "success", poi };
    } catch (error) {
      return {
        status: "error",
        message: error instanceof ApiError ? error.message : t("poiDetail.couldntLoadPlace"),
      };
    }
  }, [route.params.poiId, t]);

  useEffect(() => {
    let cancelled = false;
    resolveDetail().then((result) => {
      if (!cancelled) setLoadState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveDetail]);

  useEffect(() => {
    if (loadState.status !== "success") return;
    let cancelled = false;
    listFavorites()
      .then((favorites) => {
        if (!cancelled) setIsFavorite(favorites.some((f) => f.poi_id === loadState.poi.id));
      })
      .catch(() => undefined);
    listPoiReviews(loadState.poi.id)
      .then((fetched) => {
        if (!cancelled) setReviews(fetched);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [loadState]);

  const retryLoad = useCallback(() => {
    setLoadState({ status: "loading" });
    void resolveDetail().then(setLoadState);
  }, [resolveDetail]);

  const toggleFavorite = useCallback(async () => {
    if (loadState.status !== "success" || favoriteBusy) return;
    setFavoriteBusy(true);
    try {
      if (isFavorite) {
        await removeFavorite(loadState.poi.id);
        setIsFavorite(false);
      } else {
        await addFavorite(loadState.poi.id);
        setIsFavorite(true);
      }
    } catch {
      // A failed favorite toggle is not worth an error screen — the icon
      // simply stays in its previous state and the user can retry the tap.
    } finally {
      setFavoriteBusy(false);
    }
  }, [loadState, isFavorite, favoriteBusy]);

  const openReviewForm = useCallback(() => {
    setReviewError(null);
    setReviewForm({ visible: true, tripId: null, rating: 5, text: "" });
    listTrips()
      .then((trips) => setCompletedTrips(trips.filter((t) => t.status === "completed")))
      .catch(() => setCompletedTrips([]));
  }, []);

  const submitReview = useCallback(async () => {
    if (loadState.status !== "success" || !reviewForm.visible || !reviewForm.tripId) {
      setReviewError(t("poiDetail.chooseCompletedTrip"));
      return;
    }
    setSubmittingReview(true);
    setReviewError(null);
    try {
      await createReview(loadState.poi.id, reviewForm.tripId, reviewForm.rating, reviewForm.text || undefined);
      setReviewForm({ visible: false });
      const fetched = await listPoiReviews(loadState.poi.id);
      setReviews(fetched);
    } catch (error) {
      setReviewError(error instanceof ApiError ? error.message : t("poiDetail.couldntSubmitReview"));
    } finally {
      setSubmittingReview(false);
    }
  }, [loadState, reviewForm, t]);

  return (
    <Screen>
      <View style={[styles.container, { paddingTop: insets.top + spacing.md }]}>
      <ScreenHeader title="" />

      {loadState.status === "loading" && (
        <View style={styles.centerFill}>
          <LoadingView label={t("poiDetail.loadingPlace")} />
        </View>
      )}

      {loadState.status === "error" && (
        <View style={styles.centerFill} testID="poi-detail-error">
          <ErrorState
            message={loadState.message}
            retryLabel={t("common.retry")}
            onRetry={retryLoad}
            testID="poi-detail-retry-button"
          />
        </View>
      )}

      {loadState.status === "success" && (
        <ScrollView contentContainerStyle={styles.scrollContent} testID="poi-detail-content">
          <MapErrorBoundary fallback={<View style={styles.mapFallback} />}>
            <MapView
              testID="poi-detail-map"
              style={styles.map}
              provider={PROVIDER_GOOGLE}
              userInterfaceStyle={isDark ? "dark" : "light"}
              initialRegion={{
                latitude: loadState.poi.location.lat,
                longitude: loadState.poi.location.lng,
                latitudeDelta: 0.02,
                longitudeDelta: 0.02,
              }}
            >
              <Marker
                coordinate={{
                  latitude: loadState.poi.location.lat,
                  longitude: loadState.poi.location.lng,
                }}
                title={loadState.poi.name}
              />
            </MapView>
          </MapErrorBoundary>

          <View style={styles.body}>
            <View style={styles.nameRow}>
              <Text style={styles.name}>{loadState.poi.name}</Text>
              <Pressable
                onPress={() => void toggleFavorite()}
                disabled={favoriteBusy}
                accessibilityRole="button"
                testID="favorite-toggle-button"
              >
                <Ionicons
                  name={isFavorite ? "heart" : "heart-outline"}
                  size={26}
                  color={isFavorite ? colors.text : colors.textMuted}
                />
              </Pressable>
            </View>
            {loadState.poi.address && <Text style={styles.address}>{loadState.poi.address}</Text>}

            <Card style={styles.detailCard}>
              <DetailRow icon="pricetag-outline" label={t("poiDetail.category")}>
                {loadState.poi.category}
              </DetailRow>
              {loadState.poi.avg_cost != null && (
                <DetailRow icon="wallet-outline" label={t("poiDetail.typicalCost")}>
                  ₹{loadState.poi.avg_cost}
                </DetailRow>
              )}
              <DetailRow icon="time-outline" label={t("poiDetail.openingHours")}>
                {formatOpeningHours(loadState.poi.opening_hours).length > 0
                  ? formatOpeningHours(loadState.poi.opening_hours).join("\n")
                  : t("poiDetail.hoursNotConfirmed")}
              </DetailRow>
            </Card>

            <WeatherCard lat={loadState.poi.location.lat} lng={loadState.poi.location.lng} />

            {loadState.poi.category === "heritage" && (
              <Pressable
                style={({ pressed }) => [styles.heritageCard, pressed && styles.heritageCardPressed]}
                onPress={() =>
                  navigation.navigate("HeritageNarration", {
                    poiId: loadState.poi.id,
                    poiName: loadState.poi.name,
                  })
                }
                accessibilityRole="button"
                testID="heritage-story-button"
              >
                <Ionicons name="book-outline" size={20} color={colors.primaryText} />
                <Text style={styles.heritageCardText}>{t("poiDetail.readHeritageStory")}</Text>
                <Ionicons name="chevron-forward" size={18} color={colors.primaryText} />
              </Pressable>
            )}

            <View style={styles.reviewsSection} testID="reviews-section">
              <View style={styles.reviewsHeader}>
                <Text style={styles.reviewsHeading}>
                  {t("poiDetail.reviews")} ({reviews.length})
                </Text>
                {!reviewForm.visible && (
                  <Pressable onPress={openReviewForm} testID="write-review-button">
                    <Text style={styles.writeReviewText}>{t("poiDetail.writeReview")}</Text>
                  </Pressable>
                )}
              </View>

              {reviews.length === 0 && (
                <Text style={styles.emptyReviewsText} testID="reviews-empty">
                  {t("poiDetail.noReviewsYet")}
                </Text>
              )}

              {reviews.map((review) => (
                <Card key={review.id} style={styles.reviewCard} variant="flat" testID={`review-${review.id}`}>
                  <Text style={styles.reviewRating}>{"★".repeat(review.rating)}{"☆".repeat(5 - review.rating)}</Text>
                  {review.review_text && <Text style={styles.reviewText}>{review.review_text}</Text>}
                </Card>
              ))}

              {reviewForm.visible && (
                <Card style={styles.reviewForm} variant="flat" testID="review-form">
                  {completedTrips.length === 0 ? (
                    <Text style={styles.emptyReviewsText}>{t("poiDetail.completeATripPrompt")}</Text>
                  ) : (
                    <View style={styles.tripPickerRow}>
                      {completedTrips.map((trip) => (
                        <Pressable
                          key={trip.id}
                          onPress={() => setReviewForm({ ...reviewForm, tripId: trip.id })}
                          testID={`review-trip-${trip.id}`}
                        >
                          <Text
                            style={[
                              styles.tripChip,
                              reviewForm.tripId === trip.id && styles.tripChipActive,
                            ]}
                          >
                            {trip.title}
                          </Text>
                        </Pressable>
                      ))}
                    </View>
                  )}

                  <View style={styles.starRow}>
                    {[1, 2, 3, 4, 5].map((value) => (
                      <Pressable
                        key={value}
                        onPress={() => setReviewForm({ ...reviewForm, rating: value })}
                        testID={`review-star-${value}`}
                      >
                        <Ionicons
                          name={value <= reviewForm.rating ? "star" : "star-outline"}
                          size={26}
                          color={colors.gold}
                        />
                      </Pressable>
                    ))}
                  </View>

                  {reviewError && <Text style={styles.errorText}>{reviewError}</Text>}

                  <View style={styles.reviewFormActions}>
                    <Button
                      label={submittingReview ? t("poiDetail.submittingReview") : t("poiDetail.submitReview")}
                      onPress={() => void submitReview()}
                      disabled={submittingReview || completedTrips.length === 0}
                      testID="submit-review-button"
                      fullWidth={false}
                    />
                    <Pressable onPress={() => setReviewForm({ visible: false })} testID="cancel-review-button">
                      <Text style={styles.cancelReviewText}>{t("common.cancel")}</Text>
                    </Pressable>
                  </View>
                </Card>
              )}
            </View>
          </View>
        </ScrollView>
      )}
      </View>
    </Screen>
  );
}

function DetailRow({
  icon,
  label,
  children,
}: {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  children: React.ReactNode;
}): React.JSX.Element {
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
  return (
    <View style={styles.detailRow}>
      <Ionicons name={icon} size={18} color={colors.textMuted} />
      <View style={styles.detailTextGroup}>
        <Text style={styles.detailLabel}>{label}</Text>
        <Text style={styles.detailValue}>{children}</Text>
      </View>
    </View>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    container: { flex: 1 },
    centerFill: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
    errorText: { ...typography.body, color: colors.error, textAlign: "center" },
    scrollContent: { paddingBottom: spacing.xl },
    map: { height: 220, width: "100%" },
    mapFallback: {
      height: 220,
      width: "100%",
      backgroundColor: colors.surfaceAlt,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
    },
    body: { padding: spacing.lg, gap: spacing.sm },
    nameRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    name: { ...typography.title, color: colors.text, flex: 1 },
    address: { ...typography.body, color: colors.textMuted },
    reviewsSection: { marginTop: spacing.lg, gap: spacing.sm },
    reviewsHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
    reviewsHeading: { ...typography.subtitle, color: colors.text },
    writeReviewText: { ...typography.captionMedium, color: colors.text },
    emptyReviewsText: { ...typography.body, color: colors.textMuted },
    reviewCard: { gap: spacing.xs },
    reviewRating: { color: colors.gold, fontSize: 16 },
    reviewText: { ...typography.body, color: colors.text },
    reviewForm: { gap: spacing.sm },
    tripPickerRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
    tripChip: {
      ...typography.caption,
      color: colors.textMuted,
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.sm,
      paddingVertical: spacing.xs,
      paddingHorizontal: spacing.sm,
    },
    tripChipActive: {
      backgroundColor: colors.primarySoft,
      color: colors.text,
      borderColor: colors.primary,
    },
    starRow: { flexDirection: "row", gap: spacing.xs },
    reviewFormActions: { flexDirection: "row", alignItems: "center", gap: spacing.md },
    cancelReviewText: { ...typography.body, color: colors.textMuted },
    detailCard: { gap: spacing.md, marginTop: spacing.sm },
    heritageCard: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.sm,
      backgroundColor: colors.primary,
      borderRadius: radius.lg,
      padding: spacing.md,
      marginTop: spacing.md,
    },
    heritageCardPressed: { opacity: 0.85 },
    heritageCardText: { ...typography.subtitle, color: colors.primaryText, flex: 1 },
    detailRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
    detailTextGroup: { flex: 1 },
    detailLabel: { ...typography.caption, color: colors.textMuted },
    detailValue: { ...typography.body, color: colors.text, textTransform: "capitalize" },
  });
