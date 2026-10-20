import React from 'react';
import { C } from '../theme.js';

const ROLES = [
  { id: 'commander', title: 'Commander', desc: 'Fleet-wide readiness and decision support' },
  { id: 'base', title: 'Base Manager', desc: 'Base-level aircraft readiness' },
  { id: 'logistics', title: 'Logistics Officer', desc: 'Inventory and resource management' },
];

const LOOP = ['Predict', 'Prepare', 'Optimize', 'Recover'];

export default function RoleSelect({ onSelect, onDocs }) {
  const [base, setBase] = React.useState('alpha');
  return (
    <div className="ops-entry">
      <div className="ops-entry-inner">
        <div className="ops-label">POC demo environment · choose a demo role</div>
        <h1 className="ops-entry-title">
          Aircraft fleet readiness<br />& sustainment platform
        </h1>
        <ol className="ops-entry-loop" aria-label="Operating loop">
          {LOOP.map(step => <li key={step}>{step}</li>)}
        </ol>
        <p className="ops-entry-lede">
          ML predictions drive fleet-level operational decisions that maximize aircraft availability.
          Selected roles are demo permissions, not authenticated accounts.
        </p>

        <div className="ops-entry-roles">
          {ROLES.map(r => (
            <button key={r.id} className="ops-entry-role" onClick={() => onSelect(r.id, base)}>
              <span className="ops-entry-role-title">{r.title}</span>
              <span className="ops-entry-role-desc">{r.desc}</span>
              <span className="ops-entry-role-cta">Enter demo</span>
            </button>
          ))}
        </div>

        {onDocs && (
          <button className="ops-entry-docs" onClick={onDocs}>
            <span className="ops-label">New to the platform?</span>
            <span>Read the documentation: problem, solution, roles and the complete workflow</span>
          </button>
        )}

        <div className="ops-entry-base">
          <label htmlFor="entry-home-base">Base Manager home base</label>
          <select id="entry-home-base" className="ops-control" value={base} onChange={e => setBase(e.target.value)}>
            <option value="alpha">Base Alpha</option>
            <option value="bravo">Base Bravo</option>
            <option value="charlie">Base Charlie</option>
          </select>
        </div>
        <div className="ops-entry-foot" style={{ color: C.dim }}>
          Demo uses simulated operational context (bases, inventory, distances). Health predictions arrive via the ML API contract.
        </div>
      </div>
    </div>
  );
}
