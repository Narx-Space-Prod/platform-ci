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
