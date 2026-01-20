from flask import Blueprint, request, jsonify, send_from_directory
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import math
import pydicom

# OpenTPS Imports (optional)
OPENTPS_AVAILABLE = False
try:
    opentps_paths = [
        r"C:\opentps\opentps_core",
        "/opt/opentps/opentps_core",
        os.path.expanduser("~/opentps/opentps_core"),
    ]
    for path in opentps_paths:
        if os.path.exists(path):
            sys.path.append(path)
            break
    
    from opentps.core.data import Patient
    from opentps.core.data.images import CTImage, ROIMask
    from opentps.core.data.plan import PhotonPlanDesign, ProtonPlanDesign
    from opentps.core.processing.doseCalculation.protons.mcsquareDoseCalculator import MCsquareDoseCalculator
    from opentps.core.processing.doseCalculation.doseCalculationConfig import DoseCalculationConfig
    from opentps.core.io import mcsquareIO
    from opentps.core.io.scannerReader import readScanner
    from opentps.core.processing.imageProcessing.resampler3D import resampleImage3DOnImage3D, resampleImage3D
    from opentps.core.data import DVH
    OPENTPS_AVAILABLE = True
except ImportError:
    # OpenTPS not available - routes will return error messages
    pass

import matplotlib
matplotlib.use('Agg')  # Use a non-GUI backend before importing pyplot
import matplotlib.pyplot as plt


# Define Blueprint for Plotly-based Tutorial
plotly_tutorial = Blueprint("plotly_tutorial", __name__)

# EXAMPLE DOSE COMPUTATION FUNCTION
@plotly_tutorial.route("/compute_dose")
def compute_dose_example():
    ctCalibration = readScanner(DoseCalculationConfig().scannerFolder)
    bdl = mcsquareIO.readBDL(DoseCalculationConfig().bdlFile)

    patient = Patient()
    patient.name = 'Patient'

    ctSize = 150
    ct = CTImage()
    ct.name = 'CT'
    ct.patient = patient

    huAir = -1024.
    huWater = ctCalibration.convertRSP2HU(1.)
    data = huAir * np.ones((ctSize, ctSize, ctSize))
    data[:, 50:, :] = huWater
    ct.imageArray = data

    roi = ROIMask()
    roi.patient = patient
    roi.name = 'TV'
    roi.color = (255, 0, 0)
    data = np.zeros((ctSize, ctSize, ctSize)).astype(bool)
    data[65:85, 65:85, 65:85] = True
    roi.imageArray = data

    mc2 = MCsquareDoseCalculator()
    mc2.beamModel = bdl
    mc2.ctCalibration = ctCalibration
    mc2.nbPrimaries = 1e7

    beamNames = ["Beam1", "Beam2", "Beam3"]
    gantryAngles = [0., 90., 270.]
    couchAngles = [0., 0., 0.]

    planDesign = ProtonPlanDesign()
    planDesign.ct = ct
    planDesign.targetMask = roi
    planDesign.gantryAngles = gantryAngles
    planDesign.beamNames = beamNames
    planDesign.couchAngles = couchAngles
    planDesign.calibration = ctCalibration
    planDesign.spotSpacing = 5.0
    planDesign.layerSpacing = 5.0
    planDesign.targetMargin = 5.0

    plan = planDesign.buildPlan()
    plan.PlanName = "NewPlan"

    roi = resampleImage3DOnImage3D(roi, ct)
    COM_coord = roi.centerOfMass
    COM_index = roi.getVoxelIndexFromPosition(COM_coord)
    Z_coord = COM_index[2]

    ct_slice = ct.imageArray[:, :, Z_coord].transpose(1, 0).tolist()
    contourTargetMask = roi.getBinaryContourMask()
    mask_slice = contourTargetMask.imageArray[:, :, Z_coord].transpose(1, 0).astype(int).tolist()

    output_path = 'Output'
    os.makedirs(output_path, exist_ok=True)

    image = plt.imshow(ct.imageArray[:, :, Z_coord], cmap='Blues')
    plt.colorbar(image)
    plt.contour(contourTargetMask.imageArray[:, :, Z_coord], colors="red")
    plt.title("Created CT with ROI")
    plt.savefig(os.path.join(output_path, 'SimpleCT.png'), format='png')
    plt.close()

    doseImage = mc2.computeDose(ct, plan)
    doseImage_resampled = resampleImage3DOnImage3D(doseImage, ct)
    dose_slice = doseImage_resampled.imageArray[:, :, Z_coord].transpose(1, 0).tolist()

    scoringSpacing = [2, 2, 2]
    scoringGridSize = [int(math.floor(i / j * k)) for i, j, k in zip([150,150,150], scoringSpacing, [1,1,1])]
    roiResampled = resampleImage3D(roi, origin=ct.origin, gridSize=scoringGridSize, spacing=scoringSpacing)
    target_DVH = DVH(roiResampled, doseImage)

    dose_values = target_DVH.histogram[0].tolist()
    volume_percentages = target_DVH.histogram[1].tolist()

    fig, ax = plt.subplots(1, 2, figsize=(12, 5))
    ax[0].imshow(ct.imageArray[:, :, Z_coord].transpose(1, 0), cmap='gray')
    ax[0].imshow(contourTargetMask.imageArray[:, :, Z_coord].transpose(1, 0), alpha=.2, cmap='binary')
    dose = ax[0].imshow(doseImage_resampled.imageArray[:, :, Z_coord].transpose(1, 0), cmap='jet', alpha=.2)
    plt.colorbar(dose, ax=ax[0])
    ax[1].plot(target_DVH.histogram[0], target_DVH.histogram[1], label=target_DVH.name)
    ax[1].set_xlabel("Dose (Gy)")
    ax[1].set_ylabel("Volume (%)")
    plt.grid(True)
    plt.legend()
    plt.savefig(os.path.join(output_path, 'SimpleDose.png'), format='png')
    plt.close()

    return jsonify({
        "message": "Dose Computation Completed!",
        "image": output_path,
        "ct_slice": ct_slice,  # Limit for debugging or preview
        "mask_slice": mask_slice,
        "dose_slice": dose_slice,
        "dvh": {
            "dose_values": dose_values,
            "volume_percentages": volume_percentages
        }
    })

@plotly_tutorial.route("/get_image")
def get_image():
    output_path = os.path.join(os.getcwd(), "Output")
    print(f"Looking for image at: {output_path}")
    return send_from_directory(output_path, "SimpleDose.png")
