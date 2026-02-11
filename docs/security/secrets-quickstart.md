# Secrets Management Quick Start Guide

**For Developers:** 5-minute setup to prevent committing secrets

---

## Step 1: Install Pre-Commit Hooks (2 minutes)

```bash
# Install pre-commit
pip install pre-commit

# Navigate to project root
cd "C:\Users\Jeff0\MPANGO ERP\windsurf mpango erp"

# Install hooks
pre-commit install

# Test (should pass)
pre-commit run --all-files
```

**What this does:** Automatically scans for secrets before every commit.

---

## Step 2: Set Up Your .env File (1 minute)

```bash
# Copy example file
cp .env.example .env

# Edit with your credentials
notepad .env

# Verify it's ignored
git status  # Should NOT show .env
```

**Important:** NEVER commit `.env` files!

---

## Step 3: Verify .gitignore (30 seconds)

Check that `.gitignore` includes:

```gitignore
# Secrets
.env
.env.*
!.env.example
prod.env
secrets/
*.key
*.pem
```

---

## Step 4: Test the Protection (30 seconds)

```bash
# Try to commit a secret (should fail)
echo "SECRET_KEY=test123" > test-secret.env
git add test-secret.env
git commit -m "test"

# Should see: "ERROR: .env files are not allowed"

# Clean up
rm test-secret.env
```

---

## Common Mistakes to Avoid

### ❌ DON'T DO THIS:

```python
# Hardcoded password
DATABASE_URL = "postgresql://user:password123@localhost/db"

# Hardcoded API key
API_KEY = "YOUR_API_KEY_HERE"
```

### ✅ DO THIS INSTEAD:

```python
import os

# Use environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")
```

---

## Need Help?

- **Read full policy:** `docs/security/secrets-policy.md`
- **Security team:** security@mpango-erp.com
- **Slack:** #security-help

---

## Emergency: I Committed a Secret!

1. **STOP** - Don't push if you haven't already
2. **Notify security team immediately**
3. **Follow:** `docs/security/secrets-policy.md` Section 5 (Incident Response)
4. **Rotate the exposed credential**

**If already pushed:**
- Contact security team IMMEDIATELY
- Do NOT try to fix it yourself
- Follow incident response procedures
