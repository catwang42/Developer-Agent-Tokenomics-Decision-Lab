#!/usr/bin/env bash
# Stack driver: NONE — subject code is READ, never executed.
#
# For review-class workloads (SPEC §5.1 W6): the agent is given a diff and reports
# the defects it finds; the gate is a deterministic matcher over a sealed
# seeded-defect map, not a test run. Nothing is installed, compiled or executed in
# the subject tree, so the SPEC §2.8 checks that exist to prove an EXECUTION
# environment (2 deps, 4 clean install, 5 baseline tests, 9 clean build) have no
# referent here. This driver declares them not_applicable WITH a reason rather than
# passing them vacuously or failing them spuriously — `unavailable != 0` in spirit
# (CLAUDE.md rule 3): a check that cannot apply is recorded as such, never faked.
#
# The remaining checks are real and are still enforced: 1 commit exists, 3 paths
# exist (every file named by the review diff is present at the pin), 8 no leakage
# (the participant-visible diff carries no answer markers), 10 deterministic reset.
# Checks 6 and 7 need the human-held defect map: they report awaiting_human only
# until its runner exists, then become real — 6 scores an EMPTY review through the
# sealed runner and expects a rejection, 7 fingerprints the sealed set (a review
# task has no canonical patch; the map is the canonical reference). See validate.sh.
#
# shellcheck shell=bash

# Checks with no referent for a read-only review task. Printed as
# "<check-id>\t<reason>"; validate.sh records them not_applicable.
stack_na_checks() {
  printf '%s\t%s\n' \
    deps-orm      "review task: subject code is never executed, so there is no runtime dependency set to install or verify" \
    clean-install "review task: nothing is installed; the participant artifact is a diff, not a runnable tree" \
    baseline-tests "review task: the gate is a defect-map matcher, not a test run; no baseline suite is executed" \
    clean-build   "review task: nothing is compiled; the pinned tree is only read to generate the review diff"
}

stack_install() { :; }
stack_post_patch() { :; }
stack_clean_keep() { :; }

stack_deps_ok() { return 0; }
stack_deps_detail() { echo "not applicable (review task)"; }
stack_installed_ok() { return 0; }
stack_install_detail() { echo "not applicable (review task)"; }
stack_config_paths() { :; }

stack_baseline_tests() { return 0; }
stack_baseline_detail() { echo "not applicable (review task)"; }
stack_run_selected() { return 0; }
stack_typecheck() { return 0; }
stack_typecheck_detail() { echo "not applicable (review task)"; }
stack_build() { return 0; }
stack_build_detail() { echo "not applicable (review task)"; }
stack_coverage_summary() { return 1; }

stack_selector() { :; }
