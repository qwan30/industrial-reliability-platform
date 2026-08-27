import { test, expect } from '@playwright/test';

test.describe('Operator Console E2E Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept healthz check
    await page.route('**/healthz', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', database: 'ok' }),
      });
    });
  });

  test('renders dashboard, starts replay, and inspects live stream and alerts', async ({ page }) => {
    await page.route('**/v1/replays', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            replay_session_id: 'rep-e2e-1',
            machine_id: 'metropt3',
            state: 'RUNNING',
            speed: 100,
            range_start: '2020-04-18T00:00:00',
            range_end: '2020-04-18T00:10:00',
          },
          error: null,
        }),
      });
    });

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

  test('inspects alert drawer and generates grounded root-cause analysis', async ({ page }) => {
    // Intercept SSE stream with initial snapshot
    await page.route('**/v1/replays/rep-e2e-1/stream', async (route) => {
      const sseBody = [
        'event: snapshot\n',
        'data: ' +
          JSON.stringify({
            replay: {
              replay_session_id: 'rep-e2e-1',
              machine_id: 'metropt3',
              state: 'RUNNING',
              speed: 100,
              range_start: '2020-04-18T00:00:00',
              range_end: '2020-04-18T00:10:00',
            },
            alerts: [
              {
                alert_id: 'alt-e2e-1',
                replay_session_id: 'rep-e2e-1',
                machine_id: 'metropt3',
                state: 'OPEN',
                first_detection: '2020-04-18T00:00:00',
                last_detection: '2020-04-18T00:05:00',
                resolved_at: null,
                latest_decision_id: 'dec-1',
                policy_sha256: '0'.repeat(64),
              },
            ],
          }) +
          '\n\n',
      ].join('');

      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
        body: sseBody,
      });
    });

    // Intercept alert list and detail with RCA mocks
    await page.route('**/v1/replays/*/alerts', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            alerts: [
              {
                alert_id: 'alt-e2e-1',
                replay_session_id: 'rep-e2e-1',
                machine_id: 'metropt3',
                state: 'OPEN',
                first_detection: '2020-04-18T00:00:00',
                last_detection: '2020-04-18T00:05:00',
                resolved_at: null,
                latest_decision_id: 'dec-1',
                policy_sha256: '0'.repeat(64),
              },
            ],
          },
          error: null,
        }),
      });
    });

    await page.route('**/v1/alerts/alt-e2e-1', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            alert: {
              alert_id: 'alt-e2e-1',
              replay_session_id: 'rep-e2e-1',
              machine_id: 'metropt3',
              state: 'OPEN',
              first_detection: '2020-04-18T00:00:00',
              last_detection: '2020-04-18T00:05:00',
              resolved_at: null,
              latest_decision_id: 'dec-1',
              policy_sha256: '0'.repeat(64),
            },
            events: [],
            evidence: [
              {
                feature_name: 'tp2_mean',
                feature_value: 9.5,
                robust_deviation: 1.5,
              },
            ],
            decisions: [],
            rca: null,
          },
          error: null,
        }),
      });
    });

    await page.route('**/v1/alerts/alt-e2e-1/rca', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            schema_version: 'rca-report-v1',
            message_id: 'msg-e2e-1',
            replay_session_id: 'rep-e2e-1',
            source_dataset_sha256: '0'.repeat(64),
            contract_sha256: '1'.repeat(64),
            source_timestamp: '2020-04-18T00:05:00',
            emitted_at: '2020-04-18T00:05:01Z',
            report_id: 'rca-e2e-1',
            alert_id: 'alt-e2e-1',
            status: 'COMPLETE',
            summary: 'Discharge pressure elevated during compressor loading cycle.',
            observations: [
              {
                claim: 'tp2_mean exceeded normal operating baseline.',
                evidence_ids: ['evidence-111111111111111111111111'],
              },
            ],
            uncertainty: ['Anomaly evidence does not prove a mechanical root cause.'],
            next_checks: ['Inspect intake check valve and pressure transducers.'],
            evidence_ids: ['evidence-111111111111111111111111'],
            evidence_bundle_sha256: '2'.repeat(64),
            provider_model: 'gpt-4o',
          },
          error: null,
        }),
      });
    });

    await page.goto('/');

    // Connect to replay session
    await page.getByTestId('session-id-input').fill('rep-e2e-1');
    await page.getByTestId('connect-session-btn').click();

    // Wait for alerts to render and click the first alert row
    const alertRow = page.getByTestId('alert-item-alt-e2e-1');
    await expect(alertRow).toBeVisible();
    await alertRow.click();

    // Verify alert detail drawer opens
    await expect(page.getByTestId('alert-detail-drawer')).toBeVisible();
    await expect(page.getByTestId('evidence-table')).toBeVisible();
    await expect(page.getByTestId('rca-panel')).toBeVisible();

    // Click Generate RCA button
    const generateRcaBtn = page.getByTestId('generate-rca-btn');
    await expect(generateRcaBtn).toBeVisible();
    await generateRcaBtn.click();

    // Verify RCA content renders
    await expect(page.getByTestId('rca-status-badge')).toHaveTextContent('COMPLETE');
    await expect(page.getByTestId('rca-summary')).toContainText('Discharge pressure elevated');
    await expect(page.getByTestId('rca-citation-badge')).toHaveTextContent('evidence-111111111111111111111111');
    await expect(page.getByTestId('rca-uncertainty')).toContainText('does not prove a mechanical root cause');
  });
});

