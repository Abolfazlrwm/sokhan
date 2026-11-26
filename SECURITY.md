# Security Policy

## Reporting a vulnerability

Please do **not** open a public issue for a security vulnerability.

Use GitHub's **private vulnerability reporting**: open this repository's
**Security** tab and choose **Report a vulnerability**. Reports stay
private until you decide to disclose, and no email setup is required on
either side.

## What to include

- A short description of the issue and its impact
- Steps to reproduce (or a minimal proof of concept)
- The version or commit you tested against

## Response expectations

This is a small, single-maintainer project: triage usually happens within
a few days, fixes for confirmed vulnerabilities ship as soon as they are
ready, and coordinated disclosure is welcome.

## Code scanning policy

CodeQL (static analysis) runs on every push and weekly; findings land in
the Security tab. Every alert gets one of three dispositions, never
silence:

1. **Fix** — for findings that describe a real, reachable weakness
   (for example the polynomial email-regex backtracking and the worker
   origin check fixed in November 2026).
2. **Dismiss with a written justification** — for framework-standard
   patterns the query cannot see the context of. Each dismissal comment
   on an alert states exactly why the code is safe (for example: API
   tokens are high-entropy secrets hashed with SHA-256, which is the
   industry-standard storage for tokens, distinct from password storage
   which uses scrypt).
3. **Track as an issue** — when a fix needs design work (for example
   moving the dashboard token from localStorage to an httpOnly cookie
   implied a CSRF layer: it was tracked as #33 and has since shipped, so
   the dashboard no longer keeps the token in script-readable storage).

Dismissed alerts stay visible in the Security tab with their
justification, so the reasoning is auditable rather than hidden.
