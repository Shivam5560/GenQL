import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ThreadList } from '@/components/sidebar/thread-list';
import type { ThreadSummary } from '@/lib/types';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

function threads(count: number): ThreadSummary[] {
  return Array.from({ length: count }, (_, i) => ({
    thread_id: `t-${i}`,
    datasource_name: 'local',
    title: `Question number ${i}`,
    created_at: '2026-09-10T00:00:00Z',
    last_active_at: '2026-09-10T00:00:00Z',
  }));
}

describe('ThreadList', () => {
  it('renders a fixed page rather than every thread', () => {
    // The sidebar grew past the viewport and scrolled as a whole, taking
    // "New thread" and "Settings" off screen with it. A page of constant
    // length is what keeps everything around the list pinned.
    render(<ThreadList threads={threads(30)} />);

    expect(screen.getAllByRole('link')).toHaveLength(8);
    expect(screen.getByText('1–8 of 30')).toBeInTheDocument();
  });

  it('pages forward and back through the rest', () => {
    render(<ThreadList threads={threads(30)} />);

    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText('9–16 of 30')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /prev/i }));
    expect(screen.getByText('1–8 of 30')).toBeInTheDocument();
  });

  it('offers no pager when everything already fits', () => {
    render(<ThreadList threads={threads(3)} />);

    expect(screen.queryByRole('button', { name: /next/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole('link')).toHaveLength(3);
  });

  it('says so plainly when there are no threads yet', () => {
    render(<ThreadList threads={[]} />);

    expect(screen.getByText('No threads yet.')).toBeInTheDocument();
  });
});
