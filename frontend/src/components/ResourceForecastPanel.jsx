import React from 'react';
import { api, baseName } from '../services/api.js';
import { ActionButton, DataError, Loading, SectionTitle } from './ui.jsx';

const isNumber = value => typeof value === 'number' && Number.isFinite(value);
const countText = value => isNumber(value) ? value.toLocaleString() : '—';
const demandText = value => isNumber(value) ? value.toFixed(2) : 'Unavailable';
export const DEFAULT_FORECAST_HORIZON = 60;
const QUICK_FORECAST_HORIZONS = [30, 60, 100];
const inputStyle = {
  width: 86, background: '#151b24', color: '#e6e9ee', border: '1px solid #2a3444',
  borderRadius: 6, padding: '5px 8px', fontSize: 12,
};

export function DemandStockChart({ componentRow }) {
  const stock = componentRow?.committed_available_for_transfer;
  const demand = componentRow?.expected_demand;
  const hasStock = isNumber(stock);
  const hasDemand = isNumber(demand);
  const scale = Math.max(hasStock ? stock : 0, hasDemand ? demand : 0, 1);
  const stockWidth = hasStock ? Math.max(0, Math.min(100, (stock / scale) * 100)) : 0;
  const demandWidth = hasDemand ? Math.max(0, Math.min(100, (demand / scale) * 100)) : 0;
  return (
    <div style={{ minWidth: 160 }}>
      <svg viewBox="0 0 100 28" role="img" aria-label={`${componentRow?.component || 'Component'}: transferable stock after existing work-order commitments ${countText(stock)} units; expected demand ${demandText(demand)} units over the forecast horizon`} style={{ display: 'block', width: '100%', height: 38 }}>
        <rect x="0" y="2" width="100" height="9" rx="3" fill="#0a0e13" stroke="#2a3444" />
        {hasStock && <rect x="0" y="2" width={stockWidth} height="9" rx="3" fill="#4f9cf0" />}
        <rect x="0" y="17" width="100" height="9" rx="3" fill="#0a0e13" stroke="#2a3444" />
        {hasDemand && <rect x="0" y="17" width={demandWidth} height="9" rx="3" fill="#d8a93d" />}
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 10, color: '#8b94a3' }}>
        <span>Uncommitted transferable stock {countText(stock)}</span><span>Expected demand {demandText(demand)}</span>
      </div>
    </div>
  );
}

export function ForecastEligibilityNotice({ forecast, horizonCycles }) {
  if (forecast?.forecast_status === 'no_eligible_predictions') {
    const unavailable = isNumber(forecast.unavailable_prediction_count) ? forecast.unavailable_prediction_count : null;
    const outside = isNumber(forecast.outside_horizon_prediction_count) ? forecast.outside_horizon_prediction_count : null;
    const suggested = isNumber(forecast.suggested_horizon_cycles)
      && forecast.suggested_horizon_cycles > Number(horizonCycles)
      ? forecast.suggested_horizon_cycles
      : null;
    return (
      <div role="status" style={{ color: '#8b94a3', fontSize: 13, marginBottom: 10 }}>
        No eligible cycle predictions overlap this horizon.
        {unavailable != null ? ` ${unavailable} predictions unavailable because provider or uncertainty fields are missing.` : ''}
        {outside != null ? ` ${outside} valid predictions fall outside the selected horizon.` : ''}
        {suggested != null ? ` Try ${suggested} cycles; the backend found eligible predictions at that horizon.` : ''}
      </div>
    );
  }
  if (forecast?.forecast_status !== 'available') {
    return <div role="status" style={{ color: '#8b94a3', fontSize: 13 }}>Forecast status unavailable; demand is not treated as zero.</div>;
  }
  return null;
}

export function ForecastHorizonControls({ horizon, onHorizonChange, disabled = false }) {
  return (
    <>
      <label htmlFor="resource-forecast-horizon" style={{ color: '#8b94a3', fontSize: 11 }}>Horizon · cycles</label>
      <input
        id="resource-forecast-horizon"
        aria-label="Forecast horizon in cycles"
        type="number"
        min="1"
        step="1"
        value={horizon}
        onChange={event => onHorizonChange(event.target.value)}
        style={inputStyle}
      />
      <div role="group" aria-label="Quick-select forecast horizon" style={{ display: 'flex', gap: 4 }}>
        {QUICK_FORECAST_HORIZONS.map(cycles => (
          <button
            key={cycles}
            type="button"
            aria-label={`${cycles} cycles`}
            aria-pressed={Number(horizon) === cycles}
            disabled={disabled}
            onClick={() => onHorizonChange(String(cycles))}
            style={{
              background: Number(horizon) === cycles ? '#3a3020' : '#151b24',
              color: Number(horizon) === cycles ? '#f0c35a' : '#c6ccd6',
              border: '1px solid #2a3444', borderRadius: 6, padding: '5px 7px',
              cursor: disabled ? 'not-allowed' : 'pointer', fontSize: 10,
            }}
          >{cycles}</button>
        ))}
      </div>
    </>
  );
}

export function SuggestedMoveRow({ move, row, canRequestMove, busy = false, pending = false, onRequest }) {
  const validQuantity = Number.isInteger(move?.quantity) && move.quantity > 0;
  const feasible = move?.feasible === true && validQuantity;
  const disabled = !canRequestMove || !feasible || busy;
  const key = `${row.base_id}:${row.component}:${move?.source_base}:${move?.destination_base}`;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 8, borderTop: '1px solid #2a3444', paddingTop: 6, fontSize: 11 }}>
      <span>{baseName(move?.source_base)} → {baseName(move?.destination_base)} · {validQuantity ? `${move.quantity} unit${move.quantity === 1 ? '' : 's'}` : 'quantity unavailable'} · ETA {isNumber(move?.eta_hours) ? `${move.eta_hours}h` : '—'}{isNumber(move?.condition_pct) ? ` · condition ${move.condition_pct}%` : ''}</span>
      <button
        type="button"
        disabled={disabled}
        title={!canRequestMove ? 'Transfer requests are available in the Logistics demo role.' : !feasible ? 'This move is not marked feasible by the backend.' : undefined}
        onClick={() => onRequest?.(move, row)}
        style={{ background: '#1c2431', border: '1px solid #2a3444', color: canRequestMove && feasible ? '#e6e9ee' : '#8b94a3', borderRadius: 6, padding: '4px 9px', cursor: !disabled ? 'pointer' : 'not-allowed', fontSize: 11, opacity: !disabled ? 1 : 0.65 }}
      >
        {pending ? 'Creating…' : canRequestMove ? 'Create transfer' : 'Logistics role required'}
      </button>
    </div>
  );
}

export default function ResourceForecastPanel({ canRequestMove = false, refreshKey = 0, onRefresh }) {
  const [horizon, setHorizon] = React.useState(String(DEFAULT_FORECAST_HORIZON));
  const [forecast, setForecast] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [busyMove, setBusyMove] = React.useState(null);
  const [message, setMessage] = React.useState('');
  const [messageError, setMessageError] = React.useState(false);
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    let active = true;
    const cycles = Number(horizon);
    if (!Number.isInteger(cycles) || cycles < 1) {
      setLoading(false);
      setForecast(null);
      setError(new Error('Forecast horizon must be a positive whole number of cycles.'));
      return () => { active = false; };
    }
    setLoading(true);
    setForecast(null);
    setError(null);
    api.getResourceForecast(cycles)
      .then(result => { if (active) setForecast(result); })
      .catch(err => { if (active) { setForecast(null); setError(err); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [horizon, refreshKey, attempt]);

  const requestMove = async (move, row) => {
    const quantity = move?.quantity;
    if (!canRequestMove || move?.feasible !== true || !Number.isInteger(quantity) || quantity < 1) return;
    const key = `${row.base_id}:${row.component}:${move.source_base}:${move.destination_base}`;
    setBusyMove(key);
    setMessageError(false);
    setMessage('Submitting transfer request…');
    try {
      const transfer = await api.createTransfer({
        part_number: row.component,
        source_base: move.source_base,
        dest_base: move.destination_base,
        quantity,
      });
      setMessage(`Transfer ${transfer.id} requested: ${transfer.part_number} ${baseName(transfer.source_base)} → ${baseName(transfer.dest_base)} · ${transfer.status}.`);
      if (onRefresh) onRefresh();
      else setAttempt(value => value + 1);
    } catch (err) {
      setMessageError(true);
      setMessage(err?.message || 'Transfer request failed.');
    } finally {
      setBusyMove(null);
    }
  };

  const rows = (forecast?.bases || []).flatMap(base => (base.components || []).map(component => ({
    ...component,
    base_id: base.base_id,
    base_name: base.base_name,
  })));
  const assumptions = Array.isArray(forecast?.assumptions) ? forecast.assumptions : [];

  return (
    <section style={{ margin: '18px 0' }} aria-label="Cycle-based component demand forecast">
      <SectionTitle right={<div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 7 }}>
        <ForecastHorizonControls horizon={horizon} onHorizonChange={setHorizon} disabled={loading} />
        <ActionButton small disabled={loading || !Number.isInteger(Number(horizon)) || Number(horizon) < 1} onClick={() => setAttempt(value => value + 1)}>{loading ? 'Loading…' : 'Refresh'}</ActionButton>
      </div>}>
        Component demand forecast
      </SectionTitle>
      <div className="ops-card" style={{ padding: 14 }}>
            <div style={{ fontSize: 12, color: '#8b94a3', marginBottom: 10 }}>
          Cycle-based demand uses an assumed demo engine-to-component mapping. The normal-approximation method is indicative and uncalibrated; it is not a component diagnosis or failure probability.
        </div>
        {loading && !forecast ? <Loading>Loading cycle-based demand forecast…</Loading> : null}
        {error ? <DataError error={error}>Forecast unavailable. No fallback demand values are shown.</DataError> : null}
        {forecast && (
          <>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', fontSize: 11, color: '#8b94a3', marginBottom: 10 }}>
              <span>{forecast.horizon_cycles ?? '—'}-cycle horizon</span>
              <span>· {forecast.provider || 'Provider unavailable'}{forecast.model_version ? ` · ${forecast.model_version}` : ''}</span>
              <span>· {forecast.eligible_prediction_count ?? '—'} eligible</span>
              <span>· {forecast.unavailable_prediction_count ?? '—'} unavailable</span>
              <span>· {forecast.outside_horizon_prediction_count ?? '—'} outside horizon</span>
              <span>· {forecast.unmapped_prediction_count ?? '—'} unmapped</span>
              <span>· {forecast.excluded_open_work_order_count ?? '—'} excluded by active work orders</span>
              {forecast.mutated_state === false ? <span>· Read-only forecast</span> : <span style={{ color: '#e05c5c' }}>· Read-only status not confirmed</span>}
            </div>
            <details style={{ fontSize: 11, color: '#8b94a3', marginBottom: 10 }}>
              <summary style={{ cursor: 'pointer', color: '#d8a93d' }}>{forecast.mapping?.label || 'Assumed engine-to-component mapping'} · forecast assumptions</summary>
              {forecast.mapping?.source ? <div style={{ marginTop: 6 }}>Mapping source: {forecast.mapping.source}</div> : null}
              {forecast.mapping?.engine_to_component && Object.keys(forecast.mapping.engine_to_component).length > 0 ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 5 }}>
                  {Object.entries(forecast.mapping.engine_to_component).map(([engine, component]) => <span key={engine}>Engine {engine} → {component}</span>)}
                </div>
              ) : null}
              {forecast.demand_method ? <div style={{ marginTop: 6 }}>Method: {forecast.demand_method}</div> : null}
              {assumptions.length ? <ul style={{ margin: '5px 0 0', paddingLeft: 18 }}>{assumptions.map((item, index) => <li key={index}>{item}</li>)}</ul> : null}
            </details>
            <ForecastEligibilityNotice forecast={forecast} horizonCycles={horizon} />
            {rows.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                {rows.map((row, index) => {
                  const moves = row.demand_status === 'available' && Array.isArray(row.suggested_moves) ? row.suggested_moves : [];
                  return (
                    <div key={`${row.base_id}:${row.component}:${index}`} className="ops-card" style={{ padding: 10, borderColor: '#2a3444' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
                        <div style={{ flex: '1 1 120px', fontSize: 12 }}>
                          <b>{row.component || 'Component unavailable'}</b>{row.part_name ? <div style={{ color: '#8b94a3', fontSize: 10 }}>{row.part_name}</div> : null}
                          <div style={{ color: '#8b94a3', marginTop: 3 }}>{row.base_name || baseName(row.base_id)}</div>
                          <div style={{ color: '#8b94a3', fontSize: 10, marginTop: 3 }}>{countText(row.eligible_aircraft_count)} eligible · {countText(row.unavailable_aircraft_count)} unavailable · {countText(row.outside_horizon_aircraft_count)} outside horizon</div>
                        </div>
                        <div style={{ flex: '2 1 180px' }}><DemandStockChart componentRow={row} /></div>
                        <div style={{ flex: '1 1 130px', fontSize: 11, color: '#8b94a3' }}>
                          <div>On hand {countText(row.on_hand)} · reserved {countText(row.reserved)}</div>
                          <div>Minimum reserve {countText(row.minimum_reserve)}</div>
                          <div>Unbound inbound {countText(row.inbound_pending_or_in_transit)} · only this offsets forecast shortfall</div>
                          {isNumber(row.inbound_work_order_committed) && row.inbound_work_order_committed > 0 ? <div>WO-committed inbound {countText(row.inbound_work_order_committed)} · dedicated</div> : null}
                          {isNumber(row.inbound_proposed_for_open_work_orders) && row.inbound_proposed_for_open_work_orders > 0 ? <div>Proposed for open WOs {countText(row.inbound_proposed_for_open_work_orders)} · dedicated</div> : null}
                          <div style={{ color: isNumber(row.projected_shortfall) && row.projected_shortfall > 0 ? '#d8a93d' : '#8b94a3', marginTop: 3 }}>
                            {isNumber(row.projected_shortfall) ? `Whole units needed (rounded up): ${row.projected_shortfall}` : 'Shortfall unavailable'}
                          </div>
                        </div>
                      </div>
                      {moves.length > 0 && <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 5 }}>
                        {moves.map((move, moveIndex) => {
                          const key = `${row.base_id}:${row.component}:${move.source_base}:${move.destination_base}`;
                          return <SuggestedMoveRow key={`${key}:${moveIndex}`} move={move} row={row} canRequestMove={canRequestMove} busy={Boolean(busyMove)} pending={busyMove === key} onRequest={requestMove} />;
                        })}
                      </div>}
                    </div>
                  );
                })}
              </div>
            )}
            {!rows.length && forecast.forecast_status === 'available' ? <div style={{ color: '#8b94a3', fontSize: 13 }}>No component demand rows were returned for this horizon.</div> : null}
          </>
        )}
        {message ? <div role="status" style={{ color: messageError ? '#e05c5c' : '#d8a93d', fontSize: 12, marginTop: 10 }}>{message}</div> : null}
      </div>
    </section>
  );
}
