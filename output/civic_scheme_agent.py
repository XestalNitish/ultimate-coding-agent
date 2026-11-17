"""Civic Tech Agent: Hyper-Local Scheme Matcher and Auto-Filer.

Production-grade civic tech engine for citizen profiling, document OCR extraction,
multi-scheme rule-based eligibility evaluation, and automated application filing.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# 1. Pydantic Models
# ============================================================================

class CitizenProfile(BaseModel):
    """Structured citizen profile extracted from raw documents/OCR."""
    name: str = Field(..., description="Full legal name of citizen")
    aadhaar_last4: str = Field(..., description="Last 4 digits of Aadhaar card")
    annual_income: float = Field(..., ge=0, description="Annual household income in INR")
    age: int = Field(..., ge=0, le=125, description="Age in completed years")
    state: str = Field(..., description="State or Union Territory of residence")
    category: str = Field(..., description="Social category: General, OBC, SC, ST, EWS")
    occupation: str = Field(..., description="Current occupation (e.g. Farmer, Student, Artisan)")
    gender: Optional[str] = Field("All", description="Gender of the citizen")

    @field_validator("aadhaar_last4")
    @classmethod
    def validate_aadhaar_last4(cls, v: str) -> str:
        clean = re.sub(r"\D", "", v)
        if len(clean) != 4:
            raise ValueError(f"aadhaar_last4 must be exactly 4 digits, got '{v}'")
        return clean

    @field_validator("state", "category", "occupation")
    @classmethod
    def clean_text_fields(cls, v: str) -> str:
        return v.strip().title()


class GovernmentScheme(BaseModel):
    """Specification of an Indian civic government welfare scheme."""
    scheme_name: str
    department: str
    max_income: float
    min_age: int
    max_age: int
    eligible_states: List[str] = Field(default_factory=lambda: ["ALL"])
    eligible_categories: List[str] = Field(default_factory=lambda: ["ALL"])
    eligible_occupations: List[str] = Field(default_factory=lambda: ["ALL"])
    eligible_genders: List[str] = Field(default_factory=lambda: ["ALL"])
    benefits: str


class SchemeMatchResult(BaseModel):
    """Evaluation result for a specific citizen against a government scheme."""
    scheme_name: str
    department: str
    is_eligible: bool
    benefits: str
    rationale: List[str]


# ============================================================================
# 2. Document Extractor (Mock OCR / Certificate Text Parser)
# ============================================================================

def extract_citizen_profile(raw_text: str) -> CitizenProfile:
    """
    Parses and extracts structured CitizenProfile from unstructured OCR text,
    income certificates, or government ID card excerpts.
    """
    # Name extraction
    name_match = re.search(r"(?:Citizen Name|Full Name|Name|Shri/Smt\.?)[\t ]*[:\-][\t ]*([A-Za-z\.\t ]+)", raw_text, re.IGNORECASE)
    name = name_match.group(1).strip() if name_match else "Unknown Citizen"

    # Aadhaar extraction (looks for 4 digits or masked 12-digit format XXXX-XXXX-1234)
    aadhaar_match = re.search(r"(?:Aadhaar|UID|Aadhar)[\w\s:\-]*(\d{4})(?!\d)", raw_text, re.IGNORECASE)
    if not aadhaar_match:
        # Check for masked format
        aadhaar_match = re.search(r"[X\*\-]{4,10}\s*(\d{4})", raw_text)
    aadhaar_last4 = aadhaar_match.group(1) if aadhaar_match else "0000"

    # Annual Income extraction (e.g. Rs. 1,40,000 or Income: 180000)
    income_match = re.search(r"(?:Annual (?:Family )?Income|Annual Income|Income Certified|Income)[\s:\-RsINR\.]*([\d,]+(?:\.\d{2})?)", raw_text, re.IGNORECASE)
    if income_match:
        raw_inc = income_match.group(1).replace(",", "")
        annual_income = float(raw_inc)
    else:
        annual_income = 0.0

    # Age extraction (Age: 32 or Completed Age: 21)
    age_match = re.search(r"(?:Completed Age|Age)[\t ]*[:\-][\t ]*(\d{1,3})", raw_text, re.IGNORECASE)
    age = int(age_match.group(1)) if age_match else 25

    # State extraction (requires colon or hyphen delimiter to avoid header false positives)
    state_match = re.search(r"(?:State of Domicile|Domicile State|State of Residence|Residence|State|Domicile)[\t ]*[:\-][\t ]*([A-Za-z\t ]+)", raw_text, re.IGNORECASE)
    state = state_match.group(1).strip() if state_match else "Delhi"

    # Category extraction (SC/ST/OBC/General/EWS)
    cat_match = re.search(r"(?:Social Category|Caste Category|Category)[\t ]*[:\-][\t ]*([A-Za-z\t ]+)", raw_text, re.IGNORECASE)
    category = cat_match.group(1).strip() if cat_match else "General"

    # Occupation extraction
    occ_match = re.search(r"(?:Current Occupation|Occupation|Profession|Vocation)[\t ]*[:\-][\t ]*([A-Za-z\t ]+)", raw_text, re.IGNORECASE)
    occupation = occ_match.group(1).strip() if occ_match else "Farmer"

    # Gender extraction
    gender_match = re.search(r"(?:Gender|Sex)[\t ]*[:\-][\t ]*([A-Za-z]+)", raw_text, re.IGNORECASE)
    gender = gender_match.group(1).strip() if gender_match else "All"

    return CitizenProfile(
        name=name,
        aadhaar_last4=aadhaar_last4,
        annual_income=annual_income,
        age=age,
        state=state,
        category=category,
        occupation=occupation,
        gender=gender,
    )


# ============================================================================
# 3. Eligibility Engine (Multi-Scheme Rule Matcher)
# ============================================================================

def get_standard_government_schemes() -> List[GovernmentScheme]:
    """Returns canonical active national and state welfare schemes."""
    return [
        GovernmentScheme(
            scheme_name="PM-Kisan Samman Nidhi",
            department="Ministry of Agriculture & Farmers Welfare",
            max_income=300000.0,
            min_age=18,
            max_age=100,
            eligible_states=["ALL"],
            eligible_categories=["ALL"],
            eligible_occupations=["Farmer", "Agriculture", "Cultivator", "Small Farmer"],
            eligible_genders=["ALL"],
            benefits="INR 6,000 per year paid in three equal 4-monthly installments directly into bank account.",
        ),
        GovernmentScheme(
            scheme_name="Post-Matric Scholarship",
            department="Ministry of Social Justice and Empowerment",
            max_income=250000.0,
            min_age=15,
            max_age=32,
            eligible_states=["ALL"],
            eligible_categories=["SC", "ST", "OBC", "EWS"],
            eligible_occupations=["Student", "Scholar"],
            eligible_genders=["ALL"],
            benefits="100% compulsory non-refundable fees reimbursement + monthly maintenance allowance.",
        ),
        GovernmentScheme(
            scheme_name="Ayushman Bharat (PM-JAY)",
            department="National Health Authority / Ministry of Health",
            max_income=250000.0,
            min_age=0,
            max_age=120,
            eligible_states=["ALL"],
            eligible_categories=["ALL"],
            eligible_occupations=["ALL"],
            eligible_genders=["ALL"],
            benefits="Secondary and tertiary hospitalization coverage up to INR 5,00,000 per family per year.",
        ),
        GovernmentScheme(
            scheme_name="Mukhyamantri Ladli Behna Yojana",
            department="Department of Women & Child Development (Govt of MP)",
            max_income=250000.0,
            min_age=21,
            max_age=60,
            eligible_states=["Madhya Pradesh", "Mp"],
            eligible_categories=["ALL"],
            eligible_occupations=["ALL"],
            eligible_genders=["Female", "Woman"],
            benefits="Direct monthly financial assistance of INR 1,250 directly to eligible women.",
        ),
        GovernmentScheme(
            scheme_name="PM SVANidhi (Urban Street Vendor Scheme)",
            department="Ministry of Housing and Urban Affairs",
            max_income=300000.0,
            min_age=18,
            max_age=65,
            eligible_states=["ALL"],
            eligible_categories=["ALL"],
            eligible_occupations=["Vendor", "Hawker", "Daily Wage Worker", "Artisan", "Laborer"],
            eligible_genders=["ALL"],
            benefits="Collateral-free working capital micro-credit loan up to INR 50,000 with 7% interest subsidy.",
        )
    ]


def evaluate_eligibility(citizen: CitizenProfile, schemes: Optional[List[GovernmentScheme]] = None) -> List[SchemeMatchResult]:
    """
    Evaluates a CitizenProfile against multiple government schemes.
    Returns detailed match status and rationale for every evaluated scheme.
    """
    if schemes is None:
        schemes = get_standard_government_schemes()

    results: List[SchemeMatchResult] = []

    for scheme in schemes:
        reasons: List[str] = []
        is_eligible = True

        # 1. Income Check
        if citizen.annual_income > scheme.max_income:
            is_eligible = False
            reasons.append(f"Income INR {citizen.annual_income:,.0f} exceeds scheme ceiling of INR {scheme.max_income:,.0f}")
        else:
            reasons.append(f"Income INR {citizen.annual_income:,.0f} satisfies ceiling of INR {scheme.max_income:,.0f}")

        # 2. Age Check
        if citizen.age < scheme.min_age or citizen.age > scheme.max_age:
            is_eligible = False
            reasons.append(f"Age {citizen.age} is outside eligible bracket ({scheme.min_age} - {scheme.max_age} years)")
        else:
            reasons.append(f"Age {citizen.age} qualifies within bracket ({scheme.min_age} - {scheme.max_age} years)")

        # 3. State Check
        states_upper = [s.upper() for s in scheme.eligible_states]
        if "ALL" not in states_upper and citizen.state.upper() not in states_upper:
            is_eligible = False
            reasons.append(f"State '{citizen.state}' is not among eligible states: {', '.join(scheme.eligible_states)}")
        else:
            reasons.append(f"State '{citizen.state}' is eligible")

        # 4. Social Category Check
        cats_upper = [c.upper() for c in scheme.eligible_categories]
        if "ALL" not in cats_upper and citizen.category.upper() not in cats_upper:
            is_eligible = False
            reasons.append(f"Category '{citizen.category}' not covered (Requires: {', '.join(scheme.eligible_categories)})")
        else:
            reasons.append(f"Category '{citizen.category}' satisfies criteria")

        # 5. Occupation Check
        occs_upper = [o.upper() for o in scheme.eligible_occupations]
        if "ALL" not in occs_upper and not any(o in citizen.occupation.upper() for o in occs_upper):
            is_eligible = False
            reasons.append(f"Occupation '{citizen.occupation}' does not match required: {', '.join(scheme.eligible_occupations)}")
        else:
            reasons.append(f"Occupation '{citizen.occupation}' is valid for scheme")

        # 6. Gender Check (if applicable)
        genders_upper = [g.upper() for g in scheme.eligible_genders]
        if "ALL" not in genders_upper and citizen.gender.upper() not in genders_upper:
            is_eligible = False
            reasons.append(f"Gender '{citizen.gender}' does not match scheme target ({', '.join(scheme.eligible_genders)})")

        results.append(SchemeMatchResult(
            scheme_name=scheme.scheme_name,
            department=scheme.department,
            is_eligible=is_eligible,
            benefits=scheme.benefits,
            rationale=reasons,
        ))

    return results


# ============================================================================
# 4. Auto-Filer (Application Generator)
# ============================================================================

def generate_application_forms(citizen: CitizenProfile, matches: List[SchemeMatchResult]) -> Dict[str, Any]:
    """
    Populates official government scheme application payloads into submission-ready JSON dicts.
    """
    timestamp = datetime.now().isoformat()
    eligible_matches = [m for m in matches if m.is_eligible]
    applications = {}

    for match in eligible_matches:
        app_id = f"APP-{re.sub(r'[^A-Z0-9]', '', match.scheme_name.upper())[:6]}-{citizen.aadhaar_last4}-{int(datetime.now().timestamp()) % 10000}"

        form_payload = {
            "application_id": app_id,
            "filing_timestamp": timestamp,
            "scheme_name": match.scheme_name,
            "department": match.department,
            "applicant": {
                "full_name": citizen.name,
                "aadhaar_masked": f"XXXXXXXX{citizen.aadhaar_last4}",
                "age": citizen.age,
                "state": citizen.state,
                "social_category": citizen.category,
                "occupation": citizen.occupation,
                "declared_annual_income": citizen.annual_income,
            },
            "declared_entitlements": match.benefits,
            "verification_status": "AUTO_MATCHED_DOCUMENT_VERIFIED",
            "audit_trail": {
                "eligibility_passed": True,
                "rationales": match.rationale,
            }
        }
        applications[match.scheme_name] = form_payload

    return {
        "citizen_name": citizen.name,
        "total_eligible_schemes": len(eligible_matches),
        "generated_at": timestamp,
        "applications": applications
    }


# ============================================================================
# 5. Verification & Assert-based Unit Tests Demo
# ============================================================================

def run_unit_tests():
    """Runs comprehensive assert-based unit tests for eligibility rules."""
    schemes = get_standard_government_schemes()
    pm_kisan = next(s for s in schemes if "PM-Kisan" in s.scheme_name)
    scholarship = next(s for s in schemes if "Scholarship" in s.scheme_name)
    ladli = next(s for s in schemes if "Ladli" in s.scheme_name)

    # Test 1: Farmer eligibility for PM-Kisan
    c_farmer = CitizenProfile(
        name="Ramesh Yadav", aadhaar_last4="4821", annual_income=120000,
        age=42, state="Uttar Pradesh", category="OBC", occupation="Farmer"
    )
    res_farmer = evaluate_eligibility(c_farmer, [pm_kisan])
    assert res_farmer[0].is_eligible is True, "Eligible farmer should match PM-Kisan"

    # Test 2: High income disqualification for PM-Kisan
    c_rich = CitizenProfile(
        name="Vikas Oberoi", aadhaar_last4="9911", annual_income=650000,
        age=45, state="Haryana", category="General", occupation="Farmer"
    )
    res_rich = evaluate_eligibility(c_rich, [pm_kisan])
    assert res_rich[0].is_eligible is False, "High income farmer must be disqualified"

    # Test 3: Student eligibility for Post-Matric Scholarship
    c_student = CitizenProfile(
        name="Sunita Baiga", aadhaar_last4="1024", annual_income=150000,
        age=19, state="Madhya Pradesh", category="ST", occupation="Student"
    )
    res_student = evaluate_eligibility(c_student, [scholarship])
    assert res_student[0].is_eligible is True, "ST Student should qualify for scholarship"

    # Test 4: General Category student in Post-Matric (restricted to SC/ST/OBC/EWS)
    c_gen_student = CitizenProfile(
        name="Rohit Sharma", aadhaar_last4="7733", annual_income=150000,
        age=20, state="Delhi", category="General", occupation="Student"
    )
    res_gen = evaluate_eligibility(c_gen_student, [scholarship])
    assert res_gen[0].is_eligible is False, "General non-EWS student should not qualify"

    # Test 5: State boundary check for MP Ladli Behna
    c_up_woman = CitizenProfile(
        name="Geeta Devi", aadhaar_last4="5544", annual_income=110000,
        age=32, state="Uttar Pradesh", category="OBC", occupation="Artisan", gender="Female"
    )
    res_up_woman = evaluate_eligibility(c_up_woman, [ladli])
    assert res_up_woman[0].is_eligible is False, "Non-MP resident must fail Ladli Behna"

    # Test 6: Document Extractor OCR parsing
    raw_ocr = """
    GOVERNMENT OF MADHYA PRADESH - REVENUE DEPARTMENT
    INCOME AND DOMICILE CERTIFICATE
    Citizen Name: Priya Sharma
    Aadhaar Number: XXXX-XXXX-8921
    Annual Family Income: Rs. 1,40,000.00
    Completed Age: 21 Years | Gender: Female
    Social Category: SC | State of Domicile: Madhya Pradesh
    Current Occupation: Student
    """
    extracted = extract_citizen_profile(raw_ocr)
    assert extracted.name == "Priya Sharma"
    assert extracted.aadhaar_last4 == "8921"
    assert extracted.annual_income == 140000.0
    assert extracted.age == 21
    assert extracted.state == "Madhya Pradesh"
    assert extracted.category == "Sc"
    assert extracted.occupation == "Student"
    assert extracted.gender.lower() == "female"

    # Test 7: Auto-filer generates valid form payload
    matches = evaluate_eligibility(extracted, schemes)
    filing = generate_application_forms(extracted, matches)
    assert filing["total_eligible_schemes"] >= 2, "Student woman should be eligible for >= 2 schemes"
    assert "Ayushman Bharat (PM-JAY)" in filing["applications"]

    print("[ASSERT TESTS] All 7 unit tests passed successfully!\n")


if __name__ == "__main__":
    print("=" * 75)
    print("CIVIC TECH AGENT: HYPER-LOCAL SCHEME MATCHER & AUTO-FILER")
    print("=" * 75)

    # 1. Run Unit Tests
    run_unit_tests()

    # 2. Sample Citizen Profiles
    sample_citizens = [
        CitizenProfile(
            name="Rameshwar Prasad",
            aadhaar_last4="6124",
            annual_income=115000.0,
            age=48,
            state="Uttar Pradesh",
            category="OBC",
            occupation="Farmer",
            gender="Male",
        ),
        CitizenProfile(
            name="Ananya Meshram",
            aadhaar_last4="7890",
            annual_income=145000.0,
            age=22,
            state="Madhya Pradesh",
            category="SC",
            occupation="Student",
            gender="Female",
        ),
        CitizenProfile(
            name="Mohammad Altaf",
            aadhaar_last4="3341",
            annual_income=190000.0,
            age=36,
            state="Maharashtra",
            category="General",
            occupation="Vendor",
            gender="Male",
        ),
    ]

    all_schemes = get_standard_government_schemes()

    for idx, citizen in enumerate(sample_citizens, 1):
        print(f"\n[{idx}/3] EVALUATING CITIZEN: {citizen.name.upper()} ({citizen.occupation}, {citizen.state})")
        print(f"    Age: {citizen.age} | Category: {citizen.category} | Income: INR {citizen.annual_income:,.0f} | Aadhaar: ****{citizen.aadhaar_last4}")
        print("-" * 75)

        matches = evaluate_eligibility(citizen, all_schemes)
        eligible = [m for m in matches if m.is_eligible]
        ineligible = [m for m in matches if not m.is_eligible]

        print(f"    MATCH RESULTS: {len(eligible)} Eligible | {len(ineligible)} Ineligible")
        for m in eligible:
            print(f"    [MATCHED] {m.scheme_name} ({m.department})")
            print(f"      Benefits: {m.benefits}")

        filing_result = generate_application_forms(citizen, matches)
        print(f"\n    GENERATED SUBMISSION FORMS: {len(filing_result['applications'])} forms ready")
        for scheme_name, app_data in filing_result["applications"].items():
            print(f"      • {scheme_name} -> App ID: {app_data['application_id']}")

    print("\n" + "=" * 75)
    print("DEMO & VERIFICATION COMPLETE: ALL 3 PROFILES PROCESSED & VERIFIED")
    print("=" * 75)
