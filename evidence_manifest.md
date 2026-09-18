# Evidence Manifest — Kilo Targeted Review R1-R5-R1

Generated: 2026-09-18
Branch: kilo/tenant-bootstrap-r1r5r1-targeted-review-20260918
Base: 47b9c8d46f53f2cbdfbac9e73c2a74cf29465cdf
Commit: f1dca3d5acc45f43c8988ec7a7046077c44150ba

## Submitted Materials

| File | Purpose |
|------|---------|
| `review.md` | Full review narrative and verdict with correction note |
| `findings.csv` | Structured findings table (6 columns, all rows) |
| `evidence/results.xml` | pytest JUnit XML (end-of-file normalized by git hook) |
| `evidence/results.xml.gz` | Gzipped original JUnit XML preserving original bytes |
| `evidence/verify_o1_fixed.py` | Independent O1 and negative example verification script |

## Blob Manifests (Git blob object ID → content SHA-256)

### review.md
```
Git blob: 136b164d9616e663547b8a67919eb8d402f3e672
SHA-256: 4026840E9C230C366C5B31D444BB1DF5D496AE46788E3C4CF47A9BA871C54036
```

### findings.csv
```
Git blob: c5757f80f1da6ee01af1625a138d9fd0332c01c9
SHA-256: 712413D59796EC6937D2BAC8D0795D738BD01025F923502F75DD565DB0F0BF1F
```

### evidence/results.xml
```
Git blob: 193f4504cb2e16c10d372533ff6448292ed5b3bb
SHA-256: 2CEC54ADDC407956392184B053C19D192064071FFC605531D0C51323D4CE42C1
Original bytes SHA-256: 757073807BB97A52E779C073AD0D9487637B7106041F28318C19FCDB333C79C4
Conversion note: git end-of-file-fixer added trailing newline during commit.
Original bytes preserved in evidence/results.xml.gz.
```

### evidence/results.xml.gz
```
Git blob: ae6211d1944a8b4d95505ba9ff586b05d26f327e
SHA-256: 85D9D53A31A31D1C282FF5F23CF5D012629D5BC3D26B6106A333D2BC1ECAE874
Decompresses to original bytes SHA-256: 757073807BB97A52E779C073AD0D9487637B7106041F28318C19FCDB333C79C4
```

### evidence/verify_o1_fixed.py
```
Git blob: 0d1697eac059ad74d94b558633c5e2380195da73
SHA-256: 2BE15CD1B2C1737D08000B4D11532D44E04487E8A5594405A75C132FD98C189F
Original bytes SHA-256: 2BE15CD1B2C1737D08000B4D11532D44E04487E8A5594405A75C132FD98C189F
```

## Artifact Integrity

| Artifact | Original SHA-256 | Published SHA-256 | Match |
|----------|-----------------|-------------------|-------|
| results.xml | 757073807BB97A52E779C073AD0D9487637B7106041F28318C19FCDB333C79C4 | 2CEC54ADDC407956392184B053C19D192064071FFC605531D0C51323D4CE42C1 | NO — end-of-file normalized; original preserved in .gz |
| verify_o1_fixed.py | 2BE15CD1B2C1737D08000B4D11532D44E04487E8A5594405A75C132FD98C189F | 2BE15CD1B2C1737D08000B4D11532D44E04487E8A5594405A75C132FD98C189F | YES |

## Retention Status

| Artifact | Status |
|----------|--------|
| Original pytest stdout | NOT_RETAINED |
| Original environment record | NOT_RETAINED |
| Original secret-scan log | NOT_RETAINED |
| Original git diff --check output | NOT_RETAINED |
