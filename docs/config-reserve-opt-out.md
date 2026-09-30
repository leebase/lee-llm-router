# Scoped capacity reserve opt-out


A per-channel `reserve_fraction.overrides` value of `0.0` disables protective capacity retention, including the time-scaled coverage reserve. It does not waive exhausted, likely exhausted, unknown or stale subscription availability. Scope the override to an explicitly authorized catalog; other channels retain their configured defaults.

For the authorized exact Sol61 proof, use the private catalog `openai-sub` override and `LEE_LLM_ROUTER_RATE_TABLE` pointing at the dated exact-model rate table. This is published API list-equivalent replacement pricing, not measured subscription billing. Native cache/context tier uncertainty and actual billing remain unknown; long context may change the equivalent tariff.
