import type { Metadata, Viewport } from 'next';
import './globals.css';
import { AuthProvider } from '@/components/AuthProvider';

export const metadata: Metadata = {
  title: 'GMRAI — Gold Market Regime AI Intelligence',
  description:
    'Nền tảng phân tích chế độ thị trường vàng XAUUSD bằng AI định lượng (HMM + Random Forest).',
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
