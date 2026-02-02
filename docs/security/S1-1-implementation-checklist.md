# Track S1-1: Secrets Governance Implementation Checklist

**Date:** 2026-02-01  
**Status:** IN PROGRESS  
**Owner:** OPS AI / Security Team  

---

## Phase 1: Immediate Actions (CRITICAL - Complete Within 1 Hour)

### 1.1 Credential Rotation

- [ ] **Rotate POSTGRES_PASSWORD**
  - [ ] Generate new password: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
  - [ ] Update PostgreSQL: `ALTER USER mpango WITH PASSWORD 'NEW_PASSWORD';`
  - [ ] Update `prod.env` (outside git)
  - [ ] Update `DATABASE_URL` in `prod.env`
  - [ ] Restart backend: `docker compose restart backend`
  - [ ] Verify connection: Test health endpoint

- [ ] **Rotate SECRET_KEY**
  - [ ] Generate new key: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
  - [ ] Update `prod.env` (outside git)
  - [ ] Restart backend: `docker compose restart backend`
  - [ ] **Notify all users:** All sessions invalidated, must re-login
  - [ ] Verify: Test login endpoint

- [ ] **Review and Update CORS_ORIGINS**
  - [ ] Verify production domains are correct
  - [ ] Remove any test/development domains

### 1.2 Git History Cleaning (Coordinate with Team)

- [ ] **Backup repository**
  ```bash
  git clone . ../mpango-erp-backup
  ```

- [ ] **Install git-filter-repo**
  ```bash
  pip install git-filter-repo
  ```

- [ ] **Dry run analysis**
  ```bash
  git filter-repo --analyze --force
  cat .git/filter-repo/analysis/path-all-sizes.txt | findstr /i "prod.env secrets"
  ```

- [ ] **Review affected commits**
  ```bash
  git log --all --full-history --oneline -- prod.env secrets/
  ```

- [ ] **Notify team members**
  - [ ] Send notification about upcoming force push
  - [ ] Ensure all work is pushed
  - [ ] Schedule during low-activity period

- [ ] **Execute history rewrite**
  ```bash
  git filter-repo --path prod.env --path secrets/ --invert-paths --force
  ```

- [ ] **Verify cleanup**
  ```bash
  git log --all --full-history -- prod.env secrets/
  ```

- [ ] **Force push**
  ```bash
  git remote add origin <your-remote-url>
  git push origin --force --all
  git push origin --force --tags
  ```

- [ ] **Cleanup reflog**
  ```bash
  git reflog expire --expire=now --all
  git gc --prune=now --aggressive
  ```

- [ ] **Notify team to re-clone**
  - [ ] Send re-clone instructions
  - [ ] Verify all team members have re-cloned

---

## Phase 2: Prevention Mechanisms (Complete Within 24 Hours)

### 2.1 Pre-Commit Hooks

- [ ] **Install pre-commit**
  ```bash
  pip install pre-commit
  ```

- [ ] **Verify `.pre-commit-config.yaml` exists**
  - [ ] File created in project root
  - [ ] Contains detect-secrets hook
  - [ ] Contains gitleaks hook
  - [ ] Contains custom blocking hooks

- [ ] **Initialize detect-secrets baseline**
  ```bash
  pip install detect-secrets
  detect-secrets scan > .secrets.baseline
  ```

- [ ] **Install hooks**
  ```bash
  pre-commit install
  ```

- [ ] **Test hooks**
  ```bash
  pre-commit run --all-files
  ```

- [ ] **Commit hook configuration**
  ```bash
  git add .pre-commit-config.yaml .secrets.baseline
  git commit -m "feat(security): Add pre-commit hooks for secret detection"
  git push
  ```

### 2.2 Update .gitignore

- [ ] **Verify `.gitignore` updated**
  - [ ] Contains comprehensive secrets patterns
  - [ ] Includes `prod.env`, `*.prod.env`
  - [ ] Includes `secrets/` directory
  - [ ] Includes private keys (`*.pem`, `*.key`)
  - [ ] Includes credential files

- [ ] **Test .gitignore**
  ```bash
  echo "test" > prod.env
  git status  # Should NOT show prod.env
  rm prod.env
  ```

- [ ] **Commit .gitignore updates**
  ```bash
  git add .gitignore
  git commit -m "feat(security): Update .gitignore with comprehensive secrets patterns"
  git push
  ```

### 2.3 GitHub Actions

- [ ] **Verify security-scan.yml created**
  - [ ] File exists at `.github/workflows/security-scan.yml`
  - [ ] Contains prod.env detection
  - [ ] Contains secrets/ directory detection
  - [ ] Contains Gitleaks scan
  - [ ] Contains TruffleHog scan
  - [ ] Contains hardcoded credentials check

- [ ] **Create .github/workflows directory if needed**
  ```bash
  mkdir -p .github/workflows
  ```

- [ ] **Commit workflow**
  ```bash
  git add .github/workflows/security-scan.yml
  git commit -m "feat(security): Add GitHub Actions security scanning workflow"
  git push
  ```

- [ ] **Verify workflow runs**
  - [ ] Check GitHub Actions tab
  - [ ] Verify security scan completes successfully
  - [ ] Review any findings

---

## Phase 3: Documentation (Complete Within 48 Hours)

### 3.1 Security Policy

- [ ] **Verify `docs/security/secrets-policy.md` created**
  - [ ] Comprehensive policy document
  - [ ] Clear definitions of secrets
  - [ ] Approved management methods
  - [ ] Incident response procedures
  - [ ] Prevention mechanisms

- [ ] **Review policy with team**
  - [ ] Schedule team meeting
  - [ ] Present policy
  - [ ] Answer questions
  - [ ] Get acknowledgments

- [ ] **Commit documentation**
  ```bash
  git add docs/security/
  git commit -m "docs(security): Add comprehensive secrets management policy"
  git push
  ```

### 3.2 Quick Start Guide

- [ ] **Verify `docs/security/secrets-quickstart.md` created**
  - [ ] Simple 5-minute setup guide
  - [ ] Clear do's and don'ts
  - [ ] Emergency procedures

- [ ] **Add to README.md**
  - [ ] Link to secrets policy
  - [ ] Link to quick start guide
  - [ ] Security badge/notice

### 3.3 Update Project Documentation

- [ ] **Update README.md**
  - [ ] Add security section
  - [ ] Link to secrets policy
  - [ ] Add setup instructions

- [ ] **Update CONTRIBUTING.md**
  - [ ] Add pre-commit hook requirements
  - [ ] Add secrets policy reference
  - [ ] Add code review checklist

---

## Phase 4: Team Training (Complete Within 1 Week)

### 4.1 Developer Onboarding

- [ ] **Create onboarding checklist**
  - [ ] Read secrets policy
  - [ ] Install pre-commit hooks
  - [ ] Set up .env file correctly
  - [ ] Complete security quiz

- [ ] **Schedule training sessions**
  - [ ] Backend team
  - [ ] Frontend team
  - [ ] DevOps team

### 4.2 Training Materials

- [ ] **Create presentation**
  - [ ] Why secrets in git are dangerous
  - [ ] How to use .env files
  - [ ] How pre-commit hooks work
  - [ ] What to do if you commit a secret

- [ ] **Record training video**
  - [ ] Upload to team knowledge base
  - [ ] Add to onboarding materials

### 4.3 Acknowledgments

- [ ] **Collect acknowledgments**
  - [ ] All team members sign policy
  - [ ] Store in HR/compliance system
  - [ ] Track completion

---

## Phase 5: Monitoring and Compliance (Ongoing)

### 5.1 Regular Audits

- [ ] **Monthly checks**
  - [ ] Review git history for new secrets
  - [ ] Verify pre-commit hooks installed on all machines
  - [ ] Check CI/CD security scan results
  - [ ] Review access logs

- [ ] **Quarterly reviews**
  - [ ] Rotate production secrets
  - [ ] Update secrets policy
  - [ ] Review incident reports
  - [ ] Update training materials

### 5.2 Incident Response

- [ ] **Create incident response runbook**
  - [ ] Detection procedures
  - [ ] Escalation paths
  - [ ] Rotation procedures
  - [ ] Communication templates

- [ ] **Test incident response**
  - [ ] Conduct tabletop exercise
  - [ ] Document lessons learned
  - [ ] Update procedures

### 5.3 Metrics and Reporting

- [ ] **Track metrics**
  - [ ] Number of secrets detected (pre-commit)
  - [ ] Number of secrets detected (CI/CD)
  - [ ] Incident response times
  - [ ] Training completion rates

- [ ] **Monthly security report**
  - [ ] Secrets detection statistics
  - [ ] Incidents and resolutions
  - [ ] Compliance status
  - [ ] Recommendations

---

## Phase 6: Advanced Security (Future Enhancements)

### 6.1 Secrets Management Service

- [ ] **Evaluate options**
  - [ ] AWS Secrets Manager
  - [ ] HashiCorp Vault
  - [ ] Azure Key Vault
  - [ ] Google Secret Manager

- [ ] **Implement chosen solution**
  - [ ] Set up infrastructure
  - [ ] Migrate secrets
  - [ ] Update application code
  - [ ] Document procedures

### 6.2 Automated Rotation

- [ ] **Implement automatic rotation**
  - [ ] Database passwords (90 days)
  - [ ] API keys (90 days)
  - [ ] JWT signing keys (90 days)

- [ ] **Set up monitoring**
  - [ ] Rotation success/failure alerts
  - [ ] Expiration warnings
  - [ ] Usage anomaly detection

### 6.3 Zero-Trust Architecture

- [ ] **Implement least privilege**
  - [ ] Service accounts with minimal permissions
  - [ ] Time-limited credentials
  - [ ] Just-in-time access

- [ ] **Implement audit logging**
  - [ ] All secret access logged
  - [ ] Anomaly detection
  - [ ] Compliance reporting

---

## Verification Steps

### After Phase 1 (Immediate)

```bash
# Verify secrets removed from git
git log --all --full-history -- prod.env secrets/
# Should return nothing

# Verify new credentials work
curl http://localhost:8000/health
# Should return 200 OK

# Verify database connection
docker compose exec backend poetry run python -c "from database.session import async_engine; import asyncio; asyncio.run(async_engine.connect())"
# Should succeed
```

### After Phase 2 (Prevention)

```bash
# Test pre-commit hooks
echo "SECRET_KEY=test" > test.env
git add test.env
git commit -m "test"
# Should FAIL with secret detection error

# Test .gitignore
echo "test" > prod.env
git status
# Should NOT show prod.env

# Verify GitHub Actions
# Check Actions tab - security-scan workflow should pass
```

### After Phase 3 (Documentation)

```bash
# Verify documentation exists
ls docs/security/secrets-policy.md
ls docs/security/secrets-quickstart.md

# Verify links in README
cat README.md | grep -i security
```

---

## Sign-Off

### Phase 1: Immediate Actions
- [ ] Completed by: ________________
- [ ] Date: ________________
- [ ] Verified by: ________________

### Phase 2: Prevention Mechanisms
- [ ] Completed by: ________________
- [ ] Date: ________________
- [ ] Verified by: ________________

### Phase 3: Documentation
- [ ] Completed by: ________________
- [ ] Date: ________________
- [ ] Verified by: ________________

### Phase 4: Team Training
- [ ] Completed by: ________________
- [ ] Date: ________________
- [ ] Verified by: ________________

---

**Track S1-1 Status:** ☐ Not Started | ☐ In Progress | ☐ Complete  
**Overall Completion:** 0%  
**Target Completion Date:** 2026-02-08  
**Actual Completion Date:** ________________
