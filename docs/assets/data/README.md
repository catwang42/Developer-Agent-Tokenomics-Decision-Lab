# docs/assets/data/ — local decision tables only, never committed

`docs/screening-report.md` renders whatever `decision-table.json` it finds here. Nothing
in this directory except this README is tracked by git (see `.gitignore`).

That is deliberate. A decision table produced from real runs carries screening figures,
and those are gated:

- **CP-FINDINGS** gates any real number appearing in docs, on the site, or in a report.
- **CP-PUBLISH** gates a Pages deploy that contains results content.

Copying a table here lets you review the rendering on a workstation without a single
figure entering the repository or a published build:

```bash
.venv/bin/python -m harness.telemetry.summarize results/<batch-dir> --out-dir report/<batchN>
cp report/<batchN>/decision-table.json docs/assets/data/decision-table.json
mkdocs serve
```

To check the renderer itself with no real data at all, use the synthetic fixture instead:
`tests/fixtures/decision-report-preview-SYNTHETIC.html`.
