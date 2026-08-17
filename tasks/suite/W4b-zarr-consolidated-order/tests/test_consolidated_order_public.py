"""PUBLIC repro test for W4b — order-independence of consolidated-metadata nesting.

Provenance: this is the upstream PR's OWN new test, not a test we invented. It is
`test_flat_to_nested_is_order_independent` from
`tests/test_metadata/test_consolidated.py` as added by
zarr-developers/zarr-python#4227 (merge commit
24f9ad19430dc88bc1d92b5e1936ac6b3e20f4fe), copied verbatim including its three
parametrised key orders and its docstring.

Derivation from the upstream file (recorded so the delta is auditable):
  - the imports the test needs are made explicit here, because upstream they come
    from the surrounding module's import block;
  - `JSON` is imported at runtime rather than under `TYPE_CHECKING`, because this
    file has no `from __future__ import annotations`-guarded module scope to
    borrow it from;
  - nothing else is changed: same assertions, same parameters, same name.

The gate injects this file into the subject tree at run time and removes it again
(harness/task-tools/gate/check-public.sh). It fails on the pinned tree and passes
on the canonical fix — that is SPEC 2.8 check 6 / check 7.
"""

from __future__ import annotations

import pytest

from zarr.core.common import JSON
from zarr.core.group import ConsolidatedMetadata, GroupMetadata


@pytest.mark.parametrize(
    "order",
    [
        # keys grouped by parent, the order zarr-python used to write before it
        # started sorting the persisted keys
        ["a", "b", "a/x", "a/y", "b/x", "b/y"],
        # sibling subtrees interleaved, which is what the (depth, casefold) sort
        # produces for names differing only by case
        ["a", "b", "a/x", "b/x", "a/y", "b/y"],
        # reversed, to cover a parent appearing after its children in the mapping
        ["b/y", "b/x", "a/y", "a/x", "b", "a"],
    ],
)
def test_flat_to_nested_is_order_independent(order: list[str]) -> None:
    """The persisted key order is arbitrary, so nesting must not depend on it."""
    group_metadata: dict[str, JSON] = {"zarr_format": 3, "node_type": "group", "attributes": {}}
    consolidated = ConsolidatedMetadata.from_dict(
        {
            "kind": "inline",
            "must_understand": False,
            "metadata": dict.fromkeys(order, group_metadata),
        }
    )

    assert sorted(consolidated.metadata) == ["a", "b"]
    for name in ("a", "b"):
        child = consolidated.metadata[name]
        assert isinstance(child, GroupMetadata)
        assert child.consolidated_metadata is not None
        assert sorted(child.consolidated_metadata.metadata) == ["x", "y"]
