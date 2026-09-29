'use strict';
const { defineConfig } = require('@playwright/test');

// On Windows the UI tests drive the Edge every machine already has, so no
// browser download is needed; elsewhere, Playwright's own Chromium.
// WORK_IDE_TEST_CHANNEL overrides (e.g. "chrome", or "" for the bundled one).
const envChannel = process.env.WORK_IDE_TEST_CHANNEL;
const channel = envChannel !== undefined
  ? envChannel || undefined
  : (process.platform === 'win32' ? 'msedge' : undefined);

module.exports = defineConfig({
  timeout: 30000,
  reporter: [['list']],
  projects: [
    // The real renderer in headless Chromium, window.api mocked.
    { name: 'ui', testDir: './test/ui', use: { browserName: 'chromium', channel, headless: true } },
    // The real Electron window over a fixture repository, the agent faked.
    { name: 'smoke', testDir: './test/smoke' },
  ],
});
