// Stub for services/hooks.js used by the SSR render check.
// Fetches real data at module load and hands it back synchronously so the
// views' render bodies execute (useEffect never runs during SSR).
import { api } from '../../src/services/api.js';

const [bases, fleet, aircraft, maintenance, inventory, transfers, parts] = await Promise.all([
  api.getBases(), api.getFleet(), api.getAircraft(), api.getMaintenance(),
  api.getInventory(), api.getTransfers(), api.getParts(),
]);

const RECS = {};
const DEMAND = {};

export async function preloadRecs(ids) {
  for (const id of ids) {
    try { RECS[id] = await api.getRecommendation(id); } catch { RECS[id] = null; }
  }
}

function demand(scopeBase) {
  if (scopeBase && DEMAND[scopeBase]) return DEMAND[scopeBase];
  if (!scopeBase && DEMAND.all) return DEMAND.all;
  return null;
}

export async function preloadDemand(scopeBase) {
  try { DEMAND[scopeBase || 'all'] = await api.getResourceDemand(scopeBase); } catch { /* offline */ }
}

export function useFleetViews() {
  return { fleet, aircraft, maintenance, inventory, transfers, bases, parts, loading: false, error: null };
}

export function useResourceDemand(scopeBase, refreshKey) {
  const value = demand(scopeBase);
  return [value, value ? null : new Error('Resource demand API unavailable in render check')];
}

export function useRecommendation(id) {
  return [RECS[id] || null, null];
}

export function useLoad() {
  return [null, null];
}

export function useAction() {
  return { msg: '', busy: false, run: async () => {}, setMsg: () => {} };
}
