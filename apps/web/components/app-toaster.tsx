'use client';

import { Toaster } from 'sonner';
import { useTheme } from '@/lib/theme-provider';
import { resolveMode } from '@/lib/theme';

/**
 * Sonner has its own theme detection, but this app already threads a single
 * source of truth for light/dark through ThemeProvider (see
 * lib/theme-provider.tsx) — toasts follow that instead of guessing again from
 * `prefers-color-scheme` on their own.
 */
export function AppToaster(): React.JSX.Element {
  const { preference } = useTheme();
  // resolveMode() reads matchMedia, which does not exist during the server
  // render of this client component — 'system' is a safe placeholder there;
  // sonner's own system detection covers that one frame until the client
  // render (with `window`) takes over.
  const mode = typeof window === 'undefined' ? 'system' : resolveMode(preference);
  return (
    <Toaster
      theme={mode}
      position="top-right"
      toastOptions={{
        classNames: {
          toast: 'gq-toast',
          title: 'gq-toast-title',
          description: 'gq-toast-description',
          actionButton: 'gq-toast-action',
          cancelButton: 'gq-toast-cancel',
          closeButton: 'gq-toast-close',
          error: 'gq-toast-error',
          success: 'gq-toast-success',
        },
      }}
    />
  );
}
