import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DirectionEntry } from '@/components/direction/direction-entry';
import { ThemeProvider } from '@/lib/theme-provider';

const login = vi.fn().mockRejectedValue(new Error('login failed'));

vi.mock('@/lib/auth', () => ({
  useAuth: () => ({
    login,
    session: null,
    loading: false,
    signup: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe('DirectionEntry', () => {
  it('states a failed sign-in in the panel rather than redirecting', async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <DirectionEntry initialMode="login" openOnMount />
      </ThemeProvider>,
    );

    await user.type(screen.getByLabelText(/^email$/i), 'shivam@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'wrong-password');
    await user.click(screen.getByRole('button', { name: /enter aurasql/i }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/did not match an account/i),
    );
  });

  it('refuses a registration whose passwords disagree, before calling the API', async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <DirectionEntry initialMode="register" openOnMount />
      </ThemeProvider>,
    );

    await user.type(screen.getByLabelText(/^email$/i), 'shivam@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'correct-horse');
    await user.type(screen.getByLabelText(/confirm password/i), 'correct-house');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/passwords do not match/i);
  });

  it('renders the landing with no panel until a way in is chosen', async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <DirectionEntry initialMode="login" />
      </ThemeProvider>,
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    // The hero must be readable at rest — it is the first frame of the app.
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/ask in plain english/i);

    await user.click(screen.getByRole('button', { name: /^log in$/i }));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });
});
