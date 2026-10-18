import React from 'react';
import { baseName, failureProbabilityText, rulText } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  Badge, DataError, KpiCard, Loading, PageHeader, RiskBadge,
  SearchInput, Select, Table, riskColor, statusColor,
} from '../../components/ui.jsx';

// Commander — Fleet: every airframe across all bases with its ML health readout,
// filterable and sortable. Sorted worst-first so the aircraft that can hurt
// availability are never buried.
export default function FleetView({ onOpenAircraft, refreshKey, focusBase }) {
  const { aircraft, loading, predictionError } = useFleetViews(refreshKey);
  const [q, setQ] = React.useState('');
  const [risk, setRisk] = React.useState('');
  const [base, setBase] = React.useState(focusBase || '');
  const [sort, setSort] = React.useState('health');

  // Re-sync when the user drills in from the Bases view.
  React.useEffect(() => { setBase(focusBase || ''); }, [focusBase]);

  const rows = React.useMemo(() => {
    let out = aircraft || [];
    if (q) {
      const needle = q.toLowerCase();
      out = out.filter(a =>
        String(a.id).toLowerCase().includes(needle) ||
        String(a.type || '').toLowerCase().includes(needle) ||
        String(a.health?.required_component || a.required_component || '').toLowerCase().includes(needle));
    }
    if (risk) out = out.filter(a => (a.health?.risk_level || 'LOW') === risk);
    if (base) out = out.filter(a => a.base_id === base);

    const score = (a) => (a.health?.health_score ?? 100);
    const rank = (a) => ({ CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }[a.health?.risk_level || 'LOW']);
    return [...out].sort((x, y) =>
      sort === 'risk' ? rank(x) - rank(y)
      : sort === 'id' ? String(x.id).localeCompare(String(y.id))
      : score(x) - score(y));
  }, [aircraft, q, risk, base, sort]);

  if (loading) return <Loading>Loading fleet…</Loading>;
  if (predictionError) return <DataError error={predictionError}>Fleet health predictions are unavailable from the selected ML provider.</DataError>;

  const list = aircraft || [];
  const avg = Math.round(list.reduce((s, a) => s + (a.health?.health_score ?? 100), 0) / Math.max(1, list.length));

  const cols = [
    { key: 'id', label: 'Tail', render: a => <b style={{ fontSize: 14 }}>{a.id}</b> },
    { key: 'type', label: 'Type' },
    { key: 'base_id', label: 'Base', render: a => baseName(a.base_id) },
    {
      key: 'status', label: 'Status',
      render: a => <Badge color={statusColor(a.status)}>{String(a.status).replace(/_/g, ' ')}</Badge>,
    },
    {
      key: 'health', label: 'Health',
      render: a => (
        <span style={{ color: riskColor(a.health?.risk_level || 'LOW'), fontWeight: 700 }}>
          {a.health ? a.health.health_score + '%' : '—'}
        </span>
      ),
    },
    {
      key: 'risk', label: 'Risk',
      render: a => (a.health ? <RiskBadge risk={a.health.risk_level} /> : <span style={{ color: '#8b94a3' }}>—</span>),
    },
    { key: 'rul', label: 'RUL', align: 'right', render: a => (a.health ? rulText(a.health) : '—') },
    {
      key: 'fail', label: 'Fail prob', align: 'right',
      render: a => (a.health ? failureProbabilityText(a.health) : '—'),
    },
    {
      key: 'part', label: 'Needs part',
      render: a => a.health?.required_component || a.required_component || '—',
    },
    {
      key: 'mx', label: 'Maintenance',
      render: a => (a.maintenance ? String(a.maintenance.status).replace(/_/g, ' ') : '—'),
    },
  ];

  return (
    <div>
      <PageHeader
        title={base ? 'Fleet — ' + baseName(base) : 'Fleet'}
        subtitle="Every airframe across all bases with its ML health readout. Sorted worst-first by default so the aircraft that can hurt availability are never buried."
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, margin: '14px 0' }}>
        <KpiCard label="Total Aircraft" value={list.length} />
        <KpiCard
          label="High / Critical Risk"
          value={list.filter(a => ['HIGH', 'CRITICAL'].includes(a.health?.risk_level)).length}
          accent="#e05c5c"
        />
        <KpiCard
          label="Needs A Part"
          value={list.filter(a => a.health?.required_component || a.required_component).length}
          accent="#d8a93d"
        />
        <KpiCard label="Average Health" value={avg + '%'} accent="#3fb97f" />
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <SearchInput value={q} onChange={setQ} placeholder="Search tail, type or part…" />
        <Select
          value={risk}
          onChange={setRisk}
          label="All risk levels"
          options={['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map(r => ({ value: r, label: r }))}
        />
        <Select
          value={base}
          onChange={setBase}
          label="All bases"
          options={Array.from(new Set(list.map(a => a.base_id))).map(b => ({ value: b, label: baseName(b) }))}
        />
        <Select
          value={sort}
          onChange={setSort}
          options={[
            { value: 'health', label: 'Sort: worst health' },
            { value: 'risk', label: 'Sort: highest risk' },
            { value: 'id', label: 'Sort: tail number' },
          ]}
        />
      </div>

      <Table
        columns={cols}
        rows={rows}
        rowKey="id"
        onRowClick={a => onOpenAircraft(a.id)}
        empty={q || risk || base ? 'No aircraft match these filters.' : 'No aircraft in fleet.'}
      />
      <div style={{ fontSize: 12, color: '#5d6675', marginTop: 8 }}>
        Showing {rows.length} of {(aircraft || []).length} aircraft
        {base ? <> · filtered to <b style={{ color: '#d8a93d' }}>{baseName(base)}</b></> : null}
        {' · '}
        Click any row to open the full aircraft record.
      </div>
      {base && (
        <div style={{ marginTop: 8 }}>
          <button
            onClick={() => setBase('')}
            style={{ background: 'transparent', border: '1px solid #2a3444', color: '#c6ccd6', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 12 }}
          >
            Clear base filter
          </button>
        </div>
      )}
    </div>
  );
}
