# V4 authoritative node list (frozen; collected == run == passed)

- J00 harness credential gate (env-only, fail closed)
- J01 browser login as W1
- J02 sidebar navigation to invitation authoring
- J03 create invitation via real form
- J04 copy/share UI yields canonical fragment link
- J05 shared invitation URL opens in new context
- J06 supplier identity in rendered UI
- J07 registration form email-required and no password input
- J08 submit + mail-sink setup token through real setup page
- J09 portal link then ClientLoginPage login
- J10 /retail/join supplier code tab
- J11 code-entry lifecycle: preview -> confirm -> register -> portal login
- J12 unknown and malformed code: neutral, zero register POSTs
- J13 preview link exact w; no bare /retail/login anywhere
- J14 stale contextual session: full code-path registration, zero Authorization
- J15 double submit: exactly one POST and one binding
- J16 W1 retailer denied on W2 portal (exact status + UI)
- J17 deactivate via UI; retailer login fails afterwards
- J18 390px viewport discovery/preview/navigation (viewport simulation)

Total: 19 nodes (workers=1, retries=0)
