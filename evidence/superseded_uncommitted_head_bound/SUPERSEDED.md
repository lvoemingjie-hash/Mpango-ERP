# SUPERSEDED_UNCOMMITTED_HEAD_BOUND_EVIDENCE

The four runner artifacts in `i2-runner/` were produced during round
DC-12R1-MVP-L1-J1-H2-C-I2 **before** the candidate was committed. The
authority runner reads `candidate_sha` from the live `HEAD`; at that time
`HEAD = 24a28d76` (BASE), while the reviewed integration state was the
uncommitted staged tree `e38c6e28`. These proofs therefore bind to BASE, not
to the integration candidate.

**Classification: `SUPERSEDED_UNCOMMITTED_HEAD_BOUND_EVIDENCE`.** They are
retained verbatim for honesty only. They are NOT authority evidence for the
candidate and must not be cited as such.

The corrected, candidate-SHA-bound proofs for commit `86f41b93` live in
`evidence/runner/` (E1 round, fresh task-exclusive stack, HEAD verified ==
candidate immediately before and after both runner invocations).
