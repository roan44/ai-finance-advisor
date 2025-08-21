'use client';
import { useEffect, useState } from 'react';

export default function Home() {
  const [health, setHealth] = useState('checking...');
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    fetch('http://localhost:8000/health')
      .then(r => r.json())
      .then(j => setHealth(j.ok ? 'ok' : 'down'))
      .catch(() => setHealth('down'));
  }, []);

  async function categorize() {
    try {
      const r = await fetch('http://localhost:8000/categorize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: 'Whole Foods Market', amount: 23.45 })
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setResult(data);
    } catch (err) {
      setResult({ error: String(err) });
    }
  }

  return (
    <main style={{padding:24, fontFamily:'ui-sans-serif'}}>
      <h1>AI Finance — Skeleton</h1>
      <p>API health: {health}</p>
      <button onClick={categorize} style={{padding:8, borderRadius:8}}>Test categorize</button>
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </main>
  );
}
