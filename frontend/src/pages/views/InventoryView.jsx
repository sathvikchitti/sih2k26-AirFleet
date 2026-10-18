import React from 'react';
import { api, baseName, titleCase } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  ActionButton, Badge, DataError, KpiCard, Loading, PageHeader, SearchInput, SectionTitle, Select,
  Table,
} from '../../components/ui.jsx';

const isNumericValue = value => value != null && value !== '' && Number.isFinite(Number(value));

const numberText = value => !isNumericValue(value)
  ? '—' : Number(value).toLocaleString();

const transferableTone = value => {
  if (!isNumericValue(value)) return '#8b94a3';
  if (Number(value) <= 0) return '#e05c5c';
  if (Number(value) === 1) return '#d8a93d';
  return '#3fb97f';
};

// Logistics — Inventory: every stock line across every base, grouped by base
// so a logistics officer can see where the depth actually is.
export default function InventoryView({ refreshKey }) {
  const { inventory, bases, parts, aircraft, transfers, loading } = useFleetViews(refreshKey);
  const [q, setQ] = React.useState('');
  const [base, setBase] = React.useState('');
  const [status, setStatus] = React.useState('');

  if (loading) return <Loading>Loading inventory…</Loading>;

  const minOf = (pn) => (parts || []).find(p => p.part_number === pn)?.min_condition_pct;
  const nameOf = (pn) => (parts || []).find(p => p.part_number === pn)?.name || '—';
  const demandFor = (pn) => (aircraft || []).filter(a => (a.health?.required_component || a.required_component) === pn).length;
  const inboundTransit = (partNumber, baseId) => {
    if (!Array.isArray(transfers)) return null;
    const matching = (transfers || [])
      .filter(t => t.status === 'IN_TRANSIT' && t.part_number === partNumber && t.dest_base === baseId);
    if (!matching.length) return 0;
    if (!matching.every(t => isNumericValue(t.quantity))) return null;
    return matching.reduce((sum, transfer) => sum + Number(transfer.quantity), 0);
  };

  const inventoryRows = Array.isArray(inventory) ? inventory : [];
  let rows = inventoryRows;
  if (q) {
    const needle = q.toLowerCase();
    rows = rows.filter(i => i.part_number.toLowerCase().includes(needle) || nameOf(i.part_number).toLowerCase().includes(needle));
  }
  if (base) rows = rows.filter(i => i.base_id === base);
  if (status) rows = rows.filter(i => i.status === status);

  const stockouts = inventoryRows.filter(i => i.status === 'STOCKOUT');
  const low = inventoryRows.filter(i => i.status === 'LOW_STOCK');
  const totalUnits = Array.isArray(inventory) && inventoryRows.every(i => isNumericValue(i.quantity))
    ? inventoryRows.reduce((s, i) => s + Number(i.quantity), 0) : null;
  const reservedUnits = Array.isArray(inventory) && inventoryRows.every(i => isNumericValue(i.reserved))
    ? inventoryRows.reduce((s, i) => s + Number(i.reserved), 0) : null;
  const transferableUnits = Array.isArray(inventory) && inventoryRows.every(i => isNumericValue(i.available_for_transfer))
    ? inventoryRows.reduce((s, i) => s + Number(i.available_for_transfer), 0) : null;
  const inTransitRows = Array.isArray(transfers) ? transfers.filter(t => t.status === 'IN_TRANSIT') : null;
  const inTransitUnits = inTransitRows && inTransitRows.every(t => isNumericValue(t.quantity))
    ? inTransitRows.reduce((sum, t) => sum + Number(t.quantity), 0) : null;
  const unserviceable = inventoryRows.filter(i => i.quantity > 0 && minOf(i.part_number) != null
    && isNumericValue(i.condition_pct) && Number(i.condition_pct) < Number(minOf(i.part_number)));

  return (
    <div>
      <PageHeader
        title="Inventory"
        subtitle="Physical stock at every base. Logistics owns this data — aircraft health is never edited here, it is only read to know what is in demand."
      />

      <div className="ops-kpi-grid ops-inventory-kpis">
        <KpiCard label="On Hand" value={numberText(totalUnits)} />
        <KpiCard label="Reserved" value={numberText(reservedUnits)} />
        <KpiCard label="Free after reserve" value={numberText(transferableUnits)} />
        <KpiCard label="In Transit" value={numberText(inTransitUnits)} accent="#4f9cf0" />
      </div>
      <div className="ops-inventory-summary" aria-label="Inventory counts and interpretation">
        <span><b>Stock lines</b> {numberText(Array.isArray(inventory) ? inventory.length : null)}</span>
        <span><b>Stockouts</b> {numberText(Array.isArray(inventory) ? stockouts.length : null)}</span>
        <span><b>Low stock</b> {numberText(Array.isArray(inventory) ? low.length : null)}</span>
        <span><b>Below min condition</b> {numberText(Array.isArray(inventory) ? unserviceable.length : null)} known lines</span>
        <span className="ops-inventory-note">Free after reserve uses backend availability; condition is shown separately. In-transit units are not on-hand stock.</span>
      </div>

      <div className="ops-toolbar">
        <SearchInput value={q} onChange={setQ} placeholder="Search part number or name…" />
        <Select
          value={base}
          onChange={setBase}
          label="All bases"
          options={(bases || []).map(b => ({ value: b.id, label: b.name }))}
        />
        <Select
          value={status}
          onChange={setStatus}
          label="All statuses"
          options={['AVAILABLE', 'LOW_STOCK', 'STOCKOUT'].map(s => ({ value: s, label: s.replace(/_/g, ' ') }))}
        />
      </div>

      <AllocationPreview refreshKey={refreshKey} />

      <Table
        rowKey="id"
        minWidth={1120}
        rows={rows}
        empty={Array.isArray(inventory) ? 'No stock lines match these filters.' : 'Inventory records are unavailable.'}
        columns={[
          { key: 'part_number', label: 'Part', render: i => <b>{i.part_number}</b> },
          { key: 'name', label: 'Name', render: i => <span style={{ color: '#8b94a3' }}>{nameOf(i.part_number)}</span> },
          { key: 'base_id', label: 'Base', render: i => baseName(i.base_id) },
          { key: 'quantity', label: 'On hand', align: 'right', render: i => <b className="ops-number">{numberText(i.quantity)}</b> },
          { key: 'reserved', label: 'Reserved', align: 'right', render: i => <span className="ops-number">{numberText(i.reserved)}</span> },
          { key: 'minimum_reserve', label: 'Min reserve', align: 'right', render: i => <span className="ops-number">{numberText(i.minimum_reserve)}</span> },
          { key: 'in_transit', label: 'Inbound transit', align: 'right', render: i => <span className="ops-number">{numberText(inboundTransit(i.part_number, i.base_id))}</span> },
          {
            key: 'available_for_transfer', label: 'Free after reserve', align: 'right',
            render: i => <b className="ops-number" style={{ color: transferableTone(i.available_for_transfer) }}>{numberText(i.available_for_transfer)}</b>,
          },
          {
            key: 'condition_pct', label: 'Condition', align: 'right',
            render: i => {
              const min = minOf(i.part_number);
              const belowMinimum = i.quantity > 0 && min != null && isNumericValue(i.condition_pct)
                && Number(i.condition_pct) < Number(min);
              return (
                <span style={{ color: i.quantity === 0 ? '#5d6675' : belowMinimum ? '#e05c5c' : '#c6ccd6' }}>
                  {i.quantity === 0 ? '—' : `${numberText(i.condition_pct)}%`}
                  {i.quantity > 0 && min != null && !isNumericValue(i.condition_pct) ? <span className="ops-condition-note"> · min {min}% · unavailable</span> : null}
                  {i.quantity > 0 && min != null && isNumericValue(i.condition_pct) ? <span className="ops-condition-note">{belowMinimum ? ` · below min ${min}% · unusable` : ` · min ${min}%`}</span> : null}
                </span>
              );
            },
          },
          {
            key: 'demand', label: 'Fleet Demand', align: 'right',
            render: i => {
              const d = demandFor(i.part_number);
              return <span className="ops-number" style={{ color: d ? '#d8a93d' : '#5d6675' }}>{numberText(d)}</span>;
            },
          },
          {
            key: 'status', label: 'Status',
            render: i => (
              <Badge color={i.status === 'STOCKOUT' ? '#e05c5c' : i.status === 'LOW_STOCK' ? '#d8a93d' : '#3fb97f'}>
                {String(i.status).replace(/_/g, ' ')}
              </Badge>
            ),
          },
        ]}
      />

      {stockouts.length > 0 && (
        <>
          <SectionTitle>Stockouts</SectionTitle>
          <div className="ops-card" style={{ padding: 14, borderLeft: '4px solid #e05c5c' }}>
            {stockouts.map(i => (
              <div key={i.id} style={{ fontSize: 13, marginBottom: 4 }}>
                <b style={{ color: '#d8a93d' }}>{i.part_number}</b> at {baseName(i.base_id)} — none on hand
                {demandFor(i.part_number) ? ` · ${demandFor(i.part_number)} aircraft in the fleet need it` : ''}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function ArrivalConstraintNotice({ row }) {
  if (row?.can_start_on_arrival !== false) return null;
  const reason = row.arrival_block_reason ? titleCase(row.arrival_block_reason) : null;
  return (
    <div role="note" style={{ width: '100%', color: '#d8a93d', fontSize: 11 }}>
      Arrival does not make this work order startable under current constraints{reason ? `: ${reason}` : '.'}
    </div>
  );
}

function AllocationPreview({ refreshKey }) {
  const [preview, setPreview] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    api.getAllocationPreview()
      .then(result => { if (active) setPreview(result); })
      .catch(err => { if (active) setError(err); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refreshKey, attempt]);

  const reload = () => setAttempt(value => value + 1);
  const allocations = preview?.allocations || [];
  const effects = (preview?.inventory_effects || []).filter(row => row.planned_units_claimed || row.overallocated_units);
  const statusColor = status => status?.startsWith('PROPOSED_') ? '#d8a93d'
    : status?.includes('NO_FEASIBLE') || status?.includes('UNAVAILABLE') || status?.includes('NOT_AVAILABLE') ? '#e05c5c'
      : status?.startsWith('EXISTING_') || status?.startsWith('RECEIVED_') || status?.startsWith('IN_PROGRESS_') ? '#4f9cf0' : '#8b94a3';

  return (
    <section style={{ margin: '18px 0' }} aria-label="Shared stock allocation preview">
      <SectionTitle right={<ActionButton small disabled={loading} onClick={reload}>{loading ? 'Refreshing…' : 'Refresh preview'}</ActionButton>}>
        Shared stock allocation preview
      </SectionTitle>
      <div className="ops-card" style={{ padding: 14 }}>
        <div style={{ color: '#8b94a3', fontSize: 12, marginBottom: 10 }}>
          Read-only snapshot across open work orders. Proposed assignments are tentative; live stock and transfer checks remain authoritative when an action is approved.
        </div>
        {loading && !preview ? <Loading>Calculating shared allocation…</Loading> : null}
        {error ? <DataError error={error}>Allocation preview unavailable. Inventory actions remain governed by the live backend.</DataError> : null}
        {preview && (
          <>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10, fontSize: 11, color: '#8b94a3' }}>
              <Badge color="#4f9cf0">READ-ONLY SNAPSHOT</Badge>
              <span>{allocations.length} open work orders</span>
              <span>{(preview.conflicts || []).length} conflicts</span>
              {preview.mutated_state === false ? <span>No state changed</span> : <span style={{ color: '#e05c5c' }}>Mutation status not confirmed</span>}
            </div>
            {allocations.length === 0 ? <div style={{ color: '#8b94a3', fontSize: 13 }}>No open work orders to allocate.</div> : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {allocations.map(row => {
                  const status = row.allocation_status || 'STATUS_UNAVAILABLE';
                  const candidate = row.recommended;
                  const source = row.source_base || candidate?.source_base || candidate?.donor_base;
                  const existing = row.existing_transfer;
                  const reason = row.rejected?.[0]?.reason || row.rejected?.[0]?.detail;
                  return (
                    <div key={row.work_order_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '8px 10px', border: '1px solid #2a3444', borderRadius: 7 }}>
                      <div style={{ fontSize: 12 }}>
                        <b>{row.work_order_id}</b> · {row.aircraft_id} · {row.required_component || 'no component selected'} · {baseName(row.destination_base)}
                        {source && source !== row.destination_base ? <> ← {baseName(source)}</> : null}
                        {row.transfer_id ? <> · {row.transfer_id}</> : null}
                        {row.expected_downtime_hours != null ? <> · {row.expected_downtime_hours}h expected downtime estimate</> : null}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Badge color={statusColor(status)}>{titleCase(status)}</Badge>
                        {existing ? <span style={{ color: '#8b94a3', fontSize: 11 }}>Existing commitment</span> : status.startsWith('PROPOSED_') ? <span style={{ color: '#d8a93d', fontSize: 11 }}>Tentative</span> : null}
                      </div>
                      {reason ? <div style={{ width: '100%', color: '#e05c5c', fontSize: 11 }}>{reason}</div> : null}
                      <ArrivalConstraintNotice row={row} />
                    </div>
                  );
                })}
              </div>
            )}
            {effects.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div className="ops-label" style={{ marginBottom: 6 }}>Virtual stock effects · preview only</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {effects.map((effect, index) => (
                    <div key={`${effect.base_id}-${effect.part_number}-${index}`} style={{ fontSize: 11, color: effect.overallocated_units ? '#e05c5c' : '#8b94a3' }}>
                      {baseName(effect.base_id)} · {effect.part_number}: {effect.planned_units_claimed} planned claim(s), {effect.virtual_available_for_transfer_after_plan} transferable after plan
                      {effect.overallocated_units ? ` · ${effect.overallocated_units} overallocated` : ''}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {(preview.conflicts || []).length > 0 && (
              <div style={{ marginTop: 10, color: '#e05c5c', fontSize: 11 }}>
                Conflicts: {preview.conflicts.map((conflict, index) => `${conflict.work_order_id || conflict.transfer_id || 'Stock'} — ${titleCase(conflict.reason || 'unknown')}`).join('; ')}
              </div>
            )}
            {(preview.assumptions || []).length > 0 && (
              <details className="ops-preview-assumptions">
                <summary>Preview assumptions ({preview.assumptions.length})</summary>
                <div>{preview.assumptions.join('; ')}</div>
              </details>
            )}
          </>
        )}
      </div>
    </section>
  );
}
