import { useEffect, useState, type FormEvent } from 'react';
import { api } from './api';
import { type Catalog, type Condition, type Domain, type Profile, type StudySpec, type SurveyItem, issueValues } from './types';

const defaultCondition = (index: number): Condition => ({ label: `Condition ${String.fromCharCode(65 + index)}`, strategy: 'hybrid', duration_seconds: 600, practice: false });
const initial: StudySpec = {
  study_id: 'study', participant_id: 'P001', title: 'Negotiation study', purpose: 'demonstration',
  instructions: 'You and your negotiation partner will exchange complete offers. Use your preference scores to decide what to propose or accept. You may withdraw at any time.',
  domain: 'holiday', preference_mode: 'elicited', conditions: [defaultCondition(0)],
  order: 'as_entered', participant_index: 1, cohort: 'default', seed: 42,
  first_actor: 'human', output: 'text', surveys: [],
};

function ProfileEditor({ name, profile, change }: { name: string; profile: Profile; change: (p: Profile) => void }) {
  return <details className="profile-editor"><summary>{name} · {profile.provenance}</summary>
    <p className="muted">Issue weights must sum to 1. Value scores and reservation lie between 0 and 1.</p>
    <button type="button" className="quiet" onClick={() => {
      const total = Object.values(profile.weights).reduce((a, b) => a + b, 0);
      if (total > 0) change({ ...profile, weights: Object.fromEntries(Object.entries(profile.weights).map(([k, v]) => [k, v / total])) });
    }}>Normalize issue weights</button>
    {Object.entries(profile.weights).map(([issue, weight]) => <div className="profile-row" key={issue}>
      <label>{issue} weight<input type="number" step="any" min="0" max="1" value={weight}
        onChange={e => change({ ...profile, weights: { ...profile.weights, [issue]: Number(e.target.value) } })} /></label>
      {profile.scores[issue].map((entry, index) => <label key={entry.value}>{String(entry.value)}<input
        type="number" step="any" min="0" max="1" value={entry.score} onChange={e => change({ ...profile,
          scores: { ...profile.scores, [issue]: profile.scores[issue].map((item, i) => i === index ? { ...item, score: Number(e.target.value) } : item) } })} /></label>)}
    </div>)}
    <label>Reservation<input type="number" step="any" min="0" max="1" value={profile.reservation}
      onChange={e => change({ ...profile, reservation: Number(e.target.value) })} /></label>
  </details>;
}

export function Wizard({ catalog, done, cancel }: { catalog: Catalog; done: (id: string) => void; cancel: () => void }) {
  const [spec, setSpec] = useState<StudySpec>(initial);
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [importNotes, setImportNotes] = useState<string[]>([]);
  const [ordered, setOrdered] = useState<Condition[]>(initial.conditions);
  useEffect(() => {
    if (step !== 3) return;
    let current = true;
    api<{ conditions: Condition[] }>('/preview-study', 'POST', spec)
      .then(result => { if (current) { setOrdered(result.conditions); setError(''); } })
      .catch(e => { if (current) setError((e as Error).message); });
    return () => { current = false; };
  }, [step, spec]);
  async function importStudy(file?: File) {
    if (!file) return;
    setError('');
    try {
      if (file.size > 2_000_000) throw new Error('Configuration must be at most 2 MB.');
      const data = JSON.parse(await file.text());
      const result = await api<{ configuration: StudySpec; conditions: Condition[] }>('/preview-study', 'POST', data);
      setSpec(result.configuration); setOrdered(result.conditions); setStep(3);
    } catch (e) { setError(`Configuration import failed: ${(e as Error).message}`); }
  }
  const set = <K extends keyof StudySpec>(key: K, value: StudySpec[K]) => setSpec(s => ({ ...s, [key]: value }));
  const selectedDomain = typeof spec.domain === 'string' ? catalog.domains[spec.domain] : spec.domain;
  const condition = (index: number, change: Partial<Condition>) => set('conditions', spec.conditions.map((item, i) => i === index ? { ...item, ...change } : item));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (step < 3) { setStep(step + 1); return; }
    setBusy(true); setError('');
    try {
      const result = await api<{ plan_id: string }>('/studies', 'POST', spec);
      done(result.plan_id);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function importDomain(file?: File) {
    if (!file) return;
    setError('');
    try {
      if (file.size > 2_000_000) throw new Error('Import files must be at most 2 MB.');
      const text = await file.text();
      if (file.name.toLowerCase().endsWith('.xml')) {
        const result = await api<{ domain: Domain; notes: string[]; profile?: Profile }>('/import-domain', 'POST', { xml: text, name: file.name.replace(/\.xml$/i, '') });
        setSpec(s => ({ ...s, domain: result.domain, human_profile: result.profile, agent_profile: undefined, preference_mode: result.profile ? 'assigned' : s.preference_mode })); setImportNotes(result.notes);
      } else { const result = await api<{ domain: Domain; notes: string[]; profile?: Profile }>('/import-domain', 'POST', { json: text }); setSpec(s => ({ ...s, domain: result.domain, human_profile: result.profile, agent_profile: undefined, preference_mode: result.profile ? 'assigned' : s.preference_mode })); setImportNotes(result.notes); }
    } catch (e) { setError(`Import failed: ${(e as Error).message}`); }
  }

  async function loadProfiles() {
    try {
      const result = await api<{ human: Profile; agent: Profile }>('/preview-profiles', 'POST', { domain: spec.domain });
      setSpec(s => ({ ...s, human_profile: result.human, agent_profile: result.agent }));
    } catch (e) { setError((e as Error).message); }
  }

  return <section className="wizard panel">
    <div className="section-title"><div><p className="eyebrow">Create an experiment</p><h1>A study, ready to run</h1></div><button className="quiet" onClick={cancel}>Cancel</button></div>
    <ol className="steps">{['Study', 'Preferences', 'Sessions', 'Review'].map((label, index) => <li className={index === step ? 'current' : index < step ? 'done' : ''} key={label}><span>{index + 1}</span>{label}</li>)}</ol>
    <form onSubmit={submit}>
      {step === 0 && <div className="form-section">
        <h2>Study essentials</h2><label>Import a paper or study configuration<input type="file" accept=".json" onChange={e => void importStudy(e.target.files?.[0])} /></label>
        <label>Study purpose<select value={spec.purpose ?? 'demonstration'} onChange={e => set('purpose', e.target.value as StudySpec['purpose'])}><option value="demonstration">Demonstration — generated profiles allowed</option><option value="custom-study">Custom study — explicit configuration</option><option value="published-protocol">Published protocol — import its verified configuration</option></select></label><p className="muted">Give this participant a pseudonymous ID. Each session will have its own saved record.</p>
        <label>Study title<input required maxLength={200} value={spec.title} onChange={e => set('title', e.target.value)} /></label>
        <div className="form-grid"><label>Study ID<input required pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,79}" value={spec.study_id} onChange={e => set('study_id', e.target.value)} /></label>
          <label>Participant ID<input required pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,79}" value={spec.participant_id} onChange={e => set('participant_id', e.target.value)} /></label></div>
        <label>Participant instructions<textarea rows={4} value={spec.instructions} onChange={e => set('instructions', e.target.value)} /></label>
        <p className="hint">Use a code such as P001, rather than a participant's name. Instructions are visible in their window.</p>
      </div>}
      {step === 1 && <div className="form-section">
        <h2>Domain and preferences</h2><p className="muted">Choose what will be negotiated, then decide how preferences are established.</p>
        <div className="domain-cards">{Object.entries(catalog.domains).map(([key, domain]) => <button type="button" key={key}
          className={`domain-card ${spec.domain === key ? 'selected' : ''}`} onClick={() => setSpec(s => ({ ...s, domain: key, human_profile: undefined, agent_profile: undefined }))}>
          <span className="domain-icon" aria-hidden>{key === 'holiday' ? '◒' : key === 'fruits' ? '◉' : '◇'}</span><strong>{key === 'holiday' ? 'Holiday' : key === 'fruits' ? 'Fruits' : 'Desert Island'}</strong>
          <small>{domain.issues.length} issues · {domain.issues[0].total != null ? 'Resource allocation' : 'Categorical choices'}</small></button>)}</div>
        <div className="domain-preview">{selectedDomain?.issues?.map(issue => <div key={issue.name}><strong>{issue.name}</strong><span>{issue.total == null ? issue.values?.join(' · ') : `0–${issue.total} units`}</span></div>)}</div>
        <div className="choice-row"><label><input type="radio" checked={spec.preference_mode === 'elicited'} onChange={() => set('preference_mode', 'elicited')} />Participant ranks preferences before each session</label>
          <label><input type="radio" checked={spec.preference_mode === 'assigned'} onChange={() => set('preference_mode', 'assigned')} />Use assigned profiles</label></div>
        {spec.preference_mode === 'assigned' && <div className="inset"><p>Assigned profiles use a synthetic rank assignment unless you edit or import them here.</p>
          <button type="button" className="secondary" onClick={loadProfiles}>Edit assigned profiles</button>
          {spec.human_profile && <ProfileEditor name="Human profile" profile={spec.human_profile} change={value => set('human_profile', value)} />}
          {spec.agent_profile && <ProfileEditor name="Agent profile" profile={spec.agent_profile} change={value => set('agent_profile', value)} />}</div>}
        <details><summary>Import or edit a domain</summary><label>Import XML or JSON<input type="file" accept=".xml,.json" onChange={e => void importDomain(e.target.files?.[0])} /></label>
          {importNotes.map(note => <p className="hint" key={note}>{note}</p>)}
          <button type="button" className="quiet" onClick={() => set('domain', structuredClone(selectedDomain))}>Edit current domain</button>
          {typeof spec.domain !== 'string' && <div className="domain-editor"><label>Domain name<input value={spec.domain.name} onChange={e => set('domain', { ...selectedDomain, name: e.target.value })} /></label>
            {spec.domain.issues.map((issue, index) => <div className="form-grid" key={index}>
              <label>Issue {index + 1} name<input value={issue.name} onChange={e => set('domain', { ...selectedDomain, issues: selectedDomain.issues.map((item, i) => i === index ? { ...item, name: e.target.value } : item) })} /></label>
              <label>{issue.total != null ? 'Available units' : 'Values, separated by commas'}<input value={issue.total ?? issue.values?.join(', ')} type={issue.total != null ? 'number' : 'text'} min="0"
                onChange={e => set('domain', { ...selectedDomain, issues: selectedDomain.issues.map((item, i) => i === index ? { name: item.name, ...(issue.total != null ? { total: Number(e.target.value) } : { values: e.target.value.split(',').map(v => v.trim()) }) } : item) })} /></label>
              <button type="button" className="quiet" onClick={() => set('domain', { ...selectedDomain, issues: selectedDomain.issues.filter((_, i) => i !== index) })}>Remove issue {index + 1}</button></div>)}
            <button type="button" className="secondary" onClick={() => set('domain', { ...selectedDomain, issues: [...selectedDomain.issues, { name: `Issue ${selectedDomain.issues.length + 1}`, ...(selectedDomain.issues[0]?.total != null ? { total: 1 } : { values: ['Option A', 'Option B'] }) }] })}>Add issue</button>
          </div>}
        </details>
      </div>}
      {step === 2 && <div className="form-section"><h2>Sessions and interaction</h2><p className="muted">The order below is recorded with the experiment. Every session starts with new strategy and input state.</p>
        {spec.conditions.map((item, index) => <fieldset className="condition" key={index}><legend>Session {index + 1}</legend>
          <div className="form-grid"><label>Condition label<input required value={item.label} onChange={e => condition(index, { label: e.target.value })} /></label>
            <label>Strategy<select value={item.strategy} onChange={e => condition(index, { strategy: e.target.value })}>{catalog.strategies.map(name => <option key={name}>{name}</option>)}</select></label>
            <label>Session presentation<select value={item.output ?? ''} onChange={e => condition(index, { output: e.target.value || null })}><option value="">Study default</option>{catalog.outputs.map(name => <option key={name}>{name}</option>)}</select></label><label>Output device profile<select value={item.output_device ?? ''} onChange={e => condition(index, { output_device: e.target.value || null })}><option value="">Presentation default</option>{Object.keys(catalog.devices).map(name => <option key={name}>{name}</option>)}</select></label><label>Session domain<select value={typeof item.domain === 'string' ? item.domain : ''} onChange={e => condition(index, { domain: e.target.value || null })}><option value="">Study default</option>{Object.keys(catalog.domains).map(name => <option key={name}>{name}</option>)}</select></label>
            <label>Block (keep practice and main together)<input value={item.block ?? ''} onChange={e => condition(index, { block: e.target.value || null })} /></label><label>Break after this session (minutes)<input type="number" min="0" step="any" value={(item.break_after_seconds ?? 0) / 60} onChange={e => condition(index, { break_after_seconds: Number(e.target.value) * 60 })} /></label><label>Duration in minutes<input type="number" required min="0.02" max="1440" step="any" value={item.duration_seconds / 60} onChange={e => condition(index, { duration_seconds: Number(e.target.value) * 60 })} /></label></div>
          <div className="form-grid"><label>Human target score (0–100, optional)<input type="number" min="0" max="100" value={item.score_targets?.human != null ? item.score_targets.human * 100 : ""} onChange={e => condition(index, { score_targets: e.target.value === "" ? {} : {human: Number(e.target.value)/100} })} /></label><label>Score below this minimum becomes zero (optional)<input type="number" min="0" max="100" value={item.reward_minimums?.human != null ? item.reward_minimums.human * 100 : ""} onChange={e => condition(index, { reward_minimums: e.target.value === "" ? {} : {human: Number(e.target.value)/100} })} /></label></div><label className="checkbox"><input type="checkbox" checked={item.gestures !== false} onChange={e => condition(index, { gestures: e.target.checked })} />Enable configured gestures</label><div className="between"><label className="checkbox"><input type="checkbox" checked={item.practice} onChange={e => condition(index, { practice: e.target.checked })} />Practice session</label>
            {spec.conditions.length > 1 && <button type="button" className="quiet" onClick={() => set('conditions', spec.conditions.filter((_, i) => i !== index))}>Remove session</button>}</div>
        </fieldset>)}
        <button type="button" className="secondary" onClick={() => set('conditions', [...spec.conditions, defaultCondition(spec.conditions.length)])}>Add session</button>
        <div className="form-grid spaced"><label>Order<select value={spec.order} onChange={e => set('order', e.target.value)}><option value="as_entered">As entered</option><option value="reversed">Reverse order</option><option value="counterbalanced">Alternate by participant index</option></select></label>
          <label>Participant index<input type="number" min="1" value={spec.participant_index} onChange={e => set('participant_index', Number(e.target.value))} /></label>
          <label>Presentation<select value={spec.output} onChange={e => set('output', e.target.value)}><option value="text">Text on screen</option><option value="avatar">Browser avatar</option><option value="nao">NAO bridge</option><option value="pepper">Pepper bridge</option><option value="qt">QT bridge</option></select></label></div>
        <label>Turn interaction<select value={spec.interaction_protocol ?? "direct-offer"} onChange={e => set("interaction_protocol", e.target.value as StudySpec["interaction_protocol"])}><option value="direct-offer">Enter an offer directly</option><option value="ready-offer-response">Ready, offer, then accept or reject</option></select></label><details><summary>Optional input devices</summary><p className="hint">Devices come from the local bridge configuration loaded by the conductor. Speech becomes an editable draft before Send.</p><div className="form-grid">{(['speech', 'perception'] as const).map(kind => <label key={kind}>{kind === 'speech' ? 'Speech input' : 'Observation input'}<select value={spec[`${kind}_device`] ?? ''} onChange={e => set(`${kind}_device`, e.target.value || null)}><option value="">Not selected</option>{Object.entries(catalog.devices).filter(([, d]) => d.capabilities.includes(kind === 'speech' ? 'transcript' : 'affect')).map(([name]) => <option key={name}>{name}</option>)}</select></label>)}</div><label className="checkbox"><input type="checkbox" checked={spec.manual_affect ?? false} onChange={e => set('manual_affect', e.target.checked)} />Enable optional participant affect self-report</label></details>
        <details><summary>Advanced settings and questionnaires</summary><div className="form-grid"><label>Cohort<input value={spec.cohort} onChange={e => set('cohort', e.target.value)} /></label><label>Random seed<input type="number" value={spec.seed} onChange={e => set('seed', Number(e.target.value))} /></label><label>First offer<select value={spec.first_actor} onChange={e => set('first_actor', e.target.value)}><option value="human">Participant</option><option value="agent">Agent</option></select></label></div>
          <p className="hint">Add your approved questionnaire wording and cite its source. Example items are not substitutes for a paper's original instrument.</p>
          {spec.surveys.map((item, index) => {
            const update = (change: Partial<SurveyItem>) => set('surveys', spec.surveys.map((s, i) => i === index ? { ...s, ...change } : s));
            return <fieldset key={index}><legend>Question {index + 1}</legend><label>Question wording<input required value={item.prompt} onChange={e => update({ prompt: e.target.value })} /></label>
              <div className="form-grid"><label>When<select value={item.phase} onChange={e => update({ phase: e.target.value })}><option value="pre_study">Before the study</option><option value="pre_session">Before each session</option><option value="post_session">After each session</option><option value="post_study">After all sessions</option></select></label>
                <label>Lowest rating<input type="number" value={item.minimum} onChange={e => update({ minimum: Number(e.target.value) })} /></label><label>Highest rating<input type="number" value={item.maximum} onChange={e => update({ maximum: Number(e.target.value) })} /></label></div>
              <label>Questionnaire source<input value={item.source} onChange={e => update({ source: e.target.value })} /></label><button type="button" className="quiet" onClick={() => set('surveys', spec.surveys.filter((_, i) => i !== index))}>Remove question</button></fieldset>;
          })}
          <button type="button" className="secondary" onClick={() => set('surveys', [...spec.surveys, { id: `q${spec.surveys.length + 1}`, prompt: '', minimum: 1, maximum: 7, phase: 'post_session', required: true, source: 'researcher supplied' }])}>Add question</button>
        </details>
      </div>}
      {step === 3 && <div className="form-section"><h2>Review your study</h2><div className="review-grid"><div><span className="eyebrow">Participant</span><strong>{spec.participant_id}</strong><small>{spec.study_id} · {spec.cohort}</small></div><div><span className="eyebrow">Domain</span><strong>{selectedDomain?.name}</strong><small>{selectedDomain?.issues?.length} issues · {spec.preference_mode} preferences</small></div><div><span className="eyebrow">Protocol</span><strong>{spec.conditions.length} session{spec.conditions.length === 1 ? '' : 's'}</strong><small>{spec.output} · {spec.order.replaceAll('_', ' ')}</small></div></div>
        <blockquote>{spec.instructions}</blockquote><ol className="schedule">{ordered.map((item, i) => <li key={i}><span>{i + 1}</span><strong>{item.label}</strong><small>{item.strategy} · {item.duration_seconds / 60} min {item.practice ? '· Practice' : ''}</small></li>)}</ol>
        <p className="hint">Creating this record opens the conductor workspace. Start the clock only after the participant completes their scheduled preparation. Configuration is fixed when a session begins.</p>
      </div>}
      {error && <div role="alert" className="error">{error}</div>}
      <div className="wizard-actions"><button type="button" className="quiet" onClick={() => step ? setStep(step - 1) : cancel()}>{step ? 'Back' : 'Cancel'}</button><button className="primary" disabled={busy}>{busy ? 'Creating…' : step === 3 ? 'Create study' : 'Continue'} <span aria-hidden>→</span></button></div>
    </form>
  </section>;
}
