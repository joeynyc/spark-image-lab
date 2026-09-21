# Releases, Tags, and Public Launch

Repository visibility changes require explicit owner approval. No automation
publishes containers, model weights, or releases.

## Versioning

Use semantic versions in `VERSION` and matching annotated Git tags prefixed with
`v`. The initial private milestone is `v0.1.0-alpha.1`. Subsequent alpha
milestones increment `alpha.2`, `alpha.3`, and so on. The first public security
milestone is `v0.1.0-alpha.2`. Tag only a reviewed commit with passing checks,
and do not move or overwrite an existing tag.

Before tagging, update `CHANGELOG.md`, run CPU/container tests, perform the GPU
smoke test, and record the tested hardware and software revisions. GitHub topics
describe the project; they are not version tags. Suggested topics: `dgx-spark`,
`nvidia`, `gb10`, `qwen-image`, `gradio`, `local-ai`, `image-generation`,
`image-editing`, `python`.

## Before a Stable Release

- [x] Owner explicitly approved changing repository visibility for the public alpha.
- [ ] Fresh-clone setup verified end to end by a second tester.
- [ ] Verify pinned model terms, third-party notices, and intended use with the owner.
- [x] Review Git history for secrets, personal images, local addresses, and private paths.
- [ ] Capture approved screenshots with non-sensitive prompts/images.
- [ ] CPU CI, container checks, generation, reference edit, and restart-history tests pass.
- [ ] Smoke-test a bad upload and memory/disk failure handling.
- [x] Review dependency/security advisories; enable private vulnerability reporting.
- [ ] Test documented update and rollback on a separate checkout.
- [ ] Confirm issue templates, contribution guide, topics, description, and license.
- [ ] Write release notes with known limits and measured, scoped performance claims.

Do not claim universal hardware coverage, production hardening, commercial model
rights, or a fully offline installation. Current inference is local after setup.
