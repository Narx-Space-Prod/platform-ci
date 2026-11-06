# platform-ci

Owner: Platform engineering.

Shared validation, then application build/scan/publish and release orchestration. Callers pin approved workflow revisions by commit SHA and receive only the permissions they need.

Project guide: [DOC.md](https://github.com/Narx-Space-Prod/platform-infrastructure/blob/main/DOC.md).

## Current state

Application builds test and scan the runtime once, then transfer the exact image to
an isolated trusted publisher. The publisher uses a short-lived GitHub token to push
to GHCR and OIDC for keyless Cosign signatures/provenance/SBOMs. Publishing remains
disabled until callers grant packages:write and dedicated release credentials/package
access are configured. PR build jobs have contents:read only and never publish.
All changes after repository initialization go through feature branches and pull requests.
These repositories are public on GitHub Free. Protected `main` requires a CODEOWNER
approval, passing CI checks and resolved conversations; administrators follow the same rules.

## Reusable workflows

| Workflow | Checks |
| --- | --- |
| `workflows.yml` | GitHub Actions and embedded shell syntax using actionlint |
| `terraform.yml` | Formatting, locked provider initialization, validation and mocked Terraform tests |
| `helm.yml` | Lint, render dev/QA/production profiles, Kubernetes schema validation and missing-image rejection |
| `service.yml` | Build runtime images through test stages, reuse BuildKit caches and check non-root defaults |

There are no AWS dependencies or cluster apply operations in these workflows. Only the
main-only publisher receives packages:write and signing OIDC; release notification uses
a separately supplied GitHub App key. No workflow approves PRs or bypasses protection.
Downloads are versioned and checksum-verified; actions are pinned by commit SHA.
The Helm validator targets the current commerce chart layout rather than claiming to be a universal framework.
Each application's runtime Docker target depends on its tests. Building the runtime
therefore verifies source and packages it in one build; CI does not rebuild a separate
test image or rerun a duplicate test wrapper. Orders and cart use separate jobs/images.

## GHCR publication contract

Images use `ghcr.io/narx-space-prod/commerce-COMPONENT:COMMIT`, with deployments pinned
to the verified digest. GHCR tags are mutable at the registry: this workflow refuses a
commit tag pointing to another tested image and checks the final digest before signing.
A matching existing image is reused. Authentication/network errors fail closed.
Private packages require explicit read access for platform-gitops Actions and a separate
read:packages pull credential for the local cluster; never reuse the publishing token.
Public-package visibility is an explicit owner setting, not changed by this workflow.

Merge the shared workflow PR first. Update service callers and the GitOps builder
allowlist to the final reviewed main SHA before enabling DELIVERY_ENABLED.

## Release credential boundary

Image publication uses only the ephemeral GitHub token and main-only job guard. It
does not need a deployment environment or release App key. The GitOps notification
job uses the main-only gitops-release environment. Store NARX_RELEASE_APP_PRIVATE_KEY
there, not as a repository secret, so branch PR workflows cannot read it. Callers pass
that same secret name; the reusable job receives the protected environment's value.
Keep source CODEOWNER checks, packages permissions and signed-main builder verification.

## SonarQube Cloud source quality gate

`sonar.yml` is a separate reusable source-analysis gate for the three application
repositories. Orders includes both its Java services and the Python cart. It uses
full SCM history, a commit-pinned official scanner with signature verification,
explicit source/test scopes, and waits up to ten minutes for the server-side quality
gate. Scan errors, missing configuration, timeouts and failed gates fail the job.
Java bytecode and library inputs are compiled in the pinned Maven builder without
rerunning tests; the existing image build remains responsible for application tests.
No scanner token is passed to Maven, Docker builds, publishing or GitOps.

Activation requires an actual provisioned Sonar organisation and three GitHub-bound
projects. Connect only the three service repositories through the Sonar GitHub App.
Check the plan supports pre-merge PR analysis: the free OSS plan is distinct from
the standard Free plan, and eligibility must be confirmed in Sonar. Do not depend
on an expiring commercial trial. Select CI-based analysis (disable automatic
analysis) so each commit has one analysis authority. Establish the main baseline
before requiring PR checks.

Configure repository variables `SONAR_ORGANIZATION`, `SONAR_PROJECT_KEY` and,
optionally, `SONAR_SERVER_URL` (EU `https://sonarcloud.io`, US
`https://sonarqube.us`). Store `SONAR_TOKEN` directly in each service repository's
Actions Secrets; prefer project-scoped analysis credentials where supported. Never
paste tokens into issues, chat, properties files, or command arguments. The scanner
receives only the dedicated analysis credential, never release credentials.

Call the reviewed workflow SHA from each service CI, after workflow/secret checks:

```yaml
  sonar:
    needs: workflows
    uses: Narx-Space-Prod/platform-ci/.github/workflows/sonar.yml@REVIEWED_COMMIT_SHA
    with:
      organization: ${{ vars.SONAR_ORGANIZATION }}
      project-key: ${{ vars.SONAR_PROJECT_KEY }}
      server-url: ${{ vars.SONAR_SERVER_URL || 'https://sonarcloud.io' }}
    secrets:
      SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
```

Add `sonar` to application build jobs' `needs` so a failed quality gate prevents
publication and release intake. Preserve existing service workflow pins and signed
builder allowlists when only adding this independent job. After a real baseline
and successful PR analysis, add the observed check context to required checks;
never require a check which cannot yet run. Do not use `pull_request_target` to
execute candidate source or provide secrets to forks. Fork PRs need an explicit
maintainer-controlled process; missing credentials must not produce a green scan.

This first integration supplies source findings, duplication and maintainability
metrics. **It does not yet import test coverage.** Existing test success is not
coverage evidence: configure LCOV, Go coverage, Python coverage XML and JaCoCo XML
before claiming or enforcing a coverage threshold. Do not fabricate coverage or
exclude application code merely to pass the gate. Review initial findings and
Sonar's new-code definition, then fix findings through normal reviewed PRs.
