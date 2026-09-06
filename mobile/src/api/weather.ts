/**
 * Typed calls to GET /v1/weather — Maps Integration phase, real
 * Open-Meteo destination weather (current + short forecast). See
 * backend/app/services/open_meteo_client.py's module docstring for why
 * this is separate from the F3 outdoor-activity flagging pipeline.
 */

import { apiGet } from "./client";

export interface CurrentWeather {
  temperature_c: number;
  condition_code: number;
  condition: string;
  humidity_percent: number | null;
  wind_speed_kmh: number | null;
  is_day: boolean;
}

export interface DailyForecastEntry {
  date: string;
  temperature_max_c: number;
  temperature_min_c: number;
  condition_code: number;
  condition: string;
  precipitation_probability_percent: number | null;
}

export interface Weather {
  lat: number;
  lng: number;
  current: CurrentWeather;
  daily: DailyForecastEntry[];
}

interface Envelope<T> {
  data: T;
}

export async function fetchWeather(
  lat: number,
  lng: number,
  signal?: AbortSignal,
): Promise<Weather> {
  const envelope = await apiGet<Envelope<Weather>>(
    `/v1/weather?lat=${lat}&lng=${lng}`,
    signal,
  );
  return envelope.data;
}
