import React from 'react';
import { baseName } from '../services/api.js';

const ROLES = [
  { id: 'commander', title: 'Commander', desc: 'Fleet-wide readiness and decision support', icon: '◆' },
  { id: 'base', title: 'Base Manager', desc: 'Base-level aircraft readiness', icon: '▲' },
  { id: 'logistics', title: 'Logistics Officer', desc: 'Inventory and resource management', icon: '●' },
];

export default function RoleSelect({ onSelect }) {
  const [base, setBase] = React.useState('alpha');
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, background: 'radial-gradient(1000px 500px at 50% -10%, #1a2332 0%, #0d1117 60%)' }}>
      <div style={{ maxWidth: 760, width: '100%' }}>
        <div className="ops-label" style={{ textAlign: 'center' }}>POC Demo Environment · Demo Role Selection</div>
        <h1 style={{ textAlign: 'center', fontSize: 34, fontWeight: 800, margin: '8px 0 4px', letterSpacing: '-0.02em' }}>
          Aircraft Fleet Readiness<br />& Sustainment Platform
        </h1>
        <p style={{ textAlign: 'center', color: '#8b94a3', fontSize: 14, marginBottom: 6 }}>
          Predict → Prepare → Optimize → Recover
        </p>
        <p style={{ textAlign: 'center', color: '#5d6675', fontSize: 12, marginBottom: 26 }}>
          ML predictions drive fleet-level operational decisions that maximize aircraft availability. Selected roles are demo permissions, not authenticated accounts.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(210px,1fr))', gap: 14 }}>
          {ROLES.map(r => (
            <button key={r.id} onClick={() => onSelect(r.id, base)}
              style={{ textAlign: 'left', background: '#151b24', border: '1px solid #2a3444', borderRadius: 12, padding: 20, cursor: 'pointer', color: '#e6e9ee' }}
              onMouseOver={e => e.currentTarget.style.borderColor = '#d8a93d'}
              onMouseOut={e => e.currentTarget.style.borderColor = '#2a3444'}>
              <div style={{ fontSize: 22, color: '#d8a93d' }}>{r.icon}</div>
              <div style={{ fontWeight: 800, fontSize: 17, marginTop: 8 }}>[ {r.title} ]</div>
              <div style={{ color: '#8b94a3', fontSize: 13, marginTop: 6 }}>{r.desc}</div>
              <div style={{ marginTop: 12, fontSize: 12, fontWeight: 700, color: '#d8a93d' }}>ENTER DEMO →</div>
            </button>
          ))}
        </div>
        <div style={{ marginTop: 18, display: 'flex', gap: 10, justifyContent: 'center', alignItems: 'center', fontSize: 13, color: '#8b94a3' }}>
          <span>Base Manager home base:</span>
          <select value={base} onChange={e => setBase(e.target.value)} style={{ background: '#151b24', color: '#e6e9ee', border: '1px solid #2a3444', borderRadius: 6, padding: '4px 8px' }}>
            <option value="alpha">Base Alpha</option>
            <option value="bravo">Base Bravo</option>
            <option value="charlie">Base Charlie</option>
          </select>
        </div>
        <div style={{ marginTop: 14, textAlign: 'center', fontSize: 11, color: '#5d6675' }}>
          Demo uses simulated operational context (bases, inventory, distances). Health predictions arrive via the ML API contract.
        </div>
      </div>
    </div>
  );
}
