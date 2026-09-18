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
SHA-256: f2ad4586d00f1e6fc47eb97a3220bdcc6cb758ad689b3036782bb16d95cdbc5c
```

### findings.csv
```
Git blob: c5757f80f1da6ee01af1625a138d9fd0332c01c9
SHA-256: 884bfcae1cf0af7cbcd52c5a6a4c2e780114520a4d8ce9a793b6f0779d522ae0
```

### evidence/results.xml
```
Git blob: 193f4504cb2e16c10d372533ff6448292ed5b3bb
SHA-256: 9a9cd1c78d901815126b4553a7e588761d6651b28d8291f06ddebcf0ae3feb8d
Original bytes SHA-256: 757073807BB97A52E779C073AD0D9487637B7106041F28318C19FCDB333C79C4
Conversion note: git end-of-file-fixer added trailing newline during commit.
Original bytes preserved in evidence/results.xml.gz.
```

### evidence/results.xml.gz
```
Git blob: ae6211d1944a8b4d95505ba9ff586b05d26f327e
SHA-256: 97d2ab296d24e2d714137d685b9b673ff3ce6669e8d0fd53eb327a02d804e997
Decompresses to original bytes SHA-256: 757073807BB97A52E779C073AD0D9487637B7106041F28318C19FCDB333C79C4
```

### evidence/verify_o1_fixed.py
```
Git blob: 0d1697eac059ad74d94b558633c5e2380195da73
SHA-256: 2be15cd1b2c1737d08000b4d11532d44e04487e8a5594405a75c132fd98c189f
Original bytes SHA-256: 2be15cd1b2c1737d08000b4d11532d44e04487e8a5594405a75c132fd98c189f
```

## Artifact Integrity

| Artifact | Original SHA-256 | Published SHA-256 | Match |
|----------|-----------------|-------------------|-------|
| results.xml | 757073807BB97A52E779C073AD0D9487637B7106041F28318C19FCDB333C79C4 | 9a9cd1c78d901815126b4553a7e588761d6651b28d8291f06ddebcf0ae3feb8d | NO — end-of-file normalized; original preserved in .gz |
| verify_o1_fixed.py | 2BE15CD1B2C1737D08000B4D11532D44E04487E8A5594405A75C132FD98C189F | 2be15cd1b2c1737d08000b4d11532d44e04487e8a5594405a75c132fd98c189f | YES |

## Correction Note (2026-09-18)

The SHA-256 values for review.md, findings.csv, evidence/results.xml, and evidence/results.xml.gz in the previous version of this manifest were computed from CRLF-converted bytes (Windows line-ending view), not from the committed Git blob bytes. Those values are replaced here with the correct Git blob content SHA-256 values. The gzip outer blob SHA-256 is also corrected; the decompressed original XML bytes remain unchanged and match the previously verified SHA-256 757073807bb97a52e779c073ad0d9487637b7106041f28318c19fcdb333c79c4.

## Retention Status

| Artifact | Status |
|----------|--------|
| Original pytest stdout | NOT_RETAINED |
| Original environment record | NOT_RETAINED |
| Original secret-scan log | NOT_RETAINED |
| Original git diff --check output | NOT_RETAINED |
