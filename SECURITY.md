# Security policy

## Supported versions

Security fixes are provided for the latest commit on the `main` branch. Tagged
releases, if published later, will state their support window in their release
notes.

## Reporting a vulnerability

Do not disclose suspected vulnerabilities in public issues, pull requests, or
discussion threads. Use GitHub's **Report a vulnerability** control in this
repository's *Security* tab to submit a private report. Include a concise
description, impact, reproduction steps, and any proposed mitigation.

If private vulnerability reporting is not enabled for the repository, do not
publish the details. Open a minimal public issue that asks a maintainer to
enable it, without including the vulnerability, credentials, API IDs, request
URLs containing credentials, or proof-of-concept payloads.

## Secret handling

`LAW_API_OC` is a user-specific credential. Never commit it, include it in an
issue, paste it into a workflow log, or use it in an example. If it is exposed,
revoke or replace it through the 국가법령정보 공동활용 OpenAPI service and remove
the value from every affected environment and Git history before publishing.
