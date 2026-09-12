import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { type Draft, type Study, newRequest } from './types';

export function CameraPreview() {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [device, setDevice] = useState('');
  const [error, setError] = useState('');
  const [active, setActive] = useState(false);
  const generation = useRef(0);
  function stop() { generation.current += 1; stream.current?.getTracks().forEach(t => t.stop()); stream.current = null; setActive(false); }
  useEffect(() => () => { generation.current += 1; stream.current?.getTracks().forEach(t => t.stop()); }, []);
  async function preview() {
    stop(); setError('');
    const request = generation.current;
    try {
      const media = await navigator.mediaDevices.getUserMedia({ video: device ? { deviceId: { exact: device } } : true, audio: false });
      if (request !== generation.current) { media.getTracks().forEach(t => t.stop()); return; }
      stream.current = media; if (video.current) video.current.srcObject = media; setActive(true);
      const available = await navigator.mediaDevices.enumerateDevices();
      if (request === generation.current) setDevices(available.filter(d => d.kind === 'videoinput'));
    } catch (e) { if (request === generation.current) setError((e as Error).message); }
  }
  return <details><summary>Camera preview</summary><p className="hint">Optional local preview. Frames are neither sent to the server nor recorded. An observation device is configured separately.</p>
    <label>Camera<select value={device} onChange={e => setDevice(e.target.value)}><option value="">System default</option>{devices.map(d => <option key={d.deviceId} value={d.deviceId}>{d.label || 'Camera'}</option>)}</select></label>
    <div className="button-row"><button className="secondary" onClick={() => void preview()}>Preview selected camera</button><button className="quiet" disabled={!active} onClick={stop}>Stop camera</button></div>
    <video ref={video} autoPlay playsInline muted hidden={!active} style={{ width: '100%', maxHeight: 260 }} />{error && <p role="alert">{error}</p>}</details>;
}

export function InputDevices({ study, draft, fail }: { study: Study; draft: (d: Draft) => void; fail: (s: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [emotion, setEmotion] = useState('');
  const [valence, setValence] = useState('');
  const [arousal, setArousal] = useState('');
  const [saved, setSaved] = useState(false);
  const sid = study.current!.config.session_id;
  async function capture(kind: string) {
    setBusy(true); fail('');
    try { const result = await api<{ draft?: Draft }>(`/studies/${study.plan_id}/capture`, 'POST', { kind, request_id: newRequest(), session_id: sid }); if (result.draft) draft(result.draft); else setSaved(true); }
    catch (e) { fail((e as Error).message); } finally { setBusy(false); }
  }
  return <>{(study.speech_available || study.perception_available) && <div className="button-row">
    {study.speech_available && <button className="secondary" disabled={busy} onClick={() => void capture('speech')}>{busy ? 'Listening…' : 'Capture speech draft'}</button>}
    {study.perception_available && <button className="secondary" disabled={busy} onClick={() => void capture('perception')}>Capture observation</button>}
  </div>}{study.manual_affect && <details><summary>Optional self-report</summary><p className="hint">Report how you feel. These are your ratings, not a sensor measurement.</p><div className="form-grid"><label>Emotion<select value={emotion} onChange={e => setEmotion(e.target.value)}><option value="">Not reported</option>{['Sad', 'Anger', 'Neutral', 'Happy', 'Surprise', 'Fear', 'Disgust'].map(v => <option key={v}>{v}</option>)}</select></label><label>Valence (−1 to 1)<input type="number" min="-1" max="1" step="0.1" value={valence} onChange={e => setValence(e.target.value)} /></label><label>Arousal (−1 to 1)<input type="number" min="-1" max="1" step="0.1" value={arousal} onChange={e => setArousal(e.target.value)} /></label></div>
    <button className="secondary" disabled={busy} onClick={async () => { setBusy(true); try { await api(`/studies/${study.plan_id}/affect`, 'POST', { request_id: newRequest(), session_id: sid, values: { valence: valence === '' ? null : Number(valence), arousal: arousal === '' ? null : Number(arousal), ...(emotion ? { emotions: { [emotion]: 1 } } : {}), missing_reason: 'not_reported' } }); setSaved(true); } catch (e) { fail((e as Error).message); } finally { setBusy(false); } }}>Save self-report</button></details>}{saved && <p className="hint" role="status">Observation saved.</p>}</>;
}

export function useVisibleActions(study: Study, fail: (s: string) => void) {
  const sid = study.current?.config.session_id;
  const latest = study.current?.offers.at(-1)?.sequence;
  const terminal = study.current?.terminal_event_id;
  useEffect(() => {
    if (!sid) return;
    let cancelled = false;
    const acknowledge = async () => {
      if (cancelled || document.visibilityState !== 'visible') return;
      for (const eid of [latest ? `${sid}:${latest}` : null, terminal]) {
        if (eid) {
          try { await api(`/studies/${study.plan_id}/visible`, 'POST', { request_id: `visible-${eid}`, session_id: sid, event_id: eid }); }
          catch (e) { if (!cancelled) fail((e as Error).message); }
        }
      }
    };
    const frame = requestAnimationFrame(() => void acknowledge());
    const change = () => { void acknowledge(); };
    document.addEventListener('visibilitychange', change);
    return () => { cancelled = true; cancelAnimationFrame(frame); document.removeEventListener('visibilitychange', change); };
  }, [sid, latest, terminal, study.plan_id, fail]);
}
