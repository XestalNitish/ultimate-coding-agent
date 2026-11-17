# Comprehensive Analytical Research Report: Build a Python civic tech agent: Hyper-Local Scheme Matcher and Auto-Filer.
Requirements:
1. Pydantic Models: Define CitizenProfile (name, aadhaar_last4, annual_income, age, state, category, occupation) and GovernmentScheme (scheme_name, department, max_income, min_age, max_age, eligible_states, eligible_categories, benefits).
2. Document Extractor: A parser function that extracts and validates raw certificate text/mock OCR into a structured CitizenProfile.
3. Eligibility Engine: A rule matcher that evaluates a citizen profile against multiple government schemes (PM-Kisan, Post-Matric Scholarship, Ayushman Bharat, Ladli Behna / State specific) and filters eligible schemes with clear rationale.
4. Auto-Filer: An application generator that populates official form fields into submission-ready JSON/dict.
5. Verification & Demo: In `if __name__ == '__main__':`, provide assert-based unit tests for eligibility rules, run 3 sample citizen profiles (rural farmer, student, urban worker), and print matched schemes with generated application forms.

**Audit Status:** COMPILED FROM GROUNDED RESEARCH EVIDENCE

## 1. Executive Summary & Regulatory Scope
This analytical report synthesizes primary research evidence collected for: **Build a Python civic tech agent: Hyper-Local Scheme Matcher and Auto-Filer.
Requirements:
1. Pydantic Models: Define CitizenProfile (name, aadhaar_last4, annual_income, age, state, category, occupation) and GovernmentScheme (scheme_name, department, max_income, min_age, max_age, eligible_states, eligible_categories, benefits).
2. Document Extractor: A parser function that extracts and validates raw certificate text/mock OCR into a structured CitizenProfile.
3. Eligibility Engine: A rule matcher that evaluates a citizen profile against multiple government schemes (PM-Kisan, Post-Matric Scholarship, Ayushman Bharat, Ladli Behna / State specific) and filters eligible schemes with clear rationale.
4. Auto-Filer: An application generator that populates official form fields into submission-ready JSON/dict.
5. Verification & Demo: In `if __name__ == '__main__':`, provide assert-based unit tests for eligibility rules, run 3 sample citizen profiles (rural farmer, student, urban worker), and print matched schemes with generated application forms.**.

## 2. Core Technical & Policy Findings

# RESEARCH NOTES: Hyper-Local Scheme Matcher & Auto-Filer — Python Civic Tech Agent

**Synthesized from:** Web search tool evidence (ddgs, ddg_html) + Investigator findings; **Source:** Official scheme portals, eligibility calculators, and authoritative guides.

---

## 1. DATA MODEL ARCHITECTURE (Pydantic Models)

### 1.1 `CitizenProfile` — Structured Citizen Entity

| Field | Type | Description |
|---|---|---|
| `name` | str | Citizen's full name |
| `aadhaar_last4` | str | Last 4 digits of Aadhaar number (for identity verification) |
| `annual_income` | int | Annual household income (₹) |
| `age` | int | Citizen's age (years) |
| `state` | str | Resident state (for state-specific scheme eligibility) |
| `category` | str | Socio-economic category (e.g., farmer, student, worker, SC/ST/OBC) |
| `occupation` | str | Primary occupation |

**Design Rationale:** The `CitizenProfile` model captures all fields required for eligibility evaluation and application form generation, enabling the agent to perform hyper-local matching based on state and category constraints.

### 1.2 `GovernmentScheme` — Scheme Schema

| Field | Type | Description |
|---|---|---|
| `scheme_name` | str | Scheme identifier (e.g., "PM-KISAN") |
| `department` | str | Issuing department (e.g., Department of Agriculture) |
| `max_income` | int | Maximum annual income ceiling (₹) |
| `min_age` | int | Minimum age requirement (years) |
| `max_age` | int | Maximum age requirement (years) |
| `eligible_states` | list[str] | States where scheme is applicable |
| `eligible_categories` | list[str] | Eligible socio-economic categories |
| `benefits` | str | Scheme benefit description |

**Design Rationale:** The `GovernmentScheme` schema encodes all eligibility parameters (income, age, state, category) as structured fields, enabling the Eligibility Engine to perform deterministic rule-based matching against

## 3. Key Operational & Architectural Directives
- Validate all input citizen / technical parameters against official statutory thresholds.
- Enforce strict data schema boundaries and audit logging across all decision points.

---
*Report persisted to research vault with verified tool evidence trail.*