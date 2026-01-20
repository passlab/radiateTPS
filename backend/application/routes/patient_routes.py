import os
import json
from flask import Blueprint, request, jsonify
from application.models import db, Patient
from datetime import datetime

patient_routes = Blueprint('patient_routes', __name__)

PATIENT_DIR = os.path.join("patientData")

@patient_routes.route("/create", methods=["POST"])
def create_patient():
    try:
        data = request.json
        name = data.get("name")
        patient_id = data.get("id")
        birth_date = data.get("birthDate")
        sex = data.get("sex")

        # Validation
        if not patient_id:
            return jsonify({"error": "Patient ID is required"}), 400
        if not name:
            return jsonify({"error": "Patient name is required"}), 400

        # Check if patient already exists
        existing_patient = Patient.query.get(patient_id)
        if existing_patient:
            return jsonify({"error": f"Patient with ID {patient_id} already exists"}), 400

        # Parse birth date if provided
        birth_date_obj = None
        if birth_date:
            try:
                birth_date_obj = datetime.strptime(birth_date, "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"error": "Invalid birth date format. Use YYYY-MM-DD"}), 400

        # Create patient in database
        patient = Patient(
            id=patient_id,
            name=name,
            birth_date=birth_date_obj,
            sex=sex
        )

        db.session.add(patient)
        db.session.commit()

        # Also save to JSON for backward compatibility (optional)
        if not os.path.exists(PATIENT_DIR):
            os.makedirs(PATIENT_DIR)

        patient_json = {
            "name": name,
            "id": patient_id,
            "birthDate": birth_date,
            "sex": sex
        }

        path = os.path.join(PATIENT_DIR, f"{patient_id}.json")
        with open(path, "w") as f:
            json.dump(patient_json, f)

        return jsonify({"success": True, "message": f"Patient {name} saved.", "patient": patient.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create patient: {str(e)}"}), 500

@patient_routes.route("/load", methods=["GET"])
def load_patients():
    try:
        # Load from database (primary source)
        patients = Patient.query.all()
        patient_list = [patient.to_dict() for patient in patients]

        # Also check JSON files for any patients not in database (backward compatibility)
        if os.path.exists(PATIENT_DIR):
            patient_files = [f for f in os.listdir(PATIENT_DIR) if f.endswith(".json")]
            json_patient_ids = {p["id"] for p in patient_list}
            
            for filename in patient_files:
                try:
                    with open(os.path.join(PATIENT_DIR, filename), "r") as f:
                        json_patient = json.load(f)
                        # Only add if not already in database
                        if json_patient.get("id") not in json_patient_ids:
                            patient_list.append(json_patient)
                except Exception:
                    continue  # Skip invalid JSON files

        return jsonify(patient_list), 200

    except Exception as e:
        return jsonify({"error": f"Failed to load patients: {str(e)}"}), 500
