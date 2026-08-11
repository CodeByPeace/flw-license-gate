# Flutterwave License Gate

A minimal, forkable Flask reference for gating any resource behind a
one-time Flutterwave payment, using a license-key system.

Pay once → get a license key by email → activate the key on a resource →
resource unlocked. No subscriptions, no webhooks required, no external
license server.

## Why this exists

Flutterwave's official SDKs handle raw payment collection well, but none
of them ship the layer most indie products actually need on top: turning
a successful payment into a license key, and gating a route behind that
key. This repo is that missing layer, stripped down to the minimum,
ready to fork.

## How it works

1. Buyer visits `/pricing`, enters email, pays via Flutterwave inline checkout
2. On successful payment, the server verifies the transaction server-side
   (never trusts the client callback alone) and generates a license key
3. Buyer enters that key on `/resource/<id>/activate`
4. The resource unlocks — any route can be gated with one line:
   `if not resource_is_licensed(id): redirect to license_required`

## Quickstart

\`\`\`bash
git clone <this-repo>
cd flw-license-gate
pip install flask requests
export FLW_SECRET_KEY=your_secret_key
export FLW_PUBLIC_KEY=your_public_key
python3 app.py
\`\`\`

Visit `http://localhost:8080`.

## Adapting this to your project

Everything is built around a generic `resource` — swap that for whatever
you're actually gating (a club, a project, a document, a user account).
The core license logic (`get_license_for_resource`, `resource_is_licensed`,
`activate_license`, the Flutterwave verify call) doesn't need to change.

## Security notes

- Never trust the payment callback status alone — this template always
  re-verifies the transaction server-side against Flutterwave's API
  before issuing a license key
- Keep `FLW_SECRET_KEY` out of your repo — use environment variables
- This is a reference template, not a production payment system — review
  it for your own threat model before shipping

## License

MIT — fork it, strip it, ship it.
