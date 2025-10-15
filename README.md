# Patient Risk Scoring System

Python script to fetch patient data from the API, calculate risk scores, and submit results to the assessment API.

## Setup

Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

```bash
python3 patient_risk_scorer.py
```

The script will fetch all patients from the API, calculate their risk scores, and automatically submit results showing:
- High-risk patients (score >= 4)
- Patients with fever (temp >= 99.6°F)
- Patients with data quality issues

## Risk Scoring

**Blood Pressure:**
- Normal (Systolic <120 AND Diastolic <80): 0 points
- Elevated (Systolic 120‑129 AND Diastolic <80): 1 point
- Stage 1 (Systolic 130‑139 OR Diastolic 80‑89): 2 points
- Stage 2 (Systolic ≥140 OR Diastolic ≥90): 3 points

**Temperature:**
- Normal (≤99.5°F): 0 points
- Low Fever (99.6-100.9°F): 1 point
- High Fever (>100.9°F): 2 points

**Age:**
- Under 40: 0 points
- 40-65: 1 point
- Over 65: 2 points

Total score = BP + Temperature + Age

## Error Handling

The script handles:
- Rate limiting (429) with exponential backoff
- Server errors (500/503) with retries
- Pagination
- Invalid/missing data

## Requirements

- Python 3.6+
- requests library
