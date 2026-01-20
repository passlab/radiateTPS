import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import math 
import pydicom
import json
import pickle
from flask import Blueprint, request, jsonify, send_from_directory
from application.models import db, Patient, CTScan, ROI, TreatmentPlan, DoseResult
from application.config import config
from datetime import datetime

# OpenTPS Imports (optional - app can run without OpenTPS for basic routes)
OPENTPS_AVAILABLE = False
try:
    # Try to find OpenTPS - adjust path as needed for your system
    opentps_paths = [
        r"C:\opentps\opentps_core",  # Windows default
        "/opt/opentps/opentps_core",  # Linux/Mac alternative
        os.path.expanduser("~/opentps/opentps_core"),  # User home directory
    ]
    for path in opentps_paths:
        if os.path.exists(path):
            sys.path.append(path)
            break
    
    from opentps.core.data import Patient as OpenTPSPatient
    from opentps.core.data.images import CTImage, ROIMask
    from opentps.core.data.plan import PhotonPlanDesign, ProtonPlanDesign
    from opentps.core.processing.doseCalculation.protons.mcsquareDoseCalculator import MCsquareDoseCalculator
    from opentps.core.processing.doseCalculation.doseCalculationConfig import DoseCalculationConfig
    from opentps.core.io import mcsquareIO
    from opentps.core.io.scannerReader import readScanner
    from opentps.core.processing.imageProcessing.resampler3D import resampleImage3DOnImage3D, resampleImage3D
    from opentps.core.data import DVH
    from opentps.core.io.dataLoader import readData
    OPENTPS_AVAILABLE = True
    print("✅ OpenTPS loaded successfully")
except ImportError as e:
    print(f"⚠️  OpenTPS not available: {e}")
    print("   App will run in limited mode (basic routes only)")

import matplotlib
matplotlib.use('Agg')  # Use a non-GUI backend before importing pyplot

# Define Blueprint
main = Blueprint("main", __name__)
UPLOAD_FOLDER = config.UPLOAD_FOLDER
OUTPUT_FOLDER = config.OUTPUT_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# In-memory cache for dose images (keyed by ct_scan_id)
# This avoids recomputing dose on every slice request
_dose_image_cache = {}


# ==========================
# 🏥 Patient Management
# ==========================
@main.route("/patients", methods=["POST", "GET"])
def manage_patients():
    """Patient management endpoint (delegates to patient_routes)"""
    if request.method == "POST":
        return jsonify({"message": "Use /patients/patients/create endpoint"}), 400
    elif request.method == "GET":
        return jsonify({"message": "Use /patients/patients/load endpoint"}), 400


# ==========================
# 📄 CT Data Management
# ==========================
@main.route("/ct", methods=["POST", "GET"])
def manage_ct():
    """Upload or load CT scan data"""
    if request.method == "POST":
        return upload_ct()
    elif request.method == "GET":
        return get_ct_scans()


def upload_ct():
    """Upload a CT scan from dataset or DICOM files"""
    try:
        data = request.get_json() if request.is_json else {}
        patient_id = data.get("patient_id") or request.form.get("patient_id")
        dataset_name = data.get("dataset_name") or request.form.get("dataset_name")
        ct_name = data.get("name") or request.form.get("name", "CT Scan")
        
        if not patient_id:
            return jsonify({"error": "patient_id is required"}), 400
        
        # Check if patient exists
        patient = Patient.query.get(patient_id)
        if not patient:
            return jsonify({"error": f"Patient with ID {patient_id} not found"}), 404
        
        ct_scan = None
        
        # Option 1: Load from dataset
        if dataset_name:
            if not OPENTPS_AVAILABLE:
                return jsonify({"error": "OpenTPS required to load from dataset"}), 503
            
            try:
                dataset_path = os.path.join(os.getcwd(), "datasets", dataset_name)
                if not os.path.exists(dataset_path):
                    return jsonify({"error": f"Dataset {dataset_name} not found"}), 404
                
                # Load data using OpenTPS
                data_objects = readData(dataset_path)
                ct_image = next((d for d in data_objects if isinstance(d, CTImage)), None)
                
                if not ct_image:
                    return jsonify({"error": "CT image not found in dataset"}), 400
                
                # Create CT scan record
                ct_scan = CTScan(
                    patient_id=patient_id,
                    name=ct_name,
                    file_path=dataset_path,
                    dataset_name=dataset_name,
                    slice_count=ct_image.imageArray.shape[2] if hasattr(ct_image, 'imageArray') else None,
                    spacing=json.dumps(list(ct_image.spacing)) if hasattr(ct_image, 'spacing') else None,
                    origin=json.dumps(list(ct_image.origin)) if hasattr(ct_image, 'origin') else None,
                    grid_size=json.dumps(list(ct_image.imageArray.shape)) if hasattr(ct_image, 'imageArray') else None
                )
                
            except Exception as e:
                return jsonify({"error": f"Failed to load dataset: {str(e)}"}), 500
        
        # Option 2: Upload DICOM files (future implementation)
        elif request.files:
            # TODO: Handle DICOM file upload
            return jsonify({"error": "DICOM file upload not yet implemented"}), 501
        
        else:
            return jsonify({"error": "Either dataset_name or DICOM files required"}), 400
        
        if ct_scan:
            db.session.add(ct_scan)
            db.session.commit()
            
            return jsonify({
                "success": True,
                "message": f"CT scan '{ct_name}' uploaded successfully",
                "ct_scan": ct_scan.to_dict()
            }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to upload CT: {str(e)}"}), 500


def get_ct_scans():
    """Get CT scans for a patient or all CT scans"""
    try:
        patient_id = request.args.get("patient_id")
        ct_scan_id = request.args.get("ct_scan_id")
        
        if ct_scan_id:
            # Get specific CT scan
            ct_scan = CTScan.query.get(ct_scan_id)
            if not ct_scan:
                return jsonify({"error": f"CT scan with ID {ct_scan_id} not found"}), 404
            return jsonify({
                "success": True,
                "ct_scans": [ct_scan.to_dict()],
                "count": 1
            }), 200
        elif patient_id:
            # Get CT scans for specific patient
            ct_scans = CTScan.query.filter_by(patient_id=patient_id).all()
        else:
            # Get all CT scans
            ct_scans = CTScan.query.all()
        
        return jsonify({
            "success": True,
            "ct_scans": [ct.to_dict() for ct in ct_scans],
            "count": len(ct_scans)
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve CT scans: {str(e)}"}), 500


@main.route("/ct/<int:ct_id>/slice/<int:slice_num>", methods=["GET"])
def get_ct_slice(ct_id, slice_num):
    """Get a specific CT slice as 2D array
    Supports different views: axial (default), coronal, sagittal
    Query parameter: ?view=axial|coronal|sagittal
    """
    if not OPENTPS_AVAILABLE:
        return jsonify({"error": "OpenTPS required to load CT slices"}), 503
    
    try:
        # Get view parameter (default to axial)
        view = request.args.get('view', 'axial').lower()
        if view not in ['axial', 'coronal', 'sagittal']:
            view = 'axial'
        
        # Get CT scan from database
        ct_scan = CTScan.query.get(ct_id)
        if not ct_scan:
            return jsonify({"error": f"CT scan with ID {ct_id} not found"}), 404
        
        # Load CT image from dataset
        if not ct_scan.dataset_name:
            return jsonify({"error": "CT scan must be loaded from dataset"}), 400
        
        dataset_path = ct_scan.file_path
        if not os.path.exists(dataset_path):
            return jsonify({"error": f"Dataset path not found: {dataset_path}"}), 404
        
        # Load data using OpenTPS
        data_objects = readData(dataset_path)
        ct_image = next((d for d in data_objects if isinstance(d, CTImage)), None)
        
        if not ct_image or not hasattr(ct_image, 'imageArray'):
            return jsonify({"error": "CT image not found or invalid"}), 400
        
        # Get CT image dimensions: [X, Y, Z] = [width, height, depth]
        ct_shape = ct_image.imageArray.shape
        x_dim, y_dim, z_dim = ct_shape[0], ct_shape[1], ct_shape[2]
        
        # Debug: Check if ROIMask objects are loaded directly
        roi_masks_loaded = [d for d in data_objects if isinstance(d, ROIMask)]
        if roi_masks_loaded:
            print(f"🔍 Debug: Found {len(roi_masks_loaded)} ROIMask objects in dataset")
            for rm in roi_masks_loaded[:3]:
                print(f"   - {rm.name if hasattr(rm, 'name') else 'unnamed'}: {type(rm)}")
        
        # Extract slice based on view
        # OpenTPS uses [X, Y, Z] indexing
        if view == 'axial':
            # Axial: slice along Z-axis (top to bottom) - default
            if slice_num >= z_dim:
                return jsonify({"error": f"Slice {slice_num} exceeds Z dimension ({z_dim})"}), 400
            ct_slice = ct_image.imageArray[:, :, slice_num].transpose(1, 0).tolist()
            total_slices = z_dim
            slice_dimensions = {"width": x_dim, "height": y_dim}
            
        elif view == 'coronal':
            # Coronal: slice along Y-axis (front to back)
            if slice_num >= y_dim:
                return jsonify({"error": f"Slice {slice_num} exceeds Y dimension ({y_dim})"}), 400
            ct_slice = ct_image.imageArray[:, slice_num, :].transpose(1, 0).tolist()
            total_slices = y_dim
            slice_dimensions = {"width": x_dim, "height": z_dim}
            
        elif view == 'sagittal':
            # Sagittal: slice along X-axis (left to right)
            if slice_num >= x_dim:
                return jsonify({"error": f"Slice {slice_num} exceeds X dimension ({x_dim})"}), 400
            ct_slice = ct_image.imageArray[slice_num, :, :].transpose(1, 0).tolist()
            total_slices = x_dim
            slice_dimensions = {"width": y_dim, "height": z_dim}
        
        print(f"📊 Extracted {view} slice {slice_num}/{total_slices-1}, dimensions: {slice_dimensions}")
        
        # Try to get ROI mask slice if ROIs exist
        mask_slice = None
        roi_contours = []
        
        try:
            rt_struct = next((d for d in data_objects if d.__class__.__name__ == "RTStruct"), None)
            if rt_struct:
                # Get ROIs for this CT scan from database
                rois = ROI.query.filter_by(ct_scan_id=ct_id).all()
                
                # If no ROIs in database, auto-create ROI records from RTStruct
                if not rois:
                    for contour in rt_struct.contours:
                        # Determine ROI type and color
                        roi_type = "Target"
                        roi_color = "255,0,0"  # Red for targets
                        if any(x in contour.name.upper() for x in ["OAR", "ORGAN", "EYE", "LENS", "NERVE", "BRAINSTEM", "HIPPOCAMPUS"]):
                            roi_type = "OAR"
                            roi_color = "0,255,0"  # Green for OARs
                        elif "BODY" in contour.name.upper() or "BONE" in contour.name.upper():
                            roi_type = "Normal"
                            roi_color = "0,0,255"  # Blue for normal structures
                        
                        roi = ROI(
                            patient_id=ct_scan.patient_id,
                            ct_scan_id=ct_id,
                            name=contour.name,
                            roi_type=roi_type,
                            color=roi_color
                        )
                        db.session.add(roi)
                    try:
                        db.session.commit()
                        rois = ROI.query.filter_by(ct_scan_id=ct_id).all()
                        print(f"✅ Auto-created {len(rois)} ROIs from RTStruct")
                    except Exception as e:
                        db.session.rollback()
                        print(f"Warning: Could not auto-create ROIs: {e}")
                
                if rois:
                    # For MVP: Load first ROI mask, in production would load all
                    roi_names = [roi.name for roi in rois]
                    
                    # Debug: Check RTStruct structure - print ALL methods
                    print(f"🔍 Debug: RTStruct type: {type(rt_struct)}")
                    print(f"🔍 Debug: RTStruct module: {rt_struct.__class__.__module__}")
                    all_attrs = [attr for attr in dir(rt_struct) if not attr.startswith('_')]
                    print(f"🔍 Debug: RTStruct ALL attributes ({len(all_attrs)}): {all_attrs}")
                    # Check for mask-related methods
                    mask_methods = [m for m in all_attrs if 'mask' in m.lower() or 'roi' in m.lower() or 'convert' in m.lower() or 'raster' in m.lower()]
                    print(f"🔍 Debug: RTStruct mask/ROI methods: {mask_methods}")
                    if rt_struct.contours:
                        contour = rt_struct.contours[0]
                        print(f"🔍 Debug: First contour type: {type(contour)}")
                        print(f"🔍 Debug: First contour module: {contour.__class__.__module__}")
                        contour_attrs = [attr for attr in dir(contour) if not attr.startswith('_')]
                        print(f"🔍 Debug: First contour ALL attributes ({len(contour_attrs)}): {contour_attrs}")
                        # Check what data the contour actually contains
                        if hasattr(contour, 'points'):
                            print(f"🔍 Debug: Contour has 'points' attribute: {type(getattr(contour, 'points', None))}")
                        if hasattr(contour, 'polygons'):
                            print(f"🔍 Debug: Contour has 'polygons' attribute: {type(getattr(contour, 'polygons', None))}")
                        if hasattr(contour, 'contourData'):
                            print(f"🔍 Debug: Contour has 'contourData' attribute: {type(getattr(contour, 'contourData', None))}")
                        if hasattr(contour, 'name'):
                            print(f"🔍 Debug: First contour name: {contour.name}")
                    
                    # Method 0: Check if ROIMask objects were loaded directly from dataset
                    roi_mask_3d = None
                    if roi_masks_loaded:
                        for loaded_mask in roi_masks_loaded:
                            mask_name = getattr(loaded_mask, 'name', None)
                            if mask_name and mask_name in roi_names:
                                try:
                                    # Resample to match CT grid
                                    roi_mask_3d = resampleImage3DOnImage3D(loaded_mask, ct_image)
                                    print(f"✅ Using pre-loaded ROIMask for {mask_name}")
                                    if roi_mask_3d and hasattr(roi_mask_3d, 'imageArray'):
                                        break
                                except Exception as e:
                                    print(f"Warning: Could not resample pre-loaded mask: {e}")
                                    roi_mask_3d = None
                    
                    # Find matching contour in RTStruct and convert to ROIMask
                    if not roi_mask_3d:
                        for contour in rt_struct.contours:
                            if contour.name in roi_names:
                                try:
                                    # Convert RTStruct contour to ROIMask
                                    # Based on debug output, ROIContour has getBinaryMask() and getBinaryContourMask()
                                    roi_mask_3d = None
                                    
                                    # Method 1: Use ROIContour's built-in methods (MOST DIRECT - try this first!)
                                    try:
                                        # Try getBinaryMask() first (likely returns ROIMask with imageArray)
                                        if hasattr(contour, 'getBinaryMask'):
                                            roi_mask_3d = contour.getBinaryMask()
                                            print(f"🔍 Debug: Used getBinaryMask() for {contour.name}")
                                        # Fallback to getBinaryContourMask() (used in tutorial examples)
                                        elif hasattr(contour, 'getBinaryContourMask'):
                                            roi_mask_3d = contour.getBinaryContourMask()
                                            print(f"🔍 Debug: Used getBinaryContourMask() for {contour.name}")
                                        
                                        # If we got a mask, check if it needs resampling to match CT grid
                                        if roi_mask_3d and hasattr(roi_mask_3d, 'imageArray'):
                                            # Check if dimensions match CT image
                                            if roi_mask_3d.imageArray.shape != ct_image.imageArray.shape:
                                                # Resample ROI to match CT grid dimensions
                                                roi_mask_3d = resampleImage3DOnImage3D(roi_mask_3d, ct_image)
                                                print(f"✅ Resampled ROI mask for {contour.name} to match CT grid")
                                            else:
                                                print(f"✅ ROI mask for {contour.name} already matches CT grid")
                                    except Exception as e:
                                        print(f"Debug: Contour getBinaryMask/getBinaryContourMask failed for {contour.name}: {e}")
                                        import traceback
                                        traceback.print_exc()
                                    
                                    # Method 2: Try RTStruct's built-in conversion methods (fallback)
                                    if roi_mask_3d is None or not hasattr(roi_mask_3d, 'imageArray'):
                                        try:
                                            # Check if RTStruct can directly provide ROIMask
                                            if hasattr(rt_struct, 'getROIMask'):
                                                roi_mask_3d = rt_struct.getROIMask(contour.name)
                                            elif hasattr(rt_struct, 'getROIMaskByName'):
                                                roi_mask_3d = rt_struct.getROIMaskByName(contour.name)
                                            elif hasattr(rt_struct, 'convertContourToMask'):
                                                roi_mask_3d = rt_struct.convertContourToMask(contour.name, ct_image)
                                        except Exception as e:
                                            print(f"Debug: RTStruct method failed: {e}")
                                    
                                    # Method 3: Try to access RTStruct's internal mask storage
                                    if roi_mask_3d is None or not hasattr(roi_mask_3d, 'imageArray'):
                                        try:
                                            # Some RTStruct implementations store masks internally
                                            # Check if RTStruct has a masks dictionary or list
                                            if hasattr(rt_struct, 'masks') and isinstance(rt_struct.masks, dict):
                                                roi_mask_3d = rt_struct.masks.get(contour.name)
                                            elif hasattr(rt_struct, 'roiMasks') and isinstance(rt_struct.roiMasks, dict):
                                                roi_mask_3d = rt_struct.roiMasks.get(contour.name)
                                            
                                            # If found, resample to CT grid
                                            if roi_mask_3d and hasattr(roi_mask_3d, 'imageArray'):
                                                roi_mask_3d = resampleImage3DOnImage3D(roi_mask_3d, ct_image)
                                        except Exception as e:
                                            print(f"Debug: Internal mask access failed: {e}")
                                    
                                    # Method 4: Try RTStruct method to get mask for specific ROI name
                                    if roi_mask_3d is None or not hasattr(roi_mask_3d, 'imageArray'):
                                        try:
                                            # Try calling RTStruct methods (but NOT __getitem__ since it might be a list)
                                            # Check if it's actually a dict-like object first
                                            if isinstance(rt_struct, dict):
                                                roi_mask_3d = rt_struct.get(contour.name)
                                            elif hasattr(rt_struct, 'getMask'):
                                                roi_mask_3d = rt_struct.getMask(contour.name)
                                            elif hasattr(rt_struct, 'getMaskForROI'):
                                                roi_mask_3d = rt_struct.getMaskForROI(contour.name, ct_image)
                                            
                                            if roi_mask_3d and hasattr(roi_mask_3d, 'imageArray'):
                                                roi_mask_3d = resampleImage3DOnImage3D(roi_mask_3d, ct_image)
                                        except Exception as e:
                                            print(f"Debug: RTStruct getMask method failed: {e}")
                                    
                                    # Method 5: Try to manually create ROIMask from contour polygon data
                                    if roi_mask_3d is None or not hasattr(roi_mask_3d, 'imageArray'):
                                        try:
                                            # Check if contour has polygon/point data we can rasterize
                                            # RTStruct contours typically have points or polygons
                                            if hasattr(contour, 'points') or hasattr(contour, 'polygons') or hasattr(contour, 'contourData'):
                                                # Try to use OpenTPS's built-in conversion if available
                                                # Some RTStruct implementations can convert on-the-fly
                                                if hasattr(rt_struct, 'createMaskFromContour'):
                                                    roi_mask_3d = rt_struct.createMaskFromContour(contour.name, ct_image)
                                                elif hasattr(rt_struct, 'rasterizeContour'):
                                                    roi_mask_3d = rt_struct.rasterizeContour(contour.name, ct_image)
                                                elif hasattr(contour, 'createMask'):
                                                    roi_mask_3d = contour.createMask(ct_image)
                                                elif hasattr(contour, 'rasterize'):
                                                    roi_mask_3d = contour.rasterize(ct_image)
                                            
                                            if roi_mask_3d and hasattr(roi_mask_3d, 'imageArray'):
                                                roi_mask_3d = resampleImage3DOnImage3D(roi_mask_3d, ct_image)
                                        except Exception as e:
                                            print(f"Debug: Manual mask creation failed: {e}")
                                            import traceback
                                            traceback.print_exc()
                                    
                                    # Extract slice from 3D mask based on view
                                    if roi_mask_3d and hasattr(roi_mask_3d, 'imageArray'):
                                        try:
                                            if len(roi_mask_3d.imageArray.shape) == 3:
                                                # Extract slice based on view (same as CT slice extraction)
                                                if view == 'axial':
                                                    if slice_num < roi_mask_3d.imageArray.shape[2]:
                                                        mask_data = roi_mask_3d.imageArray[:, :, slice_num]
                                                    else:
                                                        continue
                                                elif view == 'coronal':
                                                    if slice_num < roi_mask_3d.imageArray.shape[1]:
                                                        mask_data = roi_mask_3d.imageArray[:, slice_num, :]
                                                    else:
                                                        continue
                                                elif view == 'sagittal':
                                                    if slice_num < roi_mask_3d.imageArray.shape[0]:
                                                        mask_data = roi_mask_3d.imageArray[slice_num, :, :]
                                                    else:
                                                        continue
                                                
                                                # Normalize to 0-1 range if needed
                                                if mask_data.dtype != bool:
                                                    mask_data = (mask_data > 0).astype(int)
                                                else:
                                                    mask_data = mask_data.astype(int)
                                                mask_slice = mask_data.transpose(1, 0).tolist()
                                                print(f"✅ Extracted ROI mask slice for {contour.name} at {view} slice {slice_num}")
                                            elif len(roi_mask_3d.imageArray.shape) == 2:
                                                # Already 2D, just normalize and transpose
                                                mask_data = roi_mask_3d.imageArray
                                                if mask_data.dtype != bool:
                                                    mask_data = (mask_data > 0).astype(int)
                                                else:
                                                    mask_data = mask_data.astype(int)
                                                mask_slice = mask_data.transpose(1, 0).tolist()
                                                print(f"✅ Extracted 2D ROI mask for {contour.name}")
                                        except Exception as e:
                                            print(f"⚠️  Error extracting slice from ROI mask: {e}")
                                    else:
                                        # Debug: Print what we actually got
                                        if roi_mask_3d:
                                            print(f"⚠️  ROI mask for {contour.name} has no imageArray. Type: {type(roi_mask_3d)}, Attributes: {dir(roi_mask_3d)[:10]}")
                                        else:
                                            print(f"⚠️  ROI mask for {contour.name} is None - conversion failed")
                                    
                                    # Store ROI info for display
                                    roi_color = next((roi.color for roi in rois if roi.name == contour.name), "255,0,0")
                                    roi_contours.append({
                                        "name": contour.name,
                                        "color": roi_color
                                    })
                                    
                                    # For MVP: only load first ROI that works
                                    if mask_slice is not None:
                                        break
                                except Exception as e:
                                    print(f"Warning: Could not extract ROI mask for {contour.name}: {e}")
                                    import traceback
                                    traceback.print_exc()
                                    continue
                    else:
                        # We already got a mask from pre-loaded ROIMask objects
                        pass
        except Exception as e:
            print(f"Warning: Could not load ROI data: {e}")
            import traceback
            traceback.print_exc()
        
        # Try to get dose slice if dose data exists
        dose_slice = None
        try:
            # Debug: Print all data object types to see what's available
            print(f"🔍 Debug: Checking for dose data in {len(data_objects)} data objects...")
            for i, obj in enumerate(data_objects):
                obj_type = obj.__class__.__name__
                obj_name = getattr(obj, 'name', None)
                has_image_array = hasattr(obj, 'imageArray')
                print(f"   Object {i}: {obj_type}, name={obj_name}, has_imageArray={has_image_array}")
            
            # Check if dose data exists in dataset (some datasets may have pre-computed dose)
            # Dose images in OpenTPS typically have 'imageArray' attribute like CTImage
            dose_objects = [d for d in data_objects if hasattr(d, 'imageArray') and 
                          (d.__class__.__name__ == "DoseImage" or 
                           'dose' in d.__class__.__name__.lower() or
                           (hasattr(d, 'name') and d.name and 'dose' in str(d.name).lower()))]
            
            print(f"🔍 Found {len(dose_objects)} potential dose image(s) after filtering")
            
            if dose_objects:
                print(f"🔍 Found {len(dose_objects)} potential dose image(s) in dataset")
                # Use first dose image found
                dose_image_3d = dose_objects[0]
                
                # Resample dose to match CT grid if dimensions don't match
                if dose_image_3d.imageArray.shape != ct_image.imageArray.shape:
                    print(f"📐 Resampling dose image to match CT grid...")
                    dose_image_3d = resampleImage3DOnImage3D(dose_image_3d, ct_image)
                    print(f"✅ Dose image resampled to match CT grid")
                
                # Extract slice based on view (same logic as CT slice extraction)
                if view == 'axial':
                    if slice_num < dose_image_3d.imageArray.shape[2]:
                        dose_data = dose_image_3d.imageArray[:, :, slice_num]
                    else:
                        dose_data = None
                elif view == 'coronal':
                    if slice_num < dose_image_3d.imageArray.shape[1]:
                        dose_data = dose_image_3d.imageArray[:, slice_num, :]
                    else:
                        dose_data = None
                elif view == 'sagittal':
                    if slice_num < dose_image_3d.imageArray.shape[0]:
                        dose_data = dose_image_3d.imageArray[slice_num, :, :]
                    else:
                        dose_data = None
                
                if dose_data is not None:
                    dose_slice = dose_data.transpose(1, 0).tolist()
                    print(f"✅ Extracted dose slice for {view} view, slice {slice_num}")
                else:
                    print(f"⚠️  Dose slice {slice_num} out of range for {view} view")
            else:
                # Check if there's a DoseResult record for this CT scan
                dose_results = DoseResult.query.filter_by(ct_scan_id=ct_id).filter_by(computation_status='completed').all()
                if dose_results:
                    print(f"ℹ️  Found {len(dose_results)} DoseResult record(s) for CT scan {ct_id}")
                    
                    # Check cache first (avoid recomputing on every slice request)
                    if ct_id in _dose_image_cache:
                        print(f"✅ Using cached dose image for CT scan {ct_id}")
                        dose_image_3d = _dose_image_cache[ct_id]
                    else:
                        # Get the most recent dose result
                        dose_result = dose_results[0]  # Use first/most recent
                        
                        # Try to load dose image from saved file
                        if dose_result.dose_file_path and os.path.exists(dose_result.dose_file_path):
                            print(f"📂 Loading dose image from file: {dose_result.dose_file_path}")
                            try:
                                # Check if it's a .npy file (numpy array) or .pkl file (pickle)
                                if dose_result.dose_file_path.endswith('.npy'):
                                    # Load numpy array directly
                                    dose_array = np.load(dose_result.dose_file_path)
                                    # Wrap it in a simple object
                                    class SimpleDose:
                                        def __init__(self, array):
                                            self.imageArray = array
                                            self.name = 'Dose'
                                            self.spacing = [0.468, 0.468, 1.0]
                                            self.origin = [-120.0, -120.0, -797.5]
                                    dose_image_3d = SimpleDose(dose_array)
                                    print(f"✅ Loaded dose from .npy file, shape: {dose_array.shape}")
                                else:
                                    # Try to load as pickle
                                    with open(dose_result.dose_file_path, 'rb') as f:
                                        loaded_obj = pickle.load(f)
                                    
                                    # Handle different object types
                                    if hasattr(loaded_obj, 'imageArray'):
                                        # It's already a proper object
                                        dose_image_3d = loaded_obj
                                    elif isinstance(loaded_obj, dict) and 'imageArray' in loaded_obj:
                                        # It's a dict, create a simple object
                                        class SimpleDose:
                                            def __init__(self, data):
                                                self.imageArray = data.get('imageArray')
                                                self.name = data.get('name', 'Dose')
                                                self.spacing = data.get('spacing', [0.468, 0.468, 1.0])
                                                self.origin = data.get('origin', [-120.0, -120.0, -797.5])
                                        dose_image_3d = SimpleDose(loaded_obj)
                                    elif isinstance(loaded_obj, np.ndarray):
                                        # It's just a numpy array, wrap it
                                        class SimpleDose:
                                            def __init__(self, array):
                                                self.imageArray = array
                                                self.name = 'Dose'
                                                self.spacing = [0.468, 0.468, 1.0]
                                                self.origin = [-120.0, -120.0, -797.5]
                                        dose_image_3d = SimpleDose(loaded_obj)
                                    else:
                                        print(f"⚠️  Unrecognized dose object type: {type(loaded_obj)}")
                                        dose_image_3d = None
                                
                                # Ensure the object has imageArray attribute
                                if dose_image_3d and not hasattr(dose_image_3d, 'imageArray'):
                                    print(f"⚠️  Loaded dose object doesn't have imageArray attribute")
                                    dose_image_3d = None
                                elif dose_image_3d:
                                    # Cache it for future use
                                    _dose_image_cache[ct_id] = dose_image_3d
                                    print(f"✅ Loaded and cached dose image for CT scan {ct_id}")
                                    print(f"   Dose image shape: {dose_image_3d.imageArray.shape}")
                            except Exception as e:
                                print(f"⚠️  Failed to load dose image from file: {e}")
                                import traceback
                                traceback.print_exc()
                                dose_image_3d = None
                        else:
                            if dose_result.dose_file_path:
                                print(f"⚠️  Dose file path exists but file not found: {dose_result.dose_file_path}")
                            else:
                                print(f"ℹ️  DoseResult exists but no dose_file_path. This is an old record from before dose saving was implemented.")
                            dose_image_3d = None
                    
                    # If we have dose_image_3d, extract slice
                    if dose_image_3d and hasattr(dose_image_3d, 'imageArray'):
                        # Resample to match CT grid if needed
                        if dose_image_3d.imageArray.shape != ct_image.imageArray.shape:
                            dose_image_3d = resampleImage3DOnImage3D(dose_image_3d, ct_image)
                        
                        # Extract slice based on view
                        if view == 'axial':
                            if slice_num < dose_image_3d.imageArray.shape[2]:
                                dose_data = dose_image_3d.imageArray[:, :, slice_num]
                            else:
                                dose_data = None
                        elif view == 'coronal':
                            if slice_num < dose_image_3d.imageArray.shape[1]:
                                dose_data = dose_image_3d.imageArray[:, slice_num, :]
                            else:
                                dose_data = None
                        elif view == 'sagittal':
                            if slice_num < dose_image_3d.imageArray.shape[0]:
                                dose_data = dose_image_3d.imageArray[slice_num, :, :]
                            else:
                                dose_data = None
                        
                        if dose_data is not None:
                            dose_slice = dose_data.transpose(1, 0).tolist()
                            print(f"✅ Extracted dose slice from DoseResult for {view} view, slice {slice_num}")
                        else:
                            print(f"⚠️  Dose slice {slice_num} out of range for {view} view")
                    else:
                        print(f"ℹ️  DoseResult exists but dose image not available. Dose needs to be computed and saved.")
        except Exception as e:
            print(f"Warning: Could not load dose data: {e}")
            import traceback
            traceback.print_exc()
        
        return jsonify({
            "success": True,
            "ct_slice": ct_slice,
            "mask_slice": mask_slice,
            "dose_slice": dose_slice,
            "roi_contours": roi_contours,
            "slice_num": slice_num,
            "view": view,
            "total_slices": total_slices,
            "dimensions": slice_dimensions
        }), 200
        
    except Exception as e:
        import traceback
        error_msg = f"Failed to load CT slice: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return jsonify({"error": f"Failed to load CT slice: {str(e)}"}), 500


# ==========================
# 🎯 ROI Management
# ==========================
@main.route("/roi", methods=["POST", "GET"])
def manage_roi():
    """Create or retrieve ROIs"""
    if request.method == "POST":
        return create_roi()
    elif request.method == "GET":
        return get_rois()


def create_roi():
    """Create a new ROI"""
    try:
        data = request.get_json()
        patient_id = data.get("patient_id")
        ct_scan_id = data.get("ct_scan_id")
        roi_name = data.get("name")
        roi_type = data.get("roi_type", "Target")
        color = data.get("color", "255,0,0")
        
        if not patient_id or not roi_name:
            return jsonify({"error": "patient_id and name are required"}), 400
        
        # Check if patient exists
        patient = Patient.query.get(patient_id)
        if not patient:
            return jsonify({"error": f"Patient with ID {patient_id} not found"}), 404
        
        # If ct_scan_id provided, verify it exists
        if ct_scan_id:
            ct_scan = CTScan.query.get(ct_scan_id)
            if not ct_scan:
                return jsonify({"error": f"CT scan with ID {ct_scan_id} not found"}), 404
            if ct_scan.patient_id != patient_id:
                return jsonify({"error": "CT scan does not belong to this patient"}), 400
        
        # Create ROI
        roi = ROI(
            patient_id=patient_id,
            ct_scan_id=ct_scan_id,
            name=roi_name,
            roi_type=roi_type,
            color=color
        )
        
        db.session.add(roi)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"ROI '{roi_name}' created successfully",
            "roi": roi.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create ROI: {str(e)}"}), 500


def get_rois():
    """Get ROIs for a patient or CT scan"""
    try:
        patient_id = request.args.get("patient_id")
        ct_scan_id = request.args.get("ct_scan_id")
        
        query = ROI.query
        
        if patient_id:
            query = query.filter_by(patient_id=patient_id)
        if ct_scan_id:
            query = query.filter_by(ct_scan_id=ct_scan_id)
        
        rois = query.all()
        
        return jsonify({
            "success": True,
            "rois": [roi.to_dict() for roi in rois],
            "count": len(rois)
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve ROIs: {str(e)}"}), 500


# ==========================
# ☢️ Compute Dose
# ==========================
@main.route("/dose", methods=["POST"])
def compute_dose():
    """Compute dose based on treatment plan parameters"""
    if not OPENTPS_AVAILABLE:
        return jsonify({"error": "OpenTPS required for dose computation"}), 503
    
    try:
        data = request.get_json()
        plan_id = data.get("plan_id")
        
        # If plan_id provided, load existing plan
        if plan_id:
            plan = TreatmentPlan.query.get(plan_id)
            if not plan:
                return jsonify({"error": f"Plan with ID {plan_id} not found"}), 404
        else:
            # Create plan from parameters
            plan = create_plan_from_params(data)
            if not plan:
                return jsonify({"error": "Failed to create plan"}), 400
        
        # Compute dose
        result = compute_dose_for_plan(plan)
        
        if result:
            return jsonify({
                "success": True,
                "message": "Dose computation completed",
                "result": result.to_dict()
            }), 200
        else:
            return jsonify({"error": "Dose computation failed"}), 500
            
    except Exception as e:
        return jsonify({"error": f"Failed to compute dose: {str(e)}"}), 500


def create_plan_from_params(data):
    """Create a treatment plan from parameters"""
    try:
        patient_id = data.get("patient_id")
        ct_scan_id = data.get("ct_scan_id")
        plan_name = data.get("plan_name", "New Plan")
        plan_type = data.get("plan_type", "Proton")
        target_roi_id = data.get("target_roi_id")
        
        # Get beam parameters
        beam_names = data.get("beam_names", ["Beam1", "Beam2", "Beam3"])
        gantry_angles = data.get("gantry_angles", [0., 90., 270.])
        couch_angles = data.get("couch_angles", [0., 0., 0.])
        spot_spacing = data.get("spot_spacing", 5.0)
        layer_spacing = data.get("layer_spacing", 5.0)
        target_margin = data.get("target_margin", 5.0)
        
        # Verify patient and CT scan exist
        patient = Patient.query.get(patient_id)
        if not patient:
            return None
        
        ct_scan = CTScan.query.get(ct_scan_id)
        if not ct_scan:
            return None
        
        # Create plan
        plan = TreatmentPlan(
            patient_id=patient_id,
            ct_scan_id=ct_scan_id,
            plan_name=plan_name,
            plan_type=plan_type,
            beam_names=json.dumps(beam_names),
            gantry_angles=json.dumps(gantry_angles),
            couch_angles=json.dumps(couch_angles),
            spot_spacing=spot_spacing,
            layer_spacing=layer_spacing,
            target_margin=target_margin,
            target_roi_id=target_roi_id
        )
        
        db.session.add(plan)
        db.session.commit()
        
        return plan
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating plan: {e}")
        return None


def compute_dose_for_plan(plan):
    """Compute dose for a treatment plan using OpenTPS"""
    try:
        # Load CT scan data
        ct_scan = CTScan.query.get(plan.ct_scan_id)
        if not ct_scan:
            return None
        
        # Load CT image from dataset or file
        if ct_scan.dataset_name:
            dataset_path = ct_scan.file_path
            data_objects = readData(dataset_path)
            ct_image = next((d for d in data_objects if isinstance(d, CTImage)), None)
        else:
            # TODO: Load from DICOM files
            return None
        
        if not ct_image:
            return None
        
        # Load ROI if specified
        roi_mask = None
        if plan.target_roi_id:
            roi = ROI.query.get(plan.target_roi_id)
            if roi and ct_scan.dataset_name:
                # Load ROI from dataset
                data_objects = readData(ct_scan.file_path)
                rt_struct = next((d for d in data_objects if d.__class__.__name__ == "RTStruct"), None)
                if rt_struct:
                    target_contour = next((c for c in rt_struct.contours if c.name == roi.name), None)
                    if target_contour:
                        roi_mask = ROIMask()
                        roi_mask.name = roi.name
                        # Convert contour to mask (simplified - actual implementation would be more complex)
        
        # Setup dose calculator
        ct_calibration = readScanner(DoseCalculationConfig().scannerFolder)
        bdl = mcsquareIO.readBDL(DoseCalculationConfig().bdlFile)
        
        mc2 = MCsquareDoseCalculator()
        mc2.beamModel = bdl
        mc2.ctCalibration = ct_calibration
        mc2.nbPrimaries = 1e7
        
        # Create plan design
        if plan.plan_type == "Proton":
            plan_design = ProtonPlanDesign()
        else:
            plan_design = PhotonPlanDesign()
        
        plan_design.ct = ct_image
        if roi_mask:
            plan_design.targetMask = roi_mask
        plan_design.gantryAngles = json.loads(plan.gantry_angles)
        plan_design.beamNames = json.loads(plan.beam_names)
        plan_design.couchAngles = json.loads(plan.couch_angles)
        plan_design.calibration = ct_calibration
        plan_design.spotSpacing = plan.spot_spacing
        plan_design.layerSpacing = plan.layer_spacing
        plan_design.targetMargin = plan.target_margin
        
        treatment_plan = plan_design.buildPlan()
        treatment_plan.PlanName = plan.plan_name
        
        # Compute dose
        dose_image = mc2.computeDose(ct_image, treatment_plan)
        
        # Compute DVH if ROI available
        dvh_data = None
        d95 = None
        d5 = None
        mean_dose = None
        max_dose = None
        
        if roi_mask:
            roi_resampled = resampleImage3DOnImage3D(roi_mask, ct_image)
            scoring_spacing = [2, 2, 2]
            scoring_grid_size = [int(math.floor(i / j)) for i, j in zip(ct_image.imageArray.shape, scoring_spacing)]
            roi_resampled_final = resampleImage3D(roi_resampled, origin=ct_image.origin, 
                                                   gridSize=scoring_grid_size, spacing=scoring_spacing)
            target_dvh = DVH(roi_resampled_final, dose_image)
            
            d95 = float(target_dvh.D95) if hasattr(target_dvh, 'D95') else None
            d5 = float(target_dvh.D5) if hasattr(target_dvh, 'D5') else None
            mean_dose = float(target_dvh.mean) if hasattr(target_dvh, 'mean') else None
            max_dose = float(target_dvh.max) if hasattr(target_dvh, 'max') else None
            
            dvh_data = {
                "dose_values": target_dvh.histogram[0].tolist() if hasattr(target_dvh, 'histogram') else [],
                "volume_percentages": target_dvh.histogram[1].tolist() if hasattr(target_dvh, 'histogram') else []
            }
        
        # Resample dose to match CT grid for consistent viewing
        dose_resampled = resampleImage3DOnImage3D(dose_image, ct_image)
        
        # Save dose image to file for later retrieval
        dose_filename = f"dose_image_{plan.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
        dose_file_path = os.path.join(OUTPUT_FOLDER, dose_filename)
        try:
            with open(dose_file_path, 'wb') as f:
                pickle.dump(dose_resampled, f)
            print(f"✅ Saved dose image to {dose_file_path}")
            
            # Also cache it in memory for immediate use
            _dose_image_cache[plan.ct_scan_id] = dose_resampled
            print(f"✅ Cached dose image for CT scan {plan.ct_scan_id}")
        except Exception as e:
            print(f"⚠️  Failed to save dose image: {e}")
            dose_file_path = None
        
        # Save visualization image
        z_coord = int(ct_image.imageArray.shape[2] / 2) if hasattr(ct_image, 'imageArray') else 0
        img_ct = ct_image.imageArray[:, :, z_coord].transpose(1, 0) if hasattr(ct_image, 'imageArray') else None
        img_dose = dose_resampled.imageArray[:, :, z_coord].transpose(1, 0) if hasattr(dose_resampled, 'imageArray') else None
        
        if img_ct is not None and img_dose is not None:
            fig, ax = plt.subplots(1, 1, figsize=(10, 10))
            ax.imshow(img_ct, cmap='gray')
            dose_overlay = ax.imshow(img_dose, cmap='jet', alpha=0.5)
            plt.colorbar(dose_overlay, ax=ax, label='Dose (Gy)')
            plt.title(f"Dose Distribution - {plan.plan_name}")
            
            image_filename = f"dose_result_{plan.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            image_path = os.path.join(OUTPUT_FOLDER, image_filename)
            plt.savefig(image_path, format='png', dpi=150)
            plt.close()
        else:
            image_path = None
        
        # Create dose result record
        dose_result = DoseResult(
            plan_id=plan.id,
            ct_scan_id=plan.ct_scan_id,
            roi_id=plan.target_roi_id,
            dose_file_path=dose_file_path,  # Save path to dose image file
            visualization_image_path=image_path,
            d95=d95,
            d5=d5,
            mean_dose=mean_dose,
            max_dose=max_dose,
            dvh_data=json.dumps(dvh_data) if dvh_data else None,
            computation_status='completed'
        )
        
        db.session.add(dose_result)
        db.session.commit()
        
        return dose_result
        
    except Exception as e:
        db.session.rollback()
        print(f"Error computing dose: {e}")
        import traceback
        traceback.print_exc()
        return None


# ==========================
# 📊 Retrieve Results
# ==========================
@main.route("/results", methods=["GET"])
def get_results():
    """Retrieve stored CT/dose images and DVH data"""
    try:
        plan_id = request.args.get("plan_id")
        patient_id = request.args.get("patient_id")
        ct_scan_id = request.args.get("ct_scan_id")
        
        query = DoseResult.query
        
        if plan_id:
            query = query.filter_by(plan_id=plan_id)
        elif patient_id:
            # Get results for all plans of this patient
            plans = TreatmentPlan.query.filter_by(patient_id=patient_id).all()
            plan_ids = [p.id for p in plans]
            query = query.filter(DoseResult.plan_id.in_(plan_ids))
        elif ct_scan_id:
            query = query.filter_by(ct_scan_id=ct_scan_id)
        
        results = query.order_by(DoseResult.created_at.desc()).all()
        
        return jsonify({
            "success": True,
            "results": [result.to_dict() for result in results],
            "count": len(results)
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve results: {str(e)}"}), 500


@main.route("/get_image")
def get_image():
    """Get generated dose visualization image"""
    output_path = OUTPUT_FOLDER
    image_name = request.args.get("image", "SimpleDose.png")
    
    try:
        return send_from_directory(output_path, image_name)
    except Exception as e:
        return jsonify({"error": f"Image not found: {str(e)}"}), 404


# ==========================
# 💾 Plan Management
# ==========================
@main.route("/plans", methods=["POST", "GET"])
def manage_plans():
    """Save or load treatment plans"""
    if request.method == "POST":
        return save_plan()
    elif request.method == "GET":
        return get_plans()


@main.route("/plans/<int:plan_id>", methods=["GET", "PUT", "DELETE"])
def manage_plan(plan_id):
    """Get, update, or delete a specific plan"""
    if request.method == "GET":
        return get_plan(plan_id)
    elif request.method == "PUT":
        return update_plan(plan_id)
    elif request.method == "DELETE":
        return delete_plan(plan_id)


def save_plan():
    """Save a new treatment plan"""
    try:
        data = request.get_json()
        patient_id = data.get("patient_id")
        ct_scan_id = data.get("ct_scan_id")
        plan_name = data.get("plan_name", "New Plan")
        
        if not patient_id or not ct_scan_id:
            return jsonify({"error": "patient_id and ct_scan_id are required"}), 400
        
        # Verify patient and CT scan exist
        patient = Patient.query.get(patient_id)
        if not patient:
            return jsonify({"error": f"Patient with ID {patient_id} not found"}), 404
        
        ct_scan = CTScan.query.get(ct_scan_id)
        if not ct_scan:
            return jsonify({"error": f"CT scan with ID {ct_scan_id} not found"}), 404
        
        if ct_scan.patient_id != patient_id:
            return jsonify({"error": "CT scan does not belong to this patient"}), 400
        
        # Create plan
        plan = create_plan_from_params(data)
        
        if plan:
            return jsonify({
                "success": True,
                "message": f"Plan '{plan_name}' saved successfully",
                "plan": plan.to_dict()
            }), 201
        else:
            return jsonify({"error": "Failed to create plan"}), 500
            
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to save plan: {str(e)}"}), 500


def get_plans():
    """Get treatment plans"""
    try:
        patient_id = request.args.get("patient_id")
        ct_scan_id = request.args.get("ct_scan_id")
        
        query = TreatmentPlan.query
        
        if patient_id:
            query = query.filter_by(patient_id=patient_id)
        if ct_scan_id:
            query = query.filter_by(ct_scan_id=ct_scan_id)
        
        plans = query.order_by(TreatmentPlan.created_at.desc()).all()
        
        return jsonify({
            "success": True,
            "plans": [plan.to_dict() for plan in plans],
            "count": len(plans)
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve plans: {str(e)}"}), 500


def get_plan(plan_id):
    """Get a specific plan by ID"""
    try:
        plan = TreatmentPlan.query.get(plan_id)
        if not plan:
            return jsonify({"error": f"Plan with ID {plan_id} not found"}), 404
        
        # Get associated dose results
        dose_results = DoseResult.query.filter_by(plan_id=plan_id).all()
        
        plan_dict = plan.to_dict()
        plan_dict["dose_results"] = [result.to_dict() for result in dose_results]
        
        return jsonify({
            "success": True,
            "plan": plan_dict
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve plan: {str(e)}"}), 500


def update_plan(plan_id):
    """Update an existing plan"""
    try:
        plan = TreatmentPlan.query.get(plan_id)
        if not plan:
            return jsonify({"error": f"Plan with ID {plan_id} not found"}), 404
        
        data = request.get_json()
        
        # Update allowed fields
        if "plan_name" in data:
            plan.plan_name = data["plan_name"]
        if "beam_names" in data:
            plan.beam_names = json.dumps(data["beam_names"])
        if "gantry_angles" in data:
            plan.gantry_angles = json.dumps(data["gantry_angles"])
        if "couch_angles" in data:
            plan.couch_angles = json.dumps(data["couch_angles"])
        if "spot_spacing" in data:
            plan.spot_spacing = data["spot_spacing"]
        if "layer_spacing" in data:
            plan.layer_spacing = data["layer_spacing"]
        if "target_margin" in data:
            plan.target_margin = data["target_margin"]
        if "target_roi_id" in data:
            plan.target_roi_id = data["target_roi_id"]
        
        plan.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Plan '{plan.plan_name}' updated successfully",
            "plan": plan.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update plan: {str(e)}"}), 500


def delete_plan(plan_id):
    """Delete a treatment plan"""
    try:
        plan = TreatmentPlan.query.get(plan_id)
        if not plan:
            return jsonify({"error": f"Plan with ID {plan_id} not found"}), 404
        
        plan_name = plan.plan_name
        db.session.delete(plan)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Plan '{plan_name}' deleted successfully"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete plan: {str(e)}"}), 500
