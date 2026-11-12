# Roadmap – making MEA Process Hub a professional, trusted process platform

Status of this document: proposal for the tool owner, 2026-11-12. Figures marked *measured* come from the tool itself
(fresh installation of the current version). Effort figures are estimates.

## 1. The uncomfortable part first
1. **The limiting factor is content, not software.** *Measured:* 100 processes, **0 published**, **0 with a named owner**,
   308 open findings (18 high), 42 provisional IDs, accountable role known for 4 of 1,068 RACI rows, transaction code written
   in 5 of 30 SAP steps. A handbook in which nothing is approved is a draft archive. More features do not change that.
2. **The tool is not yet an approved company system.** It has its own passwords (no single sign-on, no MFA), has had no
   security review, the EXE is unsigned, and the source repository with company documents is public.
3. **It is custom software with one maintainer.** No vendor, no support contract. Whoever sponsors it must also name who
   maintains it, or keep the exit route open (section 6).

"100x better" is therefore defined here as outcomes, not as a feature count:

| Outcome | Today (*measured*) | Target | By |
|---|---|---|---|
| Processes published (approved) | 0 % | 80 % of the core processes | day 90 |
| Processes with a named owner | 0 % | 100 % | day 30 |
| Open high-severity findings | 18 | 0 | day 45 |
| RACI rows with an accountable role | 0.4 % | 95 % of published processes | day 90 |
| People who can reach the tool with their company login | 0 | all process owners and readers in MEA | day 60 |
| Time to find a process and its current flow | not measured | under 30 seconds (test with 5 users) | day 60 |
| Processes past their review date | not tracked | 0 older than 30 days | from day 120 |

## 2. What you're assuming
- That a better tool will make the departments maintain their processes. Ownership and a review routine do that; the tool only makes it cheap.
- That IT will accept a self-built server application. Unverified until IT Security has looked at it.
- That the flows on the master canvas are the current, agreed versions. The canvas itself holds two versions of several flows.
- That a regional tool is wanted. If the group runs or plans a process platform (for example a BPM suite linked to SAP), a regional island may be asked to migrate.

## 3. What you're missing (information that would change the plan)
| Question | If the answer is … | Then |
|---|---|---|
| Does the group already license a process platform? | Yes | Position this tool as the regional clean-up workspace and build the BPMN export first (phase 3 item 1) |
| Will IT host and support a Python application? | No | Stay with the single-user EXE for authoring and distribute approved PDFs through SharePoint; drop phases 2b–2c |
| Who is the document controller, with how many hours a week? | Nobody | Do not start phase 1; nothing gets published without this role |
| How many concurrent editors are expected? | More than about 50 | Plan the database change (phase 4) early |
| Is Arabic or French content required? | Yes | Add multilingual content to phase 3 |

## 4. The plan
### Phase 0 – Safe ground (week 1, no development)
| Action | Owner | Done when |
|---|---|---|
| Make the GitHub repository private; note what was publicly readable until then and inform the information owner | You | Repository private |
| Name sponsor, document controller, and one owner per department | Sponsor | Names recorded in *Governance ▸ Ownership* |
| Ask IT: hosting, single sign-on, security review, existing process platform | You | Written answer |

### Phase 1 – Make the content true (weeks 1–8, no development; the tool already supports it)
| Action | Owner | Tool function | Done when |
|---|---|---|---|
| Assign an owner and reviewer to all 100 processes | Department heads | Governance ▸ Ownership (Excel round trip) | 100 % |
| Decide duplicates and versions: 7 Logistics twins, 2 project and 2 production E2E versions, scrap-disposal variants, 42 provisional IDs | Owners + controller | Findings register, Change ID | 0 open duplicate / conflict findings |
| Close the 18 high findings | Owners | Findings register | 0 |
| Confirm draft RACI: fill A (and C where it exists) | Owners | RACI tab; re-derive after owner entry | Draft mark gone |
| Complete the 30 SAP work instructions; name transactions in the flows | Key users | Edit draft; flow step text | Sent for review |
| Publish a first wave of 20 core processes through review and approval | Controller + approvers | Workflow | 20 published |
| Split the 5 very wide maps with export areas or accept them as overview-only | Owners | Flow Studio export areas | Readable in print |

### Phase 2 – Make it a company system (weeks 2–10)
**Change of 2026-11-12:** readers no longer need the server or single sign-on. Version 1.0.2 publishes a read-only copy of the library into
SharePoint (`docs/SHAREPOINT_PUBLISHING.md`); readers use their Microsoft 365 sign-in there. Items 2a–2d now matter only when more than a
handful of people must *edit* in one shared installation. Do the SharePoint publication first (one package upload by the SharePoint administrator).

| # | Item | Why | Effort (estimate) | Confidence |
|---|---|---|---|---|
| 2a | Internal server behind HTTPS, service account, backup and one restore test | One shared library instead of copies | 2–3 days IT, files are in `deploy/` | High |
| 2b | **Single sign-on with Microsoft Entra ID (OpenID Connect), groups mapped to roles** | Removes separate passwords, gives MFA and automatic leaver handling; precondition for IT approval | 8–12 days development + IT app registration | Medium |
| 2c | IT Security review / penetration test, fix findings | No company data in an unreviewed system | 5–10 days fixing, depends on findings | Low |
| 2d | Code-signed EXE, or retire the EXE for end users once the server runs | No SmartScreen warnings, no shadow copies of the library | 2 days + certificate | Medium |
| 2e | Teams tab and SharePoint page in two pilot departments | Put the library where people already work | 1–2 days with the admins | Medium (tenant untested) |
| 2f | E-mail or Teams notifications: tasks, review due, approval waiting | Without reminders the workflow stalls | 5–7 days (needs a mail relay or Graph permission) | Medium |

### Phase 3 – Depth that users notice (weeks 8–20, order by demand)
| # | Item | Benefit | Effort (estimate) |
|---|---|---|---|
| 1 | **BPMN 2.0 export (and import)** of flows | Keeps the content portable to any process platform; exit route | 8–10 days |
| 2 | Version comparison: text and flow differences between two revisions | Reviewers see what changed; faster approvals | 6–8 days |
| 3 | Periodic review cycle: due dates, "reviewed without change", overdue dashboard | Content stays current after the first wave | 4–5 days |
| 4 | Change requests from readers ("this step is wrong") routed to the owner | Readers become a source of corrections | 4–5 days |
| 5 | Swimlane layout and parallel paths in the flow builder | New flows match how departments draw cross-functional processes | 8–10 days |
| 6 | Process landscape navigation (level 0 → 1 → 2 drill-down from the value stream) | People find processes by where they sit in the business | 5–6 days |
| 7 | KPI register with targets, owner and actuals entered or imported from Excel | KPIs become reviewable instead of text | 6–8 days |
| 8 | Reading statistics (which processes are opened, which never) | Shows adoption; prunes dead documents | 2–3 days |
| 9 | Comments pinned to a flow shape | Precise review feedback | 3–4 days |
| 10 | Read view for phones and tablets | Warehouse and site use | 4–5 days |

### Phase 4 – Scale and assurance (after adoption is proven)
PostgreSQL instead of SQLite and a second node (only above about 50 concurrent editors), electronic signature of approvals if auditors
require it, automated browser tests and load test in the build, accessibility check, dependency scanning, published release notes,
restore drill twice a year.

## 5. Analysis – why this order
- Publishing 20 real processes creates more value than any feature and exposes what is actually missing. Phase 3 is therefore ordered by what phase 1 teaches.
- Single sign-on is the one development item that unlocks IT approval, Teams and SharePoint use at scale, and leaver handling. It comes before all comfort features.
- BPMN export is first in phase 3 because it protects everything invested in content if the group later standardises on another platform.

## 6. Strongest counterargument
A commercial process platform delivers single sign-on, vendor support, audit certification and SAP integration on day one; a regional
custom tool competes with that using one maintainer. If the group has such a platform, the rational use of this tool is narrower:
consolidate and clean the MEA content quickly (it has already turned the supplied Word handbooks and the master canvas into 100 structured,
linked, editable records), then hand the approved content over through BPMN, Word and Excel exports. That is still a good outcome –
and it is why portability ranks above new features.

## 7. Red team
| Question | Answer |
|---|---|
| Why might this fail? | No owner time: findings stay open and nothing is published. IT refuses hosting or sign-in. The maintainer leaves. |
| What would others do? | Buy a suite and migrate; or keep Word and SharePoint and accept inconsistency. |
| Most likely unintended consequence | Two "truths": the tool and the old Word handbooks circulate in parallel. |
| Mitigation | Retire each Word handbook chapter on the day its processes are published; controlled-copy note on every export (already there); monthly figure "published / owned / overdue" to the sponsor; documented build and a second person able to release. |

## 8. Recommendation
1. Week 1: phase 0. Do not add features until owners and the document controller are named.
2. Weeks 1–8: phase 1 in parallel with 2a and the IT questions.
3. Commission 2b (single sign-on) as soon as IT agrees to host; it is the gate for everything user-facing.
4. Decide at day 60 with the measured outcomes whether to continue into phase 3 or to prepare a hand-over to a group platform.

**Risk level:** Medium – mostly organisational (owner capacity, IT acceptance), not technical.
**Confidence:** High for the order of the phases; Medium for the effort figures; Low for anything that depends on the tenant and on IT policy, which could not be examined from here.
