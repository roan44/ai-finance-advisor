'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

type HealthStatus = 'checking' | 'healthy' | 'down';

type QuickStats = {
  total_transactions: number;
  total_enriched: number;
  total_advice: number;
  recent_spending: number;
};

export default function Home() {
  const base = process.env.NEXT_PUBLIC_API_BASE!;
  const [health, setHealth] = useState<HealthStatus>('checking');
  const [result, setResult] = useState<any>(null);
  const [stats, setStats] = useState<QuickStats | null>(null);

  // Check API health
  useEffect(() => {
    fetch(`${base}/`)
      .then(r => r.json())
      .then(j => setHealth(j.message ? 'healthy' : 'down'))
      .catch(() => setHealth('down'));
  }, [base]);

  // Load quick stats (we'll build this endpoint)
  useEffect(() => {
    loadStats();
  }, [base]);

  async function loadStats() {
    try {
      // For now, we'll call existing endpoints to build stats
      const [txResponse, adviceResponse] = await Promise.all([
        fetch(`${base}/transactions?limit=1000`),
        fetch(`${base}/advice/latest?limit=1000`)
      ]);

      if (txResponse.ok && adviceResponse.ok) {
        const transactions = await txResponse.json();
        const advice = await adviceResponse.json();
        
        // Calculate basic stats
        const enrichedCount = transactions.filter((tx: any) => tx.enriched).length;
        const recentSpending = transactions
          .filter((tx: any) => tx.amount < 0) // negative amounts are spending
          .slice(0, 30) // last 30 transactions
          .reduce((sum: number, tx: any) => sum + Math.abs(tx.amount), 0);

        setStats({
          total_transactions: transactions.length,
          total_enriched: enrichedCount,
          total_advice: advice.length,
          recent_spending: recentSpending
        });
      }
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  }

  async function testCategorize() {
    try {
      const r = await fetch(`${base}/categorize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          description: 'Starbucks Coffee Shop Dublin', 
          amount: -4.50 
        })
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setResult(data);
    } catch (err) {
      setResult({ error: String(err) });
    }
  }

  const healthColor = health === 'healthy' ? '#10b981' : health === 'down' ? '#ef4444' : '#f59e0b';
  const healthText = health === 'healthy' ? 'Healthy' : health === 'down' ? 'Down' : 'Checking...';

  return (
    <main style={{ padding: 24, maxWidth: 1000, margin: '0 auto' }}>
      {/* Welcome Section */}
      <section style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 32, fontWeight: 700, marginBottom: 8 }}>
          Welcome to your AI Finance Advisor
        </h1>
        <p style={{ color: '#6b7280', fontSize: 16, marginBottom: 16 }}>
          Track expenses, get AI insights, and optimize your spending with intelligent recommendations.
        </p>
        
        {/* API Status */}
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: 8,
          padding: 12,
          background: '#f9fafb',
          border: '1px solid #e5e7eb',
          borderRadius: 8 
        }}>
          <div style={{ 
            width: 8, 
            height: 8, 
            borderRadius: '50%', 
            background: healthColor 
          }} />
          <span>API Status: <strong>{healthText}</strong></span>
        </div>
      </section>

      {/* Quick Stats */}
      {stats && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>Quick Stats</h2>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', 
            gap: 16 
          }}>
            <StatCard 
              title="Total Transactions" 
              value={stats.total_transactions.toString()} 
              color="#3b82f6" 
            />
            <StatCard 
              title="AI Enriched" 
              value={stats.total_enriched.toString()} 
              color="#10b981" 
            />
            <StatCard 
              title="Advice Generated" 
              value={stats.total_advice.toString()} 
              color="#8b5cf6" 
            />
            <StatCard 
              title="Recent Spending" 
              value={`€${stats.recent_spending.toFixed(2)}`} 
              color="#f59e0b" 
            />
          </div>
        </section>
      )}

      {/* Quick Actions */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>Quick Actions</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 16 }}>
          
          <ActionCard 
            title="View Transactions"
            description="Browse and categorize your transactions with AI"
            linkHref="/transactions"
            linkText="Go to Transactions"
            color="#3b82f6"
          />
          
          <ActionCard 
            title="Get AI Advice"
            description="Generate personalized financial insights and recommendations"
            linkHref="/advisor"
            linkText="Open Advisor"
            color="#8b5cf6"
          />
          
          <div style={{
            background: '#f9fafb',
            border: '1px solid #e5e7eb',
            borderRadius: 12,
            padding: 16
          }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Test AI Categorization</h3>
            <p style={{ color: '#6b7280', fontSize: 14, marginBottom: 12 }}>
              Test how the AI categorizes a sample transaction
            </p>
            <button 
              onClick={testCategorize} 
              style={{
                background: '#10b981',
                color: 'white',
                border: 'none',
                padding: '8px 16px',
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 14,
                fontWeight: 500
              }}
            >
              Test Categorization
            </button>
            {result && (
              <details style={{ marginTop: 12 }}>
                <summary style={{ cursor: 'pointer', color: '#6b7280' }}>View Result</summary>
                <pre style={{ 
                  background: '#f3f4f6', 
                  padding: 8, 
                  borderRadius: 4, 
                  fontSize: 12, 
                  overflow: 'auto',
                  marginTop: 8
                }}>
                  {JSON.stringify(result, null, 2)}
                </pre>
              </details>
            )}
          </div>

        </div>
      </section>

      {/* Getting Started */}
      <section>
        <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>Getting Started</h2>
        <div style={{ 
          background: '#eff6ff', 
          border: '1px solid #bfdbfe', 
          borderRadius: 12, 
          padding: 20 
        }}>
          <ol style={{ margin: 0, paddingLeft: 20, color: '#1e40af' }}>
            <li style={{ marginBottom: 8 }}>
              <strong>Add transactions</strong> - Import or manually add your financial transactions
            </li>
            <li style={{ marginBottom: 8 }}>
              <strong>AI categorization</strong> - Let AI automatically categorize and enrich your data
            </li>
            <li style={{ marginBottom: 8 }}>
              <strong>Get insights</strong> - Run the advisor to generate personalized financial advice
            </li>
            <li>
              <strong>Optimize spending</strong> - Follow AI recommendations to save money and invest smarter
            </li>
          </ol>
        </div>
      </section>
    </main>
  );
}

function StatCard({ title, value, color }: { title: string; value: string; color: string }) {
  return (
    <div style={{
      background: 'white',
      border: '1px solid #e5e7eb',
      borderRadius: 12,
      padding: 16,
      borderLeft: `4px solid ${color}`
    }}>
      <div style={{ color: '#6b7280', fontSize: 14, marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: '#111827' }}>{value}</div>
    </div>
  );
}

function ActionCard({ 
  title, 
  description, 
  linkHref, 
  linkText, 
  color 
}: { 
  title: string; 
  description: string; 
  linkHref: string; 
  linkText: string; 
  color: string; 
}) {
  return (
    <div style={{
      background: 'white',
      border: '1px solid #e5e7eb',
      borderRadius: 12,
      padding: 16,
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between'
    }}>
      <div>
        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color }}>{title}</h3>
        <p style={{ color: '#6b7280', fontSize: 14, marginBottom: 16 }}>{description}</p>
      </div>
      <Link 
        href={linkHref}
        style={{
          background: color,
          color: 'white',
          textDecoration: 'none',
          padding: '8px 16px',
          borderRadius: 8,
          textAlign: 'center',
          fontSize: 14,
          fontWeight: 500,
          alignSelf: 'flex-start'
        }}
      >
        {linkText}
      </Link>
    </div>
  );
}