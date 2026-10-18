# Repository Agent Governance

## GitHub Issue Graph

- Use the live GitHub Issue Graph for all planning, routing, dependencies, dispatch, review, and completion decisions.
- Dependencies: `blockedBy` / `blocking`; decomposition: `parent` / `subIssues`; work kind: `issueType`.
- Lifecycle: GitHub Project `Status`; responsible role: GitHub Project membership.
- Read relevant fields with `gh issue view` or `gh issue list` JSON before planning or dispatch and again before lifecycle decisions.
- Update native relationships first; read back both `blockedBy` and `blocking` to verify changes.
- Bodies, comments, labels, chat, and local files cannot override or reconstruct graph state.
- If GitHub cannot be read or updated, fail closed and report unavailable control-plane state.
- PI owns contracts, graph edges, Project routing, final review, issue closure, and PR merges.
- Executors report evidence and propose graph changes; they must not silently redefine the graph.
- `.research/graph.yaml` and `.research/tasks/*.yaml` are derived caches or notes only; resolve mismatches in GitHub's favor and refresh them.

## Local synchronization after merge (owner-mandated default)

- After merging a PR, automatically fetch the remote and synchronize `main` in the primary local checkout before reporting completion. Updating only an isolated worktree is insufficient; no additional user confirmation is needed for this synchronization.
- Preserve local commits and uncommitted work. Fast-forward when possible; when histories diverge, preserve the local history and merge the remote branch locally. Never force-reset local work or publish unrelated local commits as part of synchronization.
- Before updating a dirty checkout, protect tracked and untracked changes with recoverable backups. Restore unrelated work afterward; preserve colliding or superseded files outside the active source tree with an explicit recovery inventory rather than silently overwriting them or reintroducing obsolete implementations.
- Verify that the remote merge commit is an ancestor of the primary local `main`, the delivered files exist there, and no merge conflicts remain. Report any remaining local-only commits or changes accurately; do not claim identical branches when they differ.

## Engineering principles (owner-mandated)

- Delete obsolete code; no compatibility layers, migrations for old behavior, or fallback paths.
- Implement the simplest solution for current needs; avoid speculative abstractions and configuration.
- Build a minimal end-to-end version first, then extend it; preserve working code until its replacement works.
- Keep components decoupled, single-purpose, and independently testable.
- R and Python must use mainstream, mature, maintained libraries when suitable; do not recreate their capabilities.
- Check existing dependencies and public APIs before adding packages or implementing functionality.
- If no library fits, document evaluated options and the gap; implement only the missing capability.
- Make durable architecture decisions; avoid temporary designs that require later repair.
- Learn from mature products and proven patterns.
- Every project function requires corresponding automated tests.
- Preserve raw data, enforce executable data contracts, and make analysis reproducible.
- Require relevant automated checks to pass before merging.

## R / Quarto and code organization

- Every delivery must include a reproducible Quarto (`.qmd`) document as its delivery and acceptance entry point.
- Use R for analysis; the delivery QMD records scope, inputs, results, validation evidence, and limitations.
- All R analysis tables must use `tibble`; manipulate them with tidyverse and appropriate related libraries.
- Convert database, Python, and Rcpp tabular outputs to validated tibbles at the R boundary, including typed empty tables.
- Follow tidy data: variables in columns, observations in rows, each type of observational unit in its own table.
- Put reusable package R functions in `packages/beidan/R/` and the bundled Python backend in `packages/beidan/inst/python/beidan_backend/`. Keep repository research clients in `r/` and `src/`, QMD in `quarto/`, and command entry points thin.
- QMD declares inputs, organizes analysis, and presents results; extract reusable functions into modules.
- Develop reusable functions in R, Python called through `reticulate`, or C++ exposed through `Rcpp` wrappers.
- Keep reusable implementations outside QMD; use one authoritative implementation per business/storage contract.
- Rcpp wrappers follow the same mainstream-library, data-contract, testing, and chronology requirements as R and Python functions.
- Module imports must not trigger scraping or database writes.
- Document function inputs, outputs, units, missing values, errors, and side effects where applicable.
- Pass paths, connections, and parameters explicitly; avoid hidden mutable session state.

## Dependencies and reproducibility

- Record direct dependencies, reproducible versions, and required R/Python/Quarto runtimes in project configuration.
- Install dependencies during environment setup, never during function execution or QMD rendering.
- Use `pak` for R package installation, updates, and dependency management. Use other installers only to bootstrap `pak` itself when it is unavailable.
- Select the project Python interpreter explicitly for R/Python calls; fail clearly on incorrect environments.
- Render QMD from a clean session with declared inputs and parameters, independent of RStudio globals or manual execution order.
- Do not depend on undeclared local files, personal paths, or restored workspaces.

## Data contracts and provenance

- Define row meaning, columns, types, unique keys, nullable fields, categories, units, and relationship cardinalities.
- Validate contracts at data boundaries; stop on critical failures.
- Preserve identifiers and leading zeros; distinguish missing values, zero, empty strings, and empty results.
- Make conversions explicit; never silently turn parsing failures into missing values.
- Use typed dates/timestamps and explicit timezones; distinguish event, collection, and label-availability times.
- Declare join keys/cardinality; check unmatched keys and unexpected row multiplication.
- Record filtering/deduplication reasons and counts; do not silently choose between conflicting records.
- Test database/R/Python/Rcpp conversions for nulls, integer precision, identifiers, timestamps, column types, and empty tibble schemas.
- Preserve original bytes, encoding, source identity, and collection timestamps separately from cleaned data.
- Bind derived outputs to input identities/hashes, code identity, parameters, and generation time.
- Apply the stronger cutoff receipt rules below to historical-learning outputs.

## Scraping and database interaction

- 数据采集与补缺优先使用 `agent-reach` 技能：先读取其 `SKILL.md`，按目标网站选择已有后端及失败重试链。采集结果仍须进入本项目既有的解析、核验和权威存储流程，遵守来源限频，保留原始响应、来源身份、采集时间与哈希；长期数据统一保留在 NAS，不依赖已移除的 Sandisk。

- Separate fetching, parsing, validation, and persistence into testable functions.
- Use explicit timeouts, bounded transient retries, and existing source-specific rate limits.
- Preserve raw responses for offline parsing replay; distinguish empty results from request/parser failures.
- Inject credentials through environment configuration; exclude them from code, QMD, logs, and fixtures.
- Parameterize SQL values; use the authoritative storage API for writes.
- Use transactions; define conflicts, duplicate handling, repeated-run behavior, and rollback.
- Test rollback and repeated execution; release connections/resources on both success and failure.

## CI participation (owner-mandated default)

- Agents do not participate in CI by default. Do not configure, add, trigger, monitor, retry, repair, or optimize CI workflows unless the user explicitly requests CI work.
- Do not introduce CI coverage gaps or CI status as agent-imposed acceptance/merge gates, create CI follow-up issues, or repeatedly remind the user about CI.
- Continue required local tests, reproducible QMD rendering, code review, and PI acceptance. Never report unrun or failed CI as passed.
- Respect enforced GitHub branch protection. If it actually prevents an authorized merge, report that concrete blocker once; do not bypass protection or start CI remediation without explicit instruction.

## Tests and acceptance

- Use `testthat` in `packages/beidan/tests/testthat/` for package functions and `tests/testthat/` for repository clients; use `pytest` in the relevant `tests/` area.
- Map every project function to tests, including helpers and functions defined in QMD; untested existing functions remain gaps.
- Add/update and run corresponding tests with each function change; bug fixes require regression tests.
- Test observable behavior and contracts: normal inputs, relevant boundaries/missing/empty inputs, and failure paths.
- Test third-party integration contracts; dependency internals remain the dependency's responsibility.
- Exercise test helpers through the tests they support; avoid recursive tests of tests.
- Keep routine tests deterministic with saved responses and temporary databases; separate live integration checks.
- Run R tests with `Rscript tests/testthat.R`; run Python tests with the project interpreter's `-m pytest`.
- Test Rcpp functions through their exported R wrappers, including conversion boundaries and failure paths.
- Verify key QMD in a fresh process with declared inputs, execution enabled, cache/freeze bypassed, and errors fatal.
- Rendering does not replace function tests; HTML containing execution errors fails acceptance.
- Inspect key rendered tables/figures for missing content, units, and labels; identify input snapshots and parameters.
- Verify affected function tests, data contracts, key QMD renders, and applicable cutoff governance checks locally.
- Report changed behavior, function/test mapping, exact check commands/results, and reasons for skipped checks.
- Every delivery must pass `codex review` covering its QMD, reusable implementation, tests, and data contracts before PI acceptance.
- Record the reviewed revision or file hashes, review command, findings, and resolutions in the delivery QMD; a successful process exit alone is not acceptance.
- Fix blocking findings and rerun review after relevant changes; PI verifies the final reviewed artifact before closure or merge.
- Skipped or failed required checks do not pass; documentation alone does not prove implementation or enforcement.
- Report compliance gaps with evidence and route remediation through the live Issue Graph.

## Cutoff-driven historical learning (owner-mandated)

### Scope and chronology

- Every decision-facing historical learning, calibration, tuning, selection, ranking, gate, or optimization function must receive an explicit cutoff, either as a standalone cutoff object or embedded in an explicitly passed decision object (for example, `portfolio$cutoff`). An embedded cutoff satisfies this requirement; do not require a redundant standalone cutoff argument.
- Validate the embedded cutoff and its binding to the object's input snapshots and derived artifacts. Missing, malformed, or inconsistent cutoff context must fail closed; never infer it from the current clock, hidden globals, or mutable session state. Changing the cutoff requires rebuilding the affected decision artifacts, not merely editing their cutoff field. All chronology, receipt, and cache requirements below apply equally to both forms.
- This includes preprocessing, thresholds, support depth, hyperparameters, seeds, expert admission, routing, allocation, bankroll gates, league/team effects, regimes, embeddings, priors, shrinkage, imputation, normalization, and availability gates.
- Admit actual source data and available labels strictly before cutoff; derive every fit/tune/calibration partition within that prior window.
- Fail closed on missing chronology or insufficient history.
- Use issue-level walk-forward with the target fixture-relative decision epoch as cutoff.
- Admit prior-year history and current-year issues only when their labels were actually available before cutoff.
- Exclude target/future issues and unsettled labels by both timestamp and exact target-issue identity, even if a bad source claims early target settlement.
- Freeze an immutable cutoff-keyed artifact before opening target settlement; later labels must never rewrite it.
- Name availability evidence classes: observed availability or documented conservative safe boundaries may authorize prospective use; historical timestamp proxies are diagnostic only.
- Hidden globals such as `FIT_END`, `TUNE_YEAR`, `CALIBRATION_YEAR`, or detached acceptance booleans must not control new target periods.
- Pre-rule historical packages may remain only as inventoried evidence, not reusable clean interfaces.
- Pass business constants explicitly: fixed N, CNY1,024, CNY2 units, and one ticket-level 0.65 payout factor.

### Receipts, caches, and review

- Return the learned artifact with a machine-readable receipt; independent replay is mandatory.
- Bind cutoff identity/time, maximum source/label-availability times, partitions, selected parameters, metrics, and gate predicates.
- Bind source hashes, transitive implementation hashes, model identity, imported helpers, and a cutoff-bound cache key.
- Never reuse caches across cutoffs, sources, or implementations; later issue models/caches cannot serve earlier issues.
- Every research contract and PI/adversarial review must inventory transitive historical-learning functions.
- Review cutoff receipt, maximum admitted times, partition derivation, cross-cutoff cache exclusion, and imported-helper bindings.
- Verify post-cutoff mutation invariance through selection, support, tickets, and routing; label-free final output alone does not prove causality.

### Recency and shared implementation

- Treat recency weighting as learning: pass policies explicitly and select them only inside prior cutoff windows.
- Policies include equal expansion, time/issue decay, bounded recent-state blends, change detectors, refit cadence, half-life, window, blend, threshold, and ESS floors.
- Receipts must bind the full weight ledger, effective sample size (ESS), long-history shrinkage, and policy parameters.
- Sparse recent evidence must fail closed or shrink to the frozen long-history prior.
- Recent-state blends must equal `(1-alpha) * long_history + alpha * recent_state`, with both distributions normalized and component masses reconciled separately.
- Multiplying recent rows within one global normalization is not an accepted blend.
- All chronology machinery must come from `packages/beidan/inst/python/beidan_backend/temporal_learning`, including R/QMD and imported-function usage.
- Research clients supply domain fit/predict/select callbacks only; do not copy cutoff, availability, partition, weighting, ESS, cache, receipt, runner, or replay utilities.
- New direct historical fitting outside shared learning contexts and duplicated temporal helpers fail governance checks.
- Replace/delete obsolete implementations without compatibility wrappers.
- Static enforcement scans `src/` and `scripts/`; allow legacy debt only by exact AST occurrence fingerprint and count, never whole-file exemptions.
