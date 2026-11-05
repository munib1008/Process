# Source Reconciliation Report

Generated 2026-11-05T06:48:38Z by MEA Process Hub. Regenerate with `run.py --reconcile-report <file>`.

## 1. Source audit register

| File | Cover title | Version | Declared (file name) | Actual content | Match | Confidence | Sections | Flowcharts | Tables | Processes created | Duplicate mappings |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Logistics, Warehouse | 2.1 | Logistics & Warehouse | Logistics & Warehouse | ✔ | Medium | 17 | 17 | 1 | 17 | 0 |
| MM_Cleaning_Optimization_Control_Project_Charter_Reformatted.docx | MM Cleaning & Optimization Control Project Charter | ? | Master Data Management | Master Data Management | ✔ | Medium | 8 | 3 | 5 | 1 | 0 |
| S2S_Checlist_Sales_Support_and_Material_Planning.docx | Sales Support & Material Planning Checklist Order release an | ? | Sales & Sales Support | Sales & Sales Support | ✔ | Medium | 4 | 0 | 3 | 2 | 0 |
| dormakaba_SC_Enterprise_Architecture_Level0_Level1.drawio | Level 0 – Enterprise Process Architecture | ? | Supply Chain E2E (Enterprise) | Supply Chain E2E (Enterprise) | ✔ | Medium | 0 | 0 | 0 | 2 | 0 |
| WL-M-VS-01_Virtual_Stock_Request_Flow.drawio | Virtual Stock Request (Goods Receipt, Outbound & Invoicing) | ? | Logistics & Warehouse | Logistics & Warehouse | ✔ | Medium | 0 | 0 | 0 | 1 | 0 |
| PMM-M-PR-01_Flow_Material_Master.drawio | SAP Pricing & Master Data Maintenance | ? | Product Marketing & Management | Product Marketing & Management | ✔ | Medium | 0 | 0 | 0 | 1 | 0 |
| S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Supply Chain Handbook | 1.0 | Supply Chain E2E (Enterprise) | Project Management | ✘ MISMATCH | Low | 11 | 7 | 1 | 9 | 0 |
| S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Project Management | 1.0 | Finance & Accounts | Project Management | ✘ MISMATCH | Low | 9 | 8 | 1 | 3 | 6 |
| S2S_Process_Documentation_-_Approval_processes.docx | Sales Approval | ? | Approval & Governance | Logistics & Warehouse | ✘ MISMATCH | Low | 10 | 9 | 1 | 9 | 1 |
| CS_and_MRP_Checklist.docx |  | ? | None | Sales & Sales Support | n/a | Low | 2 | 0 | 2 | 0 | 2 |

## 2. Findings requiring a decision

### High severity (22)

| Kind | Title | Detail | Status |
|---|---|---|---|
| conflict | Chart ID WL-M-SP-01 is used for different processes – provisional ID WL-M-SP-01.2 assigned | “Shipping Documentation Process – KSA” carries chart ID WL-M-SP-01, already used by WL-M-SP-01 – Shipping Documentation Process – UAE & EXP. Each process must have a unique ID. The system kept both processes and minted WL-M-SP-01.2; Document Controller must issue a permanent ID. Possible duplicate of WL-M-SP-01 – Shipping Documentation Process – UAE & EXP (title similarity 88%, text similarity 95%); kept separate because region/scope may differ – owner to confirm. | open |
| conflict | Chart ID WL-S-SC-01 is used for different processes – provisional ID WL-S-SC-01.2 assigned | “Scrap Disposal Process” carries chart ID WL-S-SC-01, already used by WL-S-SC-01 – Stock Correction Process. Each process must have a unique ID. The system kept both processes and minted WL-S-SC-01.2; Document Controller must issue a permanent ID. | open |
| conflict | Chart ID WL-M-SP-01 reused 2 times in d3e4bc74-S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Used for: Shipping Documentation Process – UAE & EXP; Shipping Documentation Process – KSA. Process IDs must be unique – see provisional IDs assigned in the Process Library. | open |
| conflict | Chart ID WL-S-SC-01 reused 2 times in d3e4bc74-S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Used for: Stock Correction Process; Scrap Disposal Process. Process IDs must be unique – see provisional IDs assigned in the Process Library. | open |
| conflict | Chart ID PM-M-IN-01 is used for different processes – provisional ID PM-M-IN-01.2 assigned | “Project Planning Process” carries chart ID PM-M-IN-01, already used by PM-M-IN-01 – Project Initiation Process. Each process must have a unique ID. The system kept both processes and minted PM-M-IN-01.2; Document Controller must issue a permanent ID. Possible duplicate of PM-M-IN-01 – Project Initiation Process (title similarity 72%, text similarity 96%); kept separate because region/scope may differ – owner to confirm. | open |
| conflict | Chart ID PM-M-IN-01 is used for different processes – provisional ID PM-M-IN-01.3 assigned | “Project Execution Process” carries chart ID PM-M-IN-01, already used by PM-M-IN-01 – Project Initiation Process. Each process must have a unique ID. The system kept both processes and minted PM-M-IN-01.3; Document Controller must issue a permanent ID. Possible duplicate of PM-M-IN-01 – Project Initiation Process (title similarity 78%, text similarity 97%); kept separate because region/scope may differ – owner to confirm. | open |
| conflict | Chart ID PM-M-IN-01 is used for different processes – provisional ID PM-M-IN-01.4 assigned | “Project Monitoring and Control Process” carries chart ID PM-M-IN-01, already used by PM-M-IN-01 – Project Initiation Process. Each process must have a unique ID. The system kept both processes and minted PM-M-IN-01.4; Document Controller must issue a permanent ID. Possible duplicate of PM-M-IN-01 – Project Initiation Process (title similarity 72%, text similarity 95%); kept separate because region/scope may differ – owner to confirm. | open |
| conflict | Chart ID PM-M-IN-01 is used for different processes – provisional ID PM-M-IN-01.5 assigned | “Project Closing Process” carries chart ID PM-M-IN-01, already used by PM-M-IN-01 – Project Initiation Process. Each process must have a unique ID. The system kept both processes and minted PM-M-IN-01.5; Document Controller must issue a permanent ID. Possible duplicate of PM-M-IN-01.2 – Project Planning Process (title similarity 85%, text similarity 98%); kept separate because region/scope may differ – owner to confirm. | open |
| conflict | Source title does not match content: 09cbf1fc-S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | File name suggests “Supply Chain E2E (Enterprise)”, but the extracted processes are mostly “Project Management”. Cover title reads: “Supply Chain Process Handbook”. The process content was classified by what it actually describes, not by file name. Confirm whether the correct file was supplied. | open |
| conflict | Chart ID PM-M-IN-01 reused 5 times in 09cbf1fc-S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Used for: Project Initiation Process; Project Planning Process; Project Execution Process; Project Monitoring and Control Process; Project Closing Process. Process IDs must be unique – see provisional IDs assigned in the Process Library. | open |
| conflict | Source title does not match content: 20434659-S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | File name suggests “Finance & Accounts”, but the extracted processes are mostly “Project Management”. Cover title reads: “Project Management Process”. The process content was classified by what it actually describes, not by file name. Confirm whether the correct file was supplied. | open |
| conflict | Chart ID PM-M-IN-01 reused 5 times in 20434659-S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Used for: Project Initiation Process; Project Planning Process; Project Execution Process; Project Monitoring and Control Process; Project Closing Process. Process IDs must be unique – see provisional IDs assigned in the Process Library. | open |
| conflict | Chart ID WL-S-QC-01 is used for different processes – provisional ID WL-S-QC-01.2 assigned | “Material Quality Assurance & Control Check” carries chart ID WL-S-QC-01, already used by WL-S-QC-01 – Quality Assurance & Control Check Process – UAE & EXP. Each process must have a unique ID. The system kept both processes and minted WL-S-QC-01.2; Document Controller must issue a permanent ID. Possible duplicate of WL-S-QC-01 – Quality Assurance & Control Check Process – UAE & EXP (title similarity 70%, text similarity 96%); kept separate because region/scope may differ – owner to confirm. | open |
| conflict | Chart ID WL-M-SP-01 is used for different processes – provisional ID WL-M-SP-01.3 assigned | “Shipping Documentation” carries chart ID WL-M-SP-01, already used by WL-M-SP-01 – Shipping Documentation Process – UAE & EXP. Each process must have a unique ID. The system kept both processes and minted WL-M-SP-01.3; Document Controller must issue a permanent ID. Possible duplicate of WL-M-SP-01.2 – Shipping Documentation Process – KSA (title similarity 77%, text similarity 95%); kept separate because region/scope may differ – owner to confirm. | open |
| conflict | Chart ID WL-M-OB-01 is used for different processes – provisional ID WL-M-OB-01.2 assigned | “Material Dispatch” carries chart ID WL-M-OB-01, already used by WL-M-OB-01 – Material Dispatch Process – UAE & EXP. Each process must have a unique ID. The system kept both processes and minted WL-M-OB-01.2; Document Controller must issue a permanent ID. Possible duplicate of WL-M-OB-01 – Material Dispatch Process – UAE & EXP (title similarity 65%, text similarity 91%); kept separate because region/scope may differ – owner to confirm. | open |
| conflict | Chart ID WL-M-IA-01 is used for different processes – provisional ID WL-M-IA-01.2 assigned | “Inventory Audit” carries chart ID WL-M-IA-01, already used by WL-M-IA-01 – Inventory Audit Process – UAE & EXP. Each process must have a unique ID. The system kept both processes and minted WL-M-IA-01.2; Document Controller must issue a permanent ID. Possible duplicate of WL-M-IA-01 – Inventory Audit Process – UAE & EXP (title similarity 62%, text similarity 90%); kept separate because region/scope may differ – owner to confirm. | open |
| conflict | Chart ID WL-S-SC-01 is used for different processes – provisional ID WL-S-SC-01.3 assigned | “Stock Correction” carries chart ID WL-S-SC-01, already used by WL-S-SC-01 – Stock Correction Process. Each process must have a unique ID. The system kept both processes and minted WL-S-SC-01.3; Document Controller must issue a permanent ID. Possible duplicate of WL-S-SC-01 – Stock Correction Process (title similarity 80%, text similarity 92%); kept separate because region/scope may differ – owner to confirm. | open |
| conflict | Source title does not match content: bfb31fb3-S2S_Process_Documentation_-_Approval_processes.docx | File name suggests “Approval & Governance”, but the extracted processes are mostly “Logistics & Warehouse”. Cover title reads: “Sales Approval PROCESSES”. The process content was classified by what it actually describes, not by file name. Confirm whether the correct file was supplied. | open |
| gap | Source document not supplied: Purchase and Planning | The brief lists 12 source documents; “Purchase and Planning” has not been imported. Processes and chapters for this area are Documentation Required until it is uploaded. | open |
| gap | Source document not supplied: Production | The brief lists 12 source documents; “Production” has not been imported. Processes and chapters for this area are Documentation Required until it is uploaded. | open |
| gap | Source document not supplied: Service and Installation | The brief lists 12 source documents; “Service and Installation” has not been imported. Processes and chapters for this area are Documentation Required until it is uploaded. | open |
| gap | Source document not supplied: Product Marketing & Management | The brief lists 12 source documents; “Product Marketing & Management” has not been imported. Processes and chapters for this area are Documentation Required until it is uploaded. | open |

### Medium severity (22)

| Kind | Title | Detail | Status |
|---|---|---|---|
| conflict | ID prefix does not match department: PP-M-PQ-01 “Material Pick & Pack Process – UAE & EXP” | Prefix PP denotes Planning / Procurement; the process was placed in Logistics & Warehouse based on its title. Owner decision required on ID scheme and department. | open |
| conflict | ID prefix does not match department: PP-M-PQ-02 “Material Pick & Pack Process – KSA” | Prefix PP denotes Planning / Procurement; the process was placed in Logistics & Warehouse based on its title. Owner decision required on ID scheme and department. | open |
| uncertain | 15 flowcharts imported as reference images (d3e4bc74-S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx) | The source flowcharts are embedded pictures, not draw.io/Visio objects. Each is wrapped in an editable draw.io page with the picture as a locked reference layer. Shapes/connectors were not auto-reconstructed (risk of silent errors); each is flagged Requires Functional Validation. | open |
| gap | Step-by-step activities, RACI, SAP transactions absent in d3e4bc74-S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | 14 processes are documented only as a flowchart plus a short description. Activity tables, RACI, SAP transaction references, SLAs and risks must be authored by process owners (Documentation Required). Nothing was invented. | open |
| uncertain | Activities extracted automatically from native diagram (5c4ef6a8-dormakaba_SC_Enterprise_Architecture_Level0_Level1.drawio) | 2 diagram page(s) were parsed: step order follows the connectors, roles follow the drawn swimlane, SAP transaction codes were read from shape text. Verify against the process owner before approval. RACI, KPIs, SLA owners and decision criteria are not in the diagram and remain Documentation Required. | open |
| uncertain | Proposed (not approved) content inside dfcb6467-WL-M-VS-01_Virtual_Stock_Request_Flow.drawio | The diagram contains a lane marked as a recommended addition that is not part of the original process (Exception Path – RECOMMENDED ADDITION (not in original process)). It was imported but labelled [PROPOSED] and must not be treated as approved procedure. | open |
| uncertain | Activities extracted automatically from native diagram (dfcb6467-WL-M-VS-01_Virtual_Stock_Request_Flow.drawio) | 1 diagram page(s) were parsed: step order follows the connectors, roles follow the drawn swimlane, SAP transaction codes were read from shape text. Verify against the process owner before approval. RACI, KPIs, SLA owners and decision criteria are not in the diagram and remain Documentation Required. | open |
| conflict | Inconsistent process ID inside f59d3f1e-PMM-M-PR-01_Flow_Material_Master.drawio | Page/file name and diagram title carry different IDs: PMM-M-PR-01, PMM-MM-PR-01. Chart ID PMM-M-PR-01 was used (from the page/file name). Owner must confirm the correct ID. | open |
| uncertain | Activities extracted automatically from native diagram (f59d3f1e-PMM-M-PR-01_Flow_Material_Master.drawio) | 1 diagram page(s) were parsed: step order follows the connectors, roles follow the drawn swimlane, SAP transaction codes were read from shape text. Verify against the process owner before approval. RACI, KPIs, SLA owners and decision criteria are not in the diagram and remain Documentation Required. | open |
| gap | No flowchart image found for FI-M-PC-01 – Production Costing Process | Source section “Production Costing Process” in 09cbf1fc-S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx states chart ID FI-M-PC-01 but contains no flowchart image. Flowchart must be drawn (Flow Studio) – Documentation Required. | open |
| conflict | ID prefix does not match department: PP-M-SC-01 “Subcontracting Process” | Prefix PP denotes Planning / Procurement; the process was placed in Project Management based on its title. Owner decision required on ID scheme and department. | open |
| uncertain | 6 flowcharts imported as reference images (09cbf1fc-S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx) | The source flowcharts are embedded pictures, not draw.io/Visio objects. Each is wrapped in an editable draw.io page with the picture as a locked reference layer. Shapes/connectors were not auto-reconstructed (risk of silent errors); each is flagged Requires Functional Validation. | open |
| gap | Step-by-step activities, RACI, SAP transactions absent in 09cbf1fc-S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | 7 processes are documented only as a flowchart plus a short description. Activity tables, RACI, SAP transaction references, SLAs and risks must be authored by process owners (Documentation Required). Nothing was invented. | open |
| conflict | ID prefix does not match department: PP-M-PP-01 “Project Management General Overview” | Prefix PP denotes Planning / Procurement; the process was placed in Project Management based on its title. Owner decision required on ID scheme and department. | open |
| conflict | ID prefix does not match department: PP-M-SC-01 “Subcontracting Process” | Prefix PP denotes Planning / Procurement; the process was placed in Project Management based on its title. Owner decision required on ID scheme and department. | open |
| uncertain | 7 flowcharts imported as reference images (20434659-S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx) | The source flowcharts are embedded pictures, not draw.io/Visio objects. Each is wrapped in an editable draw.io page with the picture as a locked reference layer. Shapes/connectors were not auto-reconstructed (risk of silent errors); each is flagged Requires Functional Validation. | open |
| gap | Step-by-step activities, RACI, SAP transactions absent in 20434659-S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | 6 processes are documented only as a flowchart plus a short description. Activity tables, RACI, SAP transaction references, SLAs and risks must be authored by process owners (Documentation Required). Nothing was invented. | open |
| conflict | ID prefix does not match department: SA-M-PM-01 “Project Management Process” | Prefix SA denotes Sales Approval; the process was placed in Project Management based on its title. Owner decision required on ID scheme and department. | open |
| uncertain | 8 flowcharts imported as reference images (bfb31fb3-S2S_Process_Documentation_-_Approval_processes.docx) | The source flowcharts are embedded pictures, not draw.io/Visio objects. Each is wrapped in an editable draw.io page with the picture as a locked reference layer. Shapes/connectors were not auto-reconstructed (risk of silent errors); each is flagged Requires Functional Validation. | open |
| gap | Step-by-step activities, RACI, SAP transactions absent in bfb31fb3-S2S_Process_Documentation_-_Approval_processes.docx | 8 processes are documented only as a flowchart plus a short description. Activity tables, RACI, SAP transaction references, SLAs and risks must be authored by process owners (Documentation Required). Nothing was invented. | open |
| duplicate | Same process appears in more than one source: SAL-FRM-01 – Sales Order Release Checklist (Sales Support / Customer Service) | Chart ID (none) / “Customer Service Checklist” also found in 31e10ee2-CS_and_MRP_Checklist.docx. Text similarity 64% versus the primary definition. Content differs – owner must decide which text is correct (not auto-merged). | open |
| duplicate | Same process appears in more than one source: MPL-FRM-01 – PR Validation Checklist (Material Planning / MRP) | Chart ID (none) / “MRP Checklist” also found in 31e10ee2-CS_and_MRP_Checklist.docx. Text similarity 82% versus the primary definition. Content differs – owner must decide which text is correct (not auto-merged). | open |

### Low severity (34)

| Kind | Title | Detail | Status |
|---|---|---|---|
| gap | Provisional ID LOG-REF-ESC-01 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| gap | Provisional ID LOG-REF-INTRO-01 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| gap | Provisional ID MDM-F-MM-01 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| gap | Provisional ID SAL-FRM-01 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| gap | Provisional ID MPL-FRM-01 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| gap | Provisional ID E2E-REF-L0-01 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| uncertain | Shape/lane placement inconsistency in f59d3f1e-PMM-M-PR-01_Flow_Material_Master.drawio | “Validate Request” is structurally inside lane “Procurement (Buyer)” but drawn in “PMM (Pricing Analyst)” (drawn position used) | open |
| gap | No 'Responsible' list for FI-M-PC-01 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for PM-M-IN-01 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for PM-M-IN-01.2 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for PM-M-IN-01.3 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for PP-M-SC-01 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for PM-M-IN-01.4 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for PM-M-IN-01.5 | Source section does not name responsible departments/roles. | open |
| gap | Provisional ID LOG-REF-ESC-02 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| gap | Provisional ID E2E-REF-INTRO-01 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| duplicate | Same process appears in more than one source: PM-M-IN-01 – Project Initiation Process | Chart ID PM-M-IN-01 / “Project Initiation Process” also found in 20434659-S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx. Text similarity 100% versus the primary definition. Content is essentially identical; keep one controlled definition. | open |
| duplicate | Same process appears in more than one source: PM-M-IN-01.2 – Project Planning Process | Chart ID PM-M-IN-01 / “Project Planning Process” also found in 20434659-S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx. Text similarity 100% versus the primary definition. Content is essentially identical; keep one controlled definition. | open |
| duplicate | Same process appears in more than one source: PM-M-IN-01.3 – Project Execution Process | Chart ID PM-M-IN-01 / “Project Execution Process” also found in 20434659-S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx. Text similarity 100% versus the primary definition. Content is essentially identical; keep one controlled definition. | open |
| duplicate | Same process appears in more than one source: PP-M-SC-01 – Subcontracting Process | Chart ID PP-M-SC-01 / “Subcontracting Process” also found in 20434659-S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx. Text similarity 100% versus the primary definition. Content is essentially identical; keep one controlled definition. | open |
| duplicate | Same process appears in more than one source: PM-M-IN-01.4 – Project Monitoring and Control Process | Chart ID PM-M-IN-01 / “Project Monitoring and Control Process” also found in 20434659-S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx. Text similarity 100% versus the primary definition. Content is essentially identical; keep one controlled definition. | open |
| duplicate | Same process appears in more than one source: PM-M-IN-01.5 – Project Closing Process | Chart ID PM-M-IN-01 / “Project Closing Process” also found in 20434659-S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx. Text similarity 100% versus the primary definition. Content is essentially identical; keep one controlled definition. | open |
| gap | Provisional ID LOG-REF-ESC-03 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| gap | Provisional ID PRJ-REF-INTRO-01 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| gap | No 'Responsible' list for SA-M-PM-01 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for WL-S-QC-01.2 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for WL-S-FH-02 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for WL-M-PP-01 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for WL-M-SP-01.3 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for WL-M-OB-01.2 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for WL-M-IA-01.2 | Source section does not name responsible departments/roles. | open |
| gap | No 'Responsible' list for WL-S-SC-01.3 | Source section does not name responsible departments/roles. | open |
| gap | Provisional ID LOG-REF-ESC-04 | No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller. | open |
| duplicate | Same process appears in more than one source: LOG-REF-INTRO-01 – Introduction, Scope and Benefits | Chart ID (none) / “Introduction” also found in bfb31fb3-S2S_Process_Documentation_-_Approval_processes.docx. Text similarity 100% versus the primary definition. Content is essentially identical; keep one controlled definition. | open |

## 3. Source → destination map (every extracted section is accounted for)

| Source file | Source section | Chart ID in source | → Process ID | Role |
|---|---|---|---|---|
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Logistics and Warehouse General Overview | WL-M-WL-01 | WL-M-WL-01 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Material Inbound Process | WL-M-IB-01 | WL-M-IB-01 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Fragile Handling Process | WL-S-FH-01 | WL-S-FH-01 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Quality Assurance & Control Check Process – UAE & EXP | WL-S-QC-01 | WL-S-QC-01 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Quality Assurance & Control Check Process – KSA | WL-S-QC-02 | WL-S-QC-02 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Material Pick & Pack Process – UAE & EXP | PP-M-PQ-01 | PP-M-PQ-01 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Material Pick & Pack Process – KSA | PP-M-PQ-02 | PP-M-PQ-02 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Shipping Documentation Process – UAE & EXP | WL-M-SP-01 | WL-M-SP-01 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Shipping Documentation Process – KSA | WL-M-SP-01 | WL-M-SP-01.2 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Material Dispatch Process – UAE & EXP | WL-M-OB-01 | WL-M-OB-01 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Material Dispatch Process – KSA | WL-M-OB-02 | WL-M-OB-02 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Inventory Audit Process – UAE & EXP | WL-M-IA-01 | WL-M-IA-01 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Inventory Audit Process – KSA | WL-M-IA-02 | WL-M-IA-02 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Stock Correction Process | WL-S-SC-01 | WL-S-SC-01 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Scrap Disposal Process | WL-S-SC-01 | WL-S-SC-01.2 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Escalation Matrix and KPIs |  | LOG-REF-ESC-01 | primary |
| S2S_Process_Documentation_-_Logistics_and_Ware_house_v2.1.docx | Introduction |  | LOG-REF-INTRO-01 | primary |
| MM_Cleaning_Optimization_Control_Project_Charter_Reformatted.docx | (whole document) |  | MDM-F-MM-01 | primary |
| S2S_Checlist_Sales_Support_and_Material_Planning.docx | Sales Support Team |  | SAL-FRM-01 | primary |
| S2S_Checlist_Sales_Support_and_Material_Planning.docx | Material Planning Team |  | MPL-FRM-01 | primary |
| dormakaba_SC_Enterprise_Architecture_Level0_Level1.drawio | Level 0 - Enterprise Architecture |  | E2E-REF-L0-01 | primary |
| dormakaba_SC_Enterprise_Architecture_Level0_Level1.drawio | Level 1 - Supply Chain Value Stream | SC-M-VS-01 | SC-M-VS-01 | primary |
| WL-M-VS-01_Virtual_Stock_Request_Flow.drawio | WL-M-VS-01 | WL-M-VS-01 | WL-M-VS-01 | primary |
| PMM-M-PR-01_Flow_Material_Master.drawio | PMM-M-PR-01 | PMM-M-PR-01 | PMM-M-PR-01 | primary |
| S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Production Costing Process | FI-M-PC-01 | FI-M-PC-01 | primary |
| S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Project Initiation Process | PM-M-IN-01 | PM-M-IN-01 | primary |
| S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Project Planning Process | PM-M-IN-01 | PM-M-IN-01.2 | primary |
| S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Project Execution Process | PM-M-IN-01 | PM-M-IN-01.3 | primary |
| S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Subcontracting Process | PP-M-SC-01 | PP-M-SC-01 | primary |
| S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Project Monitoring and Control Process | PM-M-IN-01 | PM-M-IN-01.4 | primary |
| S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Project Closing Process | PM-M-IN-01 | PM-M-IN-01.5 | primary |
| S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Escalation Matrix and KPIs |  | LOG-REF-ESC-02 | primary |
| S2S_Process_Documentation_-_dormakaba_MEA_Supply_chain_v1.0.docx | Introduction; Benefits of an Integrated Supply Chain; This handbook |  | E2E-REF-INTRO-01 | primary |
| S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Project Management General Overview | PP-M-PP-01 | PP-M-PP-01 | primary |
| S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Project Initiation Process | PM-M-IN-01 | PM-M-IN-01 | duplicate |
| S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Project Planning Process | PM-M-IN-01 | PM-M-IN-01.2 | duplicate |
| S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Project Execution Process | PM-M-IN-01 | PM-M-IN-01.3 | duplicate |
| S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Subcontracting Process | PP-M-SC-01 | PP-M-SC-01 | duplicate |
| S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Project Monitoring and Control Process | PM-M-IN-01 | PM-M-IN-01.4 | duplicate |
| S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Project Closing Process | PM-M-IN-01 | PM-M-IN-01.5 | duplicate |
| S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Escalation Matrix and KPIs |  | LOG-REF-ESC-03 | primary |
| S2S_Process_Documentation_-_Finance_and_Accounts_v0.1.docx | Introduction |  | PRJ-REF-INTRO-01 | primary |
| S2S_Process_Documentation_-_Approval_processes.docx | Project Management Process | SA-M-PM-01 | SA-M-PM-01 | primary |
| S2S_Process_Documentation_-_Approval_processes.docx | Material Quality Assurance & Control Check | WL-S-QC-01 | WL-S-QC-01.2 | primary |
| S2S_Process_Documentation_-_Approval_processes.docx | FRAGILE HANDLING | WL-S-FH-02 | WL-S-FH-02 | primary |
| S2S_Process_Documentation_-_Approval_processes.docx | Material Pick and Pack | WL-M-PP-01 | WL-M-PP-01 | primary |
| S2S_Process_Documentation_-_Approval_processes.docx | Shipping Documentation | WL-M-SP-01 | WL-M-SP-01.3 | primary |
| S2S_Process_Documentation_-_Approval_processes.docx | Material Dispatch | WL-M-OB-01 | WL-M-OB-01.2 | primary |
| S2S_Process_Documentation_-_Approval_processes.docx | Inventory Audit | WL-M-IA-01 | WL-M-IA-01.2 | primary |
| S2S_Process_Documentation_-_Approval_processes.docx | Stock Correction | WL-S-SC-01 | WL-S-SC-01.3 | primary |
| S2S_Process_Documentation_-_Approval_processes.docx | Escalation Matrix and KPIs |  | LOG-REF-ESC-04 | primary |
| S2S_Process_Documentation_-_Approval_processes.docx | Introduction |  | LOG-REF-INTRO-01 | duplicate |
| CS_and_MRP_Checklist.docx | Customer Service Checklist |  | SAL-FRM-01 | duplicate |
| CS_and_MRP_Checklist.docx | MRP Checklist |  | MPL-FRM-01 | duplicate |

## 4. Departments without documented processes (Documentation Required)

- Procurement
- Production & Engineering
- Service & Installation
- Approval & Governance
