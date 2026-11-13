# Security review pack – MEA Process Hub 1.2.0

For IT Security. It states what the tool is, where data goes, which controls exist and how they were tested, and what is
**not** covered. Nothing here replaces an independent review; no penetration test has been done.

## 1. What it is
| Item | Fact |
|---|---|
| Purpose | Process documentation: library, flowcharts, review and approval workflow, exports |
| Form | One Python program (standard-library web server, SQLite database). Packaged as a Windows EXE or run from source |
| Data | Process documents, flowcharts, imported Word/draw.io sources, user accounts, comments, findings, audit log – classification *Internal* |
| Storage | One data folder on the host: `mea_hub.sqlite3`, uploaded sources, pictures, exports, backups. Not encrypted by the tool |
| Users | Local accounts (PBKDF2-HMAC-SHA256, 200,000 iterations, per-user salt) and/or Microsoft Entra ID sign-in |
| Roles | admin, controller, dept_owner, editor, reviewer, approver, viewer; editors and department owners can be limited to one department |
| Code | `mea_hub/` (about 9,000 lines), 39 automated tests in `tests/test_core.py`; third-party libraries: python-docx, lxml, reportlab, openpyxl, Pillow; draw.io web app (Apache-2.0) served locally; Microsoft Teams JavaScript SDK (MIT) served locally |

## 2. Deployment variants and network
| Variant | Listens on | Inbound | Outbound |
|---|---|---|---|
| Single PC (EXE) | `127.0.0.1:8765` only | None from the network | None |
| Internal server | `127.0.0.1:8765` behind IIS/nginx with TLS | 443 to the proxy | Only if configured: `login.microsoftonline.com` (sign-in), the mail relay, one Teams webhook address |
| SharePoint publication | No server | – | – (a read-only folder in a SharePoint library, shown by an SPFx web part) |

The tool has no TLS of its own, sends no telemetry and contacts no update service. If the local copy of the draw.io editor is missing
it falls back to `embed.diagrams.net`; the release package contains the local copy, so this does not occur there.

## 3. Controls and their evidence
| Control | Implementation | Test (in `tests/test_core.py`) |
|---|---|---|
| Authentication | Session cookie `HttpOnly`, `SameSite=Strict`, `Secure` behind HTTPS, 12-hour lifetime; sign-in throttled after 8 failures per user name in 15 minutes | `test_hosted_mode_secure_cookie_and_login_throttle` |
| Single sign-on | OpenID Connect code flow with PKCE; one-time state; ID token signature (RS256, ≥ 2048 bit), issuer, audience, tenant, validity, nonce verified; single tenant only | `test_single_sign_on_with_entra_id` |
| Authorisation | Every API route checks the role and, where relevant, the department of the process | `test_permissions_and_csrf`, `test_scoped_editor_cannot_edit_other_department` |
| CSRF | State-changing requests need the `X-CSRF-Token` header bound to the session | `test_permissions_and_csrf`, `test_embedding_in_sharepoint_is_opt_in` |
| Framing / clickjacking | `X-Frame-Options: SAMEORIGIN` and `frame-ancestors 'self'`; other sites only when named in the start settings | `test_embedding_in_sharepoint_is_opt_in`, `test_teams_tab_package_and_pages` |
| Script injection | Content-Security-Policy `script-src 'self'`; rich text cleaned on the server with an allow-list; uploaded pictures served with `Content-Security-Policy: sandbox` | `test_sanitizer_blocks_xss` |
| XML handling | draw.io and Word XML with `DOCTYPE`/`ENTITY` is rejected; size limits 80 MB per upload | `test_diagram_xml_safety`, `test_import_rejects_non_docx` |
| Host header | Requests for other host names are refused unless listed | `test_permissions_and_csrf` |
| Integrity of approved content | Published versions cannot be changed; separation of duties between author, reviewer and approver | `test_full_approval_workflow_and_immutability` |
| Traceability | Audit log of sign-ins, failed sign-ins, changes, exports, ID changes; exports carry a snapshot hash | `test_exports`, `test_process_id_change_is_controlled_and_follows_everywhere` |
| Secrets | Client secret, mail password and webhook address are read from files or the environment, never stored in the database or shown in the interface | `test_single_sign_on_with_entra_id`, `test_notifications_by_mail_and_teams` |
| Read-only publication | The reader shows file content as text and cleans formatted sections again | Browser test with a tampered file (no script runs) |

## 4. Known gaps – please assess
| Gap | Consequence | Possible treatment |
|---|---|---|
| No independent penetration test or code review | Unknown vulnerabilities | Review before production data is entered |
| Data folder and backups are not encrypted | Whoever reads the disk reads the library and the password hashes | Disk encryption on the host; restrict the folder to the service account |
| The audit log is in the same database | A host administrator can alter it | Forward host logs / regular signed backups if tamper evidence is required |
| Local accounts have no MFA and no password-complexity policy beyond 8 characters | Weak local passwords | Use Entra sign-in and `MEA_HUB_OIDC_ONLY=1`; keep one local administrator with a long password |
| Session lifetime is fixed (12 hours), no idle time-out, no forced sign-out when an Entra account is disabled | Access continues until the session ends | Shorter lifetime can be set in `config.SESSION_HOURS`; accept or request a change |
| Uploads are not scanned for malware | A malicious Word file is stored and can be downloaded again by staff | Host anti-malware on the data folder |
| No general request rate limit | Denial of service by an authenticated user is possible | Limit at the reverse proxy |
| Library versions are minimum versions, not pinned | A rebuild may pull newer versions | Pin and scan dependencies in the build |
| The EXE is unsigned unless a certificate is added to the build | SmartScreen warning; cannot be verified by publisher | Add the certificate (the build has an optional signing step) or run from source |
| Single maintainer | Fixes depend on one person | Second maintainer; escrow of the build |
| Entra sign-in, IIS/nginx set-up, SharePoint web part and Teams app were not run on the company tenant | Behaviour there is unproven | Pilot with IT |

## 5. Suggested test scope
1. Authentication and session handling (local and Entra), including the framed sign-in window.
2. Authorisation: horizontal (department scope) and vertical (role) access on `/api/*`.
3. Import parsers: hostile `.docx` and `.drawio` files.
4. Stored content rendering: rich text, flow labels, comments, the read-only reader.
5. Export generation with hostile content (Word, PDF, HTML, publication).
6. Configuration: start settings, file permissions on the data folder and secret files, reverse-proxy headers.

## 6. Where to look
`mea_hub/security.py` (passwords, sanitiser, XML checks), `mea_hub/server.py` (headers, cookies, routes), `mea_hub/service.py` (`can`, `need`,
workflow), `mea_hub/sso.py`, `mea_hub/notify.py`, `deploy/` (proxy samples), `.github/workflows/build-exe.yml` (build and start-up test).

## Additions in version 1.4.0
| Area | Control | Test |
|---|---|---|
| Suggestions from readers (`POST /api/process/<id>/change-request`) | The only write path of the reader role. Needs a session and the CSRF token; only on a version the user may read; text limited to 4,000 characters and stored as plain text; at most 25 open suggestions per user; recorded in the audit log with the user name. | `test_readers_suggest_changes_and_comments_are_pinned_to_a_step` |
| KPI actuals (`POST /api/kpis/value`) | Edit permission on the process; KPI must exist in the document; period and number validated; audit log. | `test_reading_statistics_and_kpi_actuals` |
| Reading statistics | Reader stored as keyed hash, counts only in the report, 400 days retention. | same test |
| Landscape | Readers get published maps only; click areas are computed on the server from the drawing, the page inserts no markup from documents. | `test_parallel_steps_swimlanes_and_landscape` |

Known gap: there is no rate limit per minute on suggestions beyond the cap of 25 open ones.

## Additions in version 1.5.0
| Area | Control | Test |
|---|---|---|
| Signed decisions | Chained records with SHA-256 fingerprint of the approved content; tampering with a record or with a released version is detected; optional re-authentication at the decision; failed attempts count towards the sign-in lock | `test_signed_decisions_and_register_check` |
| Restore | Drill restores into a temporary folder and verifies integrity, counts, file hashes; never touches live data | `test_restore_drill_and_many_people_at_once` |
| Availability under load | Short requests serialised, long jobs outside; 400 simulated users without errors; load test in the build | `tools/load_test.py`, `docs/LOAD_TEST.md` |
| Dependencies | Pinned (`requirements-lock.txt`), scanned by pip-audit in every build, Dependabot monthly and grouped. 2026-11-13: the first scan found 42 known vulnerabilities in Pillow 12.3.0 (image library, used for flow pictures) and stopped the release; Pillow 13.0.0 fixes them and the scan is clean. Versions 1.0.0–1.4.0 were built with whatever Pillow version was newest on the build day and were not scanned | build job *Known vulnerabilities in dependencies* |
| Browser behaviour | End-to-end journey with five roles and the Content-Security-Policy active; no script error tolerated | `tests/e2e/run.js` |
| Accessibility | WCAG 2.1 A/AA automated rules on nine pages, no finding | same |

Known gaps (unchanged or new): no penetration test yet; the signature register is tamper-evident, not tamper-proof against somebody with write
access to the database file who recomputes the chain; `synchronous = NORMAL` means a power cut can lose the last commits (never corrupt the
file); a single server process – no failover.
