# Artifact scanner — NOT_RUN

`tools/scan-artifacts.mjs` is a post-run scan of browser artifacts and
the task maildir. The browser phase was never entered (backend
authentic RED stop rule), no artifacts directory and no maildir exist.
The scanner is therefore NOT_RUN by construction; there is nothing to
scan. No sanitized dynamic-scan result can be produced for a run that
never happened; reporting one would be fabrication.
