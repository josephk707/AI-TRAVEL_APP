/**
 * Typed calls to /v1/quick-plans* — F22 Weekend/Local Outing Quick Plan,
 * see docs/API_SPECIFICATION.md §18.
 */

import { apiPost } from "./client";

export interface QuickPlanItem {
  poi_id: string;
  poi_name: string;
  poi_category: string;
  sequence_order: number;
}

export interface QuickPlan {
  id: string;
  user_id: string;
  time_available_min: number | null;
  budget: number | null;
  occasion: string | null;
  summary: string;
  generated_at: string;
  items: QuickPlanItem[];
}

export interface SaveToCollectionResult {
  collection_id: string;
  collection_name: string;
  item_count: number;
}

interface Envelope<T> {
  data: T;
}

export async function createQuickPlan(
  timeAvailableMin: number,
  options?: { budget?: number; occasion?: string; lat?: number; lng?: number },
): Promise<QuickPlan> {
  const envelope = await apiPost<Envelope<QuickPlan>>("/v1/quick-plans", {
    time_available_min: timeAvailableMin,
    budget: options?.budget,
    occasion: options?.occasion,
    lat: options?.lat,
    lng: options?.lng,
  });
  return envelope.data;
}

export async function saveQuickPlanToCollection(quickPlanId: string): Promise<SaveToCollectionResult> {
  const envelope = await apiPost<Envelope<SaveToCollectionResult>>(
    `/v1/quick-plans/${quickPlanId}/save-to-collection`,
  );
  return envelope.data;
}
