/**
 * Classic technical indicators, computed client-side over the candle array
 * the chart already holds. Every function returns arrays aligned with the
 * input, using `null` during the warm-up window so Plotly renders gaps
 * instead of misleading partial values.
 */

import type { Candle } from '../api/client';

export function sma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  const p = Math.max(1, Math.round(period));
  if (values.length < p) return out;
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= p) sum -= values[i - p];
    if (i >= p - 1) out[i] = sum / p;
  }
  return out;
}

export function ema(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  const p = Math.max(1, Math.round(period));
  if (values.length < p) return out;
  const k = 2 / (p + 1);
  let prev = 0;
  for (let i = 0; i < p; i++) prev += values[i];
  prev /= p; // SMA seed
  out[p - 1] = prev;
  for (let i = p; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

export interface BollingerBands {
  upper: (number | null)[];
  mid: (number | null)[];
  lower: (number | null)[];
}

export function bollinger(values: number[], period = 20, mult = 2): BollingerBands {
  const p = Math.max(2, Math.round(period));
  const upper: (number | null)[] = new Array(values.length).fill(null);
  const mid: (number | null)[] = new Array(values.length).fill(null);
  const lower: (number | null)[] = new Array(values.length).fill(null);

  for (let i = p - 1; i < values.length; i++) {
    let sum = 0;
    for (let j = i - p + 1; j <= i; j++) sum += values[j];
    const mean = sum / p;
    let variance = 0;
    for (let j = i - p + 1; j <= i; j++) variance += (values[j] - mean) ** 2;
    const sd = Math.sqrt(variance / p);
    mid[i] = mean;
    upper[i] = mean + mult * sd;
    lower[i] = mean - mult * sd;
  }
  return { upper, mid, lower };
}

/** Cumulative VWAP over the loaded window (resets at the fetch window). */
export function vwap(candles: Candle[]): (number | null)[] {
  const out: (number | null)[] = new Array(candles.length).fill(null);
  let pv = 0;
  let vol = 0;
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const typical = (c.h + c.l + c.c) / 3;
    const v = c.v > 0 ? c.v : 0;
    pv += typical * v;
    vol += v;
    out[i] = vol > 0 ? pv / vol : null;
  }
  return out;
}

export interface DonchianChannel {
  upper: (number | null)[];
  lower: (number | null)[];
}

export function donchian(candles: Candle[], period = 20): DonchianChannel {
  const p = Math.max(2, Math.round(period));
  const upper: (number | null)[] = new Array(candles.length).fill(null);
  const lower: (number | null)[] = new Array(candles.length).fill(null);
  for (let i = p - 1; i < candles.length; i++) {
    let hi = -Infinity;
    let lo = Infinity;
    for (let j = i - p + 1; j <= i; j++) {
      if (candles[j].h > hi) hi = candles[j].h;
      if (candles[j].l < lo) lo = candles[j].l;
    }
    upper[i] = hi;
    lower[i] = lo;
  }
  return { upper, lower };
}
