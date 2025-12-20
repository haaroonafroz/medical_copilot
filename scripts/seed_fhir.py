import os
import json
import requests
from fhir.resources.R4B.patient import Patient
from fhir.resources.R4B.observation import Observation
from fhir.resources.R4B.condition import Condition
from fhir.resources.R4B.medicationstatement import MedicationStatement
from fhir.resources.R4B.allergyintolerance import AllergyIntolerance
from datetime import datetime, timezone

# Configuration
FHIR_BASE_URL = os.getenv("FHIR_BASE_URL") or "http://localhost:8080/fhir"
PATIENT_ID = "test-patient-001"

def create_patient():
    """Creates a synthetic patient with Hypertension."""
    
    # 1. Patient: John Doe
    pat = Patient(
        id=PATIENT_ID,
        active=True,
        gender="male",
        birthDate="1975-05-15",
        name=[{"family": "Doe", "given": ["John"]}]
    )

    # 2. Condition: Hypertension (SNOMED: 38341003)
    cond = Condition(
        id=f"{PATIENT_ID}-hypertension",
        subject={"reference": f"Patient/{PATIENT_ID}"},
        clinicalStatus={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        code={"coding": [{"system": "http://snomed.info/sct", "code": "38341003", "display": "Hypertension"}]}
    )

    # 3. Allergy: Penicillin (Crucial for Agentic Safety Checks)
    allergy = AllergyIntolerance(
        id=f"{PATIENT_ID}-allergy-pen",
        patient={"reference": f"Patient/{PATIENT_ID}"},
        clinicalStatus={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}]},
        code={"coding": [{"system": "http://snomed.info/sct", "code": "764146007", "display": "Allergy to Penicillin"}]},
        criticality="high"
    )

    # 4. Medication: Lisinopril (ACE Inhibitor)
    # Using R4 structure: medicationCodeableConcept
    med = MedicationStatement(
        id=f"{PATIENT_ID}-med-1",
        status="active",
        subject={"reference": f"Patient/{PATIENT_ID}"},
        dateAsserted=datetime.now(timezone.utc).isoformat(),
        medicationCodeableConcept={
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "29046", "display": "Lisinopril 10 MG"}]
        }
    )

    # 5. Obeservation: Blood Pressure
    obs = Observation(
        id=f"{PATIENT_ID}-obs-1", # Standardized ID
        status="final",
        subject={"reference": f"Patient/{PATIENT_ID}"}, # This link enables the search!
        code={
            "coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Blood pressure panel with all children optional"}]
        },
        effectiveDateTime=datetime.now(timezone.utc).isoformat(),
        component=[
            {
                "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"}]},
                "valueQuantity": {"value": 150, "unit": "mm[Hg]", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"}
            },
            {
                "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic blood pressure"}]},
                "valueQuantity": {"value": 95, "unit": "mm[Hg]", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"}
            }
        ]
    )

    resources = [pat, cond, allergy, med, obs]
    
    for res in resources:
        res_type = res.__resource_type__
        # model_dump_json(exclude_none=True) keeps the payload clean
        payload = json.loads(res.json()) 
        
        url = f"{FHIR_BASE_URL}/{res_type}/{res.id}"
        try:
            resp = requests.put(url, json=payload)
            if resp.status_code in [200, 201]:
                print(f"✅ Synced {res_type}/{res.id}")
            else:
                print(f"❌ Error {res_type}: {resp.text}")
        except Exception as e:
            print(f"Connection failed: {e}")

if __name__ == "__main__":
    create_patient()