import React from 'react';
import { api, baseName, distanceBetween, etaBetween, rulText } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  ActionButton, DataError, Empty, KpiCard, Loading, PageHeader, RiskBadge,
  SectionTitle, StatusMsg, Table,
} from '../../components/ui.jsx';

// Logistics — Maintenance Resources: the demand side of logistics. Which work
// orders are blocked on a component, whether any base can cover them, and a
// one-click request to unblock. This is the view that turns the ML service's
// "this aircraft needs a part" into an actual physical movement.
export default function MaintenanceResourcesView({ onOpenAircraft, refreshKey, refresh }) {
  const { maintenance, aircraft, inventory, bases, parts, loading, predictionError } = useFleetViews(refreshKey);
  const [msg, setMsg] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  if (loading) return <Loading>Loading maintenance resources…</Loading>;
  if (predictionError) return <DataError error={predictionError}>Maintenance resource urgency cannot be assessed because aircraft predictions are unavailable.</DataError>;

  const mxList = (maintenance || []).filter(m => m.status !== 'COMPLETED');
  const acById = Object.fromEntries((aircraft || []).map(a => [a.id, a]));
  const blocked = mxList.filter(m => ['WAITING_FOR_COMPONENT', 'AWAITING_DELIVERY'].includes(m.status));

  // For each blocked work order, find every base that holds serviceable stock.
  const rows = blocked.map(m => {
    const part = (parts || []).find(p => p.part_number === m.component);
    const minCond = part ? part.min_condition_pct : null;
    const home = acById[m.aircraft_id]?.base_id;
    const donors = (bases || [])
      .map(b => {
        const row = inventory.find(i => i.base_id === b.id && i.part_number === m.component);
        const free = row ? row.quantity - (row.reserved || 0) : 0;
        const cond = row ? row.condition_pct : 0;
        return {
          base_id: b.id,
          base: baseName(b.id),
          free,
          condition_pct: cond,
          distance_km: distanceBetween(home, b.id),
          eta_hours: etaBetween(home, b.id),
          serviceable: free > 0 && (minCond == null || cond >= minCond),
          isHome: b.id === home,
        };
      })
      .filter(d => !d.isHome)
      .sort((x, y) => {
        if (x.serviceable !== y.serviceable) return x.serviceable ? -1 : 1;
        return x.distance_km - y.distance_km;
      });
    return {
      ...m,
      aircraft: acById[m.aircraft_id],
      home,
      part,
      donors,
      best: donors.find(d => d.serviceable) || null,
      remainingUsefulLife: acById[m.aircraft_id]?.health ? rulText(acById[m.aircraft_id].health) : '—',
    };
  });

  const covered = rows.filter(r => r.best);
  const uncoverable = rows.filter(r => !r.best);
  const partsDemanded = new Set(rows.map(r => r.component)).size;

  const requestTransfer = async (r) => {
    if (!r.best) return;
    setBusy(true);
    setMsg(`Raising transfer for ${r.aircraft_id}…`);
    try {
      const t = await api.createTransfer({
        part_number: r.component,
        source_base: r.best.base_id,
        dest_base: r.home,
        quantity: 1,
      });
      setMsg(`Transfer ${t.id} raised: ${t.part_number} ${baseName(t.source_base)} → ${baseName(t.dest_base)} · status ${t.status}, ETA ${t.eta_hours}h.`);
      refresh();
    } catch (e) {
      setMsg(e?.message || 'Transfer request failed. Check the backend connection and try again.');
    } finally {
      setBusy(false);
    }
  };

  const cols = [
    {
      key: 'aircraft_id', label: 'Aircraft',
      render: r => (
        <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <b>{r.aircraft_id}</b>
          {r.aircraft?.health?.risk_level && <RiskBadge risk={r.aircraft.health.risk_level} />}
        </span>
      ),
    },
    { key: 'base', label: 'Needs At', render: r => baseName(r.home) },
    { key: 'component', label: 'Component', render: r => <b style={{ color: '#d8a93d' }}>{r.component}</b> },
    { key: 'rul', label: 'RUL', align: 'right', render: r => r.remainingUsefulLife },
    { key: 'priority', label: 'Priority', render: r => r.priority },
    {
      key: 'status', label: 'Blocked Because',
      render: r => (
        <span style={{ fontSize: 12, color: r.best ? '#d8a93d' : '#e05c5c' }}>
          {r.best ? 'no stock at ' + baseName(r.home) : 'no serviceable stock fleet-wide'}
        </span>
      ),
    },
    {
      key: 'donor', label: 'Best Donor',
      render: r => (r.best
        ? <span>{r.best.base} · {r.best.free} free · {r.best.condition_pct}% cond<br /><span style={{ color: '#8b94a3', fontSize: 11 }}>{r.best.distance_km} km · ETA {r.best.eta_hours}h</span></span>
        : <span style={{ color: '#e05c5c' }}>none available</span>),
    },
    {
      key: 'action', label: 'Action', align: 'right',
      render: r => (
        <ActionButton
          small
          primary={!!r.best}
          disabled={busy || !r.best}
          onClick={() => requestTransfer(r)}
        >
          {r.best ? 'Request Transfer' : 'Blocked'}
        </ActionButton>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Maintenance Resources"
        subtitle="The demand side of logistics: every work order that is waiting on a physical component, and whether any base can actually cover it. Logistics moves parts — it never changes a maintenance decision."
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, margin: '14px 0' }}>
        <KpiCard label="Open Work Orders" value={mxList.length} />
        <KpiCard label="Blocked On A Part" value={blocked.length} accent="#e05c5c" />
        <KpiCard label="Coverable" value={covered.length} accent="#3fb97f" sub="a donor base has stock" />
        <KpiCard label="Uncoverable" value={uncoverable.length} accent="#d8a93d" />
        <KpiCard label="Parts Demanded" value={partsDemanded} accent="#d8a93d" />
      </div>

      <StatusMsg>{msg}</StatusMsg>

      <SectionTitle>Component demand — can we cover it?</SectionTitle>
      {rows.length === 0 ? (
        <div className="ops-card"><Empty>No open work order is waiting on a component.</Empty></div>
      ) : (
        <Table columns={cols} rows={rows} rowKey="id" onRowClick={r => onOpenAircraft(r.aircraft_id)} />
      )}

      {uncoverable.length > 0 && (
        <>
          <SectionTitle>Needs external sourcing</SectionTitle>
          <div className="ops-card" style={{ padding: 14, borderLeft: '4px solid #e05c5c' }}>
            <div style={{ fontSize: 13, marginBottom: 8 }}>
              These work orders cannot be cleared by moving stock between bases — every unit in the fleet is either consumed, reserved or below its minimum serviceable condition.
            </div>
            {uncoverable.map(r => (
              <div key={r.id} style={{ fontSize: 13, marginBottom: 6 }}>
                <b>{r.aircraft_id}</b> at {baseName(r.home)} needs <b style={{ color: '#d8a93d' }}>{r.component}</b> ·{' '}
                {r.donors.length
                  ? r.donors.map(d => `${d.base} (${d.free} free @ ${d.condition_pct}%)`).join(' · ')
                  : 'no other base holds this part'}
              </div>
            ))}
          </div>
        </>
      )}

      <SectionTitle>Availability of demanded components</SectionTitle>
      <Table
        rowKey="part_number"
        empty="No components are in demand."
        rows={[...new Set(rows.map(r => r.component))].map(pn => {
          const p = (parts || []).find(x => x.part_number === pn);
          return {
            part_number: pn,
            name: p ? p.name : '—',
            category: p ? p.category : '—',
            min_condition_pct: p ? p.min_condition_pct : null,
            totalQty: (inventory || []).filter(i => i.part_number === pn).reduce((s, i) => s + i.quantity, 0),
            serviceable: (bases || []).filter(b => {
              const row = inventory.find(i => i.base_id === b.id && i.part_number === pn);
              return row && row.quantity - (row.reserved || 0) > 0 && (p ? row.condition_pct >= p.min_condition_pct : true);
            }).length,
            wantedBy: rows.filter(r => r.component === pn).map(r => r.aircraft_id),
          };
        })}
        columns={[
          { key: 'part_number', label: 'Part', render: r => <b>{r.part_number}</b> },
          { key: 'name', label: 'Name' },
          { key: 'category', label: 'Category' },
          { key: 'totalQty', label: 'Units In Fleet', align: 'right' },
          {
            key: 'serviceable', label: 'Serviceable At', align: 'right',
            render: r => (
              <span style={{ color: r.serviceable ? '#3fb97f' : '#e05c5c', fontWeight: 700 }}>
                {r.serviceable} base{r.serviceable === 1 ? '' : 's'}
              </span>
            ),
          },
          {
            key: 'wantedBy', label: 'Wanted By',
            render: r => r.wantedBy.length
              ? r.wantedBy.map(id => (
                <button
                  key={id}
                  onClick={e => { e.stopPropagation(); onOpenAircraft(id); }}
                  style={{ background: '#151b24', border: '1px solid #2a3444', borderRadius: 6, padding: '2px 7px', marginRight: 4, color: '#e6e9ee', cursor: 'pointer', fontSize: 12 }}
                >
                  {id}
                </button>
              ))
              : '—',
          },
        ]}
      />

      <SectionTitle>Resource utilisation — components not tied to any open work order</SectionTitle>
      <div style={{ fontSize: 13, color: '#8b94a3' }}>
        {(parts || [])
          .filter(p => !rows.some(r => r.component === p.part_number))
          .map(p => p.part_number + ' (' + p.name + ')')
          .join(' · ') || 'Every catalogue component is tied to at least one open work order.'}
      </div>
    </div>
  );
}
