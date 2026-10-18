import React from 'react';
import { api } from './api.js';

// Shared data loading for the per-view pages. Every view depends on
// refreshKey (bumped by mutations / demo reset), so all pages refetch together.
export function useLoad(loader, refreshKey, deps = []) {
  const [data, setData] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    let live = true;
    setError(null);
    Promise.resolve()
      .then(loader)
      .then(d => { if (live) setData(d); })
      .catch(e => { if (live) setError(e); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey, ...deps]);

  return [data, error];
}

export function useFleetViews(refreshKey) {
  const [fleet, fe] = useLoad(() => api.getFleet(), refreshKey);
  const [aircraft, ae] = useLoad(() => api.getAircraft(), refreshKey);
  const [maintenance, me] = useLoad(() => api.getMaintenance(), refreshKey);
  const [inventory, ie] = useLoad(() => api.getInventory(), refreshKey);
  const [transfers, te] = useLoad(() => api.getTransfers(), refreshKey);
  const [bases, be] = useLoad(() => api.getBases(), refreshKey);
  const [parts, pe] = useLoad(() => api.getPartsLive(), refreshKey);

  return {
    fleet, aircraft, maintenance, inventory, transfers, bases, parts, partsError: pe,
    loading: (!fleet || !aircraft) && !(fe || ae),
    error: fe || ae || me || ie || te || be || null,
    predictionError: ae || null,
  };
}

export function useRecommendation(aircraftId, refreshKey) {
  return useLoad(
    () => (aircraftId ? api.getRecommendation(aircraftId) : Promise.resolve(null)),
    refreshKey,
    [aircraftId]
  );
}

// Demand vs supply is computed by the backend; the view only renders it.
export function useResourceDemand(scopeBase, refreshKey) {
  return useLoad(
    () => api.getResourceDemand(scopeBase),
    refreshKey,
    [scopeBase]
  );
}

// Wraps a mutating API call with a pending flag + inline status message so
// every view reports success/failure the same way.
export function useAction(refresh) {
  const [msg, setMsg] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const run = async (fn, success, failure) => {
    setBusy(true);
    setMsg(success ? 'Working…' : '');
    try {
      await fn();
      setMsg(success || 'Done');
      refresh();
    } catch (e) {
      setMsg(failure || 'Action failed — backend offline. Start it: uvicorn app.main:app');
    } finally {
      setBusy(false);
    }
  };

  return { msg, busy, run, setMsg };
}
