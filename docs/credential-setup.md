# Credential and Infrastructure Setup

Do not paste secrets into chat or commit them. Put local values in `.env`; use each provider's secret store in deployed environments.

## Recommended hosting architecture

- **React console:** Cloudflare Pages
- **Public ingress/security:** Cloudflare Worker in front of the API domain
- **FastAPI runner:** Google Cloud Run in `asia-south1` (Mumbai)
- **State and reactive queries:** Convex
- **Scheduled triggers:** Convex scheduled functions/cron calling authenticated runner endpoints
- **Secrets:** Google Secret Manager for Cloud Run; Cloudflare encrypted secrets for the Worker; Convex environment variables for Convex functions

Cloud Run is recommended because the selected calendar is Google Calendar, Mumbai is close to the clinic, containerized FastAPI deploys cleanly, and it supports production revisions, autoscaling, service accounts, logging, and Secret Manager. Configure a minimum instance later if cold-start latency is unacceptable. The Cloudflare Worker should validate/rate-limit public ingress but must not contain agency logic.

## 1. Telegram

1. In Telegram, open `@BotFather`.
2. Run `/newbot`, choose the display name and username, and copy the bot token into `TELEGRAM_BOT_TOKEN`.
3. Generate a random webhook secret and set `TELEGRAM_WEBHOOK_SECRET`.
4. Send one message to the bot after the local/public webhook is ready.
5. Read the incoming update's `message.chat.id` from sanitized development logs or the Telegram `getUpdates` response and set `TELEGRAM_ADMIN_CHAT_ID`.
6. After deployment, register the HTTPS webhook URL and the same secret token.

Required variables:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_ADMIN_CHAT_ID=
TELEGRAM_ALLOWED_CHAT_IDS=
```

## 2. Convex

1. Create or sign in to a Convex account.
2. Create a project for the clinic agency with separate development and production deployments.
3. During scaffold, run `npx convex dev` and complete the browser authorization.
4. Copy the generated deployment name and URL to `.env`.
5. Create/use a production deploy key only in CI or the protected deployment environment.

Required variables:

```dotenv
CONVEX_DEPLOYMENT=
CONVEX_URL=
CONVEX_DEPLOY_KEY=
```

Never expose `CONVEX_DEPLOY_KEY` in the React client. The frontend may use the public deployment URL; privileged mutations must enforce authorization.

## 3. Google Calendar

### Recommended production setup: dedicated calendar plus service account

1. Create/select a Google Cloud project.
2. Enable **Google Calendar API**.
3. Create a service account for the runner.
4. Create a dedicated clinic coordination calendar in Google Calendar.
5. Share only that calendar with the service account email and grant permission to make changes to events.
6. Copy the calendar ID from Calendar settings into `GOOGLE_CALENDAR_ID`.
7. For local development only, download a service-account JSON key outside the repository and set `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`.
8. For Cloud Run, do not upload a JSON key. Run Cloud Run as the service account and use Application Default Credentials.

Required variables:

```dotenv
GOOGLE_CALENDAR_ID=
GOOGLE_SERVICE_ACCOUNT_JSON_PATH=
GOOGLE_CALENDAR_TIMEZONE=Asia/Kolkata
GOOGLE_CALENDAR_HOLD_MINUTES=15
GOOGLE_CALENDAR_SLOT_MINUTES=30
GOOGLE_CALENDAR_BUFFER_BEFORE_MINUTES=0
GOOGLE_CALENDAR_BUFFER_AFTER_MINUTES=10
```

If service-account calendar sharing is restricted by Workspace policy, use OAuth and populate the `GOOGLE_OAUTH_*` variables instead.

### Appointment state

The selected workflow is **tentative hold pending deposit**:

1. Patient explicitly selects a slot.
2. Runner rechecks availability.
3. Runner creates a private tentative event with a 15-minute expiry and stable idempotency key.
4. Runner creates the Dodo checkout.
5. Signed payment webhook confirms the event.
6. Expired/failed payment releases the hold and offers fresh slots.

## 4. Hosted model provider

Choose one provider or gateway that exposes the selected models. Create a restricted API key and add it only to `.env`/Secret Manager.

```dotenv
LLM_API_KEY=
LLM_BASE_URL=
MANAGER_MODEL=
COMPLIANCE_MODEL=
TRIAGE_MODEL=
KNOWLEDGE_MODEL=
DRAFTER_MODEL=
BOOKING_MODEL=
LIFECYCLE_MODEL=
LLM_JUDGE_MODEL=
MAX_CASE_COST_USD=1.00
```

Production model IDs must be pinned rather than aliases where the provider supports versioned IDs. Manager and Compliance should use the strongest reliable model; other roles can use a faster model after evals prove safety and routing quality.

## 5. Dodo Payments

1. Create/sign in to the Dodo Payments dashboard.
2. Use test mode initially.
3. Create the booking-deposit product/price in INR.
4. Create a restricted test API key and set `DODO_API_KEY`.
5. After the runner has a public URL, add its Dodo webhook endpoint in the dashboard.
6. Subscribe to the checkout/payment success, failure, cancellation, and refund-related events used by the application.
7. Copy the endpoint signing secret into `DODO_WEBHOOK_SECRET`.
8. Set success and cancellation URLs to console pages under the final domain.
9. Complete at least one test checkout and verify signature handling and idempotency before enabling live mode.

```dotenv
DODO_API_KEY=
DODO_WEBHOOK_SECRET=
DODO_ENVIRONMENT=test_mode
DODO_PRODUCT_ID=
DODO_CURRENCY=INR
DODO_DEPOSIT_PERCENT=20
DODO_SUCCESS_URL=
DODO_CANCEL_URL=
```

Do not switch to live mode until refund, expiry, duplicate webhook, and partial-failure behavior passes acceptance tests.

## 6. ElevenLabs

1. Create/sign in to ElevenLabs.
2. Create a restricted API key.
3. Select a voice suitable for the clinic's supported languages and copy its
   non-secret **Voice ID**.
4. Pin supported STT/TTS model IDs after testing latency and quality.
5. Keep raw-audio storage disabled unless a separate consent and retention policy is approved.

```dotenv
ELEVENLABS_API_KEY=
ELEVENLABS_STT_MODEL_ID=scribe_v1
ELEVENLABS_TTS_MODEL_ID=eleven_multilingual_v2
ELEVENLABS_VOICE_ID=
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
VOICE_MAX_AUDIO_BYTES=26214400
# Optional metadata only; this adapter does not call the Agents Platform.
ELEVENLABS_AGENT_ID=
STORE_RAW_AUDIO=false
```

`ELEVENLABS_API_KEY` is the only secret and must remain in the runner's
server-side `.env`/Secret Manager. The exact required non-secret settings are
`ELEVENLABS_VOICE_ID`, `ELEVENLABS_STT_MODEL_ID=scribe_v1`,
`ELEVENLABS_TTS_MODEL_ID=eleven_multilingual_v2`, and
`ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128`. `ELEVENLABS_AGENT_ID` is optional and
is retained only as deployment metadata: Hermes/OpenAI orchestration generates
the authoritative reply; ElevenLabs performs STT and TTS only. Missing key or
voice ID leaves voice disabled without affecting text workflows.

## 7. Linkup

1. Create/sign in to Linkup.
2. Create an API key.
3. Put it in `LINKUP_API_KEY`.
4. Keep the domain allowlist fixed to the clinic-owned sites.

```dotenv
LINKUP_API_KEY=
LINKUP_ALLOWED_DOMAINS=clearskin.in,hairmdindia.com
LINKUP_TIMEOUT_SECONDS=15
```

The selected policy allows immediate cited answers from allowlisted domains. Pricing, contraindication, and pre/post-care claims should still be checked against structured clinic policy; conflicts defer to the approved KB and create a KB-gap review item.

## 8. Cloudflare Pages

1. Create/sign in to Cloudflare.
2. Add/verify the desired domain if it is not already in the account.
3. Go to **Workers & Pages → Create → Pages → Connect to Git**.
4. Select the public GitHub repository.
5. Set the console root directory to `console`.
6. Set the production build command and output directory after Vite is scaffolded (normally `npm run build` and `dist`).
7. Add only public frontend variables, such as the Convex public URL and API base URL. Never add server API keys to Pages build variables.
8. Add a custom console domain, for example `ops.example.com`.

Local/automation variables:

```dotenv
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_PAGES_PROJECT_NAME=clinic-agency-console
CLOUDFLARE_CONSOLE_DOMAIN=
```

### Cloudflare API token

Create a custom token under **My Profile → API Tokens** with the narrowest practical permissions:

- Account / Cloudflare Pages: Edit
- Account / Workers Scripts: Edit (only if deploying the ingress Worker)
- Zone / DNS: Edit for the selected zone (only if automation manages DNS)
- Zone / Zone: Read

Restrict the token to the specific account and zone. Store it as `CLOUDFLARE_API_TOKEN`; never expose it to the browser.

## 9. Cloudflare Worker ingress

1. Create a Worker named `clinic-agency-ingress`.
2. Bind a route such as `api.example.com/*`.
3. Configure the Cloud Run origin URL as an encrypted Worker secret.
4. Store webhook verification material as encrypted Worker secrets where edge verification is implemented.
5. Add request-size limits, rate limiting, bot controls, correlation IDs, and strict allowed routes.
6. Forward only valid traffic to Cloud Run.

```dotenv
CLOUDFLARE_WORKER_NAME=clinic-agency-ingress
CLOUDFLARE_ZONE_ID=
CLOUDFLARE_API_DOMAIN=
```

The Worker should not receive model-provider, Calendar, Dodo API, Linkup, or ElevenLabs credentials.

## 10. Google Cloud Run

1. Create/select the Google Cloud project and enable Cloud Run, Artifact Registry, Cloud Build, Secret Manager, and Calendar APIs.
2. Create an Artifact Registry Docker repository in `asia-south1`.
3. Create a dedicated Cloud Run runtime service account.
4. Grant only required permissions: Secret Manager accessor for named secrets and Calendar access through sharing/domain policy. Avoid project-wide Editor.
5. Store server secrets in Secret Manager.
6. Build and deploy the FastAPI container to Cloud Run in `asia-south1`.
7. Initially permit ingress only from the Cloudflare path where practical; otherwise require a shared origin secret and deny direct webhook routes without it.
8. Set concurrency and timeout based on load tests. Start conservatively; increase only with evidence.
9. Map the API domain through Cloudflare to the Worker, not directly to an unprotected service URL.

```dotenv
GCP_PROJECT_ID=
GCP_REGION=asia-south1
GCP_CLOUD_RUN_SERVICE=clinic-agency-runner
GCP_ARTIFACT_REGISTRY=clinic-agency
GCP_SERVICE_ACCOUNT_EMAIL=
```

## 11. Optional WhatsApp

Only configure after Telegram is stable and only if the existing approved Meta app can be repointed safely.

```dotenv
WHATSAPP_ENABLED=false
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=
```

Use a system-user token appropriate for server use, verify Meta webhook signatures, and never expose the token in the console.

## 12. Clinic policy information still required

The owner is final approver. Create versioned, auditable cards for:

- Clinic locations and opening hours
- Clinicians and procedure eligibility
- Prices and price qualifiers
- Deposit percentage and hold expiry
- Cancellation, rescheduling, refund, no-show, and EMI policies
- Red-flag list and approved urgent acknowledgement
- Prohibited claims and required disclaimers
- Approved pre-care and post-care instructions
- Source URL, approval status, approver, and approved timestamp for every card

Website-derived content starts as `draft`. It may be used immediately only through the explicitly allowed Linkup cited-answer path; structured policy cards require owner approval before becoming `approved`.
