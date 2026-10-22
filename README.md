# platform-ci

Owner: Platform engineering.

Shared validation, then application build/scan/publish and release orchestration. Callers pin approved workflow revisions by commit SHA and receive only the permissions they need.

Project guide: [DOC.md](https://github.com/Narx-Space-Prod/platform-infrastructure/blob/main/DOC.md).
The guide is introduced in the infrastructure foundation PR and becomes available on main after review.

## Current state

Foundation only. Application code, cloud infrastructure and end-to-end delivery are not deployed.
All changes after repository initialization go through feature branches and pull requests.
These private repositories use GitHub Free; review enforcement requires the planned Team upgrade.

## Reusable workflows

| Workflow | Checks |
| --- | --- |
| `workflows.yml` | GitHub Actions and embedded shell syntax using actionlint |
| `terraform.yml` | Formatting, locked provider initialization, validation and mocked Terraform tests |
| `helm.yml` | Lint, render dev/QA/production profiles, Kubernetes schema validation and missing-image rejection |

There are no AWS permissions, deployment credentials, auto-approval or apply operations in these workflows.
Downloads are versioned and checksum-verified; actions are pinned by commit SHA.
The Helm validator targets the current commerce chart layout rather than claiming to be a universal framework.
