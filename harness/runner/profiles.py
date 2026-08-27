"""Driver profiles: how a batch treats time.

A profile answers two questions the rest of the runner then obeys without
deciding anything:

  1. **How long may a leg run before we stop it?** — the workshop-owned kill
     (SPEC 1.3). One number, applied at ``harness/container/exec.spawn_with_timeout``.
  2. **When does a leg become "over budget" without being stopped?** — the soft
     budget. Crossing it stamps ``overrun_flag``/``overrun_s`` and the run
     continues.

Splitting the two is the whole point. Until now they were one number: a leg that
hit ``agent_timeout_s`` was killed, and what it would have produced was
unknowable. That is fine when the question is "how much does this cost inside a
fixed budget"; it is fatal when the question is "how much does a failure cost",
because a right-censored attempt reports the budget rather than the bill. The
transfer probe asks the second question, so it needs attempts that run to
completion and a *recorded* overrun rather than a truncated one.

A profile is a RUN CONDITION, not a tuning knob. Changing which profile a
dataset ran under changes what its numbers mean, so it is recorded in three
places, none of which requires a new event type (the vocabulary is frozen,
CP-SCHEMA): the profile NAME and the resolved ``timeout_s``/``budget_s`` go into
each leg's ``invocation.txt`` entry, the per-attempt ``budget_s``/``elapsed_s``/
``overrun_flag``/``overrun_s`` are stamped on the leg's existing
``model_call_completed`` event, and the dataset as a whole carries a marker file
(:func:`dataset_marker`) saying which profile produced it.

**Batch-1 pins are untouched.** ``batch1`` is the default and resolves to
exactly the behaviour that shipped: kill at ``agent_timeout_s``, no soft budget,
``--print-timeout`` straight from the manifest. Nothing here changes a number
any existing dataset ran under.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

# --------------------------------------------------------------------------- #
# Go durations (Product B's --print-timeout takes one)
# --------------------------------------------------------------------------- #
def go_duration(seconds: int) -> str:
    """Format whole ``seconds`` as a Go duration, e.g. ``1200 -> '20m0s'``.

    Round-trips through ``harness.adapters.agy.print_timeout_seconds``; the pair
    is pinned together by tests/test_transfer_profile.py. Deliberately narrow —
    integers only, no fractional seconds — because the only producer is a task's
    ``agent_timeout_s``, which the task loader already requires to be a positive
    integer.
    """
    if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
        raise ValueError(f"go_duration needs a positive integer seconds, got {seconds!r}")
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes}m{secs}s"
    return f"{minutes}m{secs}s"


# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LegTimeouts:
    """The resolved time contract for one leg of one task.

    ``kill_s`` is OUR subprocess kill; ``budget_s`` is the soft budget whose
    crossing is recorded rather than enforced (``None`` = no soft budget, so
    ``kill_s`` is the only line and crossing it is a kill, as in batch 1).
    ``print_timeout`` is the product's OWN timeout, passed verbatim to Product B;
    it must stay strictly below ``kill_s`` so the product stops itself first and
    leaves a diagnosable product error instead of an opaque kill.
    """

    budget_s: Optional[int]
    kill_s: int
    print_timeout: Optional[str]

    def __post_init__(self) -> None:
        if self.kill_s <= 0:
            raise ValueError(f"kill_s must be positive, got {self.kill_s}")
        if self.budget_s is not None and self.budget_s > self.kill_s:
            raise ValueError(
                f"soft budget {self.budget_s}s is above the hard kill {self.kill_s}s; "
                f"a budget that can never be crossed without a kill is not a budget"
            )


@dataclass(frozen=True)
class DriverProfile:
    """A named time contract a whole dataset ran under."""

    name: str
    #: Hard kill as a multiple of the task's ``agent_timeout_s``. ``1.0`` means
    #: the budget IS the kill (batch-1 behaviour).
    hard_kill_multiple: float
    #: True => ``agent_timeout_s`` becomes a soft budget: crossing it is stamped
    #: and the leg continues to ``hard_kill_multiple x agent_timeout_s``.
    warn_dont_kill: bool
    #: True => re-pin the product's own ``--print-timeout`` to the task's
    #: ``agent_timeout_s`` instead of using the manifest's flat pin.
    repin_print_timeout: bool
    #: One line, stamped into the dataset marker and every started event.
    summary: str
    #: Why this profile exists and what it costs the reader. Long-form, for the
    #: marker file — a dataset whose timing rules differ from batch 1's must say
    #: so where someone comparing them will trip over it.
    rationale: str

    def timeouts(self, agent_timeout_s: int,
                 manifest_print_timeout: Optional[str] = None) -> LegTimeouts:
        """Resolve this profile against one task's pinned ``agent_timeout_s``."""
        if not isinstance(agent_timeout_s, int) or agent_timeout_s <= 0:
            raise ValueError(
                f"agent_timeout_s must be a positive integer, got {agent_timeout_s!r}")
        kill_s = int(round(agent_timeout_s * self.hard_kill_multiple))
        budget_s = agent_timeout_s if self.warn_dont_kill else None
        if self.repin_print_timeout:
            print_timeout: Optional[str] = go_duration(agent_timeout_s)
        else:
            print_timeout = manifest_print_timeout
        return LegTimeouts(budget_s=budget_s, kill_s=kill_s, print_timeout=print_timeout)


BATCH1 = DriverProfile(
    name="batch1",
    hard_kill_multiple=1.0,
    warn_dont_kill=False,
    repin_print_timeout=False,
    summary="kill at agent_timeout_s; no soft budget; --print-timeout from the manifest",
    rationale=(
        "The shipped batch-1/batch-2 contract, reproduced exactly. The task's "
        "agent_timeout_s is the kill: an attempt that reaches it is terminated and "
        "its usage is recorded unavailable. Product B's --print-timeout stays at "
        "the manifest's flat 15m0s pin, which is BELOW the longer task budgets — a "
        "recorded limitation (manifest notes.print_timeout_basis), not an accident. "
        "Any dataset already published ran under this profile and must keep running "
        "under it; re-timing a comparison arm silently is how two batches stop "
        "being comparable."
    ),
)

TRANSFER_PROBE = DriverProfile(
    name="transfer-probe",
    hard_kill_multiple=3.0,
    warn_dont_kill=True,
    repin_print_timeout=True,
    summary=(
        "agent_timeout_s is a SOFT budget (stamped, not enforced); hard kill at 3x; "
        "--print-timeout re-pinned per task to agent_timeout_s"
    ),
    rationale=(
        "The transfer probe measures the cost of failure, so an attempt that is cut "
        "off reports the budget instead of the bill. Under this profile the task's "
        "agent_timeout_s becomes a soft line: crossing it stamps overrun_flag and "
        "overrun_s on the leg's model_call_completed event, emits a warning, and the "
        "attempt continues. The hard kill moves to 3x, which is a backstop against a "
        "hung process rather than a budget.\n"
        "\n"
        "Product B's --print-timeout is re-pinned per task to that same "
        "agent_timeout_s, which restores TIMEOUT PARITY: under the manifest's flat "
        "15m0s pin a 2700s task budget gave Product B 900s and then a product error, "
        "so the two products were not being given the same amount of time to fail in. "
        "print < kill still holds by construction (T < 3T), so the product's own "
        "timeout still fires before ours.\n"
        "\n"
        "This is a NEW ARM CONDITION. Runs under this profile are not comparable "
        "with batch-1 or batch-2 timing on duration, on truncation rate, or on any "
        "cost figure that a truncation would have bounded. Do not pool them."
    ),
)

PROFILES: Dict[str, DriverProfile] = {p.name: p for p in (BATCH1, TRANSFER_PROBE)}
DEFAULT_PROFILE = BATCH1.name


def get_profile(name: Optional[str]) -> DriverProfile:
    """Look up a profile by name; ``None`` gives the batch-1 default."""
    key = name or DEFAULT_PROFILE
    try:
        return PROFILES[key]
    except KeyError:
        raise ValueError(
            f"unknown driver profile {key!r}; known: {', '.join(sorted(PROFILES))}"
        ) from None


def dataset_marker(profile: DriverProfile, *, dataset: str,
                   tasks: Optional[Dict[str, int]] = None) -> str:
    """The NEW-ARM marker text a driver writes beside a dataset it creates.

    ``tasks`` maps task_id -> agent_timeout_s so the marker states the resolved
    numbers rather than the rule, and a reader does not have to recompute them.
    Returns text; writing it is the driver's job, and only at launch.
    """
    lines = [
        f"# Dataset timing profile: {profile.name}",
        "",
        f"Dataset: `{dataset}`",
        f"Profile: **{profile.name}** — {profile.summary}",
        "",
    ]
    if profile.name != DEFAULT_PROFILE:
        lines += [
            "> **NEW ARM CONDITION.** This dataset did not run under the batch-1 "
            "timing contract.",
            "",
        ]
    lines += [profile.rationale, ""]
    if tasks:
        lines += [
            "## Resolved per task",
            "",
            "| task | agent_timeout_s | soft budget | hard kill | --print-timeout |",
            "|---|---|---|---|---|",
        ]
        for task_id in sorted(tasks):
            t = profile.timeouts(tasks[task_id])
            budget = f"{t.budget_s}s" if t.budget_s is not None else "none (kill is the line)"
            lines.append(
                f"| {task_id} | {tasks[task_id]} | {budget} | {t.kill_s}s | "
                f"{t.print_timeout or 'manifest pin'} |"
            )
        lines.append("")
    return "\n".join(lines)
