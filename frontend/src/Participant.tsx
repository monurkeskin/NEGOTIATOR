import { useEffect, useState } from 'react';
import { api } from './api';
import { InputDevices, useVisibleActions } from './Devices';
import { type CommandResult, type Draft, type OfferRecord, type Study, type Value, issueValues, newRequest, score } from './types';

export const clockText = (seconds: number) => {
  const total = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(total / 60).toString().padStart(2, '0')}:${(total % 60).toString().padStart(2, '0')}`;
};

export function Preferences({ study, refresh, fail }: { study: Study; refresh: () => Promise<void>; fail: (e: string) => void }) {
  const [order, setOrder] = useState(() => study.domain.issues.map(i => i.name));
  const [ranks, setRanks] = useState<Record<string, Value[]>>(() => Object.fromEntries(study.domain.issues.map(i => [i.name, issueValues(i)])));
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState<{ issue?: string; index: number } | null>(null);
  const moveIssue = (from: number, to: number) => {
    if (to < 0 || to >= order.length) return;
    const next = [...order]; const [item] = next.splice(from, 1); next.splice(to, 0, item); setOrder(next);
  };
  const moveValue = (issue: string, from: number, to: number) => {
    if (to < 0 || to >= ranks[issue].length) return;
    const next = [...ranks[issue]]; const [item] = next.splice(from, 1); next.splice(to, 0, item); setRanks({ ...ranks, [issue]: next });
  };
  async function confirm() {
    setBusy(true);
    try { await api(`/studies/${study.plan_id}/preferences`, 'POST', { request_id: newRequest(), phase_id: study.phase_id, issues: order, values: ranks }); await refresh(); }
    catch (e) { fail((e as Error).message); } finally { setBusy(false); }
  }
  const total = order.length * (order.length + 1) / 2;
  return <section className="panel preference-panel"><p className="eyebrow">Before session {study.sequence_index}</p><h1>What matters to you?</h1>
    <p>Place the most important issue first. Within each issue, put your favorite option first. Use the arrows or drag items to reorder them.</p>
    <div className="ranking-list">{order.map((name, index) => <section className="ranking-card" key={name}
      onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (drag && !drag.issue) moveIssue(drag.index, index); setDrag(null); }}>
      <div className="rank-heading" draggable onDragStart={() => setDrag({ index })}><span className="rank-number">{index + 1}</span>
        <h2>{name}</h2><span className="weight-preview">{((order.length - index) / total * 100).toFixed(1)}% weight</span>
        <div className="rank-buttons"><button aria-label={`Move ${name} up`} disabled={index === 0} onClick={() => moveIssue(index, index - 1)}>↑</button><button aria-label={`Move ${name} down`} disabled={index === order.length - 1} onClick={() => moveIssue(index, index + 1)}>↓</button></div></div>
      <ol className="value-ranks">{ranks[name].map((value, rank) => <li draggable key={value} onDragStart={e => { e.stopPropagation(); setDrag({ issue: name, index: rank }); }} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); e.stopPropagation(); if (drag?.issue === name) moveValue(name, drag.index, rank); setDrag(null); }}>
        <span>{rank + 1}</span><strong>{String(value)}</strong><div className="rank-buttons"><button aria-label={`Move ${name}: ${value} up`} disabled={rank === 0} onClick={() => moveValue(name, rank, rank - 1)}>↑</button><button aria-label={`Move ${name}: ${value} down`} disabled={rank === ranks[name].length - 1} onClick={() => moveValue(name, rank, rank + 1)}>↓</button></div></li>)}</ol>
    </section>)}</div>
    <div className="inset"><strong>Your score follows these preferences.</strong><p>More important issues contribute more to your total. The first value has the highest score. Weights are saved at full precision; the percentages above are rounded for display.</p></div>
    <div className="right"><button className="primary" disabled={busy} onClick={confirm}>{busy ? 'Saving…' : 'Confirm preferences'}</button></div>
  </section>;
}

export function History({ offers, conductor = false }: { offers: OfferRecord[]; conductor?: boolean }) {
  return <section className="panel history-panel"><div className="section-title"><h2>Offer history</h2><span className="badge neutral">{offers.length} offers</span></div>
    {offers.length === 0 ? <div className="empty-small">No offers yet</div> : <div className="table-scroll"><table><thead><tr><th scope="col">Offer</th><th scope="col">From</th><th scope="col">Proposal</th><th scope="col">{conductor ? 'Human' : 'Your score'}</th>{conductor && <th scope="col">Agent</th>}</tr></thead><tbody>
      {[...offers].reverse().map(o => <tr key={o.offer_id}><td>#{o.round}</td><td><span className={`actor ${o.actor}`}>{o.actor === 'human' ? conductor ? 'Human' : 'You' : 'Agent'}</span></td><td className="bid-cell">{Object.entries(o.bid).map(([key, value]) => <span key={key}><b>{key}</b> {String(value)}</span>)}</td><td>{score(o.utilities.human)}</td>{conductor && <td>{score(o.utilities.agent)}</td>}</tr>)}</tbody></table></div>}
  </section>;
}

export function OfferPlot({ offers }: { offers: OfferRecord[] }) {
  const x = (i: number) => 34 + i / Math.max(1, offers.length - 1) * 360;
  const y = (u: number) => 133 - u * 108;
  return <figure className="offer-plot"><figcaption>Human score across offers <small>0–100 scale</small></figcaption><svg viewBox="0 0 420 158" role="img" aria-label="Human utility of each committed offer, on a 0 to 100 score scale">
    {[0, .5, 1].map(u => <g key={u}><line x1="34" x2="405" y1={y(u)} y2={y(u)} stroke="#dde7e4" /><text x="26" y={y(u) + 4} textAnchor="end" fontSize="10" fill="#59706b">{u * 100}</text></g>)}
    {offers.length > 1 && <polyline points={offers.map((o, i) => `${x(i)},${y(o.utilities.human)}`).join(' ')} fill="none" stroke="#668780" strokeWidth="2" />}
    {offers.map((o, i) => <circle key={o.offer_id} cx={x(i)} cy={y(o.utilities.human)} r="4" fill={o.actor === 'human' ? '#236d60' : '#8068b1'}><title>Offer {o.round}: {score(o.utilities.human)}</title></circle>)}
    <text x="217" y="155" textAnchor="middle" fontSize="10" fill="#59706b">Offer order</text></svg></figure>;
}

function Avatar({ happy = false }: { happy?: boolean }) {
  return <svg className="avatar" viewBox="0 0 120 120" role="img" aria-label="Browser negotiation agent"><rect x="12" y="18" width="96" height="85" rx="30" fill="#d5eae3" /><circle cx="42" cy="54" r="8" fill="#23453e" /><circle cx="78" cy="54" r="8" fill="#23453e" /><path d={happy ? 'M 40 77 Q 60 98 80 77' : 'M 43 83 Q 60 89 77 83'} fill="none" stroke="#23453e" strokeWidth="5" strokeLinecap="round" /><path d="M60 18V9" stroke="#23453e" strokeWidth="3" /><circle cx="60" cy="7" r="4" fill="#bf9559" /></svg>;
}

export function Negotiation({ study, refresh, fail }: { study: Study; refresh: () => Promise<void>; fail: (e: string) => void }) {
  const session = study.current!;
  const last = session.offers.at(-1);
  const [values, setValues] = useState<Record<string, Value>>(() => Object.fromEntries(study.domain.issues.map(i => {
    const sorted = [...study.human_profile.scores[i.name]].sort((a, b) => b.score - a.score);
    return [i.name, sorted[0].value];
  })));
  const [text, setText] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<number | null>(null);
  const staged = session.interaction_phase !== 'direct-offer';
  const canAct = session.status === 'active' && session.next_actor === 'human' && !study.presentation_pending;
  const canOffer = canAct && (!staged || session.interaction_phase === 'offer');
  const canAccept = canAct && (!staged || session.interaction_phase === 'response');
  const stageText: Record<string, string> = { notification: 'Choose Ready when you have a proposal in mind.', offer: 'Enter your complete proposal.', response: 'Accept or reject your partner’s offer.' };
  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => { void api<{ utility: number }>(`/studies/${study.plan_id}/preview-offer`, 'POST', { values }).then(result => { if (live) setPreview(result.utility); }).catch(() => { if (live) setPreview(null); }); }, 120);
    return () => { live = false; clearTimeout(timer); };
  }, [values, study.plan_id]);
  async function send(kind: string) {
    setBusy(true); fail('');
    try {
      const result = await api<CommandResult>(`/studies/${study.plan_id}/command`, 'POST', { kind, request_id: newRequest(), session_id: session.config.session_id, expected_offer_count: session.offers.length, ...(kind === 'offer' ? { values } : {}), ...(kind === 'text' ? { text } : {}), ...(['accept', 'reject', 'text'].includes(kind) && last?.actor === 'agent' ? { offer_id: last.offer_id } : {}) });
      setDraft(result.committed ? null : result.draft); if (result.committed) setText(''); await refresh();
    } catch (e) { fail((e as Error).message); } finally { setBusy(false); }
  }
  return <><div className="session-top"><div><p className="eyebrow">Session {study.sequence_index} of {study.session_count}</p><h1>Your negotiation</h1><p>{canAct ? (stageText[session.interaction_phase] ?? 'Your turn to offer or respond.') : 'Your partner is preparing a response.'}</p></div><div className="clock-card"><span>Time remaining</span><strong aria-label="Time remaining">{clockText(session.remaining_seconds)}</strong><progress max="1" value={1 - session.elapsed_fraction} /></div></div>
    <div className="negotiation-grid"><section className="panel proposal"><div className="section-title"><h2>{last?.actor === 'agent' ? 'Your partner’s offer' : 'Current offer'}</h2>{study.output === 'avatar' && <Avatar />}</div>
      {last ? <><dl className="offer-values">{Object.entries(last.bid).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{String(value)}</dd></div>)}</dl><div className="score-card"><span>Your score</span><strong>{score(last.utilities.human)}<small>/100</small></strong></div></> : <p className="muted">Choose a complete proposal to begin. For allocations, quantities are the units you keep.</p>}
      <button className="primary full" disabled={!canAccept || last?.actor !== 'agent' || busy} onClick={() => void send('accept')}>Accept offer</button>{staged && <button className="secondary full" disabled={!canAccept || busy} onClick={() => void send('reject')}>Reject offer</button>}<p className="hint">Acceptance applies to the latest offer from your partner.</p>{session.config.score_targets?.human != null && <p>Target: {score(session.config.score_targets.human)}/100. {session.config.reward_minimums?.human != null ? `Agreements below ${score(session.config.reward_minimums.human)}/100 receive zero game points.` : "This is your goal for the negotiation."}</p>}
    </section><section className="panel composer"><div className="section-title"><h2>Build your offer</h2><span className="badge neutral">Your quantities / choices</span></div>
      {staged && <button className="primary" disabled={!canAct || session.interaction_phase !== 'notification' || busy} onClick={() => void send('ready')}>Ready to propose</button>}
      <div className="composer-fields">{study.domain.issues.map(issue => <label key={issue.name}>{issue.name}<select disabled={!canOffer || busy} value={String(values[issue.name])} onChange={e => setValues({ ...values, [issue.name]: issue.total != null ? Number(e.target.value) : e.target.value })}>
        {issueValues(issue).map(value => <option key={value} value={String(value)}>{String(value)}</option>)}</select></label>)}</div>
      <div className="between spaced"><div className="preview-score"><span>Proposed score</span><strong>{score(preview)}<small>/100</small></strong></div><button className="primary" disabled={!canOffer || busy} onClick={() => void send('offer')}>Send offer</button></div>
      <div className="divider">or use text</div><label>Your message<textarea rows={2} value={text} disabled={!canAct || busy} onChange={e => setText(e.target.value)} placeholder={study.domain.issues.slice(0, 2).map(i => `${i.name}=${issueValues(i)[0]}`).join('; ') + '…'} /></label>
      <div className="right"><button className="secondary" disabled={!canAct || !text.trim() || busy} onClick={() => void send('text')}>Send text</button></div>
      <InputDevices study={study} draft={d => { setText(d.transcript); setDraft(d); }} fail={fail} />
      {draft && <div className="clarification" role="status"><strong>Clarify your offer</strong>{draft.missing.length > 0 && <p>Missing: {draft.missing.join(', ')}</p>}{draft.ambiguous.length > 0 && <p>More than one possible value: {draft.ambiguous.join(', ')}</p>}{draft.invalid.length > 0 && <p>Check these values: {draft.invalid.join(', ')}</p>}<small>Your message is a draft. No offer has been committed.</small></div>}
    </section></div><History offers={session.offers} /><div className="between"><p className="hint">Your choices and the offers shown here belong to this session.</p><button className="quiet danger" disabled={busy || session.status !== 'active'} onClick={() => void send('withdraw')}>Withdraw</button></div>
  </>;
}

function Survey({ study, refresh, fail }: { study: Study; refresh: () => Promise<void>; fail: (s: string) => void }) {
  const [answers, setAnswers] = useState<Record<string, number | null>>({});
  const [busy, setBusy] = useState(false);
  return <section className="panel survey-panel"><p className="eyebrow">{study.survey_phase?.replaceAll('_', ' ')}</p><h1>A few questions</h1><p>Answer for the session or phase indicated above.</p><form onSubmit={async e => {
    e.preventDefault(); setBusy(true); try { await api(`/studies/${study.plan_id}/survey`, 'POST', { request_id: newRequest(), phase_id: study.phase_id, answers }); await refresh(); } catch (error) { fail((error as Error).message); } finally { setBusy(false); }
  }}>{study.survey_items.map(item => <fieldset className="survey-item" key={item.id}>
    <legend>{item.prompt}</legend>
    {(item.minimum_label || item.maximum_label) && <div className="between hint" aria-label="Rating scale">
      <span>{item.minimum}{item.minimum_label && ` — ${item.minimum_label}`}</span>
      <span>{item.maximum}{item.maximum_label && ` — ${item.maximum_label}`}</span>
    </div>}
    <div className="rating-options">{Array.from({ length: item.maximum - item.minimum + 1 }, (_, i) => i + item.minimum).map(value => <label key={value}><input type="radio" required={item.required !== false} name={item.id} value={value} checked={answers[item.id] === value} onChange={() => setAnswers({ ...answers, [item.id]: value })} /><span>{value}</span></label>)}</div>
    {item.required === false && <button type="button" className="quiet" onClick={() => setAnswers({ ...answers, [item.id]: null })}>Skip this question</button>}
  </fieldset>)}<div className="right"><button className="primary" disabled={busy}>Save answers</button></div></form></section>;
}

export function Participant({ study, refresh, fail }: { study: Study; refresh: () => Promise<void>; fail: (s: string) => void }) {
  useVisibleActions(study, fail);
  async function next() {
    try { await api(`/studies/${study.plan_id}/next`, 'POST', { request_id: newRequest(), phase_id: study.phase_id }); await refresh(); }
    catch (e) { fail((e as Error).message); }
  }
  if (study.phase === 'preferences') return <Preferences key={`prefs-${study.sequence_index}`} study={study} refresh={refresh} fail={fail} />;
  if (study.phase === 'survey') return <Survey key={`${study.survey_phase}-${study.sequence_index}`} study={study} refresh={refresh} fail={fail} />;
  if (study.phase === 'active') return <Negotiation key={study.current?.config.session_id} study={study} refresh={refresh} fail={fail} />;
  const result = study.current?.outcome;
  const agreement = result?.reason === 'agreement';
  return <section className="panel phase-panel"><div className="phase-symbol" aria-hidden>{study.phase === 'result' && agreement ? '✓' : study.phase === 'break' ? '◒' : '◇'}</div>
    <p className="eyebrow">{study.phase === 'complete' ? 'Study complete' : `Session ${study.sequence_index} of ${study.session_count}`}</p>
    <h1>{study.phase === 'ready' ? 'Ready for the session' : study.phase === 'break' ? 'Take a short break' : study.phase === 'complete' ? 'Thank you' : agreement ? 'Agreement reached' : 'Session ended'}</h1>
    <p>{study.phase === 'ready' ? 'Your preferences are saved. The experiment conductor will start the session when you are ready.' : study.phase === 'break' ? 'Complete the scheduled break, then continue to prepare for the next session.' : study.phase === 'complete' ? 'Your completed sessions and responses have been saved.' : agreement ? 'You and your partner accepted the same offer.' : `The session ended: ${result?.reason.replaceAll('_', ' ') ?? ''}.`}</p>
    {study.phase === 'result' && result?.utilities && <div className="score-card"><span>Your agreed score</span><strong>{score(result.utilities.human)}<small>/100</small></strong></div>}
    {study.phase === 'result' && result?.payoffs && study.current?.config.reward_minimums?.human != null && <div className="score-card" aria-label="Game score"><span>Game score</span><strong>{score(result.payoffs.human)}<small>/100</small></strong></div>}
    {study.phase === 'ready' && <blockquote>{study.instructions}</blockquote>}
    {study.phase === 'break' && <p aria-label="Break time remaining">{Math.ceil(study.break_remaining_seconds)} seconds remaining{study.break_restarted ? ' · The application restarted; the full break is required again.' : ''}</p>}
    {['result', 'break'].includes(study.phase) && <button className="primary" disabled={study.phase === 'break' && study.break_remaining_seconds > 0} onClick={() => void next()}>Continue <span aria-hidden>→</span></button>}
  </section>;
}
