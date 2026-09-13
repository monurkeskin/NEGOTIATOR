import { test, expect } from '@playwright/test';

const headers = { 'X-Negotiator-Token': 'synthetic-browser-test' };

test('scale meanings are visible and optional answers can remain missing', async ({ page, request }) => {
  const response = await request.post('/api/studies', { headers, data: {
    study_id: 'survey-anchors', participant_id: 'SYNTHETIC_ANCHORS', preference_mode: 'assigned',
    surveys: [{ id: 'rating', prompt: 'Synthetic rating', phase: 'pre_study', minimum: 1, maximum: 9,
      minimum_label: 'Strongly disagree', maximum_label: 'Strongly agree', required: false }],
  } });
  expect(response.ok()).toBe(true);
  const { plan_id, participant_token } = await response.json();
  await page.goto(`/?view=participant&plan=${plan_id}#token=${participant_token}`);
  await expect(page.getByText('1 — Strongly disagree', { exact: true })).toBeVisible({ timeout: 3000 });
  await expect(page.getByText('9 — Strongly agree', { exact: true })).toBeVisible({ timeout: 3000 });
  await page.getByRole('button', { name: 'Skip this question' }).click();
  await page.getByRole('button', { name: 'Save answers' }).click();
  const state = await request.get(`/api/studies/${plan_id}`, { headers });
  expect((await state.json()).phase).toBe('ready');
});

test('consecutive questionnaire phases do not carry previous answers forward', async ({ page, request }) => {
  const response = await request.post('/api/studies', { headers, data: {
    study_id: 'survey-phases', participant_id: 'SYNTHETIC_PHASES', preference_mode: 'assigned',
    surveys: [
      { id: 'rating', prompt: 'Before the study', phase: 'pre_study', minimum: 1, maximum: 9 },
      { id: 'rating', prompt: 'Before this session', phase: 'pre_session', minimum: 1, maximum: 9 },
    ],
  } });
  const { plan_id, participant_token } = await response.json();
  await page.goto(`/?view=participant&plan=${plan_id}#token=${participant_token}`);
  await page.getByRole('radio', { name: '9', exact: true }).check();
  await page.getByRole('button', { name: 'Save answers' }).click();
  await expect(page.getByText('Before this session', { exact: true })).toBeVisible();
  await expect(page.getByRole('radio', { checked: true })).toHaveCount(0, { timeout: 3000 });
});
