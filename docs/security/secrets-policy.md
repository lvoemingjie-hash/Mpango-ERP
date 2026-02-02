# Secrets Management Policy

**Version:** 1.0  
**Effective Date:** 2026-02-01  
**Owner:** Security Team  
**Status:** MANDATORY  

---

## 1. Policy Statement

**NO SECRETS SHALL BE COMMITTED TO VERSION CONTROL UNDER ANY CIRCUMSTANCES.**

This policy applies to all Mpango ERP repositories, branches, and commits. Violation of this policy is considered a **CRITICAL security incident** requiring immediate remediation.

---

## 2. Scope

### 2.1 What Constitutes a "Secret"

Secrets include, but are not limited to:

#### Credentials
- Database passwords and connection strings
- API keys and tokens
- Service account credentials
- OAuth client secrets
- SSH private keys
- TLS/SSL certificates and private keys

#### Application Secrets
- JWT signing keys (`SECRET_KEY`)
- Encryption keys
- Session secrets
- HMAC secrets

#### Third-Party Service Credentials
- AWS access keys and secret keys
- Google Cloud service account keys
- Azure connection strings
- Stripe API keys
- SendGrid API keys
- Any third-party API credentials

#### Infrastructure Secrets
- Docker registry credentials
- Kubernetes secrets
- Terraform state encryption keys
- Ansible vault passwords

### 2.2 Files That Must NEVER Be Committed

- `prod.env`, `production.env`, `*.prod.env`
- `secrets/` directory and all contents
- `.env` files (except `.env.example`)
- `credentials.json`, `service-account*.json`
- `*.pem`, `*.key` (private keys)
- `id_rsa`, `id_ed25519` (SSH keys)
- Database dumps containing production data
- Any file containing plaintext passwords or API keys

---

## 3. Approved Secrets Management Methods

### 3.1 Local Development

**Use `.env` files with `.gitignore`:**

```bash
# Create .env from template
cp .env.example .env

# Edit with your local credentials
nano .env

# Verify it's ignored
git status  # Should NOT show .env
```

**File permissions:**
```bash
chmod 600 .env
chmod 600 prod.env
```

### 3.2 Production Deployment

**Option 1: Environment Variables (Recommended)**

Set environment variables directly on the server:

```bash
# In systemd service file
Environment="DATABASE_URL=postgresql://..."
Environment="SECRET_KEY=..."

# Or in docker-compose.yml
environment:
  - DATABASE_URL=${DATABASE_URL}
  - SECRET_KEY=${SECRET_KEY}
```

**Option 2: Secrets Management Service**

Use a dedicated secrets manager:

- **AWS Secrets Manager** - For AWS deployments
- **HashiCorp Vault** - For on-premise or multi-cloud
- **Azure Key Vault** - For Azure deployments
- **Google Secret Manager** - For GCP deployments

**Option 3: Encrypted Secrets (Advanced)**

Use tools like:
- `git-crypt` - Transparent encryption in git
- `sops` - Encrypted secrets with key management
- `ansible-vault` - For Ansible deployments

### 3.3 CI/CD Pipelines

**Use GitHub Secrets / GitLab CI Variables:**

```yaml
# GitHub Actions
env:
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
  SECRET_KEY: ${{ secrets.SECRET_KEY }}
```

**Never:**
- Hardcode secrets in workflow files
- Echo secrets in logs
- Store secrets in artifacts

---

## 4. Secret Generation Guidelines

### 4.1 Password Requirements

- **Minimum length:** 32 characters
- **Character set:** Alphanumeric + symbols
- **Randomness:** Use cryptographically secure random generator

```bash
# Generate secure password
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Or using openssl
openssl rand -base64 32
```

### 4.2 Secret Key Requirements

- **Minimum length:** 64 characters
- **Uniqueness:** Different key for each environment
- **Rotation:** Rotate every 90 days or after exposure

```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### 4.3 API Key Management

- Use separate keys for development, staging, and production
- Implement key rotation procedures
- Monitor key usage and set up alerts
- Revoke keys immediately upon suspected compromise

---

## 5. Incident Response

### 5.1 If Secrets Are Committed to Git

**IMMEDIATE ACTIONS (Within 1 Hour):**

1. **Rotate ALL exposed credentials immediately**
2. **Remove secrets from git history** (see Section 6)
3. **Force push cleaned history**
4. **Notify security team**
5. **Review access logs for unauthorized access**

### 5.2 Severity Classification

| Exposure Type | Severity | Response Time |
|---------------|----------|---------------|
| Production database password | CRITICAL | < 1 hour |
| SECRET_KEY / JWT signing key | CRITICAL | < 1 hour |
| API keys with write access | HIGH | < 4 hours |
| API keys with read-only access | MEDIUM | < 24 hours |
| Development credentials | LOW | < 1 week |

### 5.3 Notification Requirements

**CRITICAL incidents require notification to:**
- Security team
- DevOps team
- Engineering manager
- CTO (for production exposures)

---

## 6. Git History Cleaning Procedures

### 6.1 Using git-filter-repo (Recommended)

```bash
# Install
pip install git-filter-repo

# Backup repository
git clone . ../repo-backup

# Remove secrets from history
git filter-repo --path prod.env --invert-paths --force
git filter-repo --path secrets/ --invert-paths --force

# Force push
git push origin --force --all
git push origin --force --tags
```

### 6.2 Team Coordination

**Before force pushing:**

1. Notify all team members
2. Ensure all work is pushed
3. Schedule during low-activity period
4. Provide re-clone instructions

**After force push:**

```bash
# Team members must re-clone
git clone <repo-url> mpango-erp-clean
```

---

## 7. Prevention Mechanisms

### 7.1 Pre-Commit Hooks (MANDATORY)

Install pre-commit hooks on all development machines:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Test
pre-commit run --all-files
```

### 7.2 CI/CD Checks (MANDATORY)

All repositories must have:
- GitHub Actions secret detection workflow
- Automated security scanning on every PR
- Blocking checks that prevent merging if secrets detected

### 7.3 Code Review Requirements

**Reviewers must verify:**
- No `.env` files (except `.env.example`)
- No hardcoded credentials
- No API keys in code
- No database connection strings
- Proper use of environment variables

---

## 8. Training and Awareness

### 8.1 Onboarding Requirements

All new developers must:
- Read and acknowledge this policy
- Complete secrets management training
- Install pre-commit hooks
- Demonstrate proper `.env` file usage

### 8.2 Ongoing Training

- Quarterly security awareness training
- Incident case studies and lessons learned
- Updates on new threats and best practices

---

## 9. Compliance and Auditing

### 9.1 Regular Audits

**Monthly:**
- Review git history for accidental commits
- Verify pre-commit hooks are installed
- Check CI/CD security scans

**Quarterly:**
- Rotate production secrets
- Review access logs
- Update secrets management procedures

### 9.2 Audit Trail

Maintain records of:
- Secret rotation dates
- Incident response actions
- Policy violations and remediation
- Training completion

---

## 10. Exceptions and Waivers

### 10.1 No Exceptions

There are **NO EXCEPTIONS** to the "no secrets in git" rule.

### 10.2 Test Data

Test credentials may be committed ONLY if:
- Clearly marked as test/dummy data
- Not valid for any real system
- Documented in code comments

Example:
```python
# TEST CREDENTIALS - NOT REAL
TEST_DB_PASSWORD = "test_password_123"  # Only for local testing
```

---

## 11. Tools and Resources

### 11.1 Recommended Tools

- **detect-secrets** - Pre-commit secret scanning
- **gitleaks** - Git history secret detection
- **trufflehog** - Deep secret scanning
- **git-filter-repo** - History rewriting
- **sops** - Encrypted secrets management

### 11.2 Useful Commands

```bash
# Check for secrets in current commit
git diff --cached | grep -i "password\|secret\|key"

# Scan entire repository
gitleaks detect --source . --verbose

# Generate secure random string
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Check file permissions
ls -la .env prod.env
```

---

## 12. Policy Violations

### 12.1 Consequences

Violations of this policy may result in:
- Immediate incident response procedures
- Mandatory retraining
- Performance review documentation
- Disciplinary action (for repeated violations)

### 12.2 Reporting Violations

If you discover secrets in git:
1. **DO NOT** pull or clone the repository
2. Immediately notify security team
3. Follow incident response procedures
4. Document the discovery

---

## 13. Policy Updates

This policy will be reviewed and updated:
- Annually (minimum)
- After any security incident
- When new tools or practices emerge
- Upon regulatory requirement changes

**Last Updated:** 2026-02-01  
**Next Review:** 2027-02-01  

---

## 14. Acknowledgment

By contributing to Mpango ERP repositories, you acknowledge that you have read, understood, and agree to comply with this Secrets Management Policy.

**Signature:** _________________________  
**Date:** _________________________  
**Name:** _________________________  

---

## Appendix A: Quick Reference

### ✅ DO

- Use `.env` files (gitignored)
- Use environment variables
- Use secrets management services
- Rotate secrets regularly
- Use strong, random secrets
- Install pre-commit hooks
- Review code for secrets

### ❌ DON'T

- Commit `.env` files
- Hardcode passwords
- Share secrets via email/chat
- Reuse secrets across environments
- Use weak or predictable secrets
- Disable security checks
- Ignore security warnings

---

## Appendix B: Emergency Contacts

**Security Team:**
- Email: security@mpango-erp.com
- Slack: #security-incidents
- On-call: +1-XXX-XXX-XXXX

**Incident Response:**
- Email: incidents@mpango-erp.com
- Escalation: CTO, VP Engineering

---

**Document Control:**
- **Version:** 1.0
- **Approved by:** Security Team
- **Effective Date:** 2026-02-01
- **Classification:** Internal Use Only
