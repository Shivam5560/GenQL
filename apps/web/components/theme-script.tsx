import { THEME_STORAGE_KEY } from '@/lib/theme';

// Runs before first paint, so the page never flashes the wrong theme while the
// profile request is in flight. Mirrors applyTheme() in lib/theme.ts exactly.
const BOOT = `(function(){try{var r=document.documentElement,k=${JSON.stringify(
  THEME_STORAGE_KEY,
)},p=localStorage.getItem(k);if(p!=='light'&&p!=='dark')p='system';if(p==='system')r.removeAttribute('data-theme');else r.setAttribute('data-theme',p);r.classList.toggle('dark',p==='dark'||(p==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches));}catch(e){}})();`;

export function ThemeScript(): React.JSX.Element {
  return <script dangerouslySetInnerHTML={{ __html: BOOT }} />;
}
