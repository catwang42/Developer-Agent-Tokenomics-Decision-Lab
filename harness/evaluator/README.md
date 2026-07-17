# Independent Evaluation Gate (SPEC 2.6; built in Phases 2-3)
Priority: hidden deterministic tests -> type/lint -> regression -> security (where
relevant) -> timed human-review rubric. Model-based review supplementary and separately
measured; the generating model is never the sole verifier. Sealed hidden tests: hash
recorded per result; rotated per cycle; stored in tasks/hidden/ (gitignored, human-held).
