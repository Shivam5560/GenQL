import { test, expect } from '@playwright/test';

// Requires the full stack running: FastAPI backend, self-hosted GoTrue, and
// this Next.js app, all pointed at each other per apps/web/.env.local.example.
// Run manually against a real environment — this is not part of `npm run test`.
test('register, ask a question, execute, sign out', async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;

  await page.goto('/signup');
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill('a-secure-password-1');
  await page.getByRole('button', { name: /create account/i }).click();

  await expect(page).toHaveURL('/');
  await page.getByPlaceholder(/ask a question/i).fill('How many orders were placed last quarter?');
  await page.getByRole('button', { name: /send/i }).click();

  await expect(page).toHaveURL(/\/thread\//);
  await expect(page.getByRole('button', { name: /run query/i })).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: /run query/i }).click();
  await expect(page.getByRole('button', { name: /^yes$/i })).toBeVisible();

  await page.goto('/settings');
  await page.getByRole('button', { name: /sign out/i }).click();
  await expect(page).toHaveURL('/login');
});
