export async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
  }
  return response.status === 204 ? null : response.json();
}
export const json = body => ({ method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
