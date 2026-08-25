/**
 * Typed calls to /v1/pois/* — see docs/API_SPECIFICATION.md §5.
 */

import { apiGet } from "./client";

export type PoiCategory =
  | "heritage"
  | "restaurant"
  | "attraction"
  | "nature"
  | "shopping"
  | "other";

export interface PoiCoordinates {
  lat: number;
  lng: number;
}

export interface Poi {
  id: string;
  name: string;
  category: PoiCategory;
  location: PoiCoordinates;
  address: string | null;
  city: string | null;
  region: string | null;
  country: string;
  opening_hours: Record<string, unknown> | null;
  avg_cost: number | null;
  source: "curated" | "places_api";
  is_heritage_flagship: boolean;
  created_at: string;
  updated_at: string;
}

interface Envelope<T> {
  data: T;
  meta?: { degraded_mode?: boolean | null; message?: string | null } | null;
}

export interface PoiSearchResult {
  pois: Poi[];
  degraded: boolean;
  message: string | null;
}

export interface SearchPoisParams {
  query?: string;
  category?: PoiCategory;
  lat?: number;
  lng?: number;
  radiusM?: number;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export async function searchPois(
  params: SearchPoisParams,
  signal?: AbortSignal,
): Promise<PoiSearchResult> {
  const query = buildQuery({
    query: params.query,
    category: params.category,
    lat: params.lat,
    lng: params.lng,
    radius_m: params.radiusM,
  });
  const envelope = await apiGet<Envelope<Poi[]>>(`/v1/pois/search${query}`, signal);
  return {
    pois: envelope.data,
    degraded: envelope.meta?.degraded_mode ?? false,
    message: envelope.meta?.message ?? null,
  };
}

export interface NearbyPoisParams {
  lat: number;
  lng: number;
  radiusM?: number;
  category?: PoiCategory;
}

export async function fetchNearbyPois(
  params: NearbyPoisParams,
  signal?: AbortSignal,
): Promise<Poi[]> {
  const query = buildQuery({
    lat: params.lat,
    lng: params.lng,
    radius_m: params.radiusM,
    category: params.category,
  });
  const envelope = await apiGet<Envelope<Poi[]>>(`/v1/pois/nearby${query}`, signal);
  return envelope.data;
}

export async function fetchPoi(poiId: string, signal?: AbortSignal): Promise<Poi> {
  const envelope = await apiGet<Envelope<Poi>>(`/v1/pois/${poiId}`, signal);
  return envelope.data;
}
