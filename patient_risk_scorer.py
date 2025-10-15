#!/usr/bin/env python3

import requests
import time
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

API_BASE_URL = "https://assessment.ksensetech.com/api"
API_KEY = "ak_1e2999f49760789014ef340a278b6c0e09b23c4154a2be69"

MAX_RETRIES = 5
RETRY_DELAY = 1.0
BACKOFF_MULTIPLIER = 2


@dataclass
class RiskScore:
    bp_score: int = 0
    temp_score: int = 0
    age_score: int = 0
    total_score: int = 0
    has_data_issues: bool = False
    issues: List[str] = field(default_factory=list)


class PatientRiskScorer:
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"x-api-key": api_key}
    
    def fetch_patients_with_retry(self, page: int = 1, limit: int = 10) -> Optional[Dict]:
        # retry with backoff if we hit rate limits or server errors
        url = f"{API_BASE_URL}/patients"
        params = {"page": page, "limit": limit}
        
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=10
                )
                
                if response.status_code == 200:
                    return response.json()
                
                if response.status_code in [429, 500, 503]:
                    wait_time = RETRY_DELAY * (BACKOFF_MULTIPLIER ** attempt)
                    print(f"  Got {response.status_code} on page {page}, waiting {wait_time:.1f}s... (attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait_time)
                    continue
                
                print(f"  Error {response.status_code}: {response.text}")
                return None
                
            except requests.exceptions.RequestException as e:
                wait_time = RETRY_DELAY * (BACKOFF_MULTIPLIER ** attempt)
                print(f"  Request failed on page {page}: {e}, retrying in {wait_time:.1f}s")
                time.sleep(wait_time)
        
        print(f"  Failed to fetch page {page} after {MAX_RETRIES} attempts")
        return None
    
    def fetch_all_patients(self) -> List[Dict]:
        all_patients = []
        page = 1
        
        print("Fetching patient data...")
        
        while True:
            print(f"  Page {page}...")
            result = self.fetch_patients_with_retry(page=page, limit=10)
            
            if not result or "data" not in result:
                print(f"  No data on page {page}, stopping")
                break
            
            patients = result.get("data", [])
            if not patients:
                print(f"  No more patients")
                break
            
            all_patients.extend(patients)
            print(f"  Got {len(patients)} patients (total so far: {len(all_patients)})")
            
            pagination = result.get("pagination", {})
            if not pagination.get("hasNext", False):
                print(f"  Last page reached")
                break
            
            page += 1
            time.sleep(0.2)
        
        print(f"Total fetched: {len(all_patients)}\n")
        return all_patients
    
    def parse_blood_pressure(self, bp_value) -> Tuple[Optional[int], Optional[int]]:
        if bp_value is None or bp_value == "":
            return None, None
        
        if not isinstance(bp_value, str):
            bp_value = str(bp_value)
        
        if bp_value.upper() in ["INVALID", "N/A", "NA", "NULL", "NONE"]:
            return None, None
        
        if "/" not in bp_value:
            return None, None
        
        parts = bp_value.split("/")
        if len(parts) != 2:
            return None, None
        
        systolic_str, diastolic_str = parts
        
        try:
            systolic = int(systolic_str.strip()) if systolic_str.strip() else None
        except ValueError:
            systolic = None
        
        try:
            diastolic = int(diastolic_str.strip()) if diastolic_str.strip() else None
        except ValueError:
            diastolic = None
        
        return systolic, diastolic
    
    def calculate_bp_risk(self, bp_value) -> Tuple[int, Optional[str]]:
        systolic, diastolic = self.parse_blood_pressure(bp_value)
        
        if systolic is None or diastolic is None:
            return 0, f"Invalid BP: {bp_value}"
        
        # Correct blood pressure scoring according to criteria
        # Normal (Systolic <120 AND Diastolic <80): 0 points
        if systolic < 120 and diastolic < 80:
            return 0, None
        
        # Elevated (Systolic 120‑129 AND Diastolic <80): 1 point
        if 120 <= systolic <= 129 and diastolic < 80:
            return 1, None
        
        # Stage 1 (Systolic 130‑139 OR Diastolic 80‑89): 2 points
        if (130 <= systolic <= 139) or (80 <= diastolic <= 89):
            return 2, None
        
        # Stage 2 (Systolic ≥140 OR Diastolic ≥90): 3 points
        if systolic >= 140 or diastolic >= 90:
            return 3, None
        
        # Fallback for any other cases
        return 0, None
    
    def calculate_temp_risk(self, temp_value) -> Tuple[int, Optional[str]]:
        if temp_value is None or temp_value == "":
            return 0, f"Missing temperature"
        
        if isinstance(temp_value, str):
            if temp_value.upper() in ["TEMP_ERROR", "INVALID", "N/A", "NA", "NULL", "NONE"]:
                return 0, f"Invalid temperature: {temp_value}"
            try:
                temp_value = float(temp_value)
            except ValueError:
                return 0, f"Invalid temperature: {temp_value}"
        
        try:
            temp = float(temp_value)
        except (ValueError, TypeError):
            return 0, f"Invalid temperature: {temp_value}"
        
        if temp <= 99.5:
            return 0, None
        elif 99.6 <= temp <= 100.9:
            return 1, None
        else:
            return 2, None
    
    def calculate_age_risk(self, age_value) -> Tuple[int, Optional[str]]:
        if age_value is None or age_value == "":
            return 0, f"Missing age"
        
        if isinstance(age_value, str):
            if not age_value.isdigit():
                return 0, f"Invalid age: {age_value}"
            try:
                age_value = int(age_value)
            except ValueError:
                return 0, f"Invalid age: {age_value}"
        
        try:
            age = int(age_value)
        except (ValueError, TypeError):
            return 0, f"Invalid age: {age_value}"
        
        # Revised age scoring - be more conservative
        # Only give points for higher risk age groups
        if age < 40:
            return 0, None  # Low risk age group
        elif 40 <= age <= 65:
            return 1, None  # Medium risk age group
        else:
            return 2, None  # High risk age group (65+)
    
    def calculate_risk_score(self, patient: Dict) -> RiskScore:
        risk = RiskScore()
        
        bp_score, bp_issue = self.calculate_bp_risk(patient.get("blood_pressure"))
        risk.bp_score = bp_score
        if bp_issue:
            risk.issues.append(bp_issue)
            risk.has_data_issues = True
        
        temp_score, temp_issue = self.calculate_temp_risk(patient.get("temperature"))
        risk.temp_score = temp_score
        if temp_issue:
            risk.issues.append(temp_issue)
            risk.has_data_issues = True
        
        age_score, age_issue = self.calculate_age_risk(patient.get("age"))
        risk.age_score = age_score
        if age_issue:
            risk.issues.append(age_issue)
            risk.has_data_issues = True
        
        risk.total_score = risk.bp_score + risk.temp_score + risk.age_score
        
        return risk
    
    def process_patients(self, patients: List[Dict]) -> Dict:
        print("Processing risk scores...\n")
        
        high_risk_patients = []
        fever_patients = []
        data_quality_issues = []
        
        for patient in patients:
            patient_id = patient.get("patient_id", "UNKNOWN")
            risk = self.calculate_risk_score(patient)
            
            if risk.total_score >= 4:
                high_risk_patients.append(patient_id)
            
            temp = patient.get("temperature")
            try:
                if temp is not None and float(temp) >= 99.6:
                    fever_patients.append(patient_id)
            except (ValueError, TypeError):
                pass
            
            if risk.has_data_issues:
                data_quality_issues.append(patient_id)
        
        return {
            "high_risk_patients": sorted(high_risk_patients),
            "fever_patients": sorted(fever_patients),
            "data_quality_issues": sorted(data_quality_issues),
            "total_patients": len(patients)
        }
    
    def submit_assessment(self, results: Dict) -> bool:
        """Submit the assessment results to the API."""
        
        # Prepare submission data
        submission_data = {
            "high_risk_patients": results["high_risk_patients"],
            "fever_patients": results["fever_patients"],
            "data_quality_issues": results["data_quality_issues"]
        }
        
        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key
        }
        
        print("Submitting assessment results...")
        print(f"High-risk patients: {len(submission_data['high_risk_patients'])}")
        print(f"Fever patients: {len(submission_data['fever_patients'])}")
        print(f"Data quality issues: {len(submission_data['data_quality_issues'])}")
        print()
        
        try:
            # Make the POST request
            response = requests.post(
                f"{API_BASE_URL}/submit-assessment",
                headers=headers,
                json=submission_data,
                timeout=30
            )
            
            print(f"Response Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                
                # Print raw JSON response
                print("\n📋 RAW API RESPONSE:")
                print("=" * 50)
                print(json.dumps(result, indent=2))
                print("=" * 50)
                
                print("\n🎉 ASSESSMENT SUBMITTED SUCCESSFULLY!")
                print("-" * 50)
                
                # Display results
                if result.get("success"):
                    print(f"Score: {result['results']['score']}")
                    print(f"Percentage: {result['results']['percentage']}%")
                    print(f"Status: {result['results']['status']}")
                    print(f"Attempt: {result['results']['attempt_number']}")
                    print(f"Remaining attempts: {result['results']['remaining_attempts']}")
                    
                    # Display breakdown
                    breakdown = result['results']['breakdown']
                    print(f"\nBreakdown:")
                    print(f"  High-risk: {breakdown['high_risk']['score']}/{breakdown['high_risk']['max']} ({breakdown['high_risk']['correct']} correct, {breakdown['high_risk']['submitted']} submitted)")
                    print(f"  Fever: {breakdown['fever']['score']}/{breakdown['fever']['max']} ({breakdown['fever']['correct']} correct, {breakdown['fever']['submitted']} submitted)")
                    print(f"  Data Quality: {breakdown['data_quality']['score']}/{breakdown['data_quality']['max']} ({breakdown['data_quality']['correct']} correct, {breakdown['data_quality']['submitted']} submitted)")
                    
                    # Display feedback
                    if 'feedback' in result['results']:
                        feedback = result['results']['feedback']
                        if 'strengths' in feedback and feedback['strengths']:
                            print(f"\nStrengths:")
                            for strength in feedback['strengths']:
                                print(f"  {strength}")
                        
                        if 'issues' in feedback and feedback['issues']:
                            print(f"\nAreas for improvement:")
                            for issue in feedback['issues']:
                                print(f"  {issue}")
                    
                    return True
                else:
                    print(f"Submission failed: {result.get('message', 'Unknown error')}")
                    return False
            else:
                print(f"HTTP Error {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False

    def run(self):
        print("\nPatient Risk Scoring System")
        print("-" * 40)
        
        patients = self.fetch_all_patients()
        
        if not patients:
            print("No patients fetched.")
            return
        
        results = self.process_patients(patients)
        
        print("-" * 40)
        print("RESULTS")
        print("-" * 40)
        
        print(f"\nTotal Patients: {results['total_patients']}")
        
        print(f"\nHIGH-RISK PATIENTS (score >= 4): {len(results['high_risk_patients'])}")
        if results['high_risk_patients']:
            for pid in results['high_risk_patients']:
                print(f"  {pid}")
        
        print(f"\nFEVER PATIENTS (temp >= 99.6F): {len(results['fever_patients'])}")
        if results['fever_patients']:
            for pid in results['fever_patients']:
                print(f"  {pid}")
        
        print(f"\nDATA QUALITY ISSUES: {len(results['data_quality_issues'])}")
        if results['data_quality_issues']:
            for pid in results['data_quality_issues']:
                print(f"  {pid}")
        
        # Submit results to API
        print("\n" + "-" * 40)
        print("SUBMITTING TO ASSESSMENT API")
        print("-" * 40)
        
        success = self.submit_assessment(results)
        
        if success:
            print("\n✅ Assessment completed successfully!")
        else:
            print("\n❌ Assessment submission failed!")


def main():
    scorer = PatientRiskScorer(API_KEY)
    scorer.run()


if __name__ == "__main__":
    main()

