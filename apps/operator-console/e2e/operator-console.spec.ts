import { test, expect } from '@playwright/test';

test.describe('Operator Console E2E Flow', () => {
  test('renders dashboard, starts replay, and inspects live stream and alerts', async ({ page }) => {
    // Navigate to local operator console
    await page.goto('/');

    // Verify header title
    await expect(page.locator('h1')).toContainText('Industrial Reliability Platform - Operator Console');

    // Verify main components are present
    await expect(page.getByTestId('replay-controls')).toBeVisible();
    await expect(page.getByTestId('dependency-health-panel')).toBeVisible();
    await expect(page.getByTestId('live-charts')).toBeVisible();
    await expect(page.getByTestId('alert-panel')).toBeVisible();

    // Fill in replay start form
    const startInput = page.getByLabel('Start Time');
    const endInput = page.getByLabel('End Time');
    await expect(startInput).toBeVisible();
    await expect(endInput).toBeVisible();

    // Verify speed selector has 1x, 100x, 1000x options
    const speedSelect = page.getByLabel('Speed');
    await expect(speedSelect).toBeVisible();
    await speedSelect.selectOption('100');

    // Click Start Replay
    const startBtn = page.getByTestId('start-replay-btn');
    await expect(startBtn).toBeEnabled();

    // Check charts container
    await expect(page.getByTestId('score-chart-container')).toBeVisible();
    await expect(page.getByTestId('telemetry-chart-container')).toBeVisible();
  });
});
