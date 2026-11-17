// Carries their name because it was built for them. Says so, on every page.
export const DISCLAIMER = "Built for a job application. Not affiliated with or endorsed by Plexxcon; all data is synthetic.";

// Same origin in dev (Vite proxy) and in production (nginx sidecar).
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// Operator write token. Open the site once with ?write_token=<value>; it is
// kept in sessionStorage, scrubbed from the URL, and sent as X-Write-Token.
// It unlocks every write - drafts, submissions, reviews, confirmed dockets - and
// exempts the session from the assistant's rate limit. The plain link is the
// read-only role, and says so when you try.
const TOKEN_KEY = "plexxcon_demo_write_token";
const ACTOR_KEY = "plexxcon_demo_actor";

function captureTokenFromUrl() {
  try {
    const url = new URL(window.location.href);
    const token = url.searchParams.get("write_token");
    if (token) {
      sessionStorage.setItem(TOKEN_KEY, token);
      url.searchParams.delete("write_token");
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    }
  } catch { /* storage blocked */ }
}
captureTokenFromUrl();

export function writeToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
}

export function authHeaders() {
  const token = writeToken();
  return token ? { "X-Write-Token": token } : {};
}

// Who the operator is acting as. Recorded on every write and used for
// separation of duties (nobody decides their own request); never trusted as
// identity. A production build takes it from the identity provider.
export function actorName() {
  try { return sessionStorage.getItem(ACTOR_KEY) || "Estimator A"; } catch { return "Estimator A"; }
}

export function setActorName(name) {
  try { sessionStorage.setItem(ACTOR_KEY, name); } catch { /* storage blocked */ }
}

// The assistant sends the same headers so the operator is exempt from its rate limit.
export function requestHeaders() {
  return { "X-Actor": actorName(), ...authHeaders() };
}
