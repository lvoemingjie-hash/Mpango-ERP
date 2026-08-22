# Security Boundary

- No SECRET_KEY, DATABASE_URL, JWT, or passwords committed
- No Authorization headers in evidence
- No Playwright traces committed
- No email tokens committed (dev_sink only)
- debug/dev-emails endpoint removed from committed code
- Candidate source restored to byte-identical state
