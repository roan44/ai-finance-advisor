'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Navigation() {
  const pathname = usePathname();

  return (
    <header style={{
      background: '#111827',
      color: 'white',
      padding: '12px 24px',
      display: 'flex',
      alignItems: 'center',
      gap: 24,
      borderBottom: '1px solid #374151'
    }}>
      <h1 style={{ 
        margin: 0, 
        fontSize: 20, 
        fontWeight: 700 
      }}>
        AI Finance Advisor
      </h1>
      
      <nav style={{ display: 'flex', gap: 16 }}>
        <Link 
          href="/" 
          style={{
            color: pathname === '/' ? '#60a5fa' : '#d1d5db',
            textDecoration: 'none',
            padding: '8px 12px',
            borderRadius: 6,
            background: pathname === '/' ? '#1e3a8a' : 'transparent',
            transition: 'all 0.2s'
          }}
        >
          Dashboard
        </Link>
        
        <Link 
          href="/transactions" 
          style={{
            color: pathname === '/transactions' ? '#60a5fa' : '#d1d5db',
            textDecoration: 'none',
            padding: '8px 12px',
            borderRadius: 6,
            background: pathname === '/transactions' ? '#1e3a8a' : 'transparent',
            transition: 'all 0.2s'
          }}
        >
          Transactions
        </Link>
        
        <Link 
          href="/advisor" 
          style={{
            color: pathname === '/advisor' ? '#60a5fa' : '#d1d5db',
            textDecoration: 'none',
            padding: '8px 12px',
            borderRadius: 6,
            background: pathname === '/advisor' ? '#1e3a8a' : 'transparent',
            transition: 'all 0.2s'
          }}
        >
          Advisor
        </Link>
      </nav>
    </header>
  );
}