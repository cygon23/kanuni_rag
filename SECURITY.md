# Security Policy

## Supported versions

Kanuni is pre-1.0 and under active development. Only the `main` branch
receives security fixes.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, email **godfreymuganyizi45@gmail.com** with:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a proof of concept if available.
- Any suggested remediation, if you have one.

We aim to acknowledge reports within 5 business days and to provide a
remediation timeline once the issue is confirmed. Please allow us a
reasonable period to fix the issue before any public disclosure.

## Scope

In scope: the API service, ingestion worker, frontend, and infrastructure
configuration in this repository. Out of scope: third-party services we
depend on (Supabase, Groq, Hugging Face, Vercel, GlitchTip) — report
those directly to the respective vendor.

## Handling of secrets

Secrets are only ever supplied via environment variables (see
`.env.example`). If you discover a secret committed to this repository's
history, please report it privately using the contact above rather than via
a public issue or PR.
