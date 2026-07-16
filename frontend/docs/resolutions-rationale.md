# Frontend `resolutions` Rationale

`package.json` does not support inline comments. This file is the canonical explanation for every entry in `frontend/package.json -> resolutions`.

## Why these overrides exist
- Keep vulnerable or unstable transitive versions pinned to reviewed versions.
- Prevent dependency drift from re-introducing known security/runtime regressions.
- Maintain deterministic installs across CI and preview environments.

## Resolution map

| Resolution key | Pinned version | Rationale |
|---|---:|---|
| `**/@xmldom/xmldom` | `0.8.13` | Security hardening for XML parsing transitive usage. |
| `**/minimatch` | `10.2.4` | Avoid historical glob/ReDoS and parser edge regressions in older transitive ranges. |
| `**/node-forge` | `1.4.0` | Pin cryptography utility dependency to audited runtime version. |
| `**/path-to-regexp` | `8.4.0` | Route-matching parser hardening and consistency across tooling. |
| `**/picomatch` | `4.0.4` | Glob matcher security/perf stability across lint/build transitive graph. |
| `**/tar` | `7.5.12` | Archive extraction hardening for known historical transitive risks. |
| `**/undici` | `6.24.0` | HTTP client runtime/security consistency for transitive network consumers. |
| `**/flatted` | `3.4.2` | Keep serializer dependency at patched stable version. |
| `**/lodash` | `4.18.1` | Prevent drift to legacy lodash transitive variants with known advisories. |
| `**/follow-redirects` | `1.16.0` | Redirect handling security patch consistency. |
| `**/ajv` | `6.14.0` | JSON schema validator transitive compatibility and patched baseline lock. |
| `**/js-yaml` | `4.1.1` | YAML parser security hardening for downstream tools. |
| `**/@eslint/plugin-kit` | `0.7.1` | ESLint plugin ecosystem compatibility/security consistency in CI. |
| `**/yaml` | `2.8.3` | YAML parser runtime and security stability for toolchain dependencies. |
| `**/brace-expansion` | `5.0.5` | Mitigate older brace expansion parser vulnerability patterns. |
| `**/markdown-it` | `14.1.1` | Markdown parser security/runtime patch baseline. |

## Update policy
- If a resolution is changed, update this file in the same PR/commit.
- Include CVE/advisory or regression ticket reference when available.