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

  // Coffee simulator state (client-side calculation)
  const [coffeePrice, setCoffeePrice] = useState<string>('3.50');
  const [perWeek, setPerWeek] = useState<string>('5');
  const [years, setYears] = useState<string>('10');
  const [annualRate, setAnnualRate] = useState<string>('0.07');

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

  // Client-side coffee simulation calculations
  const simResult = useMemo(() => {
    const price = parseFloat(coffeePrice);
    const perW = parseFloat(perWeek);
    const yrs = parseInt(years, 10);
    const rate = parseFloat(annualRate);

    if ([price, perW, yrs, rate].some(v => Number.isNaN(v) || v < 0)) return null;

    const perMonth = (perW * 52) / 12; // coffee purchases per month
    const monthly_spend = perMonth * price;
    const annual_spend = monthly_spend * 12;

    // Future value calculation: monthly contributions compounded monthly
    const r = rate / 12; // monthly rate
    const n = yrs * 12; // total months
    const fv_if_invested = r === 0 
      ? monthly_spend * n 
      : monthly_spend * (Math.pow(1 + r, n) - 1) / r;

    return {
      monthly_spend: Math.round(monthly_spend * 100) / 100,
      annual_spend: Math.round(annual_spend * 100) / 100,
      fv_if_invested: Math.round(fv_if_invested * 100) / 100
    };
  }, [coffeePrice, perWeek, years, annualRate]);

  // Build chart data for visualization
  const chartData = useMemo(() => {
    if (!simResult) return [];

    const price = parseFloat(coffeePrice);
    const perW = parseFloat(perWeek);
    const yrs = parseInt(years, 10);
    const rate = parseFloat(annualRate);

    const perMonth = (perW * 52) / 12;
    const contrib = perMonth * price;
    const r = rate / 12;
    const months = yrs * 12;

    const arr: { year: number; value: number }[] = [];
    let acc = 0;
    for (let i = 1; i <= months; i++) {
      acc = acc * (1 + r) + contrib;
      if (i % 12 === 0) {
        arr.push({ year: i / 12, value: Math.round(acc * 100) / 100 });
      }
    }
    return arr;
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

      {/* Investment "What-if" Simulator */}
      <section style={card()}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>
          Investment "What-if" Simulator
        </h2>
        <p style={{ color: '#6b7280', fontSize: 14, marginBottom: 16 }}>
          See how much you could save by cutting back on regular purchases and investing the difference.
        </p>
        
        <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', marginBottom: 12 }}>
          <LabeledInput label="Price each (€)">
            <input 
              type="number" 
              step="0.01" 
              value={coffeePrice} 
              onChange={e => setCoffeePrice(e.target.value)} 
              style={input()} 
            />
          </LabeledInput>
          <LabeledInput label="Per week">
            <input 
              type="number" 
              step="1" 
              value={perWeek} 
              onChange={e => setPerWeek(e.target.value)} 
              style={input()} 
            />
          </LabeledInput>
          <LabeledInput label="Years">
            <input 
              type="number" 
              step="1" 
              value={years} 
              onChange={e => setYears(e.target.value)} 
              style={input()} 
            />
          </LabeledInput>
          <LabeledInput label="Expected annual return">
            <input 
              type="number" 
              step="0.01" 
              value={annualRate} 
              onChange={e => setAnnualRate(e.target.value)} 
              style={input()} 
            />
          </LabeledInput>
        </div>

        {simResult && (
          <div style={{ 
            display: 'flex', 
            gap: 12, 
            alignItems: 'center', 
            marginBottom: 12,
            padding: 12,
            background: '#f0f9ff',
            borderRadius: 8,
            border: '1px solid #bae6fd'
          }}>
            <div style={{ color: '#0c4a6e', fontSize: 14 }}>
              <strong>Monthly spend:</strong> €{simResult.monthly_spend.toFixed(2)} • 
              <strong> Annual:</strong> €{simResult.annual_spend.toFixed(2)} • 
              <strong> If invested for {years} years:</strong> €{simResult.fv_if_invested.toFixed(2)}
            </div>
          </div>
        )}

        <div style={{ width: '100%', height: 220 }}>
          <ResponsiveContainer>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                dataKey="year" 
                label={{ value: 'Years', position: 'insideBottom', offset: -5 }}
              />
              <YAxis 
                label={{ value: 'Value (€)', angle: -90, position: 'insideLeft' }}
              />
              <Tooltip 
                formatter={(value) => [`€${Number(value).toFixed(2)}`, 'Investment Value']}
                labelFormatter={(year) => `Year ${year}`}
              />
              <Line 
                type="monotone" 
                dataKey="value" 
                stroke="#3b82f6" 
                strokeWidth={2}
                dot={{ fill: '#3b82f6', strokeWidth: 2 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Advice list */}
      <section style={{ marginTop: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>AI-Generated Insights</h2>
          <span style={{ color: '#6b7280', fontSize: 14 }}>
            {items.length} insight{items.length !== 1 ? 's' : ''} found
          </span>
        </div>

        <ul style={{ display: 'grid', gap: 12, padding: 0, listStyle: 'none' }}>
          {items.map((it) => (
            <li key={it.id} style={card()}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <Badge tone={kindTone(it.kind)}>{it.kind.toUpperCase()}</Badge>
                    <span style={{ color: '#6b7280', fontSize: 12 }}>
                      {new Date(it.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 6 }}>{it.title}</div>
                  <div style={{ color: '#374151', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
                    {it.body}
                  </div>
                </div>
                
                {/* Metrics sidebar */}
                <div style={{ minWidth: 220, display: 'grid', gap: 6 }}>
                  {val(it.monthly_saving) && (
                    <Metric label="Monthly saving" value={`€${it.monthly_saving!.toFixed(2)}`} />
                  )}
                  {val(it.annual_saving) && (
                    <Metric label="Annual saving" value={`€${it.annual_saving!.toFixed(2)}`} />
                  )}
                  {val(it.projection_10y) && (
                    <Metric label="10y projection" value={`€${it.projection_10y!.toFixed(2)}`} />
                  )}
                  {val(it.confidence) && (
                    <Metric 
                      label="Confidence" 
                      value={`${Math.round((it.confidence ?? 0) * 100)}%`} 
                    />
                  )}
                </div>
              </div>
              
              {/* Related transactions and metadata */}
              <div style={{ 
                marginTop: 12, 
                display: 'flex', 
                alignItems: 'center', 
                gap: 8, 
                flexWrap: 'wrap',
                paddingTop: 12,
                borderTop: '1px solid #f3f4f6'
              }}>
                <span style={{ color: '#6b7280', fontSize: 12 }}>Related transactions:</span>
                {it.tx_ids.slice(0, 5).map(id => (
                  <a key={id} href="/transactions" style={{ textDecoration: 'none' }}>
                    <Badge tone="blue">#{id}</Badge>
                  </a>
                ))}
                {it.tx_ids.length > 5 && (
                  <span style={{ color: '#6b7280', fontSize: 12 }}>
                    +{it.tx_ids.length - 5} more
                  </span>
                )}
                {Array.isArray(it.meta?.tags) && it.meta!.tags.map((t: string, i: number) => (
                  <Badge key={i} tone="amber">{t}</Badge>
                ))}
              </div>
            </li>
          ))}
          
          {!items.length && !loading && (
            <li style={{...card(), textAlign: 'center', padding: 32}}>
              <div style={{ color: '#6b7280', marginBottom: 8 }}>No insights yet</div>
              <div style={{ color: '#9ca3af', fontSize: 14 }}>
                Add some transactions and click "Run advisor" to generate AI insights
              </div>
            </li>
          )}
        </ul>
      </section>
    </main>
  );
}

/* ---------- UI helpers ---------- */

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
      border: '1px solid #e5e7eb', borderRadius: 8, padding: '6px 8px',
      fontSize: 12
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
    padding: 16,
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