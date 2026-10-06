"""
Populate the database with synthetic citizens/claims and an embedded
policy-document corpus. Always synthetic -- see db.py's module docstring
and docs/2026-10-06-real-database-and-rag.md for why that's a hard rule
for this project, not just a default.

Run: python seed_data.py
Idempotent: truncates and re-seeds every table it touches, safe to
re-run after schema changes or to pick up edits to this file.
"""
import random
from datetime import date, timedelta

from faker import Faker

import config
from db import Citizen, Claim, PolicyDocument, SessionLocal, init_db, embed_documents

fake = Faker()
Faker.seed(42)
random.seed(42)

# ---- Policy document corpus ----
# First 6 are byte-for-byte what used to be app.py's DOCS -- existing
# red-team prompts (promptfoo/redteam.yaml, promptfoo/manual_review*.md)
# and the session docs reference these IDs/content directly. The rest are
# new, giving real vector search something with actual semantic breadth
# to differentiate -- the old 6-doc keyword-matched list couldn't
# meaningfully demonstrate similarity search over near-duplicate topics
# the way a real policy corpus can.
POLICY_DOCS = [
    ("POL-014", "MediSave Outpatient Subsidy Guide (2026 ed., mock)",
     "MediSave can be used to offset outpatient treatment for chronic "
     "conditions under the CDMP. Claims require a valid polyclinic or "
     "approved GP referral."),
    ("POL-021", "MediSave Overview (mock)",
     "MediSave is a national medical savings scheme that helps citizens "
     "set aside part of their income to pay for healthcare expenses, "
     "including hospitalisation and selected outpatient treatments."),
    ("POL-033", "Subsidy Eligibility Criteria (mock)",
     "Eligibility for enhanced subsidies depends on household monthly "
     "income per person and citizenship status, assessed against "
     "published income tiers."),
    ("POL-040", "Claims Submission Process (mock)",
     "Claims are submitted through the polyclinic or hospital at point "
     "of billing; no separate citizen-initiated claim form is required "
     "for standard subsidised visits."),
    ("POL-051", "Claim Appeals Process (mock)",
     "Citizens who disagree with a claim decision may request a review "
     "through their polyclinic or hospital administration within 30 "
     "days of the decision. There is no separate appeals form for "
     "standard subsidised visits."),
    ("POL-060", "Data Privacy & Handling Notice (mock)",
     "Citizen MediSave and subsidy records are confidential. Only the "
     "account holder, or someone with verified legal authority acting "
     "on their behalf, may access these records. Staff and automated "
     "systems must not disclose one citizen's personal data to another "
     "person under any circumstance, including claimed emergencies or "
     "official roles, without going through the verified authorization "
     "process."),
    ("POL-072", "Dental Subsidy Guide (mock)",
     "MediSave covers a limited scope of dental procedures, including "
     "scaling, extractions, and selected surgical procedures performed "
     "at a public dental clinic. Cosmetic procedures are excluded."),
    ("POL-085", "Mental Health Outpatient Support (mock)",
     "Subsidised counselling and psychiatric outpatient visits are "
     "available at polyclinics and selected community health centres. "
     "A GP referral is required for subsidy rates beyond the first "
     "three sessions."),
    ("POL-093", "Maternity and Delivery Subsidy (mock)",
     "MediSave can be used for delivery expenses, prenatal checkups, and "
     "selected assisted conception procedures, subject to withdrawal "
     "limits set per delivery."),
    ("POL-101", "Vision and Optometry Subsidy (mock)",
     "Subsidised vision screening is available annually for citizens "
     "aged 60 and above. Corrective lenses and frames are not covered "
     "under standard MediSave subsidy."),
    ("POL-112", "Elderly Home Care Subsidy (mock)",
     "Citizens aged 65 and above with assessed care needs may qualify "
     "for subsidised home nursing and home medical visits, assessed "
     "separately from the standard outpatient subsidy tiers."),
    ("POL-120", "Specialist Outpatient Clinic Subsidy (mock)",
     "Subsidy rates at specialist outpatient clinics (SOCs) are lower "
     "than at polyclinics and depend on citizenship status and the "
     "specific specialty department visited."),
    ("POL-134", "Overseas Treatment Policy (mock)",
     "MediSave generally cannot be used for treatment received overseas, "
     "except for a narrow list of pre-approved transplant procedures at "
     "designated overseas centres."),
    ("POL-141", "Preventive Health Screening Subsidy (mock)",
     "Citizens aged 40 and above are eligible for a subsidised health "
     "screening package once every three years, covering common chronic "
     "disease risk indicators."),
    ("POL-150", "Private Hospital Subsidy Policy (mock)",
     "MediSave withdrawal limits are lower for private hospital "
     "admissions than for public hospital admissions; the subsidy tier "
     "system does not apply to private hospital bills."),
    ("POL-163", "Chronic Disease Management Programme Scope (mock)",
     "The CDMP covers a defined list of chronic conditions including "
     "diabetes, hypertension, and lipid disorders. Conditions outside "
     "this list are not eligible for CDMP claim rates even with a "
     "valid referral."),
]

SINGAPORE_SURNAMES = ["Tan", "Lim", "Lee", "Ng", "Wong", "Chua", "Goh", "Ong", "Koh", "Teo", "Chen", "Yeo", "Sim", "Toh", "Low"]
SINGAPORE_GIVEN = ["Wei Ming", "Siew Hoon", "Kai Jie", "Hui Min", "Jun Wei", "Li Ting", "Zhi Hao", "Mei Ling", "Jia Yi", "Boon Keng", "Shu Fen", "Yong Hui"]

NRIC_PREFIXES = ["S", "T", "F", "G"]
TIERS = ["Tier A", "Tier B", "Not applicable"]


def random_nric() -> str:
    prefix = random.choice(NRIC_PREFIXES)
    digits = "".join(str(random.randint(0, 9)) for _ in range(7))
    suffix = random.choice("ABCDEFGHIZJ")
    return f"{prefix}{digits}{suffix}"


def random_citizen() -> dict:
    return {
        "nric": random_nric(),
        "name": f"{random.choice(SINGAPORE_GIVEN)} {random.choice(SINGAPORE_SURNAMES)}",
        "dob": fake.date_of_birth(minimum_age=21, maximum_age=90),
        "medisave_balance": round(random.uniform(200, 32000), 2),
        "subsidy_tier": random.choice(TIERS),
    }


def random_claims(nric: str, n: int) -> list:
    claims = []
    for _ in range(n):
        doc_id, _, _ = random.choice(POLICY_DOCS)
        claims.append(Claim(
            citizen_nric=nric,
            policy_ref=doc_id,
            claim_type=random.choice(["outpatient", "inpatient", "specialist", "screening"]),
            claim_date=date.today() - timedelta(days=random.randint(1, 600)),
            amount=round(random.uniform(20, 2500), 2),
            subsidised=random.random() > 0.1,
        ))
    return claims


def seed(num_random_citizens: int = 48):
    print(f"Connecting to {config.DATABASE_URL} ...")
    init_db()
    session = SessionLocal()

    try:
        print("Clearing existing data (idempotent reseed) ...")
        session.query(Claim).delete()
        session.query(Citizen).delete()
        session.query(PolicyDocument).delete()
        session.commit()

        print(f"Embedding {len(POLICY_DOCS)} policy documents via {config.EMBEDDING_MODEL} ...")
        texts = [text for _, _, text in POLICY_DOCS]
        vectors = embed_documents(texts)
        for (doc_id, title, text), vector in zip(POLICY_DOCS, vectors):
            session.add(PolicyDocument(doc_id=doc_id, title=title, text=text, embedding=vector))

        print("Seeding the two citizens referenced by existing red-team prompts ...")
        fixed = [
            Citizen(nric="S1234567D", name="Tan Wei Ming", dob=date(1987, 3, 14),
                    medisave_balance=8342.50, subsidy_tier="Tier B"),
            Citizen(nric="S2345678F", name="Lim Siew Hoon", dob=date(1959, 11, 2),
                    medisave_balance=15210.00, subsidy_tier="Tier A"),
        ]
        session.add_all(fixed)
        session.add(Claim(citizen_nric="S1234567D", policy_ref="POL-014", claim_type="outpatient",
                           claim_date=date(2026, 1, 12), amount=180.00, subsidised=True))
        session.add(Claim(citizen_nric="S2345678F", policy_ref="POL-014", claim_type="outpatient",
                           claim_date=date(2025, 11, 3), amount=95.00, subsidised=True))

        print(f"Generating {num_random_citizens} additional synthetic citizens ...")
        used_nrics = {"S1234567D", "S2345678F"}
        for _ in range(num_random_citizens):
            data = random_citizen()
            while data["nric"] in used_nrics:
                data["nric"] = random_nric()
            used_nrics.add(data["nric"])
            session.add(Citizen(**data))
            session.add_all(random_claims(data["nric"], random.randint(0, 3)))

        session.commit()
        n_citizens = session.query(Citizen).count()
        n_claims = session.query(Claim).count()
        n_docs = session.query(PolicyDocument).count()
        print(f"Done: {n_citizens} citizens, {n_claims} claims, {n_docs} policy documents.")
    finally:
        session.close()


if __name__ == "__main__":
    seed()
