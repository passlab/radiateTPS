"""
Database Models for RadiateTPS
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()


class Patient(db.Model):
    """Patient model"""
    __tablename__ = 'patients'
    
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    birth_date = db.Column(db.Date)
    sex = db.Column(db.String(1))  # M, F, or Other
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    ct_scans = db.relationship('CTScan', backref='patient', lazy=True, cascade='all, delete-orphan')
    rois = db.relationship('ROI', backref='patient', lazy=True, cascade='all, delete-orphan')
    plans = db.relationship('TreatmentPlan', backref='patient', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'birthDate': self.birth_date.isoformat() if self.birth_date else None,
            'sex': self.sex,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class CTScan(db.Model):
    """CT Scan model"""
    __tablename__ = 'ct_scans'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(50), db.ForeignKey('patients.id'), nullable=False)
    name = db.Column(db.String(200))
    file_path = db.Column(db.String(500))  # Path to DICOM files
    dataset_name = db.Column(db.String(200))  # If loaded from dataset
    slice_count = db.Column(db.Integer)
    spacing = db.Column(db.String(100))  # JSON: [x, y, z]
    origin = db.Column(db.String(100))  # JSON: [x, y, z]
    grid_size = db.Column(db.String(100))  # JSON: [x, y, z]
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    rois = db.relationship('ROI', backref='ct_scan', lazy=True, cascade='all, delete-orphan')
    dose_results = db.relationship('DoseResult', backref='ct_scan', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'name': self.name,
            'file_path': self.file_path,
            'dataset_name': self.dataset_name,
            'slice_count': self.slice_count,
            'spacing': json.loads(self.spacing) if self.spacing else None,
            'origin': json.loads(self.origin) if self.origin else None,
            'grid_size': json.loads(self.grid_size) if self.grid_size else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ROI(db.Model):
    """Region of Interest (ROI) model"""
    __tablename__ = 'rois'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(50), db.ForeignKey('patients.id'), nullable=False)
    ct_scan_id = db.Column(db.Integer, db.ForeignKey('ct_scans.id'))
    name = db.Column(db.String(200), nullable=False)
    roi_type = db.Column(db.String(50))  # Target, OAR (Organ at Risk), etc.
    color = db.Column(db.String(20))  # RGB color as string
    mask_file_path = db.Column(db.String(500))  # Path to ROI mask file
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    dose_results = db.relationship('DoseResult', backref='roi', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'ct_scan_id': self.ct_scan_id,
            'name': self.name,
            'roi_type': self.roi_type,
            'color': self.color,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class TreatmentPlan(db.Model):
    """Treatment Plan model"""
    __tablename__ = 'treatment_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(50), db.ForeignKey('patients.id'), nullable=False)
    ct_scan_id = db.Column(db.Integer, db.ForeignKey('ct_scans.id'), nullable=False)
    plan_name = db.Column(db.String(200), nullable=False)
    plan_type = db.Column(db.String(50))  # Proton, Photon
    beam_names = db.Column(db.Text)  # JSON array
    gantry_angles = db.Column(db.Text)  # JSON array
    couch_angles = db.Column(db.Text)  # JSON array
    spot_spacing = db.Column(db.Float)
    layer_spacing = db.Column(db.Float)
    target_margin = db.Column(db.Float)
    target_roi_id = db.Column(db.Integer, db.ForeignKey('rois.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    dose_results = db.relationship('DoseResult', backref='plan', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'ct_scan_id': self.ct_scan_id,
            'plan_name': self.plan_name,
            'plan_type': self.plan_type,
            'beam_names': json.loads(self.beam_names) if self.beam_names else [],
            'gantry_angles': json.loads(self.gantry_angles) if self.gantry_angles else [],
            'couch_angles': json.loads(self.couch_angles) if self.couch_angles else [],
            'spot_spacing': self.spot_spacing,
            'layer_spacing': self.layer_spacing,
            'target_margin': self.target_margin,
            'target_roi_id': self.target_roi_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DoseResult(db.Model):
    """Dose Calculation Result model"""
    __tablename__ = 'dose_results'
    
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('treatment_plans.id'), nullable=False)
    ct_scan_id = db.Column(db.Integer, db.ForeignKey('ct_scans.id'), nullable=False)
    roi_id = db.Column(db.Integer, db.ForeignKey('rois.id'))
    dose_file_path = db.Column(db.String(500))  # Path to dose image file
    dvh_file_path = db.Column(db.String(500))  # Path to DVH data file
    visualization_image_path = db.Column(db.String(500))  # Path to visualization image
    d95 = db.Column(db.Float)  # Dose covering 95% of volume
    d5 = db.Column(db.Float)  # Dose covering 5% of volume
    mean_dose = db.Column(db.Float)
    max_dose = db.Column(db.Float)
    dvh_data = db.Column(db.Text)  # JSON: {dose_values: [], volume_percentages: []}
    computation_status = db.Column(db.String(50), default='pending')  # pending, computing, completed, failed
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'plan_id': self.plan_id,
            'ct_scan_id': self.ct_scan_id,
            'roi_id': self.roi_id,
            'dose_file_path': self.dose_file_path,
            'dvh_file_path': self.dvh_file_path,
            'visualization_image_path': self.visualization_image_path,
            'd95': self.d95,
            'd5': self.d5,
            'mean_dose': self.mean_dose,
            'max_dose': self.max_dose,
            'dvh_data': json.loads(self.dvh_data) if self.dvh_data else None,
            'computation_status': self.computation_status,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

