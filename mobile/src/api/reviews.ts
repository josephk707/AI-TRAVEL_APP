/**
 * Typed calls to /v1/reviews, /v1/pois/{id}/reviews — F14, see
 * docs/API_SPECIFICATION.md §12.
 */

import { apiGet, apiPost } from "./client";

export type ReviewStatus = "pending" | "published" | "rejected";

export interface Review {
  id: string;
  user_id: string;
  poi_id: string;
  trip_id: string;
  rating: number;
  review_text: string | null;
  status: ReviewStatus;
  created_at: string;
}

interface Envelope<T> {
  data: T;
}

export async function createReview(
  poiId: string,
  tripId: string,
  rating: number,
  reviewText?: string,
): Promise<Review> {
  const envelope = await apiPost<Envelope<Review>>("/v1/reviews", {
    poi_id: poiId,
    trip_id: tripId,
    rating,
    review_text: reviewText,
  });
  return envelope.data;
}

export async function listPoiReviews(poiId: string, signal?: AbortSignal): Promise<Review[]> {
  const envelope = await apiGet<Envelope<Review[]>>(`/v1/pois/${poiId}/reviews`, signal);
  return envelope.data;
}
