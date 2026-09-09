import { KeystoneEntry } from '@/components/keystone/keystone-entry';

/**
 * `?auth=login` / `?auth=register` opens the panel on arrival, so a redirect
 * from a protected route lands on the form rather than on the landing.
 * Resolved here, in the server component, rather than read from
 * `window.location` on the client — that would have to happen in an effect,
 * one render after the page has already painted without the panel.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ auth?: string }>;
}) {
  const { auth } = await searchParams;
  const mode = auth === 'register' ? 'register' : 'login';
  return <KeystoneEntry initialMode={mode} openOnMount={auth === 'login' || auth === 'register'} />;
}
