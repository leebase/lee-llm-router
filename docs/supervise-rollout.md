# Supervise rollout and CLI use

The accepted supervise contract ships in the generated shims. Render and inspect
shims through the existing `lee-llm-router shims` commands before adopting them
in a project. Existing active sessions retain their loaded instructions.

## Parent admission

Pass `run --unit-id ID --unit-state STATE.jsonl --unit-decision decision.json`
together to enable durable parent admission. The controller records decisions;
the router reserves a start before dispatch and retains each finish. See the
[parent admission contract](staffing/supervise-parent-admission.md) and its
[decision example](staffing/supervise-parent-decision.example.json). Missing
records, exhausted limits and prohibited unchanged methods stop admission.
Legacy runs without these three flags keep their existing behavior.

## Exact route authority and reserve policy

An explicitly pinned `--route` may carry `--authorized-by lee --reason TEXT`.
This waives only `never_automatic`; availability, reserve, credentials and
reviewer independence remain enforced. Automatic selection gets no exception.
The caller must state Lee's actual authority; these flags confer none themselves.

For deliberately consuming available subscription capacity, an existing scoped
policy can set the channel reserve fraction to zero. See
[reserve opt-out](config-reserve-opt-out.md). Positive known capacity then clears
the reserve calculation, while exhausted, unknown and stale availability still
fail their normal checks. Other reserve settings retain D334 per-bucket coverage
and D216 fallback protection. Model names and prices come from the caller's
catalog and dated rate table; this publication does not replace that catalog.

## Codex over SSH

The governed dispatcher honors the existing explicit Codex binary override,
then normal PATH resolution, then an executable `~/.local/bin/codex`. The
fallback resolves a genuine installed symlink to its package binary, preserving
adjacent native helpers. Missing installations fail without launching a provider.
See [the executable binding contract](codex-governed-executable-binding.md).

## Publication provenance

Runtime bytes match the independently accepted installed rollout. Necessary
pre-existing dependencies are the D334 availability/coverage implementation,
structured reserve enforcement, explicit pinned-route authorization and the
reviewed Claude directory/identity/control-plane launch inputs. Their original
reviews and the consuming rollout acceptance remain the authority; publication
adds no routing policy, capability or sandbox relaxation. Historical candidate
notes below the work records retain their original dates and pending language;
Lee accepted the rollout and authorized publication on 2026-09-30.
