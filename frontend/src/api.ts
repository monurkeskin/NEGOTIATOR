const params = new URLSearchParams(window.location.search);
const role = params.get('view') === 'participant' ? 'participant' : 'conductor';
const storageKey = `negotiator-access-${role}-${role === 'participant' ? params.get('plan') : 'local'}`;
const supplied = new URLSearchParams(window.location.hash.slice(1)).get('token');
if (supplied) {
  sessionStorage.setItem(storageKey, supplied);
  history.replaceState(null, '', window.location.pathname + window.location.search);
}
export const token = sessionStorage.getItem(storageKey) ?? '';
export const participant = role === 'participant';

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method, headers: { 'Content-Type': 'application/json', 'X-Negotiator-Token': token },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const message = Array.isArray(data.detail) ? data.detail.map((item: { msg: string }) => item.msg).join('; ') : data.detail;
    throw new Error(message || 'The request could not be completed.');
  }
  return data as T;
}

export function participantUrl(plan: string, access: string): string {
  return `${location.origin}/?view=participant&plan=${encodeURIComponent(plan)}#token=${encodeURIComponent(access)}`;
}
