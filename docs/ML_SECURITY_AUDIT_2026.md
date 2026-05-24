# 2026 ML Security Audit

Generated from local repository evidence. This file is intentionally conservative: it reports files, controls, and gaps that can be inspected in this repository.

## Scope

- Topic: Agentic trust boundaries
- Standards map: OWASP LLM01, OWASP LLM06, OWASP LLM08
- Data provenance: Security fixtures over code diffs; no company dataset claimed.
- Git state at generation: dirty
- Test files detected: 3
- GitHub workflows detected: 1

## Evidence Found

- trust boundary
- untrusted diff
- langgraph
- pip-audit

## Open Gaps

- No configured evidence-map gaps detected.

## Recruiter Signal

This repository should be evaluated by running its checked-in tests and CI/security gates. Do not cite benchmark numbers or production readiness unless the repo contains the command, artifact, and current passing validation needed to reproduce the claim.

## Rebuild

Run from the profile repository:

```bash
python tools/build_security_dashboard.py
```
