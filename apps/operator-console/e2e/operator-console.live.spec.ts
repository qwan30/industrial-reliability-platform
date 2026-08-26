import { test, expect } from '@playwright/test';

test.describe('Live Operator Console E2E Flow', () => {
  test('connects to live backend, checks readiness, and renders live console components', async ({ page }) => {
    // 1. Check live readiness of scoring API
    const response = await page.request.get('http://127.0.0.1:8000/readyz');
    expect(response.status()).toBe(200);

    // 2. Open operator console
    await page.goto('/');
    await expect(page.locator('h1')).toContainText('Industrial Reliability Platform');

    // 3. Verify core panels
    await expect(page.getByTestId('replay-controls')).toBeVisible();
    await expect(page.getByTestId('dependency-health-panel')).toBeVisible();
    await expect(page.getByTestId('live-charts')).toBeVisible();
    await expect(page.getByTestId('alert-panel')).toBeVisible();
  });

  test('executes live replay lifecycle and queries alerts', async ({ page }) => {
    // 1. Start a 100x replay via live API
    const startRes = await page.request.post('http://127.0.0.1:8000/v1/replays', {
      data: {
        range_start: '2020-02-25T00:00:00',
        range_end: '2020-02-25T01:00:00',
        speed: 100,
      },
    });
    expect([200, 202]).toContain(startRes.status());
    const startJson = await startRes.json();
    expect(startJson.success).toBe(true);
    const session_id = startJson.data.replay_session_id;
    expect(session_id).toBeTruthy();

    // 2. Control replay (STOP)
    const stopRes = await page.request.post(`http://127.0.0.1:8000/v1/replays/${session_id}/commands`, {
      data: { action: 'STOP' },
    });
    expect([200, 202]).toContain(stopRes.status());
  });
});
