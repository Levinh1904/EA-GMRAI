import type { Metadata, Viewport } from 'next';
import './globals.css';
import { AuthProvider } from '@/components/AuthProvider';

export const metadata: Metadata = {
  title: 'GMRAI — TRADE_ENS XAUUSD',
  description: 'Nền tảng nghiên cứu tín hiệu XAUUSD M15 bằng TRADE_ENS: LONG / SHORT / NO_TRADE.',
};

export const viewport: Viewport = {
  themeColor: '#0a0d12',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
