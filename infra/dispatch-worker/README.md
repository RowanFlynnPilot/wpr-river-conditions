# Dispatch worker

A Cloudflare Worker that triggers the `Fetch Data & Deploy` workflow every
30 minutes. It exists because GitHub's scheduler is best-effort: between
August and October 2026 it delivered about 6 of the 38 configured runs a day.

The cron in `deploy.yml` stays as a fallback, so nothing breaks if this worker
is never deployed or goes down.

## One-time setup (about 10 minutes, free tier)

1. **Create a GitHub token.** GitHub → Settings → Developer settings →
   Fine-grained tokens → Generate new token.
   - Repository access: only `RowanFlynnPilot/wpr-river-conditions`
   - Permissions: **Actions → Read and write** (nothing else)
   - Set an expiry you will remember; the worker stops triggering when it lapses.
2. **Deploy the worker** from this folder:

   ```
   npx wrangler login
   npx wrangler deploy
   npx wrangler secret put GITHUB_TOKEN
   ```

3. **Check it.** Within 30 minutes a run with the `workflow_dispatch` event
   should appear under the repo's Actions tab. `npx wrangler tail` shows the
   worker's log if it does not.

## When the token expires

Dispatches start failing with 401 and the worker's error rate goes to 100% in
the Cloudflare dashboard. The fallback cron keeps the site updating slowly, and
the `Data freshness check` workflow fails if the data gets more than 6 hours
old. Generate a new token and run `npx wrangler secret put GITHUB_TOKEN` again.
