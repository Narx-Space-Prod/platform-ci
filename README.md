# platform-ci

Owner: Platform engineering.

Shared validation, then application build/scan/publish and release orchestration. Callers pin approved workflow revisions by commit SHA and receive only the permissions they need.

Project guide: [DOC.md](https://github.com/Narx-Space-Prod/platform-infrastructure/blob/main/DOC.md).

## Current state

Shared validators are merged. The application migration adds `service.yml` for a
cached Docker runtime build that includes service tests and checks the non-root image user.
ECR publishing, image signing/security scanning and release orchestration remain separate work.
All changes after repository initialization go through feature branches and pull requests.
These private repositories use GitHub Free; review enforcement requires the planned Team upgrade.

## Reusable workflows

| Workflow | Checks |
| --- | --- |
| `workflows.yml` | GitHub Actions and embedded shell syntax using actionlint |
| `terraform.yml` | Formatting, locked provider initialization, validation and mocked Terraform tests |
| `helm.yml` | Lint, render dev/QA/production profiles, Kubernetes schema validation and missing-image rejection |
| `service.yml` | Build runtime images through test stages, reuse BuildKit caches and check non-root defaults |

There are no AWS permissions, deployment credentials, auto-approval or apply operations in these workflows.
Downloads are versioned and checksum-verified; actions are pinned by commit SHA.
The Helm validator targets the current commerce chart layout rather than claiming to be a universal framework.
Each application's runtime Docker target depends on its tests. Building the runtime
therefore verifies source and packages it in one build; CI does not rebuild a separate
test image or rerun a duplicate test wrapper. Orders and cart use separate jobs/images.
