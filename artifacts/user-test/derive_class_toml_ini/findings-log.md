# User-simulation findings log: derive class TOML/INI

## 2026-09-12 — Attempt 1

Recommendation: **Ready for autonomous re-arm**

All five manifest journeys passed against the real `python3 -m lee_llm_router.doctor staff` interface. No product findings were reproduced, so the result's `findings` array is empty.

### Journey observations

- A standalone `pyproject.toml` packet exited 0 and derived `language: yaml-config`.
- A standalone `tox.ini` packet exited 0 and derived `language: yaml-config`.
- A packet combining `.toml`, `.ini`, `.yaml`, `.yml`, and `.json` exited 0 and remained `yaml-config`.
- A packet combining `.toml` and `.py` exited 0 and derived `mixed`.
- `staff --help` exposed exactly the eight language choices `python`, `typescript`, `shell`, `c`, `sql`, `yaml-config`, `markdown`, and `mixed`.
- An INI path containing the `authority` keyword exited 0, derived `yaml-config`, and recorded `authority` through `domain_matches` with `domain_source: owned_paths`.

### Input and platform evidence reviewed

- The supplied smoke result records `app_started: true`, `core_flow_completed: true`, `start_exit_code: -15`, `check_exit_code: 0`, and no blocking errors.
- The evaluator packet provides seven route-selection records, seven post-execution route attestations, seven repository-identity records, and a pre-evaluator evidence-chain snapshot with `ok: true`, 8 entries checked, and 164 artifacts checked. Semantic-judge execution is `not_applicable` because this playbook declares no semantic check.
- The preserved independent validator record reports six passing results: compile the focused test file (exit 0, 0.124787 seconds); focused pytest from the implementation step (exit 0, 28 passed/0 failed/0 skipped, 1.033689 seconds); focused pytest from repair-and-verify (exit 0, 28 passed/0 failed/0 skipped, 1.046546 seconds); Black check (exit 0, 0.298677 seconds); Ruff check (exit 0, 0.028975 seconds); and compile the implementation plus focused test file (exit 0, 0.032268 seconds). These commands were not rerun during this evaluator step.

### Findings

None.

## 2026-09-12 — Attempt 2

Recommendation: **Ready for autonomous re-arm**

All five manifest journeys passed against the real `python3 -m lee_llm_router.doctor staff` interface. This retry records absolute packet paths so that the commands are independent of the verifier's working directory. No product finding was reproduced, so the result's `findings` array remains empty.

### Journey observations

- The standalone `pyproject.toml` packet command exited 0, contained `"language":"yaml-config"`, and did not emit `PacketClassError`.
- The standalone `tox.ini` packet command exited 0, contained `"language":"yaml-config"`, and did not emit `PacketClassError`.
- The packet combining `.toml`, `.ini`, `.yaml`, `.yml`, and `.json` exited 0 and contained `"language":"yaml-config"`.
- The packet combining `.toml` and `.py` exited 0 and contained `"language":"mixed"`.
- `staff --help` exited 0 and exposed the eight choices `python`, `typescript`, `shell`, `c`, `sql`, `yaml-config`, `markdown`, and `mixed`.
- The authority-path INI packet command exited 0, contained the observed authority `domain_matches` record, reported `domain_source` as `owned_paths`, and derived `yaml-config`.

### Input and platform evidence reviewed

- The supplied smoke result records `app_started: true`, `core_flow_completed: true`, `start_exit_code: -15`, `check_exit_code: 0`, and no blocking errors.
- The evaluator evidence packet provides eight route-selection records, eight post-execution route attestations, eight passing repository-identity comparisons, and a pre-evaluator evidence-chain snapshot with `ok: true`, 9 entries checked, and 188 artifacts checked. Semantic-judge execution is `not_applicable` because this playbook declares no semantic check.
- The packet's temporal evidence records successful route execution, repository identity, and validator authority for the earlier producer steps and smoke gate. For user-simulation attempt 1, evaluator route execution and repository identity are `verified_true`, while validator authority is `verified_false` because `user_journeys_execution_verified` failed. That prior status is scoped only to attempt 1 and is the reason this report was repaired.
- The preserved authoritative validator record contains six passing results, all with exit status 0: focused-test compilation (`1f2a0d30a608c04a1a81b5f870d16c6438d8b7a60ca63fc9044ad3ba51d6c552`), implementation-step focused pytest (`e8b514bc92829f0f0e24a77d02c2328307cd8dc6ec5b2a5330fe603b316463e9`), repair-step focused pytest (`f5cf57d8cf956a96f7ae19b87db68ed2b0fd12c7ecbf277cd899d11afc9a2b11`), Black (`07b7e20a09d2992962108aa2a037969c4d0b58464ff6397bbaf98c72f87047f2`), Ruff (`04c24b15c3ab2d5bcb5d4d71d90b790aded9b916fb14d63d1b87c4f0877d18e7`), and implementation-plus-focused-test compilation (`8e8e93086623dd4e6b2126f48a46fac0522c519ca4d7f71b1e6b58bba65b8357`). These commands were not rerun during this evaluator attempt.
- Platform-owned post-execution attestations for attempt 2 are not yet available and are not certified by this evaluator.

### Findings

None.

## 2026-09-12 — Run 003dd9f505b8 Attempt 1

Recommendation: **Ready for autonomous re-arm**

All five manifest journeys passed against the real `python3 -m lee_llm_router.doctor staff` interface. No product findings were reproduced, so the result's `findings` array remains empty.

### Journey observations

- Operator derives staffing class for packet with .toml owned path: executed `python3 -m lee_llm_router.doctor staff --from-packet /home/lee/projects/lee-llm-router/tmp/derive_class_toml_ini_user_test/toml_packet.md --at 2026-09-12 --json`, exited 0, observed `"language":"yaml-config"`, no `PacketClassError`.
- Operator derives staffing class for packet with .ini owned path: executed `python3 -m lee_llm_router.doctor staff --from-packet /home/lee/projects/lee-llm-router/tmp/derive_class_toml_ini_user_test/ini_packet.md --at 2026-09-12 --json`, exited 0, observed `"language":"yaml-config"`, no `PacketClassError`.
- Operator verifies homogeneous config packets resolve to yaml-config: executed `python3 -m lee_llm_router.doctor staff --from-packet /home/lee/projects/lee-llm-router/tmp/derive_class_toml_ini_user_test/homogeneous_config_packet.md --at 2026-09-12 --json`, exited 0, observed `"language":"yaml-config"` rather than mixed.
- Operator verifies heterogeneous code and config packets resolve to mixed: executed `python3 -m lee_llm_router.doctor staff --from-packet /home/lee/projects/lee-llm-router/tmp/derive_class_toml_ini_user_test/heterogeneous_packet.md --at 2026-09-12 --json`, exited 0, observed `"language":"mixed"`.
- Operator validates closed taxonomy preservation and domain tag isolation: executed `python3 -m lee_llm_router.doctor staff --help`, exited 0, observed closed 8-value language taxonomy; executed `python3 -m lee_llm_router.doctor staff --from-packet /home/lee/projects/lee-llm-router/tmp/derive_class_toml_ini_user_test/domain_isolation_packet.md --at 2026-09-12 --json`, exited 0, observed `"domain_matches":[{"keyword":"authority","tag":"authority"}]` with `domain_source: owned_paths` and `language: yaml-config`.

### Input and platform evidence reviewed

- The supplied smoke result records `app_started: true`, `core_flow_completed: true`, `start_exit_code: -15`, `check_exit_code: 0`, and no blocking errors.
- The evaluator evidence packet provides seven route-selection records, seven post-execution route attestations, seven passing repository-identity comparisons, and a pre-evaluator evidence-chain snapshot with `ok: true`, 8 entries checked, and 164 artifacts checked. Semantic-judge execution is `not_applicable` because this playbook declares no semantic check.
- The packet's temporal evidence records successful route execution, repository identity, and validator authority for the earlier producer steps and smoke gate (steps 01, 03, 04, 05, 06, 07, 08).
- The preserved independent authoritative validator record contains six passing results, all with exit status 0:
  1. `python3 -m compileall tests/test_staffing_derive_class.py`: exit status 0, duration 0.128023s, evidence hash `8c3f92e5084e7d859a428a67fc6106dbb999eb15baaf8f1b9dee119d747fa8d7`.
  2. `python3 -m pytest tests/test_staffing_derive_class.py`: exit status 0, duration 1.134916s, 28 passed in 0.32s, evidence hash `cd6f873234e316571aba2d2b6a437be5b6d7aae6390f39a14eeeaae830d40850`.
  3. `python3 -m pytest tests/test_staffing_derive_class.py`: exit status 0, duration 1.057359s, 28 passed in 0.32s, evidence hash `a19a1167041699c8ff6da3bf224eee380cba6ec3968dbeb45879e95617b7aa85`.
  4. `BLACK_NUM_WORKERS=1 python3 -m black --check src/lee_llm_router/staffing/derive_class.py tests/test_staffing_derive_class.py`: exit status 0, duration 0.301396s, evidence hash `92338bc62d289f313d874b8cb1f8f07d2980051dfc22981f7215502926e5a1b8`.
  5. `python3 -m ruff check src/lee_llm_router/staffing/derive_class.py tests/test_staffing_derive_class.py`: exit status 0, duration 0.028783s, evidence hash `3976acd94e7f4f8deab7e98e5b743e0e54b0f945d69552d11451ba7afd368952`.
  6. `python3 -m compileall src/lee_llm_router/staffing/derive_class.py tests/test_staffing_derive_class.py`: exit status 0, duration 0.031417s, evidence hash `0d9681520895e2bbff47f399092e80a445fb22a9266cfbaf5d0d23bec3021bdd`.
  These commands were not rerun during this evaluator step.
- Platform-owned post-execution attestations for this step are produced after return and are not certified in advance.

### Findings

None.

