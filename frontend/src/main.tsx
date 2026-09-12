import { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, participant, participantUrl, token } from './api';
import { Participant, History, OfferPlot, clockText } from './Participant';
import { CameraPreview } from './Devices';
import { Wizard } from './Wizard';
import { type Catalog, type Study, newRequest, score } from './types';
import './style.css';

const phaseName: Record<string, string> = { preferences: 'Preference preparation', ready: 'Ready to start', active: 'In progress', result: 'Session ended', break: 'Between sessions', survey: 'Questionnaire', complete: 'Complete' };

function Conductor({ study, refresh, fail }: { study: Study; refresh: () => Promise<void>; fail: (s: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [report, setReport] = useState<{report_id: string; html: string} | null>(null);
  const [preflight, setPreflight] = useState<string>('');
  const [reason, setReason] = useState('');
  const session = study.current;
  async function act(path: string, body?: unknown) {
    setBusy(true); fail('');
    try { await api(`/studies/${study.plan_id}/${path}`, 'POST', body); await refresh(); if (path === 'note') setNote(''); }
    catch (e) { fail((e as Error).message); } finally { setBusy(false); }
  }
  return <><div className="section-title dashboard-title"><div><p className="eyebrow">Conductor workspace</p><h1>{study.title}</h1><p className="muted">{study.participant_id} · {study.domain.name} · Session {study.sequence_index} of {study.session_count}</p></div><span className={`badge ${study.phase}`}>{phaseName[study.phase]}</span></div>
    <div className="control-strip"><div><strong>Participant display</strong><p>Open this separate view on the participant's screen.</p></div><a className="secondary" href={participantUrl(study.plan_id, study.participant_token!)} target="_blank" rel="noreferrer">Open participant view <span aria-hidden>↗</span></a></div>
    <div className="dashboard-grid"><section className="panel protocol"><div className="section-title"><h2>Session sequence</h2><span className="badge neutral">Config v{study.config_version}</span></div><ol className="schedule">{study.conditions?.map((condition, index) => <li className={index + 1 === study.sequence_index ? 'selected' : ''} key={index}><span>{index + 1}</span><div><strong>{condition.label}</strong><small>{condition.strategy} · {condition.duration_seconds / 60} min · {condition.practice ? 'Practice' : 'Study session'}</small></div>{study.completed_sessions.some(s => s.sequence_index === index + 1) && <b aria-label="Ended">✓</b>}</li>)}</ol>
      <p className="hint">{study.phase === 'preferences' ? 'Waiting for preference confirmation in the participant window.' : study.phase === 'ready' ? 'Preparation is complete. Start when both sides are ready.' : study.phase === 'active' ? 'The clock continues until agreement, withdrawal, deadline or explicit termination.' : study.phase === 'survey' ? 'The scheduled questionnaire is open in the participant window.' : 'The participant can continue through the configured sequence.'}</p>
      <button className="primary full" disabled={study.phase !== 'ready' || busy || Boolean(study.readiness?.length)} onClick={() => void act('start')}>Start session <span aria-hidden>→</span></button></section>
      <section className="panel live-summary"><div className="section-title"><h2>Session overview</h2><span className="status-dot">Local records</span></div><div className="stat-grid"><div><small>Offers</small><strong>{session?.offers.length ?? 0}</strong></div><div><small>Time remaining</small><strong>{session ? clockText(session.remaining_seconds) : '—'}</strong></div><div><small>Turn</small><strong className="word-stat">{session?.status === 'active' ? session.next_actor : '—'}</strong></div></div>
        {session && <OfferPlot offers={session.offers} />}{session?.outcome && <div className="outcome-summary"><strong>{session.outcome.reason.replaceAll('_', ' ')}</strong><span>Human: {score(session.outcome.utilities?.human)} · Agent: {score(session.outcome.utilities?.agent)}</span></div>}
      </section></div>
    {session && <History offers={session.offers} conductor />}
    <div className="dashboard-grid"><section className="panel"><h2>Operator notes</h2><label>Session note<textarea rows={3} value={note} onChange={e => setNote(e.target.value)} placeholder="Record relevant observations or protocol deviations." /></label><div className="right"><button className="secondary" disabled={!note.trim() || busy} onClick={() => void act('note', { phase_id: study.phase_id, request_id: newRequest(), text: note })}>Save note</button></div></section>
      <section className="panel"><h2>Study record</h2><dl className="record-details"><div><dt>Completed sessions</dt><dd>{study.completed_sessions.length} / {study.session_count}</dd></div><div><dt>Input</dt><dd>Structured offers and text</dd></div><div><dt>Presentation</dt><dd>{study.output}</dd></div><div><dt>Participant profile</dt><dd>{study.human_profile.provenance}</dd></div></dl><details><summary>End the current session</summary><label>Reason<textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} /></label><button className="secondary danger" disabled={!reason.trim() || study.phase !== 'active' || busy} onClick={() => void act('terminate', { phase_id: study.phase_id, request_id: newRequest(), text: reason })}>End session with reason</button></details></section></div>
    <section className="panel"><h2>Review and export</h2><p className="hint">Build an offline report with figures, canonical snapshots, CSV and Excel tables. Practice and interrupted sessions are identified explicitly.</p><button className="primary" disabled={busy || study.phase === 'active'} onClick={async () => { setBusy(true); fail(''); try { setReport(await api(`/studies/${study.plan_id}/report`, 'POST')); } catch (e) { fail((e as Error).message); } finally { setBusy(false); } }}>{busy ? 'Working…' : 'Build report'}</button>
    {report && <div className="button-row spaced"><button className="secondary" onClick={() => { const url = URL.createObjectURL(new Blob([report.html], { type: 'text/html' })); window.open(url, '_blank', 'noopener'); setTimeout(() => URL.revokeObjectURL(url), 60000); }}>Open report</button><button className="secondary" onClick={async () => { try { const response = await fetch(`/api/reports/${report.report_id}/download`, { headers: { 'X-Negotiator-Token': token } }); if (!response.ok) throw new Error('Report download failed.'); const url = URL.createObjectURL(await response.blob()); const a = document.createElement('a'); a.href = url; a.download = 'negotiator-report.zip'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); } catch (e) { fail((e as Error).message); } }}>Download all files (ZIP)</button></div>}</section>
    <section className="panel"><h2>Protocol and device checks</h2><p className="hint">Study purpose: {study.purpose ?? 'demonstration'}. File hashes are verified again before starting.</p>{Boolean(study.readiness?.length) && <div role="alert" className="error"><strong>Preparation required</strong><ul>{study.readiness?.map(item => <li key={item.id}>{item.reason}</li>)}</ul></div>}<p className="hint">Check selected bridges before starting. A successful connection does not replace the lab validation protocol.</p><button className="secondary" disabled={busy || study.phase === 'active'} onClick={async () => { setBusy(true); try { const result = await api(`/studies/${study.plan_id}/preflight`, 'POST'); setPreflight(JSON.stringify(result, null, 2)); } catch (e) { fail((e as Error).message); } finally { setBusy(false); } }}>Run preflight</button>{preflight && <pre className="device-receipt">{preflight === '{}' ? 'Text/browser output is ready. No external devices selected.' : preflight}</pre>}<CameraPreview /></section>
    <details className="panel"><summary>Participant instructions and scoring</summary><blockquote>{study.instructions}</blockquote><div className="domain-preview">{Object.entries(study.human_profile.weights).map(([name, weight]) => <div key={name}><strong>{name}</strong><span>{(100 * weight).toFixed(1)}% weight · {study.human_profile.scores[name].map(v => `${v.value}: ${score(v.score)}`).join(' · ')}</span></div>)}</div></details>
  </>;
}

function App() {
  const [plans, setPlans] = useState<Study[]>([]);
  const [selected, setSelected] = useState(new URLSearchParams(location.search).get('plan') ?? '');
  const [study, setStudy] = useState<Study | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [wizard, setWizard] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const selectedRef = useRef(selected); selectedRef.current = selected;
  const refreshId = useRef(0);
  const refresh = useCallback(async () => {
    const generation = ++refreshId.current;
    try {
      const fresh = selected ? await api<Study>(`/studies/${selected}`) : null;
      if (selectedRef.current !== selected || generation !== refreshId.current) return;
      if (fresh) setStudy(fresh);
      if (!participant) setPlans(await api<Study[]>('/studies'));
      setLoading(false);
    } catch (e) { setError((e as Error).message); setLoading(false); }
  }, [selected]);
  useEffect(() => {
    if (!participant && token) void api<Catalog>('/catalog').then(setCatalog).catch(e => setError(e.message));
  }, []);
  useEffect(() => {
    if (!token) { setLoading(false); return; }
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { await refresh(); if (active) timer = setTimeout(() => void poll(), 750); };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [refresh]);
  function select(id: string) {
    selectedRef.current = id; setStudy(null); setSelected(id); setWizard(false); setError('');
    const url = new URL(location.href); url.searchParams.set('plan', id); history.replaceState(null, '', url.pathname + url.search);
  }
  async function demo() {
    try {
      const result = await api<{ plan_id: string }>('/studies', 'POST', { study_id: 'demo', participant_id: `SYNTHETIC${plans.length + 1}`, title: 'A first negotiation', domain: 'holiday', preference_mode: 'assigned', conditions: [{ label: 'Synthetic practice', strategy: 'hybrid', duration_seconds: 600, practice: true }], output: 'avatar', synthetic: true });
      select(result.plan_id);
    } catch (e) { setError((e as Error).message); }
  }
  return <div className={`app ${participant ? 'participant-app' : ''}`}><header className="app-header"><a className="brand" href={participant ? '#' : '/'}><span className="brand-mark" aria-hidden>n<span>↔</span></span><div>NEGOTIATOR<small>{participant ? 'Participant view' : 'Study workspace'}</small></div></a><span className="header-chip"><i />{participant ? study?.participant_id ?? 'Participant' : 'Local experiment app'}</span></header>
    <div className="app-body">{!participant && <aside className="sidebar"><div className="sidebar-heading"><span className="eyebrow">Your studies</span><button className="new-icon" aria-label="New study" onClick={() => setWizard(true)}>+</button></div>
      {plans.length === 0 && <p className="muted sidebar-empty">Create a study to configure your first session.</p>}{plans.map(plan => <button key={plan.plan_id} className={`study-tab ${selected === plan.plan_id && !wizard ? 'selected' : ''}`} onClick={() => select(plan.plan_id)}><strong>{plan.title}</strong><span>{plan.participant_id} · {plan.completed_sessions.length}/{plan.session_count} sessions</span><small>{phaseName[plan.phase]}</small></button>)}
      <div className="sidebar-footer"><strong>One session, one record.</strong><p>Preferences, offers and outcomes stay together. Refresh either window to reconnect.</p><a href="https://doi.org/10.24963/ijcai.2024/1012" target="_blank" rel="noreferrer">Framework paper ↗</a></div></aside>}
      <main id="main-content">{!participant && <div className="mobile-nav"><label>Study<select aria-label="Select study" value={selected} onChange={e => select(e.target.value)}><option value="">Choose a study</option>{plans.map(p => <option key={p.plan_id} value={p.plan_id}>{p.title} · {p.participant_id}</option>)}</select></label><button className="secondary" onClick={() => setWizard(true)}>New study</button></div>}{!token ? <section className="panel phase-panel"><h1>Open your workspace link</h1><p>Launch <code>negotiator gui</code> and use the conductor link it opens. Participants use the separate link provided by the experiment conductor.</p></section> : <>
        {(error || study?.error) && <div className="error" role="alert">{error || study?.error}<button aria-label="Dismiss message" className="quiet" onClick={() => setError('')}>×</button></div>}
        {wizard && catalog && !participant ? <Wizard catalog={catalog} done={select} cancel={() => setWizard(false)} /> : study && selected ? participant ? <Participant key={study.plan_id} study={study} refresh={refresh} fail={setError} /> : <Conductor key={study.plan_id} study={study} refresh={refresh} fail={setError} /> : loading ? <p className="loading" role="status">Opening your workspace…</p> : <section className="welcome"><p className="eyebrow">From preparation to a complete record</p><h1>Make room for<br /><em>good negotiation research.</em></h1><p className="welcome-lead">Configure a study, guide each participant through their sessions, and keep preferences, offers and outcomes in one place.</p><div className="button-row"><button className="primary" onClick={() => setWizard(true)}>Create your first study <span aria-hidden>→</span></button><button className="secondary" onClick={() => void demo()}>Try the demo</button></div>
          <div className="workflow"><div><span>01</span><h2>Prepare</h2><p>Choose a domain, preferences, strategy and session order.</p></div><div><span>02</span><h2>Negotiate</h2><p>Run a participant display alongside your conductor workspace.</p></div><div><span>03</span><h2>Review</h2><p>Keep every committed offer and final outcome for replay and analysis.</p></div></div><div className="welcome-note"><span aria-hidden>◇</span><p>The demo uses synthetic preferences and needs no camera, microphone or robot.</p></div></section>}
      </>}</main></div><footer className="app-footer">NEGOTIATOR · Human-agent negotiation research <span>Data stays in your selected local folder.</span></footer></div>;
}

createRoot(document.getElementById('root')!).render(<App />);
