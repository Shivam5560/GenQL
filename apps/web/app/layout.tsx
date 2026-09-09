import type { Metadata } from 'next';
import { IBM_Plex_Sans, JetBrains_Mono, Space_Mono } from 'next/font/google';
import { AuthProvider } from '@/lib/auth';
import '@/styles/tokens.css';
import './globals.css';

const plexSans = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-sans',
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono',
});
const spaceMono = Space_Mono({
  subsets: ['latin'],
  weight: ['400', '700'],
  variable: '--font-eyebrow',
});

export const metadata: Metadata = {
  title: 'GenQL',
  description: 'Ask your warehouse a question.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${jetbrainsMono.variable} ${spaceMono.variable}`}>
      <body className="font-sans">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
