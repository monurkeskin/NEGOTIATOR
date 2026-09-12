import { test, expect } from '@playwright/test';

test('published protocol omissions are visible and cannot start from conductor', async ({ page, request }) => {
  const headers = { 'X-Negotiator-Token': 'synthetic-browser-test' };
  const response = await request.post('/api/studies', { headers, data: {
    study_id: 'missing-assets', participant_id: 'SYNTHETIC_PREFLIGHT', purpose: 'published-protocol',
    protocol: { id: 'fixture', revision: '1', paper: 'https://example.org/paper',
      requirements: [{ id: 'questionnaire', description: 'Original questionnaire' }] },
  } });
  const { plan_id } = await response.json();
  await page.goto(`/?plan=${plan_id}#token=synthetic-browser-test`);
  await expect(page.getByText('Original questionnaire', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start session', exact: true })).toBeDisabled();
});

test('the participant sees a timed break and cannot continue early', async ({ page, request }) => {
  const headers = { 'X-Negotiator-Token': 'synthetic-browser-test' };
  const response = await request.post('/api/studies', { headers, data: {
    study_id: 'break', participant_id: 'SYNTHETIC_BREAK', preference_mode: 'assigned',
    conditions: [{ break_after_seconds: 300 }, {}],
  } });
  const { plan_id, participant_token } = await response.json();
  const started = await request.post(`/api/studies/${plan_id}/start`, { headers });
  const current = (await started.json()).current;
  await request.post(`/api/studies/${plan_id}/command`, { headers, data: {
    request_id: 'end', kind: 'withdraw', session_id: current.config.session_id,
  } });
  await page.goto(`/?view=participant&plan=${plan_id}#token=${participant_token}`);
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(page.getByLabel('Break time remaining')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeDisabled();
});

test('conductor and participant complete two sessions with preferences, refresh and clean history', async ({ page, context }) => {
  await page.goto('/#token=synthetic-browser-test');
  await page.getByRole('button', { name: 'New study', exact: true }).click();
  await page.getByLabel('Study title').fill('Synthetic browser study');
  await page.getByLabel('Participant ID').fill('BROWSER001');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Domain and preferences' })).toBeVisible();
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await page.getByRole('button', { name: 'Add session' }).click();
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await page.getByRole('button', { name: 'Create study', exact: true }).click();
  const participantLink = page.getByRole('link', { name: 'Open participant view' });
  await expect(participantLink).toBeVisible();
  const participant = await context.newPage();
  await participant.goto((await participantLink.getAttribute('href'))!);
  await expect(participant.getByRole('heading', { name: 'What matters to you?' })).toBeVisible();
  await participant.getByRole('button', { name: 'Move Destination up', exact: true }).click();
  await participant.getByRole('button', { name: 'Confirm preferences' }).click();
  await page.getByRole('button', { name: 'Start session', exact: true }).click();
  await participant.getByLabel('Your message').fill('Hotel');
  await participant.getByRole('button', { name: 'Send text' }).click();
  await expect(participant.getByText('Clarify your offer')).toBeVisible();
  await participant.getByRole('button', { name: 'Send offer', exact: true }).click();
  await expect(participant.getByRole('button', { name: 'Accept offer', exact: true })).toBeEnabled();
  await participant.screenshot({ path: 'test-results/participant.png', fullPage: true });
  await expect(page.getByText('2 offers', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/conductor.png', fullPage: true });
  await participant.getByRole('button', { name: 'Accept offer', exact: true }).click();
  await expect(participant.getByRole('heading', { name: 'Agreement reached' })).toBeVisible();
  await participant.reload();
  await expect(participant.getByRole('heading', { name: 'Agreement reached' })).toBeVisible();
  await participant.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(participant.getByRole('heading', { name: 'Take a short break' })).toBeVisible();
  await participant.getByRole('button', { name: 'Continue', exact: true }).click();
  await participant.getByRole('button', { name: 'Confirm preferences' }).click();
  await page.getByRole('button', { name: 'Start session', exact: true }).click();
  await expect(participant.getByText('No offers yet')).toBeVisible();
  await participant.getByRole('button', { name: 'Withdraw', exact: true }).click();
  await expect(participant.getByRole('heading', { name: 'Session ended' })).toBeVisible();
  await participant.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(participant.getByRole('heading', { name: 'Thank you' })).toBeVisible();
  await page.getByRole('button', { name: 'Build report', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Open report', exact: true })).toBeVisible({ timeout: 30000 });
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download all files (ZIP)' }).click();
  expect((await download).suggestedFilename()).toBe('negotiator-report.zip');
});

test('server deadline reaches the participant screen and stays terminal after refresh', async ({ page, request }) => {
  const headers = { 'X-Negotiator-Token': 'synthetic-browser-test' };
  const response = await request.post('/api/studies', { headers, data: {
    study_id: 'timer', participant_id: 'SYNTHETIC_TIMER', preference_mode: 'assigned',
    conditions: [{ label: 'Short synthetic session', strategy: 'hybrid', duration_seconds: 2, practice: true }],
  } });
  const { plan_id, participant_token } = await response.json();
  await request.post(`/api/studies/${plan_id}/start`, { headers });
  await page.goto(`/?view=participant&plan=${plan_id}#token=${participant_token}`);
  await expect(page.getByRole('heading', { name: 'Session ended' })).toBeVisible({ timeout: 10000 });
  await expect(page.getByText('The session ended: deadline.')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Session ended' })).toBeVisible();
  const state = await request.get(`/api/studies/${plan_id}`, { headers: { 'X-Negotiator-Token': participant_token } });
  expect((await state.json()).current.remaining_seconds).toBe(0);
});

test('preference ranking remains usable with a narrow viewport and keyboard controls', async ({ page, request }) => {
  const response = await request.post('/api/studies', { headers: { 'X-Negotiator-Token': 'synthetic-browser-test' }, data: {
    study_id: 'mobile', participant_id: 'SYNTHETIC_MOBILE', domain: 'island', preference_mode: 'elicited',
  } });
  const { plan_id, participant_token } = await response.json();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/?view=participant&plan=${plan_id}#token=${participant_token}`);
  const button = page.getByRole('button', { name: 'Move food up', exact: true });
  await button.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.rank-heading h2').first()).toHaveText('food');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/preferences-mobile.png', fullPage: true });
});

test('a camera permission response arriving after leaving the panel closes its stream', async ({ page, request }) => {
  await page.addInitScript(() => {
    const state = window as typeof window & { resolveCamera: () => void; stoppedTracks: number; requestedCamera: boolean };
    state.stoppedTracks = 0;
    state.requestedCamera = false;
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: () => new Promise(resolve => {
      state.requestedCamera = true;
      state.resolveCamera = () => resolve({ getTracks: () => [{ stop: () => { state.stoppedTracks += 1; } }] });
    }) });
  });
  const response = await request.post('/api/studies', { headers: { 'X-Negotiator-Token': 'synthetic-browser-test' }, data: {
    study_id: 'camera', participant_id: 'SYNTHETIC_CAMERA', preference_mode: 'assigned', synthetic: true,
  } });
  const { plan_id } = await response.json();
  await page.goto(`/?plan=${plan_id}#token=synthetic-browser-test`);
  await page.getByText('Camera preview', { exact: true }).click();
  await page.getByRole('button', { name: 'Preview selected camera' }).click();
  await expect.poll(() => page.evaluate(() => (window as typeof window & { requestedCamera: boolean }).requestedCamera)).toBe(true);
  await page.getByRole('button', { name: 'New study', exact: true }).click();
  await page.evaluate(() => (window as typeof window & { resolveCamera: () => void }).resolveCamera());
  await expect.poll(() => page.evaluate(() => (window as typeof window & { stoppedTracks: number }).stoppedTracks)).toBe(1);
});

test('notification, rejection and offer entry remain separate after refresh', async ({ page, request }) => {
  const headers = { 'X-Negotiator-Token': 'synthetic-browser-test' };
  const created = await request.post('/api/studies', { headers, data: {
    study_id: 'dialogue', participant_id: 'SYNTHETIC_DIALOGUE', preference_mode: 'assigned',
    interaction_protocol: 'ready-offer-response',
  } });
  const { plan_id, participant_token } = await created.json();
  await request.post(`/api/studies/${plan_id}/start`, { headers });
  await page.goto(`/?view=participant&plan=${plan_id}#token=${participant_token}`);
  const offer = page.getByRole('button', { name: 'Send offer', exact: true });
  await expect(offer).toBeDisabled();
  await page.getByRole('button', { name: 'Ready to propose', exact: true }).click();
  await expect(offer).toBeEnabled();
  await offer.click();
  await expect(page.getByRole('button', { name: 'Reject offer', exact: true })).toBeEnabled();
  await expect(offer).toBeDisabled();
  await page.getByRole('button', { name: 'Reject offer', exact: true }).click();
  await page.reload();
  await expect(offer).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Ready to propose', exact: true })).toBeEnabled();
  await expect(page.getByText('2 offers', { exact: true })).toBeVisible();
});

test('a below-target agreement is allowed and the participant sees its game score', async ({ page, request }) => {
  const headers = { 'X-Negotiator-Token': 'synthetic-browser-test' };
  const profile = { weights: { apple: 1 }, scores: { apple: [0,1,2,3,4].map(q => ({value:q,score:q/4})) }, reservation: 0 };
  const response = await request.post('/api/studies', { headers, data: {
    study_id: 'rewards', participant_id: 'SYNTHETIC_REWARD', preference_mode: 'assigned', first_actor: 'agent',
    domain: { schema_version: 1, name: 'Synthetic score rule', issues: [{name:'apple',total:4}] },
    human_profile: profile, agent_profile: { ...profile, scores: { apple: [0,1,2,3,4].map(q => ({value:q,score:q === 3 ? .95 : q/8})) } },
    conditions: [{ strategy: "tsbt", score_targets: {human:.4}, reward_minimums: {human:.4} }],
  } });
  const { plan_id, participant_token } = await response.json();
  await request.post(`/api/studies/${plan_id}/start`, { headers });
  await page.goto(`/?view=participant&plan=${plan_id}#token=${participant_token}`);
  await expect(page.getByText('Target: 40.0/100', { exact: false })).toBeVisible();
  await page.getByRole('button', { name:'Accept offer',exact:true }).click();
  await expect(page.getByLabel('Game score')).toContainText('0.0');
  await expect(page.getByRole('heading', {name:'Agreement reached'})).toBeVisible();
});
