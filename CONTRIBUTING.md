# Contributing

Thanks for improving env_law. This project is a research harness, so changes
must preserve its core rule: claims about environmental law require evidence
verified from the 국가법령정보 공동활용 OpenAPI.

## Before opening a pull request

1. Create a branch from `main` and keep the change focused.
2. Do not commit `.env`, `LAW_API_OC`, API URLs with an `OC` value, run logs,
   `.harness/`, `.omc/`, or `.omx/` state.
3. Run the offline checks:

   ```bash
   npm ci
   ./scripts/release_gate.sh --skip-gitleaks
   ```

   This produces an `INCOMPLETE` diagnostic result; the required Secret scan
   workflow supplies the separate Gitleaks check on the pull request.
4. Run `npm run test:api` only with your own locally stored `LAW_API_OC`. Do
   not add the credential to test output, fixtures, screenshots, or commits.
5. Update tests and user-facing documentation when the output contract,
   supported environment, or security behavior changes.

## Pull request expectations

Describe the problem, the evidence for the change, and the checks you ran.
Avoid placing personal queries, legal case details, or any credential in a PR
description. CI must pass before merge; maintainers should use GitHub's private
security reporting channel for security-sensitive findings.

## Legal-content changes

Do not fill gaps from memory. Cite the law name, article/paragraph/item,
effective date, identifier, and source URL only after the API response verifies
them. Mark information that cannot be verified as unavailable rather than
guessing.
