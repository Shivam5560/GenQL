'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';

interface AuthUser {
  id: string;
  email: string;
}

interface Session {
  accessToken: string;
  expiresAt: number;
  user: AuthUser;
}

interface AuthContextValue {
  session: Session | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

interface SessionMessage {
  type: 'session';
  session: Session | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const REFRESH_MARGIN_MS = 60_000;
const CHANNEL_NAME = 'genql-auth';
const LOCK_KEY = 'genql_refresh_lock';
const LOCK_TTL_MS = 10_000;
const LOCK_POLL_MS = 100;
const REFRESH_RETRY_MS = 15_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Best-effort cross-tab lock. Returns a stamp identifying our hold, or null if
 * another tab holds a lock that has not yet gone stale. The stamp is unique so
 * that two tabs writing in the same millisecond can still tell their holds
 * apart; the read-back is a last-writer-wins tiebreak, not a true CAS, so this
 * narrows the race rather than eliminating it. That is sufficient here: losing
 * the race costs at most one redundant refresh call, never a lost session.
 */
function tryAcquireRefreshLock(): string | null {
  try {
    const now = Date.now();
    const raw = localStorage.getItem(LOCK_KEY);
    if (raw && now - Number(raw.split(':')[0]) < LOCK_TTL_MS) return null;
    const stamp = `${now}:${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(LOCK_KEY, stamp);
    return localStorage.getItem(LOCK_KEY) === stamp ? stamp : null;
  } catch {
    return `local:${Date.now()}`; // localStorage unavailable (private mode) — just proceed
  }
}

function releaseRefreshLock(stamp: string): void {
  try {
    if (localStorage.getItem(LOCK_KEY) === stamp) localStorage.removeItem(LOCK_KEY);
  } catch {
    // localStorage unavailable — the lock was never written, nothing to release.
  }
}

async function toSession(response: Response): Promise<Session | null> {
  if (!response.ok) return null;
  const data: { access_token: string; expires_in: number; user: AuthUser } = await response.json();
  return {
    accessToken: data.access_token,
    expiresAt: Date.now() + data.expires_in * 1000,
    user: data.user,
  };
}

export function AuthProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const channelRef = useRef<BroadcastChannel | null>(null);
  // Bumped every time another tab hands us a session, so a tab that lost the
  // refresh lock can tell whether the winner has reported back yet.
  const peerEpochRef = useRef(0);
  // The timer fires long after mount, so it reads the refresh function from a
  // ref instead of closing over a binding declared further down this component.
  const refreshRef = useRef<() => Promise<void>>(async () => {});
  // One refresh at a time per tab, shared by every caller.
  const inFlightRef = useRef<Promise<void> | null>(null);

  const scheduleRefresh = useCallback((expiresAt: number) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    const delay = Math.max(expiresAt - Date.now() - REFRESH_MARGIN_MS, 0);
    timerRef.current = setTimeout(() => {
      void refreshRef.current();
    }, delay);
  }, []);

  const applySession = useCallback(
    (next: Session | null, broadcast = true) => {
      setSession(next);
      if (next) scheduleRefresh(next.expiresAt);
      else if (timerRef.current) clearTimeout(timerRef.current);
      if (broadcast) {
        try {
          channelRef.current?.postMessage({ type: 'session', session: next } as SessionMessage);
        } catch {
          // BroadcastChannel unsupported — this tab manages its own session only.
        }
      }
    },
    [scheduleRefresh],
  );

  const refreshSession = useCallback((): Promise<void> => {
    // Coalesce concurrent callers in this tab. This also keeps React StrictMode's
    // double-invoked mount effect from racing itself over the rotating token.
    if (inFlightRef.current) return inFlightRef.current;

    const run = (async () => {
      const startEpoch = peerEpochRef.current;
      let stamp = tryAcquireRefreshLock();

      // Another tab is already refreshing. Wait for its broadcast rather than
      // firing a second /api/auth/refresh: GoTrue rotates the refresh token, so
      // a concurrent call races it and one of the two is rejected. The winner
      // broadcasts before releasing the lock, so the lock becoming free means
      // either the new session already reached us or the holder died mid-flight
      // — in both cases we stop waiting and take over. The grace on the deadline
      // guarantees we outlive a stale lock instead of giving up one tick early.
      const deadline = Date.now() + LOCK_TTL_MS + LOCK_POLL_MS * 2;
      while (stamp === null && Date.now() < deadline) {
        await sleep(LOCK_POLL_MS);
        if (peerEpochRef.current !== startEpoch) return;
        stamp = tryAcquireRefreshLock();
      }
      if (stamp === null) return;

      try {
        const response = await fetch('/api/auth/refresh', { method: 'POST' });
        // A rejected refresh is applied locally but never broadcast: another tab
        // may hold a perfectly good session, and telling it to drop one would log
        // the whole browser out over this tab's bad luck. If a peer succeeds
        // later, its broadcast restores this tab.
        applySession(await toSession(response), response.ok);
      } catch {
        // Network failure rather than a rejected token — keep the session we
        // have and retry shortly, so a blip does not strand this tab with a
        // token that quietly expires.
        scheduleRefresh(Date.now() + REFRESH_MARGIN_MS + REFRESH_RETRY_MS);
      } finally {
        releaseRefreshLock(stamp);
      }
    })();

    inFlightRef.current = run;
    return run.finally(() => {
      inFlightRef.current = null;
    });
  }, [applySession, scheduleRefresh]);

  useEffect(() => {
    refreshRef.current = refreshSession;
  }, [refreshSession]);

  useEffect(() => {
    let channel: BroadcastChannel | null = null;
    try {
      channel = new BroadcastChannel(CHANNEL_NAME);
      // One channel object per tab, used to both send and receive: a
      // BroadcastChannel never delivers to the object that posted, so this tab
      // does not hear its own broadcasts, and nothing is left open per message.
      channel.onmessage = (event: MessageEvent<SessionMessage>) => {
        if (event.data?.type !== 'session') return;
        peerEpochRef.current += 1;
        applySession(event.data.session, false);
      };
      channelRef.current = channel;
    } catch {
      // no BroadcastChannel support
    }
    void refreshSession().finally(() => setLoading(false));
    return () => {
      channel?.close();
      channelRef.current = null;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) throw new Error('login failed');
      applySession(await toSession(response));
    },
    [applySession],
  );

  const signup = useCallback(
    async (email: string, password: string) => {
      const response = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) throw new Error('signup failed');
      applySession(await toSession(response));
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: session?.accessToken }),
    });
    // An explicit logout is broadcast — every tab in this browser shares the
    // refresh cookie the route handler just cleared.
    applySession(null);
  }, [applySession, session]);

  return (
    <AuthContext.Provider value={{ session, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export type { AuthUser, Session, AuthContextValue };
