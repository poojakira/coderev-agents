# Secret Rotation Policy

Fix A5 / STRIDE-R (Repudiation) / STRIDE-I (Information Disclosure).

## Secret Inventory

| Secret | Env Var | Storage | Rotation Frequency | Owner |
|---|---|---|---|---|
| OpenAI API key | `CODEREV_LLM_API_KEY` | GitHub Actions Secret + K8s Secret `coderev-secrets/llm-api-key` | 90 days or on suspected compromise | Platform |
| API authentication key | `CODEREV_API_SECRET_KEY` | K8s Secret `coderev-secrets/api-secret-key` | 180 days | Platform |
| HuggingFace token | `CODEREV_HF_TOKEN` | GitHub Actions Secret | 180 days or on HF token expiry | ML |

## Rotation Procedure

### 1. Generate a new secret value

```bash
# For CODEREV_API_SECRET_KEY — 32 random bytes, hex-encoded
python -c "import secrets; print(secrets.token_hex(32))"
```

For `CODEREV_LLM_API_KEY`: generate a new key in the OpenAI dashboard before revoking the old one.

### 2. Update GitHub Actions Secret

```
GitHub repo → Settings → Secrets and variables → Actions → Update secret
```

### 3. Update Kubernetes Secret

```bash
kubectl create secret generic coderev-secrets \
    --from-literal=llm-api-key="$NEW_LLM_API_KEY" \
    --from-literal=api-secret-key="$NEW_API_SECRET_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -
```

### 4. Restart deployment to pick up new secret

```bash
kubectl rollout restart deployment/coderev-agents
kubectl rollout status deployment/coderev-agents --timeout=120s
```

### 5. Verify service is healthy

```bash
curl -H "X-API-Key: $NEW_API_SECRET_KEY" https://<host>/health
# Expected: {"status": "healthy", "version": "0.3.2"}
```

### 6. Revoke the old secret in the upstream system

- OpenAI: dashboard → API keys → Revoke old key
- HuggingFace: Settings → Access Tokens → Delete old token

## On Suspected Compromise

Treat any of the following as a compromise indicator:
- Unexpected charges in OpenAI billing dashboard
- `gitleaks` or `truffleHog` alert in CI
- `coderev_trust_findings_total` counter anomaly in Grafana

**Immediate action:** revoke the suspect key before generating a replacement.
Complete steps 1–6 within 30 minutes of detection.
