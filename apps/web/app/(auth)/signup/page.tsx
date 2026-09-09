import { KeystoneEntry } from '@/components/keystone/keystone-entry';

/**
 * The same entry screen as `/login`, with the panel opened on the create-account
 * side. One composition, two doors — rather than a second, thinner page that
 * would have to be kept visually in step with the first.
 */
export default function SignupPage() {
  return <KeystoneEntry initialMode="register" openOnMount />;
}
