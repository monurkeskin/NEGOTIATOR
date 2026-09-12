import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 45000,
  use: { baseURL: 'http://127.0.0.1:8769', trace: 'retain-on-failure' },
  webServer: {
    command: `../.venv/bin/python -m negotiator gui --no-browser --port 8769 --data-dir ../test-results/browser-${Date.now()}`,
    env: { NEGOTIATOR_ACCESS_TOKEN: 'synthetic-browser-test' },
    url: 'http://127.0.0.1:8769/api/health',
    reuseExistingServer: false,
    timeout: 30000,
  },
});
