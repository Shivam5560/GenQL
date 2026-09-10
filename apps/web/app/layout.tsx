import type { Metadata } from 'next';
import { IBM_Plex_Sans, JetBrains_Mono, Newsreader, Space_Mono } from 'next/font/google';
import { AuthProvider } from '@/lib/auth';
import { ThemeProvider } from '@/lib/theme-provider';
import { ThemeScript } from '@/components/theme-script';
import { AppToaster } from '@/components/app-toaster';
import { PreconnectApi } from '@/components/preconnect-api';
import '@/styles/tokens.css';
import './globals.css';
import '@/styles/motion.css';
import '@/styles/toast.css';

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
// The entry screen's display face, and the only place a serif appears in this
// app. Declared here because next/font must be initialised at module scope;
// nothing in the workspace references `font-serif`, so the workspace's type
// system is unaffected.
const newsreader = Newsreader({
  subsets: ['latin'],
  weight: ['300', '400', '500'],
  style: ['normal', 'italic'],
  variable: '--font-newsreader',
});

export const metadata: Metadata = {
  title: 'AuraSQL',
  description: 'Ask your warehouse a question.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `suppressHydrationWarning`: ThemeScript below toggles `data-theme` and
    // the `dark` class on this element before React hydrates, so the DOM it
    // finds deliberately differs from the one the server rendered. Without
    // this, every page load logs a mismatch on <html>.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${plexSans.variable} ${jetbrainsMono.variable} ${spaceMono.variable} ${newsreader.variable}`}
    >
      <body className="font-sans">
        <PreconnectApi />
        <ThemeScript />
        <AuthProvider>
          <ThemeProvider>
            {children}
            <AppToaster />
          </ThemeProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
