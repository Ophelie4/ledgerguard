# LedgerGuard

**Five GitLab Duo agents that guard money code for micro-lenders and mobile-money apps.**

In lending software the worst bugs don't crash. They quietly move money wrong: interest
computed with floats, a mobile-money callback retried and credited twice, a ledger entry
with no matching side, a borrower's phone number in the logs. LedgerGuard catches these
bugs, proves them with tests, fixes them, proves the live ledger still balances on Google
Cloud Run, and stops at a human before anything reaches production.

## The five agents

Each agent is a custom GitLab Duo Agent Platform flow in [`flows/`](flows/), running as its
own service account.

| # | Agent | Trigger | What it does |
|---|-------|---------|--------------|
| 1 | **Reviewer** ([flows/01-reviewer.yml](flows/01-reviewer.yml)) | Assign as MR reviewer | Reads the diff and posts one review covering four money risks: `FLOAT_MONEY`, `IDEMPOTENCY`, `UNBALANCED_LEDGER`, `PII_LEAK`. |
| 2 | **Test Writer** ([flows/02-test-writer.yml](flows/02-test-writer.yml)) | Mention in an MR | Turns each finding into a failing pytest in `lending/tests/test_ledgerguard_regressions.py` and commits it to the MR branch. |
| 3 | **Pipeline Fixer** ([flows/03-pipeline-fixer.yml](flows/03-pipeline-fixer.yml)) | Mention in an MR | Reads the failed job logs and commits the smallest money-safe fix to the application code. It never edits tests or CI. |
| 4 | **Deploy Verifier** ([flows/04-deploy-verifier.yml](flows/04-deploy-verifier.yml)) | Mention on a merged MR | Reads the Cloud Run deploy and the live ledger proof from CI, then reports PASS/FAIL with debits vs credits. |
| 5 | **Release Gate** ([flows/05-release-gate.yml](flows/05-release-gate.yml)) | Mention on an MR or issue | Collects every signal and gives GO or NO-GO. A human makes the final call by running the manual `release-production` job. |

```
MR opened ──► 1 Reviewer ──► 2 Test Writer ──► pipeline red ──► 3 Pipeline Fixer ──► pipeline green
                                                                                        │ merge
   human approves ◄── 5 Release Gate (GO / NO-GO) ◄── 4 Deploy Verifier ◄── Cloud Run staging + ledger proof
        │
        └──► release-production: same image promoted, ledger proof re-run on production
```

## Pipeline ([.gitlab-ci.yml](.gitlab-ci.yml))

| Stage | Job | Runs on |
|-------|-----|---------|
| test | `unit-tests` (pytest), `semgrep-sast`, `secret_detection` | every MR and branch |
| deploy | `deploy-staging`: Cloud Run service `ledgerguard-staging` | `main` |
| verify | `verify-ledger`: [scripts/reconcile.py](scripts/reconcile.py) against the live URL, saved as `ledger-proof.json` | `main` |
| release | `release-production`: **manual and blocking**. Promotes the verified image to service `ledgerguard`, then re-runs the proof | `main`, human approval |

Deploys are keyless. GitLab's OIDC token is exchanged through Google Cloud Workload
Identity Federation for a deployer service account that is restricted to this project. No
service-account keys are stored anywhere.

## The app being guarded

A small Django REST lending API (`lending/`):

- **Double-entry ledger.** `services.post()` refuses any transaction whose debits don't equal its credits.
- **Decimal money only.** `money()` is the single rounding rule. Declining-balance schedules always sum exactly to the principal.
- **Idempotent mobile-money callbacks.** Each callback has a unique `external_id` and uses `get_or_create`.
- **Masked phone numbers** in every log line.

Endpoints: `POST /loans`, `GET /loans/<id>/schedule`, `POST /repayments`,
`POST /momo/callback`, `GET /ledger/balance`.

## Demo branches (planted money bugs)

| Branch | Bug | Category |
|--------|-----|----------|
| `bug/airtel-callback` | Airtel callback uses a random reference, so a retry credits the borrower twice | IDEMPOTENCY |
| `bug/float-interest` | Interest computed with `float` and `round()` | FLOAT_MONEY |
| `bug/late-fee` | Late fee debited with no matching credit | UNBALANCED_LEDGER |
| `bug/phone-in-logs` | Raw phone number written to logs | PII_LEAK |

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                       # unit, ledger and API tests
python manage.py migrate && python manage.py runserver
STAGING_URL=http://127.0.0.1:8000 python scripts/reconcile.py   # ledger proof
```

## Set up the agents in your own GitLab project

1. In **AI → Flows → New flow**, paste each file from `flows/`. Then enable it in the project with the trigger from the table above.
2. Set up Google Cloud Workload Identity Federation for your project path (see [docs/gcp-setup.md](docs/gcp-setup.md)). Then update the variables at the top of `.gitlab-ci.yml`.

## License

MIT. Built by Ophelie Bisamaza, with help from Claude (Anthropic) as a coding assistant.
