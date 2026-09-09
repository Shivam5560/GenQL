import { NextRequest, NextResponse } from 'next/server';

const GOTRUE_URL = process.env.GOTRUE_URL ?? 'http://localhost:9999';
const REFRESH_COOKIE = 'gq_refresh';
const REFRESH_COOKIE_PATH = '/api/auth';

function setRefreshCookie(response: NextResponse, refreshToken: string): void {
  response.cookies.set(REFRESH_COOKIE, refreshToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: REFRESH_COOKIE_PATH,
    maxAge: 60 * 60 * 24 * 30,
  });
}

function clearRefreshCookie(response: NextResponse): void {
  // The path must match the one the cookie was set with, or the browser keeps it.
  response.cookies.delete({ name: REFRESH_COOKIE, path: REFRESH_COOKIE_PATH });
}

interface GoTrueSession {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: { id: string; email: string };
}

function sessionBody(gotrue: GoTrueSession) {
  return {
    access_token: gotrue.access_token,
    expires_in: gotrue.expires_in,
    user: { id: gotrue.user.id, email: gotrue.user.email },
  };
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ action: string[] }> },
): Promise<NextResponse> {
  const { action } = await params;
  const step = action[0];

  if (step === 'signup' || step === 'login') {
    const { email, password } = await request.json();
    const gotrueUrl =
      step === 'signup' ? `${GOTRUE_URL}/signup` : `${GOTRUE_URL}/token?grant_type=password`;
    const gotrueResponse = await fetch(gotrueUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!gotrueResponse.ok) {
      return new NextResponse(await gotrueResponse.text(), { status: gotrueResponse.status });
    }
    const body: GoTrueSession = await gotrueResponse.json();
    const response = NextResponse.json(sessionBody(body));
    setRefreshCookie(response, body.refresh_token);
    return response;
  }

  if (step === 'refresh') {
    const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
    if (!refreshToken) return new NextResponse('no refresh token', { status: 401 });
    const gotrueResponse = await fetch(`${GOTRUE_URL}/token?grant_type=refresh_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!gotrueResponse.ok) {
      const response = new NextResponse(await gotrueResponse.text(), {
        status: gotrueResponse.status,
      });
      clearRefreshCookie(response);
      return response;
    }
    const body: GoTrueSession = await gotrueResponse.json();
    const response = NextResponse.json(sessionBody(body));
    setRefreshCookie(response, body.refresh_token);
    return response;
  }

  if (step === 'callback') {
    const { refresh_token } = await request.json();
    const gotrueResponse = await fetch(`${GOTRUE_URL}/token?grant_type=refresh_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token }),
    });
    if (!gotrueResponse.ok) {
      return new NextResponse(await gotrueResponse.text(), { status: gotrueResponse.status });
    }
    const body: GoTrueSession = await gotrueResponse.json();
    const response = NextResponse.json(sessionBody(body));
    setRefreshCookie(response, body.refresh_token);
    return response;
  }

  if (step === 'logout') {
    const { access_token } = await request.json().catch(() => ({ access_token: undefined }));
    if (access_token) {
      // GoTrue's /logout invalidates a session given the ACCESS token as Bearer,
      // not the refresh token — so the client sends its access token in the body.
      await fetch(`${GOTRUE_URL}/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${access_token}` },
      }).catch(() => undefined); // best-effort — the cookie clears either way
    }
    const response = new NextResponse(null, { status: 204 });
    clearRefreshCookie(response);
    return response;
  }

  return new NextResponse('unknown auth action', { status: 404 });
}
