import React from 'react';
import { api, rulText, titleCase } from '../services/api.js';
import { ActionButton, Badge, DataError, SectionTitle } from './ui.jsx';
import { C } from '../theme.js';

const timeLabel = value => {
  if (!value) return 'Time unavailable';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString();
};

function recordTitle(row) {
  const record = row.record || row;
  if (row.record_type === 'audit') return titleCase(record.event_type || 'Audit record');
  if (row.record_type === 'work_order') return `Work order · current status ${titleCase(record.status || 'unknown')}`;
  if (row.record_type === 'transfer') return `Transfer · current status ${titleCase(record.status || 'unknown')}`;
  if (row.record_type === 'prediction_history') return `Prediction history · ${record.model_version || record.history_source || 'model provenance unavailable'} · ${record.risk_level || 'risk unavailable'} · RUL ${rulText(record)}`;
  if (row.record_type === 'event') return `Predicted event · current status ${titleCase(record.status || 'unknown')}`;
  return titleCase(row.record_type || 'Record');
}

export default function MaintenanceCasePanel({ aircraftId, baseId, role, homeBase, refreshKey, refresh }) {
  const [timeline, setTimeline] = React.useState(null);
  const [parts, setParts] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [partsError, setPartsError] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [busyEvent, setBusyEvent] = React.useState(null);
  const [selectedPart, setSelectedPart] = React.useState('');
  const [message, setMessage] = React.useState('');
  const [retry, setRetry] = React.useState(0);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    Promise.allSettled([api.getMaintenanceTimeline(aircraftId), api.getPartsLive()])
      .then(([timelineResult, partsResult]) => {
        if (!active) return;
        if (timelineResult.status === 'fulfilled') {
          setTimeline(timelineResult.value);
          setError(null);
        } else setError(timelineResult.reason);
        if (partsResult.status === 'fulfilled') {
          setParts(partsResult.value || []);
          setPartsError(null);
        } else setPartsError(partsResult.reason);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [aircraftId, refreshKey, retry]);

  const openEvents = (timeline?.events || []).filter(event => event.status === 'OPEN' && !event.work_order_id);
  const canTriage = role === 'base' && homeBase === baseId;
  const createWorkOrder = async event => {
    if (!selectedPart) { setMessage('Select a catalogue component before creating a work order.'); return; }
    setBusyEvent(event.id);
    setMessage('Saving human triage…');
    try {
      await api.createWorkOrderFromEvent(event.id, selectedPart);
      setMessage(`Work order created from ${event.id}. Component ${selectedPart} was selected by the operator, not predicted by the model.`);
      setRetry(value => value + 1);
      refresh();
    } catch (err) {
      setMessage(err?.message || 'Triage failed. No work order was created.');
    } finally {
      setBusyEvent(null);
    }
  };

  return (
    <section style={{ marginTop: 18 }} aria-label="Aircraft maintenance case">
      <SectionTitle right={<ActionButton small disabled={loading} onClick={() => setRetry(value => value + 1)}>{loading ? 'Loading…' : 'Refresh case'}</ActionButton>}>
        Maintenance case · traceable records
      </SectionTitle>
      {error && !timeline ? <DataError error={error}>Maintenance case timeline unavailable.</DataError> : null}
      {loading && !timeline && !error ? <div role="status" style={{ color: C.muted, fontSize: 13, padding: 10 }}>Loading linked maintenance records…</div> : null}
      {loading && timeline ? <div role="status" style={{ color: C.muted, fontSize: 11, padding: '0 2px 8px' }}>Refreshing the timeline; the last successful snapshot remains visible until it finishes.</div> : null}
      {error && timeline ? (
        <div role="alert" style={{ color: C.warn, fontSize: 12, padding: '9px 11px', marginBottom: 10, border: `1px solid ${C.warn}55`, borderRadius: 2 }}>
          Timeline refresh failed. Showing the last successfully loaded records; their snapshot time is not available. {error.message || 'Check the connection and retry.'}
          <span style={{ marginLeft: 8 }}><ActionButton small disabled={loading} onClick={() => setRetry(value => value + 1)}>Retry</ActionButton></span>
        </div>
      ) : null}
      {timeline && (
        <div className="ops-card" style={{ padding: 14 }}>
          <div style={{ fontSize: 11, color: C.muted, marginBottom: 10 }}>
            Linked by stored record IDs only. {timeline.linkage?.method || 'No inferred time-based links.'}
            {timeline.mutated_state === false ? ' This view is read-only.' : ''}
            {timeline.linkage?.unlinked_event_ids?.length ? ` Unlinked legacy events: ${timeline.linkage.unlinked_event_ids.join(', ')}.` : ''}
          </div>
          {openEvents.length > 0 && (
            <div style={{ padding: 11, border: `1px solid ${C.warn}55`, borderRadius: 2, marginBottom: 12 }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}>Open predicted event · explicit human triage</div>
              <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>
                The event is a model signal. Component selection below is an operator decision and will be recorded as such.
              </div>
              {openEvents.map(event => (
                <div key={event.id} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 9, paddingTop: 8, borderTop: `1px solid ${C.line}` }}>
                  <div style={{ minWidth: 160, fontSize: 12 }}><b>{event.id}</b> · {event.risk_level || 'risk unavailable'} · RUL {rulText(event)}</div>
                  {canTriage ? (
                    <>
                      <label htmlFor={`component-${event.id}`} style={{ color: C.muted, fontSize: 11 }}>Human-selected component</label>
                      <select id={`component-${event.id}`} value={selectedPart} onChange={e => setSelectedPart(e.target.value)} style={{ background: C.deck, border: `1px solid ${C.line}`, borderRadius: 2, padding: '7px 9px', color: C.text }}>
                        <option value="">Choose catalogue part…</option>
                        {(parts || []).map(part => <option key={part.part_number} value={part.part_number}>{part.part_number} · {part.name}</option>)}
                      </select>
                      <ActionButton primary small disabled={Boolean(busyEvent) || !parts?.length || Boolean(partsError) || loading || Boolean(error)} onClick={() => createWorkOrder(event)}>{busyEvent === event.id ? 'Saving…' : 'Create work order'}</ActionButton>
                    </>
                  ) : <Badge color={C.muted}>Base Manager at {titleCase(baseId)} triages this event</Badge>}
                </div>
              ))}
              {partsError ? <div style={{ color: C.crit, fontSize: 11, marginTop: 6 }}>Part catalogue unavailable; triage is disabled. {partsError.message}</div> : null}
            </div>
          )}
          {message ? <div role="status" style={{ color: message.includes('failed') || message.includes('Select') ? C.crit : C.warn, fontSize: 11, margin: '0 0 8px' }}>{message}</div> : null}
          {timeline.work_orders?.length > 0 && <div style={{ fontSize: 11, color: C.muted, marginBottom: 8 }}>{timeline.work_orders.length} linked work order(s) · recommendation snapshots {timeline.recommendations?.length || 0} · approval/rejection decisions {timeline.decisions?.length || 0} · transfers {timeline.transfers?.length || 0}</div>}
          {(timeline.timeline || []).length === 0 ? <div style={{ color: C.muted, fontSize: 12 }}>No stored maintenance records are linked to this aircraft yet.</div> : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {[...timeline.timeline].reverse().map((row, index) => {
                const record = row.record || row;
                const unlinked = row.link_status === 'unlinked' || row.link_status === 'aircraft_scoped';
                const candidate = record.details?.recommended_candidate || record.recommended_candidate;
                const selectedComponent = ['human_selected', 'fixture_scenario'].includes(record.component_source)
                  ? ` · ${record.component_source === 'human_selected' ? 'human-selected component' : 'scenario component'} (not ML output)` : '';
                const summary = record.event_type
                  ? `${record.summary || record.description || ''}${record.details?.work_order_id ? ` · WO ${record.details.work_order_id}` : ''}${record.details?.transfer_id ? ` · Transfer ${record.details.transfer_id}` : ''}${candidate ? ` · recorded recommendation ${candidate.source_base || '—'} → ${candidate.destination_base || '—'} · ${candidate.part_number || '—'} · ETA ${candidate.eta_hours ?? '—'}h` : ''}`
                  : record.prediction_history_origin_status === 'legacy_unknown'
                    ? `Original prediction-history link is unknown; later observations are linked only by stored IDs.${record.required_component ? ` Component ${record.required_component}${selectedComponent}.` : ''}`
                    : `${record.predicted_issue || record.issue || record.required_component || record.component || ''}${record.required_component ? selectedComponent : ''}`;
                return (
                  <div key={`${row.record_type}-${row.record_id}-${index}`} style={{ padding: '8px 0', borderTop: `1px solid ${C.line}`, display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                    <div style={{ minWidth: 130, color: C.muted, fontSize: 10 }}>{timeLabel(row.occurred_at)}</div>
                    <div style={{ flex: 1, fontSize: 12 }}>
                      <b>{recordTitle(row)}</b>
                      {(row.record_id || record.actor) ? <div style={{ color: C.dim, fontSize: 10, marginTop: 2 }}>
                        {row.record_id ? <code title={row.record_id} style={{ overflowWrap: 'anywhere', fontSize: 10 }}>{row.record_id}</code> : null}
                        {row.record_id && record.actor ? ' · ' : null}{record.actor ? `Actor: ${record.actor}` : null}
                      </div> : null}
                      {summary ? <div style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{summary}</div> : null}
                      {row.time_semantics ? <div style={{ color: C.dim, fontSize: 10, marginTop: 2 }}>{row.time_semantics}</div> : null}
                    </div>
                    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                      <Badge color={unlinked ? C.warn : C.info}>{unlinked ? 'UNLINKED' : titleCase(row.record_type)}</Badge>
                      {record.status ? <Badge color={C.muted}>CURRENT {titleCase(record.status)}</Badge> : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
