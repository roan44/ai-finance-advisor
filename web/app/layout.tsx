import { Metadata } from 'next';
import Navigation from './navigation';

export const metadata: Metadata = {
  title: 'AI Finance Advisor',
  description: 'Personal finance management with AI-powered insights and recommendations',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'ui-sans-serif, system-ui, sans-serif' }}>
        <Navigation />
        <main>
          {children}
        </main>
      </body>
    </html>
  )
}