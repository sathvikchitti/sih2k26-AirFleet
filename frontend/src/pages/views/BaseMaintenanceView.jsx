import React from 'react';
import { api, baseName, titleCase } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import { DataError, KpiCard, Loading, PageHeader, SectionTitle, Select, StatusMsg } from '../../components/ui.jsx';
import { MaintenanceTable } from './MaintenanceView.jsx';
import { C } from '../../theme.js';

// Base manager — Maintenance: work orders for this base only. The base runs the
// hands-on steps of the loop (start / complete) once the component has landed.
export default function BaseMaintenanceView({ homeBase, onOpenAircraft, refreshKey, refresh }) {
  const { aircraft, maintenance, inventory, loading, predictionError } = useFleetViews(refreshKey);
  const [status, setStatus] = React.useState('');
  const [msg, setMsg] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const act = async (fn, label) => {
    setBusy(true);
    setMsg(label + '…');
    try {
      await fn();
      setMsg(label + ' — done');
      refresh();
    } catch (e) {
      setMsg(e?.message || 'Maintenance action failed. Check the backend connection and try again.');
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Loading>Loading maintenance…</Loading>;
  if (predictionError) return <DataError error={predictionError}>Maintenance work orders cannot be scoped because aircraft predictions are unavailable.</DataError>;

  const held = (aircraft || []).filter(a => a.base_id === homeBase);
  const mine = (maintenance || []).filter(m => held.some(a => a.id === m.aircraft_id));
  const filtered = status ? mine.filter(m => m.status === status) : mine;

  const stock = (inventory || []).filter(i => i.base_id === homeBase);
  const hasPart = (pn) => stock.some(i => i.part_number === pn && i.quantity - (i.reserved || 0) > 0);
  const blocked = mine.filter(m => ['WAITING_FOR_COMPONENT', 'AWAITING_DELIVERY'].includes(m.status));
  const runnable = mine.filter(m => ['READY_TO_START', 'SCHEDULED'].includes(m.status));
  const inProgress = mine.filter(m => m.status === 'IN_PROGRESS');
  const stalled = blocked.filter(m => !hasPart(m.component));

  return (
    <div>
      <PageHeader
        title="Maintenance"
        subtitle={`Work orders for aircraft based at ${baseName(homeBase)}. Base action is required once the component has arrived — start the job, then sign it off.`}
      />

      <div className="ops-kpi-grid">
        <KpiCard label="Work Orders" value={mine.length} />
        <KpiCard label="Waiting On Parts" value={blocked.length} accent={C.crit} sub="logistics must deliver" />
        <KpiCard label="Ready To Start" value={runnable.length} accent={C.info} sub="component on hand" />
        <KpiCard label="In Progress" value={inProgress.length} accent={C.warn} />
      </div>

      {stalled.length > 0 && (
        <div className="ops-card ops-callout" style={{ '--callout': C.crit, padding: '14px 18px', marginBottom: 6 }}>
          <div className="ops-label">Cannot start — part not in local stock</div>
          <ul style={{ fontSize: 13, color: C.text2, paddingLeft: 18, margin: '6px 0 0' }}>
            {stalled.map(m => (
              <li key={m.id}>
                <b>{m.aircraft_id}</b> needs <b style={{ color: C.warn }}>{m.component}</b> — {baseName(homeBase)} holds none in free stock.
              </li>
            ))}
          </ul>
        </div>
      )}

      <StatusMsg>{msg}</StatusMsg>

      <SectionTitle
        right={
          <Select
            value={status}
            onChange={setStatus}
            label="All statuses"
            options={[...new Set(mine.map(m => m.status))].map(s => ({ value: s, label: titleCase(s) }))}
          />
        }
      >
        Work orders at {baseName(homeBase)}
      </SectionTitle>
      <MaintenanceTable
        rows={filtered}
        busy={busy}
        onOpenAircraft={onOpenAircraft}
        onStart={m => act(() => api.startMx(m.aircraft_id), `Maintenance started on ${m.aircraft_id}`)}
        onComplete={m => act(() => api.completeMx(m.aircraft_id), `Work order completed for ${m.aircraft_id}; aircraft availability is recomputed`)}
        empty="No work orders at this base."
      />

      <SectionTitle>Loop status</SectionTitle>
      <div className="ops-card" style={{ padding: 16, fontSize: 13 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {['WAITING_FOR_COMPONENT', 'AWAITING_DELIVERY', 'READY_TO_START', 'IN_PROGRESS', 'COMPLETED'].map((s, i) => (
            <React.Fragment key={s}>
              <span style={{ padding: '4px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700, background: C.panel, border: `1px solid ${C.line}`, color: C.text2 }}>
                {titleCase(s)}
              </span>
              {i < 4 && <span style={{ color: C.dim }}>→</span>}
            </React.Fragment>
          ))}
        </div>
        <div style={{ marginTop: 10, fontSize: 12, color: C.muted }}>
          Logistics moves the component through the first three states; this base performs the last two.
        </div>
      </div>
    </div>
  );
}
