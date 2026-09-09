import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LoginPage from '@/app/(auth)/login/page';

vi.mock('@/lib/auth', () => ({
  useAuth: () => ({
    login: vi.fn().mockRejectedValue(new Error('login failed')),
    session: null,
    loading: false,
    signup: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe('LoginPage', () => {
  it('shows an error message when login fails, without redirecting', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), 'shivam@example.com');
    await user.type(screen.getByLabelText(/password/i), 'wrong-password');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByText(/email or password is incorrect/i)).toBeInTheDocument(),
    );
  });
});
