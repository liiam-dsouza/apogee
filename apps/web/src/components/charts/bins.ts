/** Histogram helpers: round ticks, bins and quantiles. Pure, so they're unit-tested. */

/** Round tick values covering [lo, hi]. */
export function ticks(lo: number, hi: number, count: number): number[] {
  const raw = (hi - lo || 1) / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const out = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Number(v.toPrecision(12)))
  return out
}

/** Linear-interpolated quantile of an ascending array. */
export function quantile(sorted: number[], q: number): number {
  const i = (sorted.length - 1) * q
  const lo = Math.floor(i)
  return sorted[lo] + (sorted[Math.min(lo + 1, sorted.length - 1)] - sorted[lo]) * (i - lo)
}

export interface Bin {
  lo: number
  hi: number
  count: number
}

/** Equal-width bins on round edges; about the square root of the sample count, 6 to 30 of them. */
export function binValues(values: number[]): Bin[] {
  if (values.length === 0) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (min === max) return [{ lo: min, hi: max, count: values.length }]
  const edges = ticks(min, max, Math.min(30, Math.max(6, Math.round(Math.sqrt(values.length)))))
  if (edges[0] > min) edges.unshift(edges[0] - (edges[1] - edges[0]))
  while (edges[edges.length - 1] < max) edges.push(edges[edges.length - 1] + (edges[1] - edges[0]))
  const bins = edges.slice(0, -1).map((lo, i) => ({ lo, hi: edges[i + 1], count: 0 }))
  for (const v of values) {
    const i = Math.min(bins.length - 1, Math.floor((v - edges[0]) / (edges[1] - edges[0])))
    bins[i].count++
  }
  return bins
}
