# Configurations C1–C5 (SPEC §2.1)
One YAML per configuration. model_ref values are placeholders resolved ONLY by
manifest/delivery-manifest.yaml. cost_basis is declared per delivery org (subscription
seat vs API). The runner refuses to start if manifest resolution or cost_basis is missing.
