import React from 'react';
import { api, baseName, titleCase } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  ActionButton, Badge, KpiCard, Loading, PageHeader, SectionTitle, Select,
  StatusMsg, Table, priorityColor,
} from '../../components/ui.jsx';
import { C } from '../../theme.js';

const MX_COLOR = {
  WAITING_FOR_COMPONENT: C.crit,
  AWAITING_DELIVERY: C.warn,
  READY_TO_START: C.info,
  IN_PROGRESS: C.info,
  SCHEDULED: C.muted,
  COMPLETED: C.ok,
};

export function mxColor(status) { return MX_COLOR[status] || C.muted; }

// Maintenance work orders across the fleet. Supports the two manual steps of
// the closed loop (start / complete) for both the commander and base views.
export function MaintenanceTable({ rows, onOpenAircraft, busy, onStart, onComplete, scopeLabel }) {
  return (
    <Table
      rowKey="id"
      empty="No maintenance work orders."
      rows={rows}
      onRowClick={onOpenAircraft ? r => onOpenAircraft(r.aircraft_id) : undefined}
      columns={[
        { key: 'id', label: 'WO', nowrap: true, render: m => <span className="ops-id">{m.id}</span> },
        {
          key: 'aircraft_id', label: 'Aircraft',
          render: m => <b className="ops-id">{m.aircraft_id}</b>,
        },
        ...(scopeLabel ? [{ key: 'base', label: 'Base', render: m => scopeLabel(m) }] : []),
        { key: 'component', label: 'Component' },
        {
          key: 'priority', label: 'Priority',
          render: m => (
            <Badge color={priorityColor(m.priority)}>
              {m.priority}
            </Badge>
          ),
        },
        {
          key: 'status', label: 'Status',
          render: m => <Badge color={mxColor(m.status)}>{titleCase(m.status)}</Badge>,
        },
        { key: 'estimated_recovery_hours', label: 'Est. hours', align: 'right', render: m => (m.estimated_recovery_hours ?? '—') + (m.estimated_recovery_hours != null ? ' h' : '') },
        {
          key: 'actions', label: 'Action', align: 'right',
          render: m => (
            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }} onClick={e => e.stopPropagation()}>
              {['READY_TO_START', 'SCHEDULED'].includes(m.status) && (
                <ActionButton small disabled={busy} onClick={() => onStart(m)}>Start</ActionButton>
              )}
              {m.status === 'IN_PROGRESS' && (
                <ActionButton small primary disabled={busy} onClick={() => onComplete(m)}>Complete</ActionButton>
              )}
              {['WAITING_FOR_COMPONENT', 'AWAITING_DELIVERY', 'IN_TRANSIT'].includes(m.status) && (
                <span style={{ fontSize: 11, color: C.muted }}>awaiting part</span>
              )}
              {m.status === 'COMPLETED' && <span style={{ fontSize: 11, color: C.ok }}>done</span>}
            </div>
          ),
        },
      ]}
    />
  );
}

export default function MaintenanceView({ refreshKey, refresh }) {
  const { maintenance, aircraft, loading } = useFleetViews(refreshKey);
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

  const list = maintenance || [];
  const filtered = status ? list.filter(m => m.status === status) : list;
  const blocked = list.filter(m => ['WAITING_FOR_COMPONENT', 'AWAITING_DELIVERY'].includes(m.status));
  const active = list.filter(m => ['IN_PROGRESS', 'READY_TO_START', 'SCHEDULED'].includes(m.status));
  const done = list.filter(m => m.status === 'COMPLETED');
  const hoursToRecover = blocked.concat(active).reduce((s, m) => s + (m.estimated_recovery_hours || 0), 0);

  const baseOf = (id) => {
    const a = (aircraft || []).find(x => x.id === id);
    return a ? baseName(a.base_id) : '—';
  };

  return (
    <div>
      <PageHeader
        title="Maintenance"
        subtitle="Every open work order across the fleet. Work orders blocked on a component are the ones actually costing availability — they are called out first."
      />

      <div className="ops-kpi-grid">
        <KpiCard label="Open Work Orders" value={list.filter(m => m.status !== 'COMPLETED').length} />
        <KpiCard label="Blocked On Part" value={blocked.length} accent={C.crit} sub="no component available" />
        <KpiCard label="In Progress" value={list.filter(m => m.status === 'IN_PROGRESS').length} accent={C.info} />
        <KpiCard label="Est. Downtime" value={hoursToRecover + ' h'} accent={C.warn} sub="sum of open WOs" />
      </div>

      <StatusMsg>{msg}</StatusMsg>

      <SectionTitle
        right={
          <Select
            value={status}
            onChange={setStatus}
            label="All statuses"
            options={[...new Set(list.map(m => m.status))].map(s => ({ value: s, label: titleCase(s) }))}
          />
        }
      >
        Work orders
      </SectionTitle>
      <MaintenanceTable
        rows={filtered}
        busy={busy}
        scopeLabel={baseOf}
        onStart={m => act(() => api.startMx(m.aircraft_id), `Maintenance started on ${m.aircraft_id}`)}
        onComplete={m => act(() => api.completeMx(m.aircraft_id), `Work order completed for ${m.aircraft_id}; aircraft availability is recomputed`)}
      />

      <SectionTitle>Summary</SectionTitle>
      <div>
        <div className="ops-metric-strip">
          <div><div className="ops-label">Blocked on component</div><div className="ops-metric-value" style={{ color: C.crit }}>{blocked.length}</div></div>
          <div><div className="ops-label">Ready / scheduled</div><div className="ops-metric-value" style={{ color: C.info }}>{active.length}</div></div>
          <div><div className="ops-label">Completed</div><div className="ops-metric-value" style={{ color: C.ok }}>{done.length}</div></div>
          <div>
            <div className="ops-label">Oldest open WO</div>
            <div className="ops-metric-value ops-id" style={{ fontSize: 20, fontFamily: 'var(--font-mono)', fontWeight: 500 }}>
              {(list.filter(m => m.status !== 'COMPLETED' && m.started)[0] || {}).started?.slice(0, 10) || '—'}
            </div>
          </div>
        </div>
        <div className="ops-note" style={{ marginTop: 12 }}>
          Loop: approve sourcing → component arrives → Start → Complete work order → aircraft status is recomputed from the current classifier and prediction.
        </div>
      </div>
    </div>
  );
}
