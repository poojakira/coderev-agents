# Security Policy

## Supported Versions

`main` is supported. This is an LLM-assisted security code review prototype, not an autonomous vulnerability authority.

## Reporting Vulnerabilities

Report issues through GitHub security advisories or the maintainer profile contact. Do not submit proprietary source code as an attachment.

## Security Focus

- Treat diffs, repository text, tool output, and model responses as untrusted input.
- Static analysis findings should be combined with LLM summaries and human review.
- The agent should flag insecure patterns and summarize risk with line-level evidence.
- CI runs tests, lint, and dependency audit gates.

## Known Limitations

- LLM findings can hallucinate or miss vulnerabilities.
- Static tools have false positives and false negatives.
- This project should assist a reviewer, not replace security review ownership.
