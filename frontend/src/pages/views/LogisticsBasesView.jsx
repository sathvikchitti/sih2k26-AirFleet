import React from 'react';
import { api, baseName } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  ActionButton, Badge, DataError, Empty, KpiCard, Loading, PageHeader, SectionTitle,
  Select, StatusMsg, Table, statusColor, MiniMeter,
} from '../../components/ui.jsx';
import { C } from '../../theme.js';

const READINESS = (pct) => (pct >= 85 ? C.ok : pct >= 50 ? C.warn : C.crit);

// Logistics — Bases: the same three bases the commander commands, seen from
// logistics' side — what each holds, what it owes other bases, and which of
// its aircraft are grounded for want of a part.
export default function LogisticsBasesView({ onOpenAircraft, refreshKey, refresh }) {
  const { bases, fleet, inventory, aircraft, maintenance, parts, loading, predictionError } = useFleetViews(refreshKey);
  const [focus, setFocus] = React.useState('');
  const [msg, setMsg] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  if (loading) return <Loading>Loading bases…</Loading>;
  if (predictionError) return <DataError error={predictionError}>Cross-base demand cannot be assessed because aircraft predictions are unavailable.</DataError>;

  const baseList = bases || [];
  const nameOf = (pn) => (parts || []).find(p => p.part_number === pn)?.name || '—';
  const minOf = (pn) => (parts || []).find(p => p.part_number === pn)?.min_condition_pct;

  const detail = baseList.map(b => {
    const held = (aircraft || []).filter(a => a.base_id === b.id);
    const stock = (inventory || []).filter(i => i.base_id === b.id);
    const f = (fleet?.bases || []).find(x => x.id === b.id);
    const wos = (maintenance || []).filter(m => held.some(a => a.id === m.aircraft_id));
    const blocked = wos.filter(m =>
      ['WAITING_FOR_COMPONENT', 'AWAITING_DELIVERY'].includes(m.status) &&
      !stock.some(i => i.part_number === m.component && i.quantity - (i.reserved || 0) > 0));
    return {
      ...b,
      aircraftCount: held.length,
      available: f ? f.available : held.filter(a => a.status === 'AVAILABLE').length,
      readiness: f ? f.availability_pct : null,
      atRisk: f ? f.at_risk : held.filter(a => ['AT_RISK', 'DEGRADED'].includes(a.status)).length,
      stockLines: stock.length,
      units: stock.reduce((s, i) => s + i.quantity, 0),
      stockouts: stock.filter(i => i.status === 'STOCKOUT').map(i => i.part_number),
      unserviceable: stock.filter(i => i.quantity > 0 && minOf(i.part_number) != null && i.condition_pct < minOf(i.part_number)).map(i => i.part_number),
      blocked,
      held,
    };
  });

  const visible = focus ? detail.filter(d => d.id === focus) : detail;

  // Aircraft elsewhere that this base could help: needs a part it holds.
  const opportunities = baseList.map(b => {
    const stock = (inventory || []).filter(i => i.base_id === b.id && i.quantity - (i.reserved || 0) > 0);
    const needy = (aircraft || []).filter(a => {
      const need = a.health?.required_component || a.required_component;
      return need && a.base_id !== b.id &&
        stock.some(i => i.part_number === need && i.condition_pct >= (minOf(need) ?? 0));
    });
    return { base: b, count: needy.length, needy };
  }).filter(o => o.count > 0);

  const rebalance = async (o) => {
    setBusy(true);
    setMsg('Requesting transfer…');
    try {
      const a = o.needy[0];
      const need = a.health?.required_component || a.required_component;
      const t = await api.createTransfer({ part_number: need, source_base: o.base.id, dest_base: a.base_id, quantity: 1 });
      setMsg(`Transfer ${t.id} raised: ${need} ${baseName(o.base.id)} → ${baseName(a.base_id)} · ETA ${t.eta_hours}h.`);
      refresh();
    } catch (e) {
      setMsg(e?.message || 'Transfer request failed. Check the backend connection and try again.');
    } finally {
      setBusy(false);
    }
  };

  const cols = [
    { key: 'name', label: 'Base', render: b => <b>{b.name}</b> },
    { key: 'location', label: 'Location' },
    { key: 'aircraftCount', label: 'Aircraft', align: 'right' },
    { key: 'available', label: 'Available', align: 'right', render: b => <span style={{ color: C.ok, fontWeight: 700 }}>{b.available}</span> },
    {
      key: 'readiness', label: 'Readiness', align: 'right',
      render: b => <MiniMeter pct={b.readiness} color={b.readiness == null ? C.muted : READINESS(b.readiness)} />,
    },
    { key: 'stockLines', label: 'Stock Lines', align: 'right' },
    { key: 'units', label: 'Units', align: 'right' },
    {
      key: 'stockouts', label: 'Stockouts', align: 'right',
      render: b => (b.stockouts.length
        ? <span style={{ color: C.crit, fontWeight: 700 }}>{b.stockouts.length}</span>
        : <span style={{ color: C.dim }}>0</span>),
    },
    {
      key: 'blocked', label: 'Grounded For Parts', align: 'right',
      render: b => (b.blocked.length
        ? <span style={{ color: C.crit, fontWeight: 700 }}>{b.blocked.length}</span>
        : <span style={{ color: C.dim }}>0</span>),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Bases"
        subtitle="Every base as logistics sees it: aircraft held, parts held, and the gap between the two. Stockouts and grounded aircraft are the two numbers that matter here."
        right={
          <Select
            value={focus}
            onChange={setFocus}
            label="All bases"
            options={baseList.map(b => ({ value: b.id, label: b.name }))}
          />
        }
      />

      <div className="ops-kpi-grid">
        <KpiCard label="Bases" value={baseList.length} />
        <KpiCard label="Stock Lines" value={(inventory || []).length} />
        <KpiCard label="Stockouts" value={(inventory || []).filter(i => i.status === 'STOCKOUT').length} accent={C.crit} />
        <KpiCard label="Grounded For Parts" value={detail.reduce((s, b) => s + b.blocked.length, 0)} accent={C.crit} />
      </div>

      <StatusMsg>{msg}</StatusMsg>

      <SectionTitle>Base stock position</SectionTitle>
      <Table columns={cols} rows={visible} rowKey="id" empty="No bases configured." />

      <SectionTitle>Cross-base rebalancing opportunities</SectionTitle>
      {opportunities.length === 0 ? (
        <div className="ops-card"><Empty>No base currently holds a part another base needs.</Empty></div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(250px,1fr))', gap: 12 }}>
          {opportunities.map(o => (
            <div key={o.base.id} className="ops-card ops-callout" style={{ '--callout': C.warn, padding: '14px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <b>{o.base.name}</b>
                <Badge color={C.warn}>{o.count} could help</Badge>
              </div>
              <div style={{ fontSize: 12, color: C.muted, marginTop: 6, marginBottom: 8 }}>
                Aircraft elsewhere holding serviceable stock you could send:
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {(o.needy || []).map(a => (
                  <div key={a.id} style={{ fontSize: 12, color: C.text2 }}>
                    <b>{a.id}</b> at {baseName(a.base_id)} needs{' '}
                    <b style={{ color: C.warn }}>{a.health?.required_component || a.required_component}</b>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 10 }}>
                <ActionButton small primary disabled={busy} onClick={() => rebalance(o)}>Request Transfer</ActionButton>
              </div>
            </div>
          ))}
        </div>
      )}

      <SectionTitle>Stock held per base</SectionTitle>
      {visible.map(b => (
        <div key={b.id} style={{ marginBottom: 18 }}>
          <SectionTitle>{b.name}</SectionTitle>
          <Table
            rowKey="id"
            empty="No stock at this base."
            rows={(inventory || []).filter(i => i.base_id === b.id)}
            columns={[
              { key: 'part_number', label: 'Part', nowrap: true, render: i => <b className="ops-id">{i.part_number}</b> },
              { key: 'name', label: 'Name', nowrap: true, render: i => <span style={{ color: C.muted }}>{nameOf(i.part_number)}</span> },
              { key: 'quantity', label: 'Qty', align: 'right' },
              { key: 'reserved', label: 'Reserved', align: 'right', render: i => (i.reserved || 0) },
              {
                key: 'free', label: 'Free', align: 'right',
                render: i => {
                  const free = i.quantity - (i.reserved || 0);
                  return <b style={{ color: free <= 0 ? C.crit : free === 1 ? C.warn : C.ok }}>{free}</b>;
                },
              },
              {
                key: 'condition_pct', label: 'Condition', align: 'right',
                render: i => {
                  const min = minOf(i.part_number);
                  const ok = i.quantity > 0 && (min == null || i.condition_pct >= min);
                  return <span style={{ color: i.quantity === 0 ? C.dim : ok ? C.text2 : C.crit }}>
                    {i.quantity === 0 ? '—' : i.condition_pct + '%'}
                  </span>;
                },
              },
              {
                key: 'status', label: 'Status',
                render: i => (
                  <Badge color={statusColor(i.status)}>
                    {String(i.status).replace(/_/g, ' ')}
                  </Badge>
                ),
              },
            ]}
          />
        </div>
      ))}

      {visible.some(b => b.blocked.length > 0) && (
        <>
          <SectionTitle>Aircraft grounded for want of a part</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {visible.flatMap(b => b.blocked).map(m => (
              <div key={m.id} className="ops-card ops-callout" style={{ '--callout': C.crit, padding: '14px 18px', display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                <div style={{ fontSize: 13 }}>
                  <b>{m.aircraft_id}</b> at {baseName((aircraft || []).find(a => a.id === m.aircraft_id)?.base_id)} —{' '}
                  waiting on <b style={{ color: C.warn }}>{m.component}</b> ({m.id}, {String(m.status).replace(/_/g, ' ').toLowerCase()})
                </div>
                <ActionButton small onClick={() => onOpenAircraft(m.aircraft_id)}>View Aircraft</ActionButton>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
