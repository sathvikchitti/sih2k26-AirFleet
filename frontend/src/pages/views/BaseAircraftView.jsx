import React from 'react';
import { baseName, rulText } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  Badge, DataError, KpiCard, Loading, PageHeader, RiskBadge, SearchInput,
  Select, Table, riskColor, statusColor,
} from '../../components/ui.jsx';

// Base manager — Aircraft: the base's own airframes, with a filterable table
// and the health figures that decide whether each one flies today.
export default function BaseAircraftView({ homeBase, onOpenAircraft, refreshKey }) {
  const { aircraft, loading, predictionError } = useFleetViews(refreshKey);
  const [q, setQ] = React.useState('');
  const [status, setStatus] = React.useState('');

  if (loading) return <Loading>Loading aircraft…</Loading>;
  if (predictionError) return <DataError error={predictionError}>Aircraft predictions are unavailable from the selected ML provider.</DataError>;

  let held = (aircraft || []).filter(a => a.base_id === homeBase);
  if (q) {
    const needle = q.toLowerCase();
    held = held.filter(a => String(a.id).toLowerCase().includes(needle) || String(a.type || '').toLowerCase().includes(needle));
  }
  if (status) held = held.filter(a => a.status === status);

  const mxById = {};
  (aircraft || []).forEach(a => { if (a.maintenance) mxById[a.id] = a.maintenance; });

  const cols = [
    { key: 'id', label: 'Tail', render: a => <b style={{ fontSize: 14 }}>{a.id}</b> },
    { key: 'type', label: 'Type' },
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
      render: a => (a.health ? <RiskBadge risk={a.health.risk_level} /> : '—'),
    },
    { key: 'rul', label: 'RUL', align: 'right', render: a => (a.health ? rulText(a.health) : '—') },
    {
      key: 'part', label: 'Needs part',
      render: a => a.health?.required_component || a.required_component || '—',
    },
    {
      key: 'mx', label: 'Work order',
      render: a => (mxById[a.id] ? String(mxById[a.id].status).replace(/_/g, ' ') : '—'),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Aircraft"
        subtitle={`Airframes based at ${baseName(homeBase)}. Health figures are read from the ML service — nothing here is entered by hand.`}
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, margin: '14px 0' }}>
        <KpiCard label="Aircraft At Base" value={(aircraft || []).filter(a => a.base_id === homeBase).length} />
        <KpiCard label="Flyable" value={(aircraft || []).filter(a => a.base_id === homeBase && a.status === 'AVAILABLE').length} accent="#3fb97f" />
        <KpiCard label="Degraded / At Risk" value={(aircraft || []).filter(a => a.base_id === homeBase && ['AT_RISK', 'DEGRADED'].includes(a.status)).length} accent="#e05c5c" />
        <KpiCard label="In Maintenance" value={(aircraft || []).filter(a => a.base_id === homeBase && a.status === 'MAINTENANCE').length} accent="#4f9cf0" />
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <SearchInput value={q} onChange={setQ} placeholder="Search tail or type…" />
        <Select
          value={status}
          onChange={setStatus}
          label="All statuses"
          options={['AVAILABLE', 'AT_RISK', 'DEGRADED', 'MAINTENANCE'].map(s => ({ value: s, label: s.replace(/_/g, ' ') }))}
        />
      </div>

      <Table
        columns={cols}
        rows={held}
        rowKey="id"
        onRowClick={a => onOpenAircraft(a.id)}
        empty={q || status ? 'No aircraft match these filters.' : 'No aircraft at this base.'}
      />
      <div style={{ fontSize: 12, color: '#5d6675', marginTop: 8 }}>
        Click a row for the full record, trend and recommended sourcing.
      </div>
    </div>
  );
}
