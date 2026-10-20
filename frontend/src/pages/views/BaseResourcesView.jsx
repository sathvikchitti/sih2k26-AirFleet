import React from 'react';
import { api, baseName, distanceBetween, etaBetween } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  ActionButton, Badge, DataError, Empty, KpiCard, Loading, PageHeader, SectionTitle,
  Select, StatusMsg, Table, inputStyle, statusColor,
} from '../../components/ui.jsx';
import { C } from '../../theme.js';

// Base manager — Resources: what this base holds, what its aircraft are
// waiting on, and the ability to raise a transfer request to logistics.
export default function BaseResourcesView({ homeBase, refreshKey, refresh }) {
  const { aircraft, inventory, parts, bases, transfers, loading, predictionError } = useFleetViews(refreshKey);
  const [req, setReq] = React.useState({ part_number: '', source_base: '', quantity: '1' });
  const [msg, setMsg] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  if (loading) return <Loading>Loading resources…</Loading>;
  if (predictionError) return <DataError error={predictionError}>Base resource demand cannot be assessed because aircraft predictions are unavailable.</DataError>;

  const mine = (inventory || []).filter(i => i.base_id === homeBase);
  const held = (aircraft || []).filter(a => a.base_id === homeBase);
  const others = (bases || []).filter(b => b.id !== homeBase);
  const partList = parts || [];

  const demandFor = (pn) => held.filter(a => (a.health?.required_component || a.required_component) === pn);
  const shortages = partList.map(p => {
    const need = demandFor(p.part_number);
    const row = mine.find(i => i.part_number === p.part_number);
    const free = row ? row.quantity - (row.reserved || 0) : 0;
    return { ...p, need: need.length, free, short: Math.max(0, need.length - free) };
  }).filter(x => x.need > 0);

  const neededParts = [...new Set(held.map(a => a.health?.required_component || a.required_component).filter(Boolean))];

  const submit = async (e) => {
    e.preventDefault();
    if (!req.part_number || !req.source_base) {
      setMsg('Pick both a component and a donor base.');
      return;
    }
    setBusy(true);
    setMsg('Submitting transfer request…');
    try {
      const t = await api.createTransfer({
        part_number: req.part_number,
        source_base: req.source_base,
        dest_base: homeBase,
        quantity: Number(req.quantity) || 1,
      });
      setMsg(`Request ${t.id} raised: ${t.part_number} ${baseName(t.source_base)} → ${baseName(homeBase)}. Status ${t.status}, ETA ${t.eta_hours}h.`);
      setReq({ part_number: '', source_base: '', quantity: '1' });
      refresh();
    } catch (e) {
      setMsg(e?.message || 'Transfer request failed. Check the backend connection and try again.');
    } finally {
      setBusy(false);
    }
  };

  const cols = [
    { key: 'part_number', label: 'Part', nowrap: true, render: i => <b className="ops-id">{i.part_number}</b> },
    { key: 'name', label: 'Name', render: i => (partList.find(p => p.part_number === i.part_number) || {}).name || '—' },
    {
      key: 'quantity', label: 'Qty', align: 'right',
      render: i => <b>{i.quantity}</b>,
    },
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
        const min = (partList.find(p => p.part_number === i.part_number) || {}).min_condition_pct;
        const ok = min != null && i.quantity > 0 && i.condition_pct >= min;
        return (
          <span style={{ color: !ok && i.quantity > 0 ? C.crit : C.text2 }}>
            {i.quantity === 0 ? '—' : i.condition_pct + '%'}
            {ok ? '' : min != null && i.quantity > 0 ? ` (min ${min}%)` : ''}
          </span>
        );
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
  ];

  const inbound = (transfers || []).filter(t => t.dest_base === homeBase);
  const outbound = (transfers || []).filter(t => t.source_base === homeBase);

  return (
    <div>
      <PageHeader
        title="Resources"
        subtitle={`Component stock held at ${baseName(homeBase)}, the aircraft here that depend on it, and a way to request what you are short of.`}
      />

      <div className="ops-kpi-grid">
        <KpiCard label="Stock Lines" value={mine.length} />
        <KpiCard
          label="Units Free"
          value={mine.reduce((s, i) => s + (i.quantity - (i.reserved || 0)), 0)}
          sub={mine.reduce((s, i) => s + (i.reserved || 0), 0) + ' reserved'}
        />
        <KpiCard label="Stockouts" value={mine.filter(i => i.status === 'STOCKOUT').length} accent={C.crit} />
        <KpiCard label="Inbound Transfers" value={inbound.filter(t => t.status !== 'RECEIVED').length} accent={C.info} />
      </div>

      <SectionTitle>Stock at {baseName(homeBase)}</SectionTitle>
      <Table columns={cols} rows={mine} rowKey="id" empty="This base holds no components." />

      <SectionTitle>Aircraft here waiting on a component</SectionTitle>
      {neededParts.length === 0 ? (
        <div className="ops-card"><Empty>No aircraft at this base need a component right now.</Empty></div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))', gap: 12 }}>
          {shortages.map(s => (
            <div key={s.part_number} className="ops-card ops-callout" style={{ '--callout': (s.short ? C.crit : C.ok), padding: '14px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <b>{s.part_number}</b>
                <Badge color={s.short ? C.crit : C.ok}>{s.short ? 'SHORT ' + s.short : 'COVERED'}</Badge>
              </div>
              <div style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>{s.name}</div>
              <div style={{ fontSize: 12, marginTop: 8 }}>
                {s.need} aircraft need it · <b>{s.free}</b> free locally
              </div>
              <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>
                Aircraft: {s.need ? demandFor(s.part_number).map(a => a.id).join(', ') : '—'}
              </div>
            </div>
          ))}
        </div>
      )}

      <SectionTitle>Request a component transfer</SectionTitle>
      <form className="ops-card" style={{ padding: 16, display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }} onSubmit={submit}>
        <div>
          <div className="ops-label" style={{ marginBottom: 4 }}>Component</div>
          <Select
            value={req.part_number}
            onChange={v => setReq(r => ({ ...r, part_number: v }))}
            label="Select component…"
            options={partList.map(p => ({ value: p.part_number, label: p.part_number + ' · ' + p.name }))}
          />
        </div>
        <div>
          <div className="ops-label" style={{ marginBottom: 4 }}>From base</div>
          <Select
            value={req.source_base}
            onChange={v => setReq(r => ({ ...r, source_base: v }))}
            label="Select donor…"
            options={others.map(b => ({ value: b.id, label: b.name }))}
          />
        </div>
        <div>
          <div className="ops-label" style={{ marginBottom: 4 }}>Quantity</div>
          <input
            type="number"
            min="1"
            value={req.quantity}
            onChange={e => setReq(r => ({ ...r, quantity: e.target.value }))}
            style={{ ...inputStyle, width: 80 }}
          />
        </div>
        {req.part_number && req.source_base && (
          <div style={{ fontSize: 12, color: C.muted }}>
            ETA {etaBetween(req.source_base, homeBase)}h · {distanceBetween(req.source_base, homeBase)} km
          </div>
        )}
        <ActionButton primary disabled={busy} onClick={submit}>{busy ? 'Submitting…' : 'Raise Request'}</ActionButton>
      </form>
      <StatusMsg>{msg}</StatusMsg>

      <SectionTitle>Movement involving {baseName(homeBase)}</SectionTitle>
      <Table
        rowKey="id"
        empty="No transfers involve this base."
        rows={[...inbound.map(t => ({ ...t, dir: 'IN' })), ...outbound.map(t => ({ ...t, dir: 'OUT' }))]}
        columns={[
          { key: 'id', label: 'ID' },
          { key: 'dir', label: 'Direction', render: t => <Badge color={t.dir === 'IN' ? C.ok : C.warn}>{t.dir === 'IN' ? 'INBOUND' : 'OUTBOUND'}</Badge> },
          { key: 'part_number', label: 'Part' },
          { key: 'route', label: 'Route', render: t => baseName(t.source_base) + ' → ' + baseName(t.dest_base) },
          { key: 'status', label: 'Status', render: t => <Badge color={statusColor(t.status)}>{String(t.status).replace(/_/g, ' ')}</Badge> },
          { key: 'eta_hours', label: 'ETA', align: 'right', render: t => t.eta_hours + ' h' },
        ]}
      />
    </div>
  );
}
