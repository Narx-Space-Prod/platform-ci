# platform-ci

Owner: Platform engineering. Application repositories pin reviewed reusable GitHub
Actions workflows by commit SHA. Main requires CODEOWNER review, passing checks and
resolved conversations, including for administrators. No workflow approves code PRs
or bypasses protection. Project guide: [DOC.md](https://github.com/Narx-Space-Prod/platform-infrastructure/blob/main/DOC.md).

## Application delivery

```text
workflow syntax + Gitleaks history scan
  → cached image/test builds (Orders and Cart run concurrently)
  → SonarQube Cloud imports coverage + Java classes from those test stages
  → quality gate passes
  → isolated main-only publishers load the exact tested images, push and sign
  → release notification requests GitOps reconciliation
```

| Workflow | Responsibility |
| --- | --- |
| `workflows.yml` | actionlint and full fetched-history Gitleaks scan |
| `build.yml` | Meaningful-change detection, Docker tests, coverage export, non-root check, Trivy HIGH/CRITICAL gate and SBOM |
| `sonar.yml` | Source analysis, coverage import and server-side quality gate |
| `service.yml` | Main-only immutable image publication and keyless signing; called only after build + Sonar succeed |
| `release.yml` | Record signed image identities, notify GitOps, summarize CI execution/queue times |
| `helm.yml` | Helm rendering, schema validation and image validation |
| `terraform.yml` | Formatting, locked providers, validation, tests and IaC scanning |

Separating build and publication allows the caller to enforce one repository-wide
Sonar gate before either Orders or Cart can publish. Builds have contents:read only.
Only the isolated main publisher receives packages:write and signing id-token:write;
it never checks out or executes application code. Sonar receives only its analysis
token, and the protected main-only gitops-release environment owns the separate
release App key. Public fork PRs receive no analysis token; missing credentials fail
rather than pretending that a scan ran. Do not execute candidate source using
pull_request_target or move this work onto the shared deployment laptop.

## Coverage without duplicate test runs

Each application Dockerfile offers an `analysis` scratch target exporting reports
from the same test stage required by `runtime`. BuildKit reuses that stage; there is
no second test wrapper, separate Java compilation, or second runtime build. The
runtime remains the default final stage and contains no coverage tools/reports.

| Component | Test output | Sonar parameter |
| --- | --- | --- |
| Frontend | c8 LCOV, including currently uncovered browser application code | sonar.javascript.lcov.reportPaths |
| Catalogue | Go atomic coverage profile | sonar.go.coverage.reportPaths |
| Orders | JaCoCo XML, compiled classes and dependency JARs | sonar.coverage.jacoco.xmlReportPaths |
| Cart | coverage.py Cobertura XML | sonar.python.coverage.reportPaths |

The current-run `analysis-COMPONENT` artifacts expire after one day. Each includes
repository/commit/component identity and is checked before analysis; missing,
empty, invalid or mismatched reports fail. Build summaries report measured lines
(or Go statements), with the full report in the artifact. Coverage is not a claim
of complete test quality; uncovered source remains visible. No new blanket
coverage threshold or exclusions are introduced merely to make old code pass.
Sonar's configured new-code quality gate remains authoritative.

The meaningful-change flag still prevents unnecessary runtime publication. Report
exports run even for unchanged components so Orders' combined Java/Python project
receives a complete coverage picture; unchanged test layers can come from BuildKit
cache. Sonar consumes both components after their builds. When only one component
changes, the other publisher is skipped, and release notification still accepts
the successfully published component. Failed build/analysis/publication cannot
be treated as a successful partial release.

## SonarQube Cloud configuration

Three GitHub-bound projects use organisation `narx-space-prod` and repository
variables SONAR_ORGANIZATION, SONAR_PROJECT_KEY, SONAR_SERVER_URL. The restricted
organisation secret SONAR_TOKEN is selected for exactly those three repositories.
Automatic analysis must be disabled in each project because GitHub Actions is the
single analysis authority. The shared workflow supports the EU sonarcloud.io and
US sonarqube.us endpoints; never substitute arbitrary hosts. The official scanner
is SHA-pinned with its default signature verification enabled.

All three repositories require `sonar / Source quality gate` from GitHub Actions,
alongside their existing build/workflow checks and CODEOWNER approval. PR analysis
and merged-main analysis were verified live for the existing organisation. Check
plan entitlements before migrating to another organisation or subscription.

## Unit and component integration gates

Existing language-native unit tests run in Docker's test stages: Node's test
runner, Go test, JUnit 5 and pytest. Their coverage reports feed Sonar. The build
workflow also tests the **same loaded runtime image** before scanning/publication;
it does not rebuild an integration image or access the local Kubernetes cluster.

The `integration` composite action starts uniquely labelled, disposable Docker
resources on the GitHub-hosted runner. Orders uses real PostgreSQL and Flyway;
Cart uses real Redis. Frontend/Catalogue use an explicit HTTP contract fixture
rather than production dependencies. Tests cover successful HTTP contracts,
invalid input/authorization, database-backed session revocation, cart isolation,
and dependency failure/recovery. No AWS or payment-provider credentials are
accepted. All HTTP targets are runner-local dynamically allocated ports.

Failures block the build and therefore Sonar/publication/delivery. JUnit XML is
retained as `integration-COMPONENT` for fourteen days. Test resources, including
anonymous database volumes, are cleaned by generated resource name and job-scoped
labels, with an always-run cleanup step. Never use a global Docker prune command.
Unchanged runtimes still skip publication and runtime integration; report export
can reuse their test cache for the complete repository coverage picture.

Library CI validates this harness against four frozen application source commits
on separate hosted workers. Those are tool-contract fixtures, not replacements
for testing each application's current commit in its own build. These are
**component integration tests**, not the full payment/queue/storefront end-to-end
suite. Existing isolated Compose business-journey tests remain a separate opt-in
suite. Coverage currently represents the instrumented language tests; black-box
runtime integration coverage is not added to those percentages.

## GHCR publication and adoption

Images use `ghcr.io/narx-space-prod/commerce-COMPONENT:COMMIT`; deployments use the
verified digest. The publisher refuses a commit tag containing a different tested
image and rechecks the final digest before signing. Authentication/network errors
fail closed. Cosign signs the image, provenance and CycloneDX SBOM using OIDC. GHCR
uses the short-lived workflow token; private cluster pulls use a separate read-only
credential. Never reuse publishing or release credentials for pull access.

Merge changes to this repository first, then update caller workflow pins and the
GitOps reviewed-builder allowlist to the final merged SHA through reviewed PRs.
The publisher path remains service.yml to retain the existing certificate identity
contract. Existing consumers pinned to earlier revisions keep their old behaviour
until deliberately migrated. Preserve existing trusted builder SHAs so already
published images and rollbacks remain verifiable.

CI execution and queue durations are reported by the release-notification job.
Its timing summary is non-blocking telemetry; all test/security/release gates are
blocking. Deployment and approval time are separate and must be measured from
Argo operations and GitOps PR timestamps. These workflows do not provision AWS
resources or directly apply Kubernetes workloads.

## Single application entry workflow

`application.yml` is the application pipeline wrapper. A service caller supplies
only `application` (`frontend`, `catalogue`, or `orders`) and the two explicitly
named secrets. The wrapper binds build.yml to its own reviewed commit and owns the numbered stage graph:

```text
01 Source policy → 02 Build/test/scan → 03 Sonar quality gate
                → 04 Sign/publish → 05 Start commerce delivery
```

Orders' Cart companion runs alongside its primary build and publisher. Its skipped
jobs do not block Frontend/Catalogue, and an unchanged companion does not suppress
a successful sibling release. Builds and quality analysis cannot access the release
App key; publishers keep the existing reviewed service.yml certificate identity.
The caller must grant the maximum permissions needed by nested jobs, while each
called job retains its own narrower permissions. Never use secrets:inherit.

Release notifications include repository, commit and CI run ID so delivery can
wait for successful CI completion rather than race the final notification step.
The CI summary links to the central Commerce Delivery workflow. Source PR checks
still run in the source repository; multi-repository ownership does not require
rebuilding every service in one central checkout. Migrate required-check contexts
to the observed wrapper check names only after the new checks have passed; retain
strictness, CODEOWNER review and administrator enforcement.
