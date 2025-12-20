import json
import requests
from fhir.resources.patient import Patient
from fhir.resources.observation import Observation
from fhir.resources.condition import Condition
from fhir.resources.medicationstatement import MedicationStatement
from datetime import datetime, timezone

# Configuration
FHIR_BASE_URL = "http://localhost:8080/fhir"

def create_patient():
    """Creates a synthetic patient with Hypertension."""
    
    # 1. Define Patient
    pat = Patient(
        id="test-patient-001",
        gender="male",
        birthDate="1970-01-01",
        name=[{"family": "Doe", "given": ["John"]}]
    )
    
    # 2. Define Condition (Hypertension)
    cond = Condition(
        subject={"reference": f"Patient/{pat.id}"},
        clinicalStatus={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        code={
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": "38341003",
                "display": "Hypertensive disorder, systemic arterial (disorder)"
            }]
        }
    )

    # 3. Define Observation (High Blood Pressure)
    # Passed all required fields (status, code) into constructor to avoid validation error
    obs = Observation(
        status="final",
        subject={"reference": f"Patient/{pat.id}"},
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

    # 4. Define Current Medication (Lisinopril - ACE Inhibitor)
    med = MedicationStatement(
        status="active",
        subject={"reference": f"Patient/{pat.id}"},
        medication={
            "concept": {
                "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "29046", "display": "Lisinopril 10 MG Oral Tablet"}]
            }
        }
    )

    resources = [pat, cond, obs, med]
    
    print(f"Seeding data to {FHIR_BASE_URL}...")
    
    for resource in resources:
        resource_type = resource.__resource_type__
        # Use PUT to upsert by ID if possible, or POST
        url = f"{FHIR_BASE_URL}/{resource_type}/{resource.id}" if resource.id else f"{FHIR_BASE_URL}/{resource_type}"
        
        # We need to convert pydantic model to json
        # fhir.resources v7 uses .json() or .model_dump_json()
        payload = json.loads(resource.json())
        
        try:
            # Try PUT to create/update with specific ID
            if resource.id:
                 resp = requests.put(url, json=payload)
            else:
                 resp = requests.post(url, json=payload)
            
            if resp.status_code in [200, 201]:
                print(f"✅ Created/Updated {resource_type}")
            else:
                print(f"❌ Failed {resource_type}: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Connection Error: {e}")
            print("Ensure HAPI FHIR is running (docker-compose up -d hapi-fhir)")
            break

if __name__ == "__main__":
    create_patient()