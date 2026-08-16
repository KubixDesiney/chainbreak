# CHAINBREAK Threat Model

Method: asset-centric enumeration with STRIDE prompting, scoped to the benchmark system
itself. This is a threat model of *CHAINBREAK*, not of the AWS environments it measures.

Impact scale: **Critical** (credential compromise or damage outside the benchmark
namespace) · **High** (invalid research results published as valid, or benchmark-account
damage) · **Medium** (run failure, wasted cost, local data exposure) · **Low** (annoyance).

---

## 1. Assets

| ID | Asset | Why it matters |
|---|---|---|
| A-1 | Operator AWS credentials | Compromise reaches beyond the benchmark |
| A-2 | Benchmark STS session credentials | Namespace-scoped, but still cloud access |
| A-3 | The benchmark AWS account | Cost, and the operator's other resources if not truly isolated |
| A-4 | Terraform state | Resource inventory; possible sensitive attributes |
| A-5 | Evidence bundles | May encode account structure; are the research product |
| A-6 | Scenario files | Executed-against; shareable; untrusted input |
| A-7 | Analysis correctness | The entire value proposition |
| A-8 | CI secrets | Would grant an attacker the operator's cloud access |
| A-9 | Published reports | Reputational; may leak environment details |
| A-10 | The operator's *other* AWS accounts | Must be unreachable by construction |

---

## 2. Threats

### T-01 · Credential leakage into evidence, logs, or reports
**Assets:** A-1, A-2, A-5, A-9 · **STRIDE:** Information disclosure · **Impact:** Critical
**Vector:** A domain model gains a field holding a session token; a botocore DEBUG log
records an `Authorization` header; a report template interpolates a credential object.
**Mitigation:** SI-1 (non-serializable secret type, redaction choke point that *raises*,
log filter covering third-party loggers).
**Validation:** property-based redaction fuzzing over every model; a test that enables
botocore DEBUG logging during a fake run and greps the log; `evidence export --public`
re-scans before any file leaves the machine.
**Residual (R-1):** A field added in a future PR that bypasses `redact()` by writing
directly with `json.dump`. Mitigated by a lint rule banning `json.dump`/`open(...,"w")`
inside `evidence/` outside the writer module, and by code review.

### T-02 · Wrong-account execution
**Assets:** A-3, A-10 · **STRIDE:** Elevation / destructive misuse · **Impact:** Critical
**Vector:** An operator has production credentials in the environment and runs `chainbreak
run` in the wrong shell.
**Mitigation:** SI-6 — explicit `allowed_account_ids` allowlist with no wildcard and no
implicit default; `GetCallerIdentity` is the first call; abort on mismatch. SI-2 namespace
assertion is a second, independent barrier. Preflight P9 warns if the account contains any
`Environment=production` tagged resource.
**Validation:** `test_preflight_ordering.py` asserts exactly one AWS call before abort.
**Residual (R-3):** An operator adds their production account to the allowlist. No technical
control can prevent this; documentation states the requirement for a dedicated account, and
the P9 warning fires.

### T-03 · Over-permissive benchmark identities
**Assets:** A-3 · **STRIDE:** Elevation · **Impact:** High
**Vector:** A Terraform policy written with `Resource: "*"` for convenience; a session
policy synthesized too broadly.
**Mitigation:** All identity policies are `Condition`-scoped on `aws:ResourceTag/Namespace`
or explicit namespaced ARNs. `tflint`/`checkov` in CI with a custom rule failing any
`Resource: "*"` outside a documented allowlist (`sts:GetCallerIdentity` only). Session
policies are *generated* from bindings, never hand-written, so breadth is a code bug with a
test rather than a copy-paste error.
**Validation:** `tests/unit/test_policy_synthesis.py` asserts generated policies contain no
wildcard resource; Terraform CI policy scan.
**Residual (R-4):** Low. IAM wildcards in service-linked contexts.

### T-04 · Terraform state disclosure
**Assets:** A-4 · **STRIDE:** Information disclosure · **Impact:** Medium
**Vector:** `terraform.tfstate` committed, or a remote backend left world-readable.
**Mitigation:** `.gitignore` covers `*.tfstate*`, `*.tfvars`, `.terraform/`; a pre-commit
hook and a CI job fail on a state-shaped file in the diff; documentation requires an
encrypted backend with restricted access if remote state is used.
**Validation:** CI check `no-state-in-repo`.
**Residual (R-5):** Low.

### T-05 · Probing the wrong resource
**Assets:** A-3, A-7 · **STRIDE:** Tampering / destructive misuse · **Impact:** High
**Vector:** A binding template mis-expands; a Terraform output points at a pre-existing
bucket; two namespaces collide.
**Mitigation:** SI-2 namespace regex checked at three levels (binding expansion, explicit
assert, botocore hook); tag verification in preflight P7 confirming the resource is
CHAINBREAK-owned, not merely name-matching; namespace derived from a hash including account
and workspace so collision requires a deliberate salt reuse.
**Validation:** `test_namespace_guard.py` includes lookalike ARNs; `test_preflight.py`
covers a name-matching but untagged resource.
**Residual (R-6):** Low.

### T-06 · Cleanup failure leaving live infrastructure
**Assets:** A-3 · **STRIDE:** DoS (cost) · **Impact:** Medium
**Vector:** `terraform destroy` fails on a non-empty bucket; the process is killed mid-run
leaving an inline deny policy attached; an operator forgets.
**Mitigation:** `force_destroy` on the bucket; explicit CloudWatch log group management;
runtime mutations tracked and reverted in a `finally`; unreverted mutations printed with
exact revert commands; `chainbreak infra verify-clean` enumerates every provisioned service
by native list/tag APIs; S3 lifecycle and
DynamoDB TTL bound storage even on orphans; Budgets alarm at $5.
**Validation:** `test_cleanup_contract.py`; a chaos test that kills the orchestrator
mid-phase and asserts the revert log is complete and actionable.
**Residual (R-7):** Medium — a SIGKILL cannot run a `finally`. Mitigated by the revert log
being written *before* each mutation, so recovery information survives.

### T-07 · Cost runaway
**Assets:** A-3 · **STRIDE:** DoS · **Impact:** Medium
**Vector:** A poll phase with a 1 ms interval and a 4-hour window; a pathological scenario
with depth 20 and 50 capabilities; provisioned DynamoDB capacity.
**Mitigation:** SI-7 duration ceiling; SI-8 conservative cost estimate in preflight;
`interval_ms` floor of 100 in the schema; `max_delegation_depth` (6); on-demand DynamoDB;
Budgets alarm.
**Validation:** `test_cost_estimator.py` asserts conservatism; schema tests reject a 1 ms
interval.
**Residual (R-8):** Low.

### T-08 · Cross-run contamination
**Assets:** A-7 · **STRIDE:** Tampering · **Impact:** High
**Vector:** Two concurrent runs write to the same scratch prefix; a previous run's inline
deny policy is still attached when the next run starts.
**Mitigation:** Write probes target `scratch/{run_id}/` — run-scoped by construction, not by
convention. A run lock file per namespace prevents concurrent runs by default
(`--allow-concurrent` exists and lowers confidence). Preflight snapshots policy state and
compares against the expected baseline fingerprint; a mismatch is `CONFIGURATION_ERROR`
before any measurement.
**Validation:** `test_run_isolation.py`; `test_baseline_drift_detection.py`.
**Residual (R-9):** Low.

### T-09 · Malicious or malformed scenario input
**Assets:** A-6, local machine · **STRIDE:** Elevation, DoS · **Impact:** High
**Vector:** A shared scenario containing `!!python/object/apply:os.system`; a
billion-laughs YAML bomb; a document with 10⁶ identities; an inline policy naming a
third-party ARN.
**Mitigation:** SI-11 — restricted `SafeLoader` subclass rejecting unknown tags; alias
expansion cap; document size cap (1 MiB) and node count cap; JSON Schema with `maxItems`
everywhere; validation stage 5 rejecting literal ARNs, account IDs, and regions.
**Validation:** `test_scenario_safety.py` with each attack as a fixture.
**Residual (R-10):** Low.

### T-10 · Malicious or malformed evidence input
**Assets:** A-7, A-9 · **STRIDE:** Tampering, elevation via report · **Impact:** Medium
**Vector:** A third-party bundle with a `security_interpretation` containing
`<script>`; a 10 GB `observations.jsonl`; a manifest claiming a false root hash.
**Mitigation:** Schema validation with size bounds and streaming line-by-line parsing with a
per-line length cap; hash verification with `bundle_root_verified` stamped into every
finding; Jinja2 autoescape on with no `|safe` usage anywhere (asserted by a test that greps
the template directory).
**Validation:** `test_bundle_ingest_safety.py`; `test_no_unsafe_template_filters.py`.
**Residual (R-11):** Low.

### T-11 · Measurement error published as a finding
**Assets:** A-7, A-9 · **STRIDE:** — (integrity of research) · **Impact:** High
**Vector:** A missing marker read as a wave of denials; throttling read as revocation; clock
skew inflating a timing interval; a wrong capability→action mapping.
**Mitigation:** This is the threat the entire architecture is shaped against — precondition
verification, content-verified success, `ERROR_*` outcome classes separate from `DENIED_*`,
unanimity across trials, coverage and confidence as first-class outputs, INCONCLUSIVE
preferred over a guess, monotonic-only interval math, and negative controls proving the
detector works at all.
**Validation:** the negative-control suite; `DETECTOR_FAILURE` as a first-class finding
type; provider contract tests run against both fake and real adapters.
**Residual (R-12):** Medium and irreducible. A benchmark can be systematically wrong in a
way its own controls do not model. Mitigated only by publishing raw evidence so third
parties can re-analyze — which is why bundles are the deliverable, not just reports.

### T-12 · CI secret exposure
**Assets:** A-8, A-1 · **STRIDE:** Information disclosure · **Impact:** Critical
**Vector:** A fork PR triggering a workflow with access to repository secrets; a workflow
echoing credentials; a compromised third-party action.
**Mitigation:** **Default CI requires no AWS credentials at all** — unit and integration
layers use the fake provider. The AWS layer runs only on a manually dispatched workflow,
restricted to the `aws-benchmark` GitHub environment with required reviewers, using OIDC
role assumption (no static keys), never on `pull_request` from a fork. All third-party
actions pinned to full commit SHAs. `permissions:` is set to the minimum per job.
**Validation:** a CI lint job asserting no workflow with `pull_request_target`, no unpinned
action, and that the AWS workflow is `workflow_dispatch`-only.
**Residual (R-13):** Low.

### T-13 · Environment disclosure through published artifacts
**Assets:** A-9, A-3 · **STRIDE:** Information disclosure · **Impact:** Medium
**Vector:** A published bundle or report containing account IDs, ARNs, bucket names,
hostnames, or session names.
**Mitigation:** Account IDs and ARNs are hashed with a per-run salt throughout evidence;
scenarios contain no ARNs by construction; `evidence export --public` re-scans and prints a
diff of what it stripped; policy documents are excluded by default.
**Validation:** `test_public_export_scrub.py` with a bundle seeded with identifiers in every
field.
**Residual (R-14):** Low. Hashes are stable within a bundle by design (that is what makes
correlation possible), so an adversary who already knows a candidate ARN could confirm it
by recomputing with the salt — the salt is derived from `run_id`, which is public in the
bundle. Documented rather than hidden: bundles disclose *equality relationships*, not
identifiers.

### T-14 · Dependency supply chain
**Assets:** A-1, A-8, local machine · **STRIDE:** Elevation · **Impact:** Critical
**Vector:** A compromised release of a transitive dependency running at install time.
**Mitigation:** Lockfile with hashes committed; `pip install --require-hashes` in CI;
Dependabot with review; minimal dependency surface (six runtime deps in the core, boto3 only
under the `aws` extra); no `curl | sh` anywhere in docs or tooling.
**Validation:** CI installs from the lockfile with hash checking.
**Residual (R-15):** Medium and industry-wide.

### T-15 · Benchmark disabling its own observation
**Assets:** A-7 · **STRIDE:** Tampering · **Impact:** Medium
**Vector:** A mutation phase targeting the bootstrap or principal role, after which
snapshots and precondition checks silently fail and every subsequent probe reads as denied.
**Mitigation:** SI-12 mutation choke point refuses those targets. `identity.whoami` acts as
a per-matrix control: its failure aborts rather than being recorded as a denial.
**Validation:** `test_mutation_guard.py`.
**Residual (R-16):** Low.

---

## 3. Residual risk register

| ID | Risk | Level | Owner decision |
|---|---|---|---|
| R-1 | Future code bypassing the redaction choke point | Low | Lint rule + review; accepted |
| R-2 | Python cannot scrub secrets from memory | Low | Accepted; documented |
| R-3 | Operator allowlists a production account | Medium | Cannot be prevented technically; documented + P9 warning |
| R-7 | SIGKILL leaves a mutation attached | Medium | Revert log written pre-mutation; accepted |
| R-12 | Systematic measurement error | Medium | Irreducible; mitigated by publishing raw evidence |
| R-14 | Bundles disclose equality relationships | Low | Documented; inherent to correlatable evidence |
| R-15 | Dependency supply chain | Medium | Industry-wide; lockfile + minimal surface |

---

## 4. Out of scope

Threats to the AWS environments CHAINBREAK measures (that is the *subject*, not the
system); AWS's own security; the operator's endpoint security beyond credential handling;
and physical security. An operator running CHAINBREAK on a compromised machine has a
problem CHAINBREAK cannot solve.

---

## 5. Review cadence

This model is reviewed when: a new provider adapter is added, a new capability with
`BENIGN_WRITE` or higher sensitivity is introduced, the evidence schema changes in a way
that adds identifier-bearing fields, or CI gains any credentialed job. Each review appends a
dated entry to [docs/DECISIONS.md](docs/DECISIONS.md).
