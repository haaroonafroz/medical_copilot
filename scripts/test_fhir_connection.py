import requests
import json

BASE_URL = "http://localhost:8080/fhir"
PATIENT_ID = "test-patient-001"

def check_url(url, name):
    print(f"\n--- Checking {name} ---")
    print(f"GET {url}")
    try:
        resp = requests.get(url)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            # print(json.dumps(data, indent=2))
            
            if "entry" in data:
                print(f"✅ Found {len(data['entry'])} entries.")
                for i, entry in enumerate(data['entry']):
                    res = entry['resource']
                    print(f"  [{i}] Type: {res.get('resourceType')} | ID: {res.get('id')}")
                    # Check reference
                    if "subject" in res:
                        print(f"      Subject: {res['subject']}")
            else:
                print("⚠️  No 'entry' in response (Empty Bundle?)")
                print("Raw Response Keys:", data.keys())
        else:
            print(f"❌ Error: {resp.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    # 1. Check Patient
    check_url(f"{BASE_URL}/Patient/{PATIENT_ID}", "Patient Resource")
    
    # 2. Check Observations (try both subject and patient params)
    check_url(f"{BASE_URL}/Observation?subject=Patient/{PATIENT_ID}", "Labs (via subject)")
    check_url(f"{BASE_URL}/Observation?patient={PATIENT_ID}", "Labs (via patient param)")
    
    # 3. Check Medications
    check_url(f"{BASE_URL}/MedicationStatement?subject=Patient/{PATIENT_ID}", "Meds (Statement)")
    check_url(f"{BASE_URL}/MedicationRequest?subject=Patient/{PATIENT_ID}", "Meds (Request)")

    # 4. Check Conditions
    check_url(f"{BASE_URL}/Condition?subject=Patient/{PATIENT_ID}", "Conditions")