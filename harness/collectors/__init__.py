"""Provider-side (billing-plane) usage collectors.

Product B exposes no machine-readable usage in headless mode (SPEC 2.9 item 1),
so its token counts have to come from the provider's own metering surface. These
collectors read that surface and attribute it to runs; they never call a model.
"""
