'use client';
import { useEffect, useMemo, useState } from 'react';

type Tx = {
  id: number;
  account_id: number;
  date: string;          
  description: string;
  amount: number;
  merchant_raw?: string | null;
};

type Enriched = {
  transaction_id: number;
  merchant: string | null;
  category: string | null;
  subcategory: string | null;
  is_subscription: boolean | null;
  confidence: number | null;
  notes: string | null;
  spending_class?: 'need' | 'want' | 'savings' | null;
} | null;

export default function Transactions() {
  const base = process.env.NEXT_PUBLIC_API_BASE!;
  const [rows, setRows] = useState<Tx[]>([]);
  const [enriched, setEnriched] = useState<Record<number, Enriched>>({});
  const [loadingIds, setLoadingIds] = useState<Set<number>>(new Set());
  const [errors, setErrors] = useState<Record<number, string | null>>({});

  // --- Search state ---
  const [q, setQ] = useState<string>('');
  const [searching, setSearching] = useState<boolean>(false);

  // --- Add Transaction form state ---
  const today = new Date().toISOString().slice(0, 10);
  const [fDate, setFDate] = useState<string>(today);
  const [fDesc, setFDesc] = useState<string>('');
  const [fAmount, setFAmount] = useState<string>('0.00');
  const [fMerchantRaw, setFMerchantRaw] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [autoEnrich, setAutoEnrich] = useState<boolean>(true);
  const [formError, setFormError] = useState<string | null>(null);

  // Helper: fetch transactions (optionally with q)
  async function loadTransactions(query?: string) {
    setSearching(true);
    try {
      const url = new URL(`${base}/transactions`);
      if (query && query.trim()) url.searchParams.set('q', query.trim());
      const r = await fetch(url.toString(), { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const list: Tx[] = await r.json();
      setRows(list);

      setEnriched({});

      const p = list.map(async (tx) => {
        try {
          const res = await fetch(`${base}/transactions/${tx.id}/enriched`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data: Enriched = await res.json();
          setEnriched(prev => ({ ...prev, [tx.id]: data }));
        } catch (e: any) {
          setErrors(prev => ({ ...prev, [tx.id]: e?.message ?? 'Failed to load enrichment' }));
        }
      });
      await Promise.allSettled(p);
    } finally {
      setSearching(false);
    }
  }

  // Fetch all transactions on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`${base}/transactions`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const list: Tx[] = await r.json();
        if (cancelled) return;
        setRows(list);
        const p = list.map(async (tx) => {
          try {
            const res = await fetch(`${base}/transactions/${tx.id}/enriched`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data: Enriched = await res.json();
            if (cancelled) return;
            setEnriched(prev => ({ ...prev, [tx.id]: data }));
          } catch (e: any) {
            if (cancelled) return;
            setErrors(prev => ({ ...prev, [tx.id]: e?.message ?? 'Failed to load enrichment' }));
          }
        });
        await Promise.allSettled(p);
      } catch {
        setRows([]);
      }
    })();
    return () => { cancelled = true; };
  }, [base]);

  async function enrichOne(tx: Tx) {
    setErrors(prev => ({ ...prev, [tx.id]: null }));
    setLoadingIds(prev => new Set(prev).add(tx.id));
    try {
      const res = await fetch(`${base}/categorize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: tx.description,
          amount: tx.amount,
          transaction_id: tx.id,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? `HTTP ${res.status}`);
      setEnriched(prev => ({
        ...prev,
        [tx.id]: {
          transaction_id: tx.id,
          merchant: data.merchant ?? null,
          category: data.category ?? null,
          subcategory: data.subcategory ?? null,
          is_subscription: Boolean(data.is_subscription ?? false),
          confidence: typeof data.confidence === 'number' ? data.confidence : null,
          notes: data.notes ?? null,
          spending_class: (data.spending_class ?? null) as any,
        },
      }));
    } catch (e: any) {
      setErrors(prev => ({ ...prev, [tx.id]: e?.message ?? 'Categorize failed' }));
    } finally {
      setLoadingIds(prev => {
        const next = new Set(prev);
        next.delete(tx.id);
        return next;
      });
    }
  }

  // --- Add Transaction submit handler ---
  async function onSubmitAdd(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);

    const amt = parseFloat(fAmount);
    if (!fDesc.trim()) return setFormError('Description is required.');
    if (Number.isNaN(amt)) return setFormError('Amount must be a number.');

    setSubmitting(true);
    try {
      const res = await fetch(`${base}/transactions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: 1,
          date: fDate,
          description: fDesc.trim(),
          amount: amt,
          merchant_raw: fMerchantRaw.trim() || null,
        }),
      });
      const created: Tx | { detail?: string } = await res.json();
      if (!res.ok) throw new Error((created as any)?.detail ?? `HTTP ${res.status}`);

      setRows(prev => [created as Tx, ...prev]);
      setEnriched(prev => ({ ...prev, [(created as Tx).id]: null }));

      // Reset form
      setFDesc('');
      setFAmount('0.00');
      setFMerchantRaw('');

      if (autoEnrich) {
        await enrichOne(created as Tx);
      }
    } catch (err: any) {
      setFormError(err?.message ?? 'Failed to add transaction');
    } finally {
      setSubmitting(false);
    }
  }

  // Search handlers
  function onSearchClick() {
    loadTransactions(q);
  }
  function onClearSearch() {
    setQ('');
    loadTransactions('');
  }
  function onBadgeSearch(term: string) {
    setQ(term);
    loadTransactions(term);
  }

  function fmtAmount(v: number) {
    try { return v.toFixed(2); } catch { return String(v); }
  }
  function pct(n: number | null | undefined) {
    if (typeof n !== 'number') return '';
    return `${Math.round(n * 100)}%`;
  }

  const hasRows = useMemo(() => rows.length > 0, [rows]);

  return (
    <main style={{ padding: 24, fontFamily: 'ui-sans-serif', maxWidth: 900, margin: '0 auto' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 12 }}>Transactions</h1>

      {/* Search Bar */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr auto auto',
        gap: 8,
        alignItems: 'center',
        marginBottom: 12,
      }}>
        <input
          aria-label="Search transactions"
          placeholder="Search merchant, category, description…"
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') onSearchClick(); }}
          style={inputStyle}
        />
        <button
          onClick={onSearchClick}
          disabled={searching}
          style={buttonPrimary(searching)}
        >
          {searching ? 'Searching…' : 'Search'}
        </button>
        <button
          onClick={onClearSearch}
          disabled={searching && !q}
          style={buttonGhost()}
        >
          Clear
        </button>
      </div>

      {/* Add Transaction Form */}
      <form onSubmit={onSubmitAdd} style={{
        display: 'grid',
        gap: 10,
        padding: 16,
        marginBottom: 16,
        border: '1px solid #e5e7eb',
        borderRadius: 12,
        background: '#fafafa'
      }}>
        <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 8, alignItems: 'center' }}>
          <label htmlFor="date">Date</label>
          <input
            id="date"
            type="date"
            value={fDate}
            onChange={e => setFDate(e.target.value)}
            style={inputStyle}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 8, alignItems: 'center' }}>
          <label htmlFor="desc">Description</label>
          <input
            id="desc"
            type="text"
            placeholder="e.g. Tesco Supermarket"
            value={fDesc}
            onChange={e => setFDesc(e.target.value)}
            style={inputStyle}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 8, alignItems: 'center' }}>
          <label htmlFor="amount">Amount</label>
          <input
            id="amount"
            type="number"
            step="0.01"
            inputMode="decimal"
            value={fAmount}
            onChange={e => setFAmount(e.target.value)}
            style={inputStyle}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 8, alignItems: 'center' }}>
          <label htmlFor="merchant_raw">Merchant (raw)</label>
          <input
            id="merchant_raw"
            type="text"
            placeholder="Optional POS text"
            value={fMerchantRaw}
            onChange={e => setFMerchantRaw(e.target.value)}
            style={inputStyle}
          />
        </div>

        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 4 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={autoEnrich}
              onChange={e => setAutoEnrich(e.target.checked)}
            />
            Auto-enrich after adding
          </label>

          {formError && <span style={{ color: '#ef4444' }}>• {formError}</span>}

          <button
            type="submit"
            disabled={submitting}
            style={buttonPrimary(submitting)}
          >
            {submitting ? 'Adding…' : 'Add transaction'}
          </button>
        </div>
      </form>

      {!hasRows && <p>No transactions yet. Add one above or POST to <code>/transactions</code>.</p>}

      <ul style={{ display: 'grid', gap: 10, padding: 0, listStyle: 'none' }}>
        {rows.map((tx) => {
          const e = enriched[tx.id] ?? null;
          const isLoading = loadingIds.has(tx.id);
          const err = errors[tx.id];

          return (
            <li key={tx.id} style={{
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              padding: 12,
              display: 'grid',
              gap: 8,
              background: '#fff'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>
                    {tx.description}{' '}
                    <span style={{ color: '#6b7280' }}>• {tx.date}</span>
                  </div>
                  <div style={{ color: '#374151' }}>
                    Amount: <strong>€{fmtAmount(tx.amount)}</strong>
                    {tx.merchant_raw ? (
                      <>
                        {' '}
                        <span style={{ color: '#6b7280' }}>• raw: </span>
                        <button
                          type="button"
                          onClick={() => onBadgeSearch(tx.merchant_raw!)}
                          style={badgeLinkStyle}
                          title={`Search "${tx.merchant_raw}"`}
                        >
                          {tx.merchant_raw}
                        </button>
                      </>
                    ) : null}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button
                    onClick={() => enrichOne(tx)}
                    disabled={isLoading}
                    style={buttonPrimary(isLoading)}
                  >
                    {isLoading ? 'Enriching…' : 'Enrich'}
                  </button>
                </div>
              </div>

              {/* Enrichment display */}
              <div style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 8,
                alignItems: 'center'
              }}>
                {e ? (
                  <>
                    <Badge asButton onClick={() => onBadgeSearch(e.merchant ?? '')}>
                      {e.merchant ?? 'Unknown merchant'}
                    </Badge>
                    {e.category && (
                      <Badge tone="green" asButton onClick={() => onBadgeSearch(e.category!)}>
                        {e.category}
                      </Badge>
                    )}
                    {e.subcategory && (
                      <Badge tone="blue" asButton onClick={() => onBadgeSearch(e.subcategory!)}>
                        {e.subcategory}
                      </Badge>
                    )}
                    {typeof e.is_subscription === 'boolean' && (
                      <Badge
                        tone={e.is_subscription ? 'purple' : 'gray'}
                        asButton
                        onClick={() => onBadgeSearch(e.is_subscription ? 'subscription' : 'one-off')}
                      >
                        {e.is_subscription ? 'Subscription' : 'One-off'}
                      </Badge>
                    )}
                    {typeof e.confidence === 'number' && (
                      <Badge tone="amber">Confidence {pct(e.confidence)}</Badge>
                    )}
                    {e?.spending_class && (
                      <Badge
                        tone={e.spending_class === 'need' ? 'blue' : e.spending_class === 'savings' ? 'green' : 'amber'}
                        asButton
                        onClick={() => onBadgeSearch(e.spending_class!)}
                      >
                        {e.spending_class.charAt(0).toUpperCase() + e.spending_class.slice(1)}
                      </Badge>
                    )}

                    {e.notes && <span style={{ color: '#6b7280' }}>— {e.notes}</span>}
                  </>
                ) : (
                  <span style={{ color: '#9ca3af' }}>No enrichment yet</span>
                )}
                {err && <span style={{ color: '#ef4444' }}> • {err}</span>}
              </div>
            </li>
          );
        })}
      </ul>
    </main>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  border: '1px solid #e5e7eb',
  borderRadius: 10,
  fontSize: 14,
  background: '#fff',
};

function buttonPrimary(disabled: boolean): React.CSSProperties {
  return {
    padding: '8px 12px',
    borderRadius: 10,
    border: '1px solid #e5e7eb',
    background: disabled ? '#f3f4f6' : '#111827',
    color: disabled ? '#6b7280' : '#fff',
    cursor: disabled ? 'not-allowed' : 'pointer',
    minWidth: 120
  };
}
function buttonGhost(): React.CSSProperties {
  return {
    padding: '8px 12px',
    borderRadius: 10,
    border: '1px solid #e5e7eb',
    background: '#fff',
    color: '#111827',
    cursor: 'pointer',
    minWidth: 80
  };
}

const badgeLinkStyle: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  color: '#2563eb',
  cursor: 'pointer',
  padding: 0,
  textDecoration: 'underline',
  textUnderlineOffset: '2px',
  font: 'inherit',
};


function Badge({
  children,
  tone = 'gray',
  asButton = false,
  onClick,
}: {
  children: React.ReactNode;
  tone?: 'gray' | 'green' | 'blue' | 'purple' | 'amber';
  asButton?: boolean;
  onClick?: () => void;
}) {
  const palette: Record<string, { bg: string; fg: string; brd: string }> = {
    gray:   { bg: '#f3f4f6', fg: '#111827', brd: '#e5e7eb' },
    green:  { bg: '#ecfdf5', fg: '#065f46', brd: '#a7f3d0' },
    blue:   { bg: '#eff6ff', fg: '#1e3a8a', brd: '#bfdbfe' },
    purple: { bg: '#f5f3ff', fg: '#5b21b6', brd: '#ddd6fe' },
    amber:  { bg: '#fffbeb', fg: '#92400e', brd: '#fde68a' },
  };
  const c = palette[tone] ?? palette.gray;

  const common: React.CSSProperties = {
    display: 'inline-block',
    fontSize: 12,
    padding: '4px 8px',
    borderRadius: 999,
    background: c.bg,
    color: c.fg,
    border: `1px solid ${c.brd}`,
  };

  if (asButton) {
    return (
      <button type="button" onClick={onClick} style={{ ...common, cursor: 'pointer' }}>
        {children}
      </button>
    );
  }
  return <span style={common}>{children}</span>;
}
