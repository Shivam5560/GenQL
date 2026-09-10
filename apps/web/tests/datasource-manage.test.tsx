import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConnectForm } from '@/components/datasources/connect-form';
import { DatasourceRow } from '@/components/datasources/datasource-row';
import { EditForm } from '@/components/datasources/edit-form';
import type { Datasource } from '@/lib/types';

const WH: Datasource = {
  name: 'warehouse',
  dialect: 'postgres',
  description: 'production',
  enabled: true,
  endpoint: 'warehouse.internal:5432/analytics',
};

describe('ConnectForm dialect', () => {
  it('offers the dialects the server registered instead of a fixed one', () => {
    render(
      <ConnectForm
        dialects={['postgres', 'snowflake']}
        onSubmit={() => {}}
        onCancel={() => {}}
        submitting={false}
        error={null}
      />,
    );

    const select = screen.getByLabelText('Dialect') as HTMLSelectElement;

    expect(select.disabled).toBe(false);
    expect([...select.options].map((o) => o.value)).toEqual(['postgres', 'snowflake']);
  });

  it('submits the dialect that was chosen', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <ConnectForm
        dialects={['postgres', 'snowflake']}
        onSubmit={onSubmit}
        onCancel={() => {}}
        submitting={false}
        error={null}
      />,
    );

    await user.type(screen.getByLabelText('Name'), 'wh');
    await user.selectOptions(screen.getByLabelText('Dialect'), 'snowflake');
    await user.type(screen.getByLabelText('Host'), 'wh.internal');
    await user.type(screen.getByLabelText('Database'), 'analytics');
    await user.type(screen.getByLabelText('User'), 'reader');
    await user.click(screen.getByRole('button', { name: /connect/i }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ dialect: 'snowflake' }));
  });
});

describe('DatasourceRow', () => {
  it('offers edit and remove', () => {
    render(<DatasourceRow datasource={WH} onEdit={() => {}} onRemove={() => {}} />);

    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^remove$/i })).toBeInTheDocument();
  });

  it('asks for confirmation before removing, in the row rather than a dialog', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(<DatasourceRow datasource={WH} onEdit={() => {}} onRemove={onRemove} />);

    await user.click(screen.getByRole('button', { name: /^remove$/i }));

    expect(onRemove).not.toHaveBeenCalled();
    expect(screen.getByText(/everything discovered/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /delete it/i }));

    expect(onRemove).toHaveBeenCalledOnce();
  });

  it('abandons a confirmation that is cancelled', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(<DatasourceRow datasource={WH} onEdit={() => {}} onRemove={onRemove} />);

    await user.click(screen.getByRole('button', { name: /^remove$/i }));
    await user.click(screen.getByRole('button', { name: /keep it/i }));

    expect(onRemove).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /^remove$/i })).toBeInTheDocument();
  });
});

describe('EditForm', () => {
  it('opens on what the datasource already points at', () => {
    render(
      <EditForm
        datasource={WH}
        dialects={['postgres']}
        onSubmit={() => {}}
        onCancel={() => {}}
        submitting={false}
        error={null}
      />,
    );

    expect((screen.getByLabelText('Host') as HTMLInputElement).value).toBe('warehouse.internal');
    expect((screen.getByLabelText('Port') as HTMLInputElement).value).toBe('5432');
    expect((screen.getByLabelText('Database') as HTMLInputElement).value).toBe('analytics');
  });

  it('sends only the fields that changed', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <EditForm
        datasource={WH}
        dialects={['postgres']}
        onSubmit={onSubmit}
        onCancel={() => {}}
        submitting={false}
        error={null}
      />,
    );

    await user.clear(screen.getByLabelText('Host'));
    await user.type(screen.getByLabelText('Host'), 'new.internal');
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(onSubmit).toHaveBeenCalledWith({ host: 'new.internal' });
  });

  it('leaves the password out unless it was typed', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <EditForm
        datasource={WH}
        dialects={['postgres']}
        onSubmit={onSubmit}
        onCancel={() => {}}
        submitting={false}
        error={null}
      />,
    );

    await user.type(screen.getByLabelText('Description'), '!');
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(onSubmit).toHaveBeenCalledWith({ description: 'production!' });
  });

  it('can turn a datasource off', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <EditForm
        datasource={WH}
        dialects={['postgres']}
        onSubmit={onSubmit}
        onCancel={() => {}}
        submitting={false}
        error={null}
      />,
    );

    await user.click(screen.getByLabelText(/enabled/i));
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(onSubmit).toHaveBeenCalledWith({ enabled: false });
  });
});
