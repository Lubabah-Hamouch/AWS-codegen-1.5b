// status.json is written next to the site by the kill-switch tooling and the circuit breaker, and served uncached.
// Reading it costs no Lambda invocation, so the page knows the backend is paused before anyone presses Run.

export type SiteStatus = { live: boolean | null; since: string | null; note: string | null };

export const UNKNOWN: SiteStatus = { live: null, since: null, note: null };

export async function fetchStatus(fetchImpl: typeof fetch = fetch): Promise<SiteStatus> {
  try {
    const r = await fetchImpl("/status.json", { cache: "no-store" });
    if (!r.ok) return UNKNOWN; // e.g. local dev: no file; the first request will tell
    const j = await r.json();
    return { live: typeof j.live === "boolean" ? j.live : null, since: j.since ?? null, note: j.note ?? null };
  } catch {
    return UNKNOWN;
  }
}
