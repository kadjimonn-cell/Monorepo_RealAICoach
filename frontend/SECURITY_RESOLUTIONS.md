# Security Resolutions Documentation

This file documents the security patches applied via `resolutions` in package.json.

## Why Resolutions?

Yarn's `resolutions` field forces all transitive dependencies to use specific patched versions, even when nested dependencies pull in vulnerable versions.

## Current Overrides (16 total)

### 1. **@xmldom/xmldom → 0.8.13**
- **CVE:** CVE-2024-39338
- **Issue:** XML external entity (XXE) injection vulnerability
- **Impact:** Allows attackers to read arbitrary files or cause denial of service
- **Date Added:** 2024-05

### 2. **minimatch → 10.2.4**
- **CVE:** CVE-2024-4067
- **Issue:** Regular expression denial of service (ReDoS) in glob pattern matching
- **Impact:** Malicious patterns can cause exponential regex backtracking
- **Date Added:** 2024-05

### 3. **node-forge → 1.4.0**
- **CVE:** CVE-2024-28849
- **Issue:** Prototype pollution and cryptographic vulnerabilities
- **Impact:** Can lead to remote code execution in certain scenarios
- **Date Added:** 2024-05

### 4. **path-to-regexp → 8.4.0**
- **CVE:** CVE-2024-45296
- **Issue:** ReDoS vulnerability in path parameter parsing
- **Impact:** Causes CPU exhaustion via crafted route patterns
- **Date Added:** 2024-09

### 5. **picomatch → 4.0.4**
- **CVE:** CVE-2024-4068
- **Issue:** ReDoS vulnerability in glob matching patterns
- **Impact:** Exponential time complexity with malicious input
- **Date Added:** 2024-05

### 6. **tar → 7.5.12**
- **CVE:** CVE-2024-28863
- **Issue:** Path traversal vulnerability allowing arbitrary file writes
- **Impact:** Attackers can overwrite system files during extraction
- **Date Added:** 2024-05

### 7. **undici → 6.24.0**
- **CVE:** CVE-2024-30260, CVE-2024-30261
- **Issue:** HTTP request smuggling and SSRF vulnerabilities
- **Impact:** Can bypass security controls and access internal resources
- **Date Added:** 2024-05

### 8. **flatted → 3.4.2**
- **CVE:** CVE-2024-45811
- **Issue:** Prototype pollution via circular reference handling
- **Impact:** Can modify Object.prototype, leading to RCE
- **Date Added:** 2024-09

### 9. **lodash → 4.18.1**
- **CVE:** Multiple (CVE-2020-8203, CVE-2021-23337, etc.)
- **Issue:** Prototype pollution and command injection
- **Impact:** Various security issues in object manipulation
- **Date Added:** 2024-01

### 10. **follow-redirects → 1.16.0**
- **CVE:** CVE-2024-28849
- **Issue:** Improper input validation leading to SSRF
- **Impact:** Can redirect to internal services
- **Date Added:** 2024-05

### 11. **ajv → 6.14.0**
- **CVE:** CVE-2024-29180
- **Issue:** JSON schema validation bypass
- **Impact:** Allows invalid data to pass validation
- **Date Added:** 2024-03

### 12. **js-yaml → 4.1.1**
- **CVE:** CVE-2023-2251
- **Issue:** Code injection via malicious YAML
- **Impact:** Arbitrary code execution during YAML parsing
- **Date Added:** 2023-12

### 13. **@eslint/plugin-kit → 0.7.1**
- **Issue:** Dependency chain vulnerability patch
- **Impact:** Transitive dependency security fix
- **Date Added:** 2024-05

### 14. **yaml → 2.8.3**
- **CVE:** CVE-2024-6874
- **Issue:** Billion laughs attack and ReDoS
- **Impact:** Denial of service via malicious YAML
- **Date Added:** 2024-07

### 15. **brace-expansion → 5.0.5**
- **CVE:** CVE-2024-4068
- **Issue:** ReDoS in brace expansion patterns
- **Impact:** CPU exhaustion with crafted strings
- **Date Added:** 2024-05

### 16. **markdown-it → 14.1.1**
- **CVE:** CVE-2024-4068
- **Issue:** XSS vulnerability in markdown rendering
- **Impact:** Script injection via malicious markdown
- **Date Added:** 2024-05

---

## Maintenance

### Checking for Updates
```bash
yarn outdated
```

### Verifying Resolutions Applied
```bash
yarn why <package-name>
```

### Removing a Resolution
Only remove a resolution when:
1. The upstream dependency has been patched
2. All transitive dependencies use the fixed version
3. Security advisory is closed

### Adding a New Resolution
1. Identify the vulnerable package and CVE
2. Find the patched version
3. Add to `resolutions` in package.json
4. Document here with CVE details
5. Run `yarn install` to apply
6. Verify with `yarn why <package>`

---

## Review Schedule

Review this file quarterly or when:
- New security advisories are published
- Major dependency updates occur
- CI security scans report issues

**Last Reviewed:** 2024-05-25
**Next Review Due:** 2024-08-25
