# nthlayer-observe (Deprecated)

> **This repository is deprecated.** The functionality previously
> developed here has been consolidated into [`nthlayer-workers`][workers]
> as part of the tiered architecture migration.
>
> Active development continues in the new structure:
> - **observe module:** [`nthlayer-workers/src/nthlayer_workers/observe/`][module]
> - **Project front door:** [`nthlayer`][nthlayer]
> - **Architecture context:** [`opensrm/ARCHITECTURE.md`][arch]
>
> This repository is preserved for historical reference and will be
> archived 90 days from the date of this notice.
>
> If you arrived here from an article or external link, the up-to-date
> implementation is at [`nthlayer-workers`][workers]. Project context
> and architectural principles are at [`nthlayer`][nthlayer].

## Branch notice — `feat/decision-records` is OBSOLETE, not just deprecated

`feat/decision-records` on this repo is **obsolete and should not be
forward-ported.** The decision-records work it contains was redone in
[`nthlayer-workers/observe/decision_records.py`][module-decisions] against
the v1.5 canonical assessment schema (`kind` / `created_at` / `slo_status` /
`drift_signal` / `deploy_gate` / `dependency_graph`). The workers version is
the canonical implementation.

The branch on this repo predates the schema migration: it uses the old field
names (`assessment_type` / `timestamp`) and old type enumerations (`slo_state` /
`drift` / `gate` / `dependency`). It will not run against current
`nthlayer-core` because of field-name and type-enumeration mismatches.

If you arrive here looking for "the real decision-records implementation,"
stop digging into this branch — go to
[`nthlayer-workers/observe/decision_records.py`][module-decisions] instead.
The work is complete there with the canonical schema.

[workers]: https://github.com/rsionnach/nthlayer-workers
[module]: https://github.com/rsionnach/nthlayer-workers/tree/main/src/nthlayer_workers/observe
[module-decisions]: https://github.com/rsionnach/nthlayer-workers/blob/main/src/nthlayer_workers/observe/decision_records.py
[nthlayer]: https://github.com/rsionnach/nthlayer
[arch]: https://github.com/rsionnach/opensrm/blob/main/ARCHITECTURE.md
