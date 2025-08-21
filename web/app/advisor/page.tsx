'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';

type AdviceItem = {
  id: number;
  created_at: string;
  kind: 'switch' | 'cutback' | 'invest' | 'recipe' | 'anomaly' | 'duplicate' | string;
  title: string;
  body: string;
  monthly_saving?: number | null;
  annual_saving?: number | null;
  projection_10y?: number | null;
  confidence?: number | null;
  tx_ids: number[];
  meta?: Record<string, any>;
};

export default function AdvisorPage() {
  const base = process.env.NEXT_PUBLIC_API_BASE!;
  const [items, setItems] = useState<AdviceItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Coffee simulator state
  const [coffeePrice, setCoffeePrice] = useState<string>('3.50');
  const [perWeek, setPerWeek] = useState<string>('5');
  const [years, setYears] = useState<string>('10');
  const [annualRate, setAnnualRate] = useState<string>('0.07');
  const [simResult, setSimResult] = useState<{ monthly_spend: number, annual_spend: number, fv_if_invested: number } | null>(null);

  async function fetchLatest() {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${base}/advice/latest?limit=30`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data: AdviceItem[] = await r.json();
      setItems(data);
    } catch (e:any) {
      setError(e?.message ?? 'Failed to load advice');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  async function runAdvisor() {
    setRunning(true);
    setError(null);
    try {
      const r = await fetch(`${base}/advice/run`, { method: 'POST' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      // re-fetch
      await fetchLatest();
    } catch (e:any) {
      setError(e?.message ?? 'Failed to run advisor');
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => {
    fetchLatest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  // Coffee simulator (calls your /simulate/coffee)
  async function simulateCoffee() {
    setError(null);
    try {
      const payload = {
        price_each: parseFloat(coffeePrice),
        per_week: parseFloat(perWeek),
        years: parseInt(years, 10),
        annual_rate: parseFloat(annualRate),
      };
      const r = await fetch(`${base}/simulate/coffee`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSimResult(data);
    } catch (e:any) {
      setError(e?.message ?? 'Coffee simulation failed');
      setSimResult(null);
    }
  }

  // Build a small series for the chart (client-side; matches the params)
  const chartData = useMemo(() => {
    const price = parseFloat(coffeePrice);
    const perW = parseFloat(perWeek);
    const yrs = parseInt(years, 10);
    const rate = parseFloat(annualRate);

    if ([price, perW, yrs, rate].some(v => Number.isNaN(v) || v < 0)) return [];

    const perMonth = (perW * 52) / 12;
    const contrib = perMonth * price; // monthly spend redirected into investment
    const r = rate / 12;
    const months = yrs * 12;

    const arr: { m: number; value: number }[] = [];
    let acc = 0;
    for (let i = 1; i <= months; i++) {
      acc = acc * (1 + r) + contrib;
      if (i % 12 === 0) {
        arr.push({ m: i, value: acc });
      }
    }
    return arr.map((d, idx) => ({ year: (idx + 1), value: Math.round(d.value * 100) / 100 }));
  }, [coffeePrice, perWeek, years, annualRate]);

  return (
    <main style={{ padding: 24, fontFamily: 'ui-sans-serif', maxWidth: 1000, margin: '0 auto' }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700 }}>Advisor</h1>
        <button
          onClick={runAdvisor}
          disabled={running}
          style={btnPrimary(running)}
          title="Scan recent transactions and generate new advice insights"
        >
          {running ? 'Running…' : 'Run advisor'}
        </button>
        <button onClick={fetchLatest} disabled={loading} style={btnGhost()}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
        {error && <span style={{ color: '#ef4444' }}>• {error}</span>}
      </header>

      {/* Coffee What-if Simulator */}
      <section style={card()}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Coffee “What-if”</h2>
        <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', marginBottom: 12 }}>
          <LabeledInput label="Price each (€)">
            <input type="number" step="0.01" value={coffeePrice} onChange={e => setCoffeePrice(e.target.value)} style={input()} />
          </LabeledInput>
          <LabeledInput label="Per week">
            <input type="number" step="1" value={perWeek} onChange={e => setPerWeek(e.target.value)} style={input()} />
          </LabeledInput>
          <LabeledInput label="Years">
            <input type="number" step="1" value={years} onChange={e => setYears(e.target.value)} style={input()} />
          </LabeledInput>
          <LabeledInput label="Expected annual return">
            <input type="number" step="0.01" value={annualRate} onChange={e => setAnnualRate(e.target.value)} style={input()} />
          </LabeledInput>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
          <button onClick={simulateCoffee} style={btnPrimary(false)}>Simulate</button>
          {simResult && (
            <div style={{ color: '#374151' }}>
              Monthly spend ≈ <strong>€{simResult.monthly_spend.toFixed(2)}</strong> •
              Annual ≈ <strong>€{simResult.annual_spend.toFixed(2)}</strong> •
              10y FV ≈ <strong>€{simResult.fv_if_invested.toFixed(2)}</strong>
            </div>
          )}
        </div>
        <div style={{ width: '100%', height: 220 }}>
          <ResponsiveContainer>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="year" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="value" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Advice list */}
      <section style={{ marginTop: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>Latest insights</h2>
        <ul style={{ display: 'grid', gap: 10, padding: 0, listStyle: 'none' }}>
          {items.map((it) => (
            <li key={it.id} style={card()}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <Badge tone={kindTone(it.kind)}>{it.kind.toUpperCase()}</Badge>
                    <span style={{ color: '#6b7280', fontSize: 12 }}>{new Date(it.created_at).toLocaleString()}</span>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>{it.title}</div>
                  <div style={{ color: '#374151', whiteSpace: 'pre-wrap' }}>{it.body}</div>
                </div>
                <div style={{ minWidth: 220, display: 'grid', gap: 6 }}>
                  {val(it.monthly_saving) && <Metric label="Monthly saving" value={`€${it.monthly_saving!.toFixed(2)}`} />}
                  {val(it.annual_saving) && <Metric label="Annual saving" value={`€${it.annual_saving!.toFixed(2)}`} />}
                  {val(it.projection_10y) && <Metric label="10y projection" value={`€${it.projection_10y!.toFixed(2)}`} />}
                  {val(it.confidence) && <Metric label="Confidence" value={`${Math.round((it.confidence ?? 0) * 100)}%`} />}
                </div>
              </div>
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ color: '#6b7280', fontSize: 12 }}>Related tx:</span>
                {it.tx_ids.map(id => (
                  <a key={id} href="/transactions" style={{ textDecoration: 'none' }}>
                    <Badge tone="blue">#{id}</Badge>
                  </a>
                ))}
                {Array.isArray(it.meta?.tags) && it.meta!.tags.map((t: string, i: number) => (
                  <Badge key={i} tone="amber">{t}</Badge>
                ))}
              </div>
            </li>
          ))}
          {!items.length && !loading && (
            <li style={card()}>
              <div style={{ color: '#6b7280' }}>No advice yet — click “Run advisor”.</div>
            </li>
          )}
        </ul>
      </section>
    </main>
  );
}

/* ---------- tiny UI helpers (no external deps) ---------- */

function val<T>(x: T | null | undefined) { return x !== null && x !== undefined; }

function kindTone(kind: string): BadgeTone {
  switch (kind) {
    case 'switch': return 'purple';
    case 'cutback': return 'green';
    case 'invest': return 'amber';
    case 'recipe': return 'blue';
    case 'anomaly': return 'red';
    case 'duplicate': return 'red';
    default: return 'gray';
  }
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', gap: 8,
      border: '1px solid #e5e7eb', borderRadius: 10, padding: '6px 8px'
    }}>
      <span style={{ color: '#6b7280' }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function LabeledInput({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'grid', gap: 6, fontSize: 12, color: '#374151' }}>
      <span>{label}</span>
      {children}
    </label>
  );
}

type BadgeTone = 'gray' | 'green' | 'blue' | 'purple' | 'amber' | 'red';

function Badge({ children, tone = 'gray' }: { children: React.ReactNode; tone?: BadgeTone }) {
  const palette: Record<BadgeTone, { bg: string; fg: string; brd: string }> = {
    gray:   { bg: '#f3f4f6', fg: '#111827', brd: '#e5e7eb' },
    green:  { bg: '#ecfdf5', fg: '#065f46', brd: '#a7f3d0' },
    blue:   { bg: '#eff6ff', fg: '#1e3a8a', brd: '#bfdbfe' },
    purple: { bg: '#f5f3ff', fg: '#5b21b6', brd: '#ddd6fe' },
    amber:  { bg: '#fffbeb', fg: '#92400e', brd: '#fde68a' },
    red:    { bg: '#fef2f2', fg: '#991b1b', brd: '#fecaca' },
  };
  const c = palette[tone] ?? palette.gray;
  return (
    <span style={{
      display: 'inline-block',
      fontSize: 12,
      padding: '4px 8px',
      borderRadius: 999,
      background: c.bg,
      color: c.fg,
      border: `1px solid ${c.brd}`,
    }}>
      {children}
    </span>
  );
}

function btnPrimary(disabled: boolean): React.CSSProperties {
  return {
    padding: '8px 12px',
    borderRadius: 10,
    border: '1px solid #111827',
    background: disabled ? '#9ca3af' : '#111827',
    color: '#fff',
    cursor: disabled ? 'not-allowed' : 'pointer',
  };
}
function btnGhost(): React.CSSProperties {
  return {
    padding: '8px 12px',
    borderRadius: 10,
    border: '1px solid #e5e7eb',
    background: '#fff',
    color: '#111827',
    cursor: 'pointer',
  };
}
function card(): React.CSSProperties {
  return {
    border: '1px solid #e5e7eb',
    borderRadius: 12,
    padding: 12,
    background: '#fff',
  };
}
function input(): React.CSSProperties {
  return {
    width: '100%',
    padding: '8px 10px',
    border: '1px solid #e5e7eb',
    borderRadius: 10,
    fontSize: 14,
    background: '#fff',
  };
}
