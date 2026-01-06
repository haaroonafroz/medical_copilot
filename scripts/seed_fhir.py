"""
This script is used to seed the FHIR server with synthetic patients.
It creates a random number of patients with a random combination of conditions, medications, and observations.
It then uploads the patients to the FHIR server.
"""

import os
import random
import uuid
import json
from datetime import datetime, timezone, timedelta, date
from fhir.resources.R4B.patient import Patient
from fhir.resources.R4B.observation import Observation
from fhir.resources.R4B.condition import Condition
from fhir.resources.R4B.medicationstatement import MedicationStatement
from fhir.resources.R4B.allergyintolerance import AllergyIntolerance
import requests
from tqdm import tqdm
from decimal import Decimal

FHIR_BASE_URL = os.getenv("FHIR_BASE_URL") or "http://localhost:8080/fhir"

class FHIRJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for FHIR resources"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)
    
# Clinical scenarios with controlled complexity
SCENARIOS = {
    "hypertension": {
        "condition": {"code": "38341003", "display": "Hypertension"},
        "medications": [
            # First-line
            {"code": "29046", "display": "Lisinopril 10 MG", "tier": 1},
            {"code": "197361", "display": "Amlodipine 5 MG", "tier": 1},
            {"code": "310798", "display": "Hydrochlorothiazide 25 MG", "tier": 1},
            # Second-line
            {"code": "52175", "display": "Losartan 50 MG", "tier": 2},
            {"code": "866427", "display": "Metoprolol 50 MG", "tier": 2},
            {"code": "205326", "display": "Chlorthalidone 25 MG", "tier": 2},
        ],
        "observations": [
            {"code": "85354-9", "display": "Blood pressure", "systolic": (140, 180), "diastolic": (90, 110)},
        ]
    },
    "diabetes": {
        "condition": {"code": "44054006", "display": "Type 2 Diabetes"},
        "medications": [
            # First-line
            {"code": "860975", "display": "Metformin 500 MG", "tier": 1},
            {"code": "1546356", "display": "Empagliflozin 10 MG", "tier": 1},
            # Second-line
            {"code": "1992672", "display": "Insulin Glargine 100 UNT/ML", "tier": 2},
            {"code": "897122", "display": "Glipizide 5 MG", "tier": 2},
        ],
        "observations": [
            {"code": "2339-0", "display": "Glucose", "value": (126, 250), "unit": "mg/dL"},
            {"code": "4548-4", "display": "Hemoglobin A1c", "value": (6.5, 10.0), "unit": "%"}
        ]
    },
    "copd": {
        "condition": {"code": "13645005", "display": "Chronic obstructive pulmonary disease"},
        "medications": [
            # Bronchodilators
            {"code": "745678", "display": "Albuterol Inhaler", "tier": 1},
            {"code": "896209", "display": "Tiotropium 18 MCG", "tier": 1},
            # Combination inhalers
            {"code": "1649558", "display": "Fluticasone-Salmeterol Inhaler", "tier": 2},
            {"code": "1431076", "display": "Budesonide-Formoterol Inhaler", "tier": 2},
            # Oral agents
            {"code": "1223", "display": "Prednisone 10 MG", "tier": 3},
            {"code": "6130", "display": "Theophylline 200 MG", "tier": 3},
        ],
        "observations": [
            {"code": "20564-1", "display": "Oxygen saturation", "value": (88, 95), "unit": "%"}
        ]
    },
    "healthy": {
        "condition": None,
        "medications": [],
        "observations": [
            {"code": "85354-9", "display": "Blood pressure", "systolic": (110, 130), "diastolic": (70, 85)}
        ]
    }
}

ALLERGIES = [
    {"code": "764146007", "display": "Allergy to Penicillin"},
    {"code": "300916003", "display": "Allergy to Latex"},
    {"code": "419511003", "display": "Allergy to Iodine"},
    {"code": "91936005", "display": "Allergy to Sulfonamides"},
    None
]

NAMES = {
    "male": [
        ("Smith", "John"), ("Johnson", "Michael"), ("Williams", "David"),
        ("Brown", "Robert"), ("Jones", "James"), ("Garcia", "Carlos"),
        ("Martinez", "Jose"), ("Davis", "Daniel"), ("Rodriguez", "Luis")
    ],
    "female": [
        ("Smith", "Mary"), ("Johnson", "Patricia"), ("Williams", "Jennifer"),
        ("Brown", "Linda"), ("Jones", "Elizabeth"), ("Garcia", "Maria"),
        ("Martinez", "Ana"), ("Davis", "Sarah"), ("Rodriguez", "Sofia")
    ]
}

def generate_patient_id():
    """Generate a unique patient ID"""
    return f"synthetic-{uuid.uuid4().hex[:12]}"

def create_synthetic_patient(scenario_name: str, include_allergy: bool = True):
    """
    Create a synthetic patient with controlled complexity.
    
    Args:
        scenario_name: One of "hypertension", "diabetes", "copd", "healthy"
        include_allergy: Whether to include an allergy (randomized)
    
    Returns:
        List of FHIR resources
    """
    scenario = SCENARIOS.get(scenario_name, SCENARIOS["healthy"])
    patient_id = generate_patient_id()
    
    # Random demographics
    gender = random.choice(["male", "female"])
    family, given = random.choice(NAMES[gender])
    age = random.randint(25, 85)
    birth_year = datetime.now().year - age
    birth_date = f"{birth_year}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    
    resources = []
    
    # 1. Patient
    patient = Patient(
        id=patient_id,
        active=True,
        gender=gender,
        birthDate=birth_date,
        name=[{"family": family, "given": [given]}]
    )
    resources.append(patient)
    
    # 2. Condition (if applicable)
    if scenario["condition"]:
        condition = Condition(
            id=f"{patient_id}-condition",
            subject={"reference": f"Patient/{patient_id}"},
            clinicalStatus={
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active"
                }]
            },
            code={
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": scenario["condition"]["code"],
                    "display": scenario["condition"]["display"]
                }]
            }
        )
        resources.append(condition)
    
    # 3. Allergy (optional)
    if include_allergy:
        allergy_data = random.choice(ALLERGIES)
        if allergy_data:
            allergy = AllergyIntolerance(
                id=f"{patient_id}-allergy",
                patient={"reference": f"Patient/{patient_id}"},
                clinicalStatus={
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                        "code": "active"
                    }]
                },
                code={
                    "coding": [{
                        "system": "http://snomed.info/sct",
                        "code": allergy_data["code"],
                        "display": allergy_data["display"]
                    }]
                },
                criticality="high"
            )
            resources.append(allergy)
    
    # 4. Medications - Progressive treatment based on severity
    # Randomly decide severity (controls how many meds)
    if scenario["medications"]:
        severity = random.choice(["mild", "moderate", "severe"])
        
        if severity == "mild":
            num_meds = 1
            eligible_meds = [m for m in scenario["medications"] if m.get("tier", 1) == 1]
        elif severity == "moderate":
            num_meds = random.randint(2, 3)
            eligible_meds = [m for m in scenario["medications"] if m.get("tier", 1) <= 2]
        else:  # severe
            num_meds = random.randint(3, 4)
            eligible_meds = scenario["medications"]
        
        # Sample medications
        selected_meds = random.sample(eligible_meds, min(num_meds, len(eligible_meds)))
        # Create FHIR MedicationStatement resources
        for i, med_data in enumerate(selected_meds):
            med = MedicationStatement(
                id=f"{patient_id}-med-{i+1}",
                status="active",
                subject={"reference": f"Patient/{patient_id}"},
                dateAsserted=datetime.now(timezone.utc).isoformat(),
                medicationCodeableConcept={
                    "coding": [{
                        "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": med_data["code"],
                        "display": med_data["display"]
                    }]
                }
            )
            resources.append(med)
    
    # 5. Observations
    for i, obs_data in enumerate(scenario["observations"]):
        obs_id = f"{patient_id}-obs-{i+1}"
        
        # Handle BP specially (has components)
        if obs_data["code"] == "85354-9":
            systolic = random.randint(*obs_data["systolic"])
            diastolic = random.randint(*obs_data["diastolic"])
            
            obs = Observation(
                id=obs_id,
                status="final",
                subject={"reference": f"Patient/{patient_id}"},
                code={
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": obs_data["code"],
                        "display": obs_data["display"]
                    }]
                },
                effectiveDateTime=datetime.now(timezone.utc).isoformat(),
                component=[
                    {
                        "code": {
                            "coding": [{
                                "system": "http://loinc.org",
                                "code": "8480-6",
                                "display": "Systolic blood pressure"
                            }]
                        },
                        "valueQuantity": {
                            "value": systolic,
                            "unit": "mm[Hg]",
                            "system": "http://unitsofmeasure.org",
                            "code": "mm[Hg]"
                        }
                    },
                    {
                        "code": {
                            "coding": [{
                                "system": "http://loinc.org",
                                "code": "8462-4",
                                "display": "Diastolic blood pressure"
                            }]
                        },
                        "valueQuantity": {
                            "value": diastolic,
                            "unit": "mm[Hg]",
                            "system": "http://unitsofmeasure.org",
                            "code": "mm[Hg]"
                        }
                    }
                ]
            )
        else:
            # Simple observation with single value
            value = round(random.uniform(*obs_data["value"]), 1)
            obs = Observation(
                id=obs_id,
                status="final",
                subject={"reference": f"Patient/{patient_id}"},
                code={
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": obs_data["code"],
                        "display": obs_data["display"]
                    }]
                },
                effectiveDateTime=datetime.now(timezone.utc).isoformat(),
                valueQuantity={
                    "value": value,
                    "unit": obs_data["unit"],
                    "system": "http://unitsofmeasure.org"
                }
            )
        
        resources.append(obs)
    
    return resources, patient_id, f"{given} {family}"

def upload_resources(resources, timeout=30):
    """Upload a list of FHIR resources"""
    success = 0
    failed = 0
    errors = []
    
    for res in resources:
        res_type = res.__resource_type__
        payload = json.loads(res.json())
        url = f"{FHIR_BASE_URL}/{res_type}/{res.id}"
        
        try:
            resp = requests.put(url, json=payload, timeout=timeout)
            if resp.status_code in [200, 201]:
                success += 1
            else:
                failed += 1
                if len(errors) < 3:
                    errors.append(f"{res_type}/{res.id}: HTTP {resp.status_code} - {resp.text[:100]}")
        except requests.exceptions.Timeout:
            failed += 1
            if len(errors) < 3:
                errors.append(f"{res_type}/{res.id}: Timeout after {timeout}s")
        except Exception as e:
            failed += 1
            if len(errors) < 3:
                errors.append(f"{res_type}/{res.id}: {str(e)[:100]}")
    
    return success, failed, errors

def generate_and_seed(num_patients=10, scenario_mix=None, run_name=None):
    """
    Generate and upload synthetic patients.
    
    Args:
        num_patients: Number of patients to generate
        scenario_mix: Dict like {"hypertension": 0.4, "diabetes": 0.3, "copd": 0.2, "healthy": 0.1}
                     If None, distributes evenly
        run_name: Optional name for the output JSON file (without extension)
    """
    if scenario_mix is None:
        # Even distribution
        scenarios_list = list(SCENARIOS.keys())
        scenario_mix = {s: 1/len(scenarios_list) for s in scenarios_list}
    
    # Determine scenario for each patient
    scenarios_list = []
    for scenario, proportion in scenario_mix.items():
        count = int(num_patients * proportion)
        scenarios_list.extend([scenario] * count)
    
    # Fill remaining to reach exact num_patients
    while len(scenarios_list) < num_patients:
        scenarios_list.append(random.choice(list(scenario_mix.keys())))
    
    random.shuffle(scenarios_list)
    scenarios_list = scenarios_list[:num_patients]
    
    print(f"Generating {num_patients} synthetic patients...")
    print(f"Scenario distribution: {dict((s, scenarios_list.count(s)) for s in set(scenarios_list))}\n")
    
    total_success = 0
    total_failed = 0
    
    # Store all patient data for JSON export
    patients_summary = {
        "metadata": {
            "run_name": run_name or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_patients": num_patients,
            "scenario_distribution": dict((s, scenarios_list.count(s)) for s in set(scenarios_list)),
            "fhir_server": FHIR_BASE_URL
        },
        "patients": []
    }
    
    with tqdm(total=num_patients, desc="Creating patients", unit="patient") as pbar:
        for i, scenario in enumerate(scenarios_list, 1):
            resources, patient_id, patient_name = create_synthetic_patient(
                scenario,
                include_allergy=random.random() > 0.3  # 70% have allergy
            )
            
            success, failed, errors = upload_resources(resources)
            total_success += success
            total_failed += failed
            
            if failed > 0:
                pbar.write(f"  {patient_name} ({patient_id}): {failed} resources failed")
                pbar.write(f"    Errors: {', '.join(errors)}")
            
            # Build patient summary
            patient_summary = {
                "patient_id": patient_id,
                "name": patient_name,
                "scenario": scenario,
                "upload_status": {
                    "success": success,
                    "failed": failed,
                    "total_resources": len(resources)
                },
                "demographics": {},
                "conditions": [],
                "medications": [],
                "allergies": [],
                "observations": []
            }
            
            # Extract details from resources
            for res in resources:
                res_type = res.__resource_type__
                
                if res_type == "Patient":
                    birth_date_str = res.birthDate.isoformat() if hasattr(res.birthDate, 'isoformat') else str(res.birthDate)
                    patient_summary["demographics"] = {
                        "gender": res.gender,
                        "birthDate": birth_date_str,
                        # "age": datetime.now().year - int(res.birthDate.split('-')[0])
                        "age": datetime.now().year - res.birthDate.year,
                    }
                
                elif res_type == "Condition":
                    patient_summary["conditions"].append({
                        "code": res.code.coding[0].code if res.code and res.code.coding else None,
                        "display": res.code.coding[0].display if res.code and res.code.coding else None,
                        "status": res.clinicalStatus.coding[0].code if res.clinicalStatus else None
                    })
                
                elif res_type == "MedicationStatement":
                    patient_summary["medications"].append({
                        "code": res.medicationCodeableConcept.coding[0].code if res.medicationCodeableConcept and res.medicationCodeableConcept.coding else None,
                        "display": res.medicationCodeableConcept.coding[0].display if res.medicationCodeableConcept and res.medicationCodeableConcept.coding else None,
                        "status": res.status
                    })
                
                elif res_type == "AllergyIntolerance":
                    patient_summary["allergies"].append({
                        "code": res.code.coding[0].code if res.code and res.code.coding else None,
                        "display": res.code.coding[0].display if res.code and res.code.coding else None,
                        "criticality": res.criticality
                    })
                
                elif res_type == "Observation":
                    effective_dt = res.effectiveDateTime
                    if isinstance(effective_dt, (datetime, date)):
                        effective_dt = effective_dt.isoformat()
                    elif effective_dt is not None:
                        effective_dt = str(effective_dt)

                    obs_data = {
                        "code": res.code.coding[0].code if res.code and res.code.coding else None,
                        "display": res.code.coding[0].display if res.code and res.code.coding else None,
                        "effectiveDateTime": effective_dt
                    }
                    
                    # Handle different observation types
                    if hasattr(res, 'component') and res.component:
                        # Blood pressure or multi-component
                        obs_data["components"] = []
                        for comp in res.component:
                            obs_data["components"].append({
                                "code": comp.code.coding[0].code if comp.code and comp.code.coding else None,
                                "display": comp.code.coding[0].display if comp.code and comp.code.coding else None,
                                "value": comp.valueQuantity.value if comp.valueQuantity else None,
                                "unit": comp.valueQuantity.unit if comp.valueQuantity else None
                            })
                    elif hasattr(res, 'valueQuantity') and res.valueQuantity:
                        # Simple observation
                        obs_data["value"] = res.valueQuantity.value
                        obs_data["unit"] = res.valueQuantity.unit
                    
                    patient_summary["observations"].append(obs_data)
            
            patients_summary["patients"].append(patient_summary)
            
            if failed > 0:
                pbar.write(f"  {patient_name} ({patient_id}): {failed} resources failed")
            
            pbar.set_postfix({
                "Success": total_success,
                "Failed": total_failed
            })
            pbar.update(1)
    
    # Update final statistics
    patients_summary["metadata"]["total_resources_uploaded"] = total_success
    patients_summary["metadata"]["total_resources_failed"] = total_failed
    patients_summary["metadata"]["success_rate"] = f"{(total_success / (total_success + total_failed) * 100):.2f}%" if (total_success + total_failed) > 0 else "N/A"
    
    print(f"\n{'='*80}")
    print(f"COMPLETE")
    print(f"{'='*80}")
    print(f"Patients created: {num_patients}")
    print(f"Total resources uploaded: {total_success}")
    print(f"Total resources failed: {total_failed}")
    
    # Save JSON summary
    if run_name:
        output_dir = "fhir_data"
        os.makedirs(output_dir, exist_ok=True)
        
        output_filename = f"{run_name}.json"
        output_path = os.path.join(output_dir, output_filename)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(patients_summary, f, indent=2, ensure_ascii=False, cls=FHIRJSONEncoder)
        
        print(f"\nPatient summary saved to: {output_path}")
        print(f"   File size: {os.path.getsize(output_path) / 1024:.2f} KB")
    
    return patients_summary

if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Generate controlled synthetic patients")
    parser.add_argument("--count", type=int, default=10, help="Number of patients to generate")
    parser.add_argument("--scenario", type=str, choices=list(SCENARIOS.keys()),
                       help="Generate only this scenario (default: mixed)")
    parser.add_argument("--run-name", type=str, 
                       help="Name for the output JSON file (without extension). If not provided, JSON export is skipped.")
    args = parser.parse_args()
    
    if args.scenario:
        # Single scenario
        mix = {args.scenario: 1.0}
    else:
        # Mixed scenarios
        mix = {
            "hypertension": 0.45,
            "diabetes": 0.30,
            "copd": 0.15,
            "healthy": 0.10
        }
    
    generate_and_seed(num_patients=args.count, scenario_mix=mix, run_name=args.run_name)