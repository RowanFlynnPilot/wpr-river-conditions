// Fires the "Fetch Data & Deploy" workflow on a reliable 30-minute clock.
// GitHub's own cron is best-effort and was delivering about one run in six.
//
// Secrets (set with `wrangler secret put`):
//   GITHUB_TOKEN — fine-grained PAT, this repo only, "Actions: Read and write"

const REPO = 'RowanFlynnPilot/wpr-river-conditions';
const WORKFLOW = 'deploy.yml';

async function dispatch(env) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'wpr-river-dispatch-worker',
      },
      body: JSON.stringify({ ref: 'main' }),
    }
  );
  if (!res.ok) {
    // Thrown errors surface in the Worker's logs and its error-rate graph.
    throw new Error(`GitHub dispatch failed: ${res.status} ${await res.text()}`);
  }
}

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },
  // No public trigger: a GET only reports that the worker is deployed.
  async fetch() {
    return new Response('wpr-river-dispatch: ok\n', { status: 200 });
  },
};
