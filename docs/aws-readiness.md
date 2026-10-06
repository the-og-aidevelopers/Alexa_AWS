# Local first; AWS connection later

The app starts with `AWS_ENABLED=0`, local caregiver accounts, local routing, and SQLite. Existing credentials never activate Bedrock. Even explicit `use_bedrock=True`, `AGENT_WITH_BEDROCK=1`, and `SPEAK_WITH_BEDROCK=1` cannot bypass the global gate. There are no startup AWS provisioning calls, background model jobs, or credential discovery calls. Browser speech recognition and speech synthesis remain browser services and may need internet; local mode does not promise offline audio transcription.

## Available now

- Create a caregiver account and private household at `/login`. Passwords use salted PBKDF2-SHA256 with 600,000 iterations. Sessions expire after 12 hours, store only token hashes, use HttpOnly/SameSite=Strict cookies, and are revoked on sign out. HTTPS makes the cookie Secure.
- `/` is the caregiver schedule/today/alert dashboard; `/agent` is the older adult voice page, opened using the same caregiver session. Switching conversational mode grants no permissions. Household isolation applies to REST and direct MCP tools, including deletion and log reset.
- Add household members through the existing `register_person` tool or by adding their medicine schedules. Newly created households start empty. Existing seeded data remains in the explicit demo household, not assigned to a newly registered account.
- With multiple household members, an unnamed dose-log request asks for a name before writing. Say “Mom took the morning one.” This is manual attribution, not biometric identity.
- Bedrock routing and optional rephrasing are wired behind separate flags. Provider failures retain local routing/template speech.
- Cognito access-token verification is implemented, with signature, issuer, expiration, `token_use=access`, and client ID checks. It uses the configured pool’s fixed JWKS URL and requires an existing trusted subject-to-household mapping. Tests use locally generated RSA keys; no AWS requests.

## Connect Bedrock later

Export `AWS_ENABLED=1`, `AGENT_WITH_BEDROCK=1`, `AWS_REGION`, and `BEDROCK_MODEL_ID` explicitly. Keep `SPEAK_WITH_BEDROCK=0` unless the extra response call is wanted. Provide a workload role or local AWS profile with `bedrock:InvokeModel` restricted to the chosen model/inference profile resources. Confirm model access and region support first. Each non-mode request may make a model call; enabling rephrasing can add another. Meter costs and set account budgets before activation.

## Connect Cognito later

`infra/cognito.json` is a starter CloudFormation template for a user pool and public client; it is not deployed or validated against an AWS account. Review settings and deployment costs before creating resources. It does not create hosting, domains, hosted-login callbacks, or a frontend authentication flow.

Set `AWS_ENABLED=1`, `DOSE_AUTH_PROVIDER=cognito`, `AWS_REGION`, `COGNITO_USER_POOL_ID`, and `COGNITO_CLIENT_ID`. The adapter accepts `Authorization: Bearer <access-token>` for API/MCP requests. Before allowing access, a trusted administrator must map the verified Cognito `sub` to an account’s `cognito_sub` and household ID in the database. Never take the household ID from the token’s custom attributes, an HTTP payload, or the LLM. Unmapped subjects are denied. Local password routes are disabled in Cognito mode.

The browser login page supports local sessions only. Add the hosted-login/PKCE browser client and membership provisioning when connecting Cognito. Cognito access tokens are verified offline after fetching signing keys; revocation is not checked on every request. Use short token lifetimes and review sign-out/revocation behavior before production acceptance. Local passwords are not migrated to Cognito automatically.

## Hosting and storage

Keep one local process and SQLite for development. For an AWS deployment, choose hosting and persistent storage together. SQLite requires a durable volume and a single writer deployment; do not place it on an ephemeral container filesystem or scale independent SQLite replicas. Managed shared storage requires a real repository adapter/migration before multiple application instances. Backups, HTTPS, exact public MCP hosts/origins, and the loopback MCP URL behind a reverse proxy must be configured and tested as part of hosting. Current MCP host/origin settings intentionally support localhost only. No cloud hosting/storage resources are provisioned by this change.

## Voice identity

Voice biometrics remains disabled: no enrollment recordings, voiceprints, similarity scores, or pretend identity provider. Confirm a person by name for now. A future provider must supply enrollment/deletion, consent and retention rules, a calibrated confidence threshold, and a confirmation step for uncertain matches. A guessed name must never silently select whose dose is written. Actual microphone/noise and speaker-identity acceptance remain open.

## Optional seeded demo

`DOSE_AUTH_PROVIDER=demo` deliberately disables login and exposes only household 1. Use on localhost with sample data. It is not the default and is not suitable for a shared deployment.

## AWS references

- [Cognito JWT verification](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html)
- [CloudFormation user-pool client settings](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cognito-userpoolclient.html)
