// Service layer — UI NEVER computes health. All health comes via getHealth().
// getHealth() calls GET /api/health/{id} (FastAPI -> ml_service mock now, real model later).
// If backend is unreachable, falls back to bundled demo contract (same schema).

// Same-origin in the browser (Vite proxies /api). Absolute when set, so
// non-browser callers (e.g. the SSR view render check) can reach the API
// directly instead of silently falling back to bundled data.
const BASE = (typeof import.meta !== 'undefined'
  && import.meta.env
  && import.meta.env.VITE_API_BASE) || '';

let demoRole = null;
let demoBase = null;
let healthDataSource = 'unknown';
let lastApiResponse = null;

async function fetchJSON(url, opts) {
  const headers = new Headers(opts?.headers || {});
  if (demoRole) headers.set('X-Demo-Role', demoRole);
  if (demoRole === 'base' && demoBase) headers.set('X-Demo-Base', demoBase);
  const requestUrl = BASE + url;
  let r;
  try {
    r = await fetch(requestUrl, { ...opts, headers });
  } catch (error) {
    lastApiResponse = { ok: false, status: null, url: requestUrl, at: Date.now(), message: error?.message || 'Network request failed' };
    if (error instanceof Error) error.message = `${requestUrl}: ${error.message}`;
    throw error;
  }
  lastApiResponse = { ok: r.ok, status: r.status, url: requestUrl, at: Date.now(), message: r.ok ? '' : `HTTP ${r.status}` };
  if (!r.ok) {
    let detail = '';
    let payload;
    try {
      payload = await r.json();
      detail = typeof payload.detail === 'string' ? payload.detail : '';
    } catch {}
    const error = new Error(`${url} ${r.status}${detail ? `: ${detail}` : ''}`);
    error.status = r.status;
    error.payload = payload;
    throw error;
  }
  return r.json();
}

function mayUseDemoFallback(error) {
  // A direct API base is a deliberate live-provider selection. Never replace
  // its response or CORS/network failure with plausible-looking demo records.
  // Same-origin proxy mode retains the clearly marked offline demo fallback.
  return !BASE && !error?.status && error?.name === 'TypeError';
}

// ---- Bundled fallback (same contract as backend mock) ----
const FALLBACK_HEALTH = {
  A17: { aircraft_id: 'A17', health_score: 41, failure_probability: 0.78, rul: 12, confidence: 0.91, risk_level: 'CRITICAL', predicted_maintenance: true, required_component: 'HP-204', history_source: 'illustrative', is_synthetic: true },
  A19: { aircraft_id: 'A19', health_score: 92, failure_probability: 0.06, rul: 145, confidence: 0.96, risk_level: 'LOW', predicted_maintenance: false, required_component: null },
  A21: { aircraft_id: 'A21', health_score: 76, failure_probability: 0.32, rul: 38, confidence: 0.88, risk_level: 'MEDIUM', predicted_maintenance: true, required_component: 'FP-102' },
  A23: { aircraft_id: 'A23', health_score: 88, failure_probability: 0.10, rul: 110, confidence: 0.94, risk_level: 'LOW', predicted_maintenance: false, required_component: null },
  A24: { aircraft_id: 'A24', health_score: 68, failure_probability: 0.45, rul: 38, confidence: 0.86, risk_level: 'MEDIUM', predicted_maintenance: true, required_component: 'OE-310' },
  A26: { aircraft_id: 'A26', health_score: 90, failure_probability: 0.08, rul: 130, confidence: 0.95, risk_level: 'LOW', predicted_maintenance: false, required_component: null },
  A28: { aircraft_id: 'A28', health_score: 55, failure_probability: 0.58, rul: 20, confidence: 0.84, risk_level: 'MEDIUM', predicted_maintenance: true, required_component: 'FP-102' },
  A32: { aircraft_id: 'A32', health_score: 93, failure_probability: 0.05, rul: 120, confidence: 0.97, risk_level: 'LOW', predicted_maintenance: false, required_component: null },
  A33: { aircraft_id: 'A33', health_score: 89, failure_probability: 0.09, rul: 105, confidence: 0.95, risk_level: 'LOW', predicted_maintenance: false, required_component: null },
  A35: { aircraft_id: 'A35', health_score: 72, failure_probability: 0.38, rul: 55, confidence: 0.87, risk_level: 'MEDIUM', predicted_maintenance: true, required_component: 'HP-204' },
};

const FALLBACK_BASES = [
  { id: 'alpha', name: 'Base Alpha', location: 'Northern Sector', lat: 28.61, lon: 77.20 },
  { id: 'bravo', name: 'Base Bravo', location: 'Western Sector', lat: 27.90, lon: 76.10 },
  { id: 'charlie', name: 'Base Charlie', location: 'Central Sector', lat: 26.50, lon: 77.80 },
];

const FALLBACK_PARTS = [
  { part_number: 'HP-204', name: 'High-Pressure Turbine Module', category: 'Engine', min_condition_pct: 40 },
  { part_number: 'FP-102', name: 'Fuel Pump Assembly', category: 'Fuel', min_condition_pct: 35 },
  { part_number: 'OE-310', name: 'Oil Cooler / Heat Exchanger', category: 'Engine', min_condition_pct: 35 },
  { part_number: 'AV-077', name: 'Avionics LRU', category: 'Avionics', min_condition_pct: 50 },
];

const FALLBACK_MAINTENANCE = [
  { id: 'mx-01', aircraft_id: 'A17', component: 'HP-204', priority: 'CRITICAL', status: 'WAITING_FOR_COMPONENT', estimated_recovery_hours: 6, started: '2026-10-05T08:00:00Z' },
  { id: 'mx-02', aircraft_id: 'A28', component: 'FP-102', priority: 'LOW', status: 'IN_PROGRESS', estimated_recovery_hours: 3, started: '2026-10-05T14:00:00Z' },
  { id: 'mx-03', aircraft_id: 'A21', component: 'FP-102', priority: 'MEDIUM', status: 'SCHEDULED', estimated_recovery_hours: 4, started: null },
  { id: 'mx-04', aircraft_id: 'A24', component: 'OE-310', priority: 'MEDIUM', status: 'SCHEDULED', estimated_recovery_hours: 5, started: null },
];

const FALLBACK_TRANSFERS = [
  { id: 'T-101', part_number: 'FP-102', source_base: 'alpha', dest_base: 'bravo', quantity: 1, status: 'IN_TRANSIT', eta_hours: 2.0, created: '2026-10-06T02:00:00Z' },
  { id: 'T-102', part_number: 'OE-310', source_base: 'charlie', dest_base: 'bravo', quantity: 1, status: 'PENDING_APPROVAL', eta_hours: 4.3, created: '2026-10-06T04:00:00Z' },
];

const FALLBACK_AIRCRAFT = [
  { id: 'A17', base_id: 'alpha', type: 'Fighter Mk-II', status: 'AT_RISK', required_component: 'HP-204', required_by_hours: 8, estimated_recovery_hours: 6, priority: 'CRITICAL' },
  { id: 'A19', base_id: 'alpha', type: 'Fighter Mk-II', status: 'AVAILABLE', required_component: null },
  { id: 'A21', base_id: 'alpha', type: 'Transport H-4', status: 'DEGRADED', required_component: 'FP-102', required_by_hours: 30, estimated_recovery_hours: 4, priority: 'MEDIUM' },
  { id: 'A23', base_id: 'alpha', type: 'Fighter Mk-II', status: 'AVAILABLE', required_component: null },
  { id: 'A24', base_id: 'bravo', type: 'Fighter Mk-II', status: 'DEGRADED', required_component: 'OE-310', required_by_hours: 36, estimated_recovery_hours: 5, priority: 'MEDIUM' },
  { id: 'A26', base_id: 'bravo', type: 'Transport H-4', status: 'AVAILABLE', required_component: null },
  { id: 'A28', base_id: 'bravo', type: 'Fighter Mk-II', status: 'MAINTENANCE', required_component: 'FP-102', estimated_recovery_hours: 3, priority: 'LOW' },
  { id: 'A32', base_id: 'charlie', type: 'Transport H-4', status: 'AVAILABLE', required_component: null },
  { id: 'A33', base_id: 'charlie', type: 'Fighter Mk-II', status: 'AVAILABLE', required_component: null },
  { id: 'A35', base_id: 'charlie', type: 'Fighter Mk-II', status: 'DEGRADED', required_component: 'HP-204', required_by_hours: 48, estimated_recovery_hours: 6, priority: 'LOW' },
];

const FALLBACK_INV = [
  { id: 'inv-01', base_id: 'alpha', part_number: 'HP-204', quantity: 0, reserved: 0, condition_pct: 0, status: 'STOCKOUT' },
  { id: 'inv-02', base_id: 'bravo', part_number: 'HP-204', quantity: 1, reserved: 0, condition_pct: 42, status: 'AVAILABLE' },
  { id: 'inv-03', base_id: 'charlie', part_number: 'HP-204', quantity: 2, reserved: 0, condition_pct: 84, status: 'AVAILABLE' },
  { id: 'inv-04', base_id: 'alpha', part_number: 'FP-102', quantity: 4, reserved: 1, condition_pct: 91, status: 'AVAILABLE' },
  { id: 'inv-05', base_id: 'bravo', part_number: 'FP-102', quantity: 1, reserved: 0, condition_pct: 66, status: 'AVAILABLE' },
  { id: 'inv-06', base_id: 'charlie', part_number: 'OE-310', quantity: 3, reserved: 0, condition_pct: 78, status: 'AVAILABLE' },
  { id: 'inv-07', base_id: 'bravo', part_number: 'OE-310', quantity: 0, reserved: 0, condition_pct: 0, status: 'STOCKOUT' },
  { id: 'inv-08', base_id: 'alpha', part_number: 'OE-310', quantity: 2, reserved: 0, condition_pct: 88, status: 'AVAILABLE' },
  { id: 'inv-09', base_id: 'alpha', part_number: 'AV-077', quantity: 2, reserved: 0, condition_pct: 95, status: 'AVAILABLE' },
  { id: 'inv-10', base_id: 'charlie', part_number: 'AV-077', quantity: 1, reserved: 0, condition_pct: 61, status: 'LOW_STOCK' },
];

let useFallback = false;

function fallbackHealth(id) {
  const health = FALLBACK_HEALTH[id];
  return health ? { ...health, rul_unit: 'flight_hours', history_source: 'illustrative', is_synthetic: true, model_version: 'demo-fallback' } : health;
}

export const api = {
  setDemoContext: (role, base) => {
    demoRole = role || null;
    demoBase = role === 'base' ? (base || 'alpha') : null;
  },
  isFallback: () => healthDataSource === 'fallback',
  getConnectionStatus: () => ({ ...lastApiResponse }),
  getFleet: async () => {
    try { return await fetchJSON('/api/fleet/overview'); }
    catch (e) { if (!mayUseDemoFallback(e)) throw e; useFallback = true; return fallbackFleet(); }
  },
  getAircraft: async () => {
    try { const rows = await fetchJSON('/api/aircraft'); healthDataSource = 'live'; return rows; }
    catch (e) {
      if (!mayUseDemoFallback(e)) { healthDataSource = 'unavailable'; throw e; }
      useFallback = true;
      healthDataSource = 'fallback';
      return FALLBACK_AIRCRAFT.map(a => ({ ...a, health: fallbackHealth(a.id), maintenance: null }));
    }
  },
  getAircraftDetail: async (id) => {
    try { const detail = await fetchJSON('/api/aircraft/' + id); healthDataSource = 'live'; return detail; }
    catch (e) {
      if (!mayUseDemoFallback(e)) { healthDataSource = 'unavailable'; throw e; }
      useFallback = true;
      healthDataSource = 'fallback';
      const a = FALLBACK_AIRCRAFT.find(x => x.id === id);
      const h = FALLBACK_HEALTH[id];
      const mx = FALLBACK_MAINTENANCE.find(m => m.aircraft_id === id) || null;
      return { ...a, health: fallbackHealth(id), history_source: 'illustrative', is_synthetic: true, trend: fallbackTrend(h.health_score), maintenance: mx, resource_availability: FALLBACK_INV.filter(i => i.part_number === (h.required_component || a.required_component)), recommendation: null };
    }
  },
  // Pure ML contract consumer:
  getHealth: async (id) => {
    try { const prediction = await fetchJSON('/api/health/' + id); healthDataSource = 'live'; return prediction; }
    catch (e) {
      if (!mayUseDemoFallback(e)) { healthDataSource = 'unavailable'; throw e; }
      useFallback = true;
      healthDataSource = 'fallback';
      return fallbackHealth(id);
    }
  },
  getInventory: async () => {
    try { return await fetchJSON('/api/inventory'); }
    catch (e) { if (!mayUseDemoFallback(e)) throw e; useFallback = true; return FALLBACK_INV; }
  },
  getInventoryLive: async () => fetchJSON('/api/inventory'),
  getParts: async () => {
    try { return await fetchJSON('/api/parts'); }
    catch (e) { if (!mayUseDemoFallback(e)) throw e; useFallback = true; return FALLBACK_PARTS; }
  },
  getPartsLive: async () => fetchJSON('/api/parts'),
  getBases: async () => {
    try { return await fetchJSON('/api/bases'); }
    catch (e) {
      if (!mayUseDemoFallback(e)) throw e;
      useFallback = true;
      return FALLBACK_BASES.map(b => ({
        ...b,
        aircraft: FALLBACK_AIRCRAFT.filter(a => a.base_id === b.id).map(a => a.id),
      }));
    }
  },
  getTransfers: async () => {
    try { return await fetchJSON('/api/transfers'); }
    catch (e) { if (!mayUseDemoFallback(e)) throw e; useFallback = true; return FALLBACK_TRANSFERS.map(t => ({ ...t })); }
  },
  getMaintenance: async () => {
    try { return await fetchJSON('/api/maintenance'); }
    catch (e) { if (!mayUseDemoFallback(e)) throw e; useFallback = true; return FALLBACK_MAINTENANCE.map(m => ({ ...m })); }
  },
  getWorkOrders: async () => fetchJSON('/api/maintenance/work-orders'),
  getMaintenanceTimeline: async (aircraftId, workOrderId) => {
    const params = new URLSearchParams();
    if (workOrderId) params.set('work_order_id', workOrderId);
    return fetchJSON('/api/aircraft/' + encodeURIComponent(aircraftId) + '/maintenance-timeline' + (params.size ? '?' + params.toString() : ''));
  },
  createWorkOrderFromEvent: async (eventId, requiredComponent) => fetchJSON('/api/maintenance/events/' + encodeURIComponent(eventId) + '/work-order', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ required_component: requiredComponent || null, actor: demoRole || 'base' }),
  }),
  getDemoScenario: async () => {
    try { return await fetchJSON('/api/demo/scenario'); }
    catch (e) { if (e?.status === 404) return null; throw e; }
  },
  // Demand vs supply is computed by the backend (spec section 22: no business
  // logic in UI components). Falls back to an empty shape, not a recomputation.
  getResourceDemand: async (baseId) => {
    try { return await fetchJSON('/api/resources/demand' + (baseId ? '?base_id=' + baseId : '')); }
    catch (e) { useFallback = true; throw e; }
  },
  // Cycle-based demand is a strict live-provider contract; never substitute
  // illustrative fallback data when the selected prediction provider fails.
  getResourceForecast: async (horizonCycles = 30) => {
    const params = new URLSearchParams({ horizon_cycles: String(horizonCycles) });
    return fetchJSON('/api/resources/forecast?' + params.toString());
  },
  // Read-only deterministic allocation over a shared inventory snapshot.
  // This endpoint proposes allocations only; it does not create transfers.
  getAllocationPreview: async (workOrderIds) => {
    const params = new URLSearchParams();
    (workOrderIds || []).forEach(id => params.append('work_order_ids', id));
    return fetchJSON('/api/resources/allocation-preview' + (params.size ? '?' + params.toString() : ''));
  },
  getReadinessSimulation: async (horizonHours = 48, workOrderIds) => {
    const params = new URLSearchParams({ horizon_hours: String(horizonHours) });
    (workOrderIds || []).forEach(id => params.append('work_order_ids', id));
    return fetchJSON('/api/fleet/readiness-simulation?' + params.toString());
  },
  // Offline synthetic scenario results are a strict backend contract. Never
  // replace evaluation output with fallback operational/demo data.
  getEvaluationSummary: async () => fetchJSON('/api/evaluation/summary'),
  getRiskBands: async () => fetchJSON('/api/policy/risk-bands'),
  getFd001Metrics: async () => fetchJSON('/api/ml/fd001/metrics'),
  getWorkOrderRecommendation: async (woId) => {
    return fetchJSON('/api/work-orders/' + woId + '/recommendation');
  },
  getImpactPreview: async (woId) => {
    try { return await fetchJSON('/api/work-orders/' + woId + '/impact'); }
    catch (e) { useFallback = true; throw e; }
  },
  getMaintenanceKnowledge: async () => {
    try { return await fetchJSON('/api/maintenance/knowledge'); }
    catch (e) { if (!mayUseDemoFallback(e)) throw e; useFallback = true; return { rules: [] }; }
  },
  getRecommendation: async (id) => {
    try { return await fetchJSON('/api/recommendations/' + id); }
    catch (e) {
      if (!mayUseDemoFallback(e)) throw e;
      useFallback = true;
      // Local rule-based fallback mirroring backend logic for standalone demo
      return localRecommendation(id);
    }
  },
  approveRecommendation: async (id) => {
    const r = await fetchJSON('/api/recommendations/' + id + '/approve', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actor: demoRole || 'commander' }),
    });
    return r;
  },
  approveWorkOrderRecommendation: async (workOrderId) => fetchJSON('/api/work-orders/' + workOrderId + '/recommendation/approve', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor: demoRole || 'commander' }),
  }),
  receiveTransfer: async (tid) => fetchJSON('/api/transfers/' + tid + '/receive?actor=' + encodeURIComponent(demoRole || 'logistics'), { method: 'POST' }),
  approveTransfer: async (tid) => fetchJSON('/api/transfers/' + tid + '/approve', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor: demoRole || 'logistics' }),
  }),
  createTransfer: async (body) => fetchJSON('/api/transfers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...body, actor: demoRole || body.actor || 'logistics' }),
  }),
  startMx: async (id) => fetchJSON('/api/maintenance/' + id + '/start?actor=' + encodeURIComponent(demoRole || 'base'), { method: 'POST' }),
  completeMx: async (id) => fetchJSON('/api/maintenance/' + id + '/complete?actor=' + encodeURIComponent(demoRole || 'base'), { method: 'POST' }),
  resetDemo: async () => fetchJSON('/api/demo/reset', { method: 'POST' }),
};

function fallbackFleet() {
  const total = FALLBACK_AIRCRAFT.length;
  const available = FALLBACK_AIRCRAFT.filter(a => a.status === 'AVAILABLE').length;
  return {
    total, available,
    maintenance: FALLBACK_AIRCRAFT.filter(a => a.status === 'MAINTENANCE').length,
    at_risk: FALLBACK_AIRCRAFT.filter(a => ['AT_RISK', 'DEGRADED'].includes(a.status)).length,
    high_risk: 1,
    availability_pct: Math.round(available / total * 1000) / 10,
    bases: FALLBACK_BASES.map(b => {
      const acs = FALLBACK_AIRCRAFT.filter(a => a.base_id === b.id);
      const av = acs.filter(a => a.status === 'AVAILABLE').length;
      return { id: b.id, name: b.name, aircraft_count: acs.length, available: av, availability_pct: Math.round(av / acs.length * 1000) / 10, at_risk: acs.filter(a => ['AT_RISK', 'DEGRADED'].includes(a.status)).length, maintenance: acs.filter(a => a.status === 'MAINTENANCE').length };
    })
  };
}

function fallbackTrend(score) {
  const start = Math.min(98, score + 22);
  return Array.from({ length: 12 }, (_, i) => Math.round(start - ((start - score) / 11) * i));
}

const DIST = { 'alpha|bravo': 120, 'alpha|charlie': 380, 'bravo|charlie': 260 };
function dist(a, b) {
  if (a === b) return 0;
  return DIST[a + '|' + b] ?? DIST[b + '|' + a] ?? 200;
}

function localRecommendation(id) {
  const h = FALLBACK_HEALTH[id];
  const ac = FALLBACK_AIRCRAFT.find(a => a.id === id);
  const part = h.required_component;
  const cands = FALLBACK_INV.filter(i => i.part_number === part && i.base_id !== ac.base_id && (i.quantity - (i.reserved || 0)) > 0 && i.condition_pct >= 40)
    .map(i => ({ donor_base: i.base_id, quantity_available: i.quantity, condition_pct: i.condition_pct, distance_km: dist(ac.base_id, i.base_id), eta_hours: Math.round(dist(ac.base_id, i.base_id) / 60 * 10) / 10, expected_downtime_hours: Math.round(dist(ac.base_id, i.base_id) / 60 * 10) / 10 + 5, score: dist(ac.base_id, i.base_id) }))
    .sort((x, y) => x.score - y.score);
  const rec = cands[0];
  return {
    aircraft_id: id, home_base: ac.base_id, required_component: part,
    risk_level: h.risk_level, rul: h.rul, candidates: cands,
    recommended: rec ? { ...rec, reasons: [`Required for high-risk aircraft ${id} (RUL ${rulText(h)})`, 'Available immediately at donor base', `${rec.eta_hours}-hour estimated transfer (${rec.distance_km} km)`, `Component condition ${rec.condition_pct}% satisfies requirement`, 'Donor base retains minimum reserve', `Lowest expected fleet downtime (~${rec.expected_downtime_hours}h)`] } : null
  };
}

export const BASES = FALLBACK_BASES;
export const PARTS = FALLBACK_PARTS;
export function baseName(id) {
  return (FALLBACK_BASES.find(b => b.id === id) || {}).name || id;
}
export function partName(pn) {
  return (FALLBACK_PARTS.find(p => p.part_number === pn) || {}).name || pn;
}
export function partCategory(pn) {
  return (FALLBACK_PARTS.find(p => p.part_number === pn) || {}).category || '—';
}
export function minCondition(pn) {
  const p = FALLBACK_PARTS.find(x => x.part_number === pn);
  return p ? p.min_condition_pct : null;
}
export function distanceBetween(a, b) { return dist(a, b); }
export function etaBetween(a, b) { return Math.round(dist(a, b) / 60 * 10) / 10; }
export function distanceText(value) {
  return value == null || value === '' || !Number.isFinite(Number(value)) ? '—' : `${Number(value)} km`;
}
export function etaText(value) {
  return value == null || value === '' || !Number.isFinite(Number(value)) ? '—' : `${Number(value)}h`;
}
export function titleCase(s) {
  return String(s || '').toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function rulValue(prediction) {
  return prediction?.remaining_useful_life ?? prediction?.rul ?? null;
}

export function rulUnit(prediction) {
  const unit = prediction?.rul_unit || prediction?.remaining_useful_life_unit;
  if (!unit) return rulValue(prediction) != null ? 'flight hours' : '';
  const normalized = String(unit).toLowerCase().replace(/_/g, ' ');
  if (['cycle', 'cycles'].includes(normalized)) return 'cycles';
  if (['hour', 'hours', 'flight hour', 'flight hours'].includes(normalized)) return 'flight hours';
  return normalized;
}

export function rulText(prediction) {
  const value = rulValue(prediction);
  if (value == null) return '—';
  const unit = rulUnit(prediction);
  const numericValue = Number(value);
  const formattedValue = Number.isFinite(numericValue)
    ? Number.isInteger(numericValue) ? String(numericValue) : numericValue.toFixed(2)
    : String(value);
  return unit ? `${formattedValue} ${unit}` : formattedValue;
}

export function failureProbabilityText(prediction) {
  const value = prediction?.failure_probability;
  if (value == null || value === '' || !Number.isFinite(Number(value))) return 'Unavailable';
  return `${Math.round(Number(value) * 100)}%`;
}

export function healthScoreText(prediction) {
  const value = prediction?.health_score;
  return value == null || value === '' || !Number.isFinite(Number(value)) ? 'Unavailable' : `${value}%`;
}
