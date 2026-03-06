import { render, type RenderOptions } from '@testing-library/react';
import { UserProvider } from '../contexts/UserContext';
import { EnvironmentProvider } from '../contexts/EnvironmentContext';
import type { ReactElement } from 'react';

export function renderWithEnv(ui: ReactElement, options?: RenderOptions) {
  return render(
    <UserProvider>
      <EnvironmentProvider>{ui}</EnvironmentProvider>
    </UserProvider>,
    options
  );
}
