'use client';
import { useEffect, useState } from 'react';

export default function Home() {
  const [health, setHealth] = useState<string>('checking...');
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_BASE}/health`)
        .then(r => r.json())
        .then(j => setHealth(j.ok ? 'ok' : 'down'))
        .catch(() => setHealth('down'));
  }, []);

  async function categorize() {
    const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/categorize`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({description: "Whole Foods Market, amount: 23.45"})
    });
    setResult(await r.json());
  }

  return (
    <main style={{padding:24, fontFamily: 'Arial, sans-serif'}}>
        <h1>AI Finance — Skeleton</h1>
        <p>API health: {health}</p>
        <button onClick={categorize} style={{padding:8, borderRadius:8}}>Test categorize</button>
        {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </main>
  );
}
