/**
 * Typed calls to /v1/favorites, /v1/collections — F13, see
 * docs/API_SPECIFICATION.md §11.
 */

import { apiDelete, apiGet, apiPost } from "./client";

export interface Favorite {
  poi_id: string;
  poi_name: string;
  poi_category: string;
  created_at: string;
}

export interface Collection {
  id: string;
  user_id: string;
  name: string;
  created_at: string;
  item_count: number;
}

export interface CollectionItem {
  poi_id: string;
  poi_name: string;
  poi_category: string;
  added_at: string;
}

interface Envelope<T> {
  data: T;
}

export async function addFavorite(poiId: string): Promise<void> {
  await apiPost<Envelope<{ poi_id: string; favorited: boolean }>>("/v1/favorites", {
    poi_id: poiId,
  });
}

export async function removeFavorite(poiId: string): Promise<void> {
  await apiDelete(`/v1/favorites/${poiId}`);
}

export async function listFavorites(signal?: AbortSignal): Promise<Favorite[]> {
  const envelope = await apiGet<Envelope<Favorite[]>>("/v1/favorites", signal);
  return envelope.data;
}

export async function createCollection(name: string): Promise<Collection> {
  const envelope = await apiPost<Envelope<Collection>>("/v1/collections", { name });
  return envelope.data;
}

export async function listCollections(signal?: AbortSignal): Promise<Collection[]> {
  const envelope = await apiGet<Envelope<Collection[]>>("/v1/collections", signal);
  return envelope.data;
}

export async function addCollectionItem(collectionId: string, poiId: string): Promise<CollectionItem[]> {
  const envelope = await apiPost<Envelope<CollectionItem[]>>(
    `/v1/collections/${collectionId}/items`,
    { poi_id: poiId },
  );
  return envelope.data;
}

export async function listCollectionItems(
  collectionId: string,
  signal?: AbortSignal,
): Promise<CollectionItem[]> {
  const envelope = await apiGet<Envelope<CollectionItem[]>>(
    `/v1/collections/${collectionId}/items`,
    signal,
  );
  return envelope.data;
}
