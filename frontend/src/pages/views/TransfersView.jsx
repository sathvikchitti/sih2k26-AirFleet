import React from 'react';
import { api, baseName, distanceText, etaText } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  ActionButton, Badge, Empty, KpiCard, Loading, PageHeader, SearchInput,
  SectionTitle, Select, StatusMsg, Table,
} from '../../components/ui.jsx';

const TONE = {
  PENDING_APPROVAL: '#d8a93d',
  IN_TRANSIT: '#4f9cf0',
  RECEIVED: '#3fb97f',
};

const quantityText = value => value == null || value === '' || !Number.isFinite(Number(value))
  ? '—' : Number(value).toLocaleString();

// Logistics — Transfers: the movement pipeline, plus the ability to raise a
// new transfer. Approve releases stock, simulate arrival lands it and pushes
// the dependent work order forward.
export default function TransfersView({ refreshKey, refresh }) {
  const { transfers, inventory, parts, partsError, bases, aircraft, loading } = useFleetViews(refreshKey);
  const [q, setQ] = React.useState('');
  const [status, setStatus] = React.useState('');
  const [msg, setMsg] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [form, setForm] = React.useState({ part_number: '', source_base: '', dest_base: '', quantity: '1' });

  const act = async (fn, label) => {
    setBusy(true);
    setMsg(label + '…');
    try {
      await fn();
      setMsg(label + ' — done');
      refresh();
      return true;
    } catch (e) {
      setMsg(e?.message || 'Transfer action failed. Check the backend connection and try again.');
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Loading>Loading transfers…</Loading>;

  const list = transfers || [];
  let rows = list;
  if (q) {
    const needle = q.toLowerCase();
    rows = rows.filter(t =>
      String(t.id).toLowerCase().includes(needle) ||
      String(t.part_number).toLowerCase().includes(needle) ||
      baseName(t.source_base).toLowerCase().includes(needle) ||
      baseName(t.dest_base).toLowerCase().includes(needle));
  }
  if (status) rows = rows.filter(t => t.status === status);

  const submit = async (e) => {
    e.preventDefault();
    if (!Array.isArray(parts) || parts.length === 0 || partsError) {
      setMsg(partsError?.message || 'The live component catalogue is unavailable; no transfer was requested.');
      return;
    }
    if (!form.part_number || !form.source_base || !form.dest_base) {
      setMsg('Pick a component, a source base and a destination base.');
      return;
    }
    if (form.source_base === form.dest_base) {
      setMsg('Source and destination must be different bases.');
      return;
    }
    const quantity = Number(form.quantity);
    if (!Number.isInteger(quantity) || quantity < 1) {
      setMsg('Quantity must be a whole number of at least 1.');
      return;
    }
    const succeeded = await act(
      () => api.createTransfer({
        part_number: form.part_number,
        source_base: form.source_base,
        dest_base: form.dest_base,
        quantity,
      }),
      'Transfer requested'
    );
    if (succeeded) setForm({ part_number: '', source_base: '', dest_base: '', quantity: '1' });
  };

  const donorStock = (pn, bid) => {
    if (!Array.isArray(inventory)) return null;
    const row = inventory.find(i => i.part_number === pn && i.base_id === bid);
    return row ? row.available_for_transfer : null;
  };

  return (
    <div>
      <PageHeader
        title="Transfers"
        subtitle="Every component movement between bases. Approve releases the donor's stock, arrival credits the destination and unlocks the dependent work order."
      />

      <div className="ops-kpi-grid">
        <KpiCard label="Total Transfers" value={list.length} />
        <KpiCard label="Pending Approval" value={list.filter(t => t.status === 'PENDING_APPROVAL').length} accent="#d8a93d" />
        <KpiCard label="In Transit" value={list.filter(t => t.status === 'IN_TRANSIT').length} accent="#4f9cf0" />
        <KpiCard label="Received" value={list.filter(t => t.status === 'RECEIVED').length} accent="#3fb97f" />
      </div>

      <StatusMsg>{msg}</StatusMsg>

      <SectionTitle>Raise a transfer</SectionTitle>
      <form className="ops-card ops-form-grid" onSubmit={submit}>
        <div className="ops-form-field">
          <label className="ops-form-label" htmlFor="transfer-component">Component</label>
          <Select
            id="transfer-component"
            value={form.part_number}
            onChange={v => setForm(f => ({ ...f, part_number: v }))}
            label={partsError ? 'Catalogue unavailable' : parts == null ? 'Loading component catalogue…' : parts.length ? 'Select component…' : 'No components in catalogue'}
            options={(parts || []).map(p => ({ value: p.part_number, label: p.part_number + ' · ' + p.name }))}
          />
          {partsError ? <div role="alert" style={{ color: '#e05c5c', fontSize: 11, marginTop: 5 }}>Live component catalogue unavailable. Transfer creation is disabled. {partsError.message}</div> : null}
        </div>
        <div className="ops-form-field">
          <label className="ops-form-label" htmlFor="transfer-source">From</label>
          <Select
            id="transfer-source"
            value={form.source_base}
            onChange={v => setForm(f => ({ ...f, source_base: v }))}
            label="Source…"
            options={(bases || []).map(b => ({ value: b.id, label: b.name }))}
          />
        </div>
        <div className="ops-form-field">
          <label className="ops-form-label" htmlFor="transfer-destination">To</label>
          <Select
            id="transfer-destination"
            value={form.dest_base}
            onChange={v => setForm(f => ({ ...f, dest_base: v }))}
            label="Destination…"
            options={(bases || []).filter(b => b.id !== form.source_base).map(b => ({ value: b.id, label: b.name }))}
          />
        </div>
        <div className="ops-form-field">
          <label className="ops-form-label" htmlFor="transfer-quantity">Quantity</label>
          <input
            id="transfer-quantity"
            type="number"
            min="1"
            step="1"
            required
            value={form.quantity}
            onChange={e => setForm(f => ({ ...f, quantity: e.target.value }))}
            className="ops-control ops-number"
          />
        </div>
        <div className="ops-form-summary">
          {form.source_base && form.dest_base ? <>
            Route distance and ETA are shown after the backend records the transfer.
            {form.part_number ? <> · {quantityText(donorStock(form.part_number, form.source_base))} free after reserve at source</> : null}
          </> : 'Choose a route and component; the backend validates transfer availability when requested.'}
          </div>
        <div className="ops-form-submit"><ActionButton primary disabled={busy || !Array.isArray(parts) || parts.length === 0 || Boolean(partsError)} onClick={submit}>{busy ? 'Submitting…' : 'Create Transfer'}</ActionButton></div>
      </form>

      <SectionTitle>Movement pipeline</SectionTitle>
      <div className="ops-toolbar">
        <SearchInput value={q} onChange={setQ} placeholder="Search id, part or base…" />
        <Select
          value={status}
          onChange={setStatus}
          label="All statuses"
          options={['PENDING_APPROVAL', 'IN_TRANSIT', 'RECEIVED'].map(s => ({ value: s, label: s.replace(/_/g, ' ') }))}
        />
      </div>

      {rows.length === 0 ? (
        <div className="ops-card"><Empty>No transfers match these filters.</Empty></div>
      ) : (
        <Table
          rowKey="id"
          minWidth={980}
          rows={rows}
          columns={[
            { key: 'id', label: 'ID', render: t => <span className="font-mono">{t.id}</span> },
            { key: 'part_number', label: 'Part', render: t => <b>{t.part_number}</b> },
            { key: 'route', label: 'Route', render: t => baseName(t.source_base) + ' → ' + baseName(t.dest_base) },
            { key: 'quantity', label: 'Qty', align: 'right', render: t => <span className="ops-number">{quantityText(t.quantity)}</span> },
            { key: 'distance_km', label: 'Distance', align: 'right', render: t => <span className="ops-number">{distanceText(t.distance_km)}</span> },
            { key: 'eta_hours', label: 'ETA', align: 'right', render: t => <span className="ops-number">{etaText(t.eta_hours)}</span> },
            {
              key: 'for_aircraft', label: 'For',
              render: t => (t.for_aircraft
                ? <b style={{ color: '#d8a93d' }}>{t.for_aircraft}</b>
                : <span style={{ color: '#5d6675' }}>—</span>),
            },
            {
              key: 'status', label: 'Status',
              render: t => <Badge color={TONE[t.status] || '#8b94a3'}>{String(t.status).replace(/_/g, ' ')}</Badge>,
            },
            {
              key: 'action', label: 'Action', align: 'right',
              render: t => (
                <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                  {t.status === 'PENDING_APPROVAL' && (
                    <ActionButton small disabled={busy} onClick={() => act(() => api.approveTransfer(t.id), t.id + ' approved → IN TRANSIT')}>
                      Approve
                    </ActionButton>
                  )}
                  {t.status === 'IN_TRANSIT' && (
                    <ActionButton small primary disabled={busy} onClick={() => act(() => api.receiveTransfer(t.id), t.id + ' received')}>
                      Simulate arrival
                    </ActionButton>
                  )}
                  {t.status === 'RECEIVED' && <span style={{ fontSize: 11, color: '#3fb97f' }}>landed</span>}
                </div>
              ),
            },
          ]}
        />
      )}

      <SectionTitle>Aircraft unblocked by these movements</SectionTitle>
      {(() => {
        const inFlight = list.filter(t => t.status !== 'RECEIVED' && t.for_aircraft);
        if (!inFlight.length) {
          return <div className="ops-card"><Empty>No transfers are currently holding up a work order.</Empty></div>;
        }
        return (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))', gap: 12 }}>
            {inFlight.map(t => (
              <div key={t.id} className="ops-card" style={{ padding: 14, borderLeft: '4px solid #4f9cf0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <b>{t.for_aircraft}</b>
                  <Badge color={TONE[t.status]}>{String(t.status).replace(/_/g, ' ')}</Badge>
                </div>
                <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 6 }}>
                  Waiting on <b style={{ color: '#d8a93d' }}>{t.part_number}</b> from {baseName(t.source_base)}, ETA {etaText(t.eta_hours)}
                </div>
                <div style={{ fontSize: 12, marginTop: 6 }}>
                  Destination: {baseName(t.dest_base)} ·{' '}
                  {(aircraft || []).find(a => a.id === t.for_aircraft)?.status?.replace(/_/g, ' ') || '—'}
                </div>
              </div>
            ))}
          </div>
        );
      })()}
    </div>
  );
}
