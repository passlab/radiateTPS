"""
Tutorial Code for OpenTPS Dose Computation
-----------------------------------------
This script is based on the OpenTPS tutorial and serves as a reference.
It should not be used as the main API but can be used for testing and validation.
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import math 
import pydicom
from flask import Blueprint, request, jsonify

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


# Define Blueprint for reference (not used in main API)
tutorial = Blueprint("tutorial", __name__)

# Example dose computation function
@tutorial.route("/compute_dose")
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

# ROI mask means (Region of Interest Mask, embedded in the image) ->  the region of interest is the area that we are interested in, in this case the tumor
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

    img_ct = ct.imageArray[:, :, Z_coord].transpose(1, 0)
    contourTargetMask = roi.getBinaryContourMask()
    img_mask = contourTargetMask.imageArray[:, :, Z_coord].transpose(1, 0)

    output_path = 'Output'
    os.makedirs(output_path, exist_ok=True)

    image = plt.imshow(img_ct, cmap='Blues')
    plt.colorbar(image)
    plt.contour(img_mask, colors="red")
    plt.title("Created CT with ROI")
    plt.savefig(os.path.join(output_path, 'SimpleCT.png'), format='png')
    plt.close()

    doseImage = mc2.computeDose(ct, plan)
    img_dose = resampleImage3DOnImage3D(doseImage, ct)
    img_dose = img_dose.imageArray[:, :, Z_coord].transpose(1, 0)
    scoringSpacing = [2, 2, 2]
    scoringGridSize = [int(math.floor(i / j * k)) for i, j, k in zip([150,150,150], scoringSpacing, [1,1,1])]
    roiResampled = resampleImage3D(roi, origin=ct.origin, gridSize=scoringGridSize, spacing=scoringSpacing)
    target_DVH = DVH(roiResampled, doseImage)

    fig, ax = plt.subplots(1, 2, figsize=(12, 5))
    ax[0].imshow(img_ct, cmap='gray')
    ax[0].imshow(img_mask, alpha=.2, cmap='binary')
    dose = ax[0].imshow(img_dose, cmap='jet', alpha=.2)
    plt.colorbar(dose, ax=ax[0])
    ax[1].plot(target_DVH.histogram[0], target_DVH.histogram[1], label=target_DVH.name)
    ax[1].set_xlabel("Dose (Gy)")
    ax[1].set_ylabel("Volume (%)")
    plt.grid(True)
    plt.legend()
    plt.savefig(os.path.join(output_path, 'SimpleDose.png'), format='png')
    # plt.show()

    print('D95 = ' + str(target_DVH.D95) + ' Gy')
    print('D5 = ' + str(target_DVH.D5) + ' Gy')
    print('D5 - D95 =  {} Gy'.format(target_DVH.D5 - target_DVH.D95))

    return jsonify({"message": "Dose Computation Completed!", "image": output_path})

from flask import send_from_directory

@tutorial.route("/get_image")
def get_image():
    output_path = os.path.join(os.getcwd(), "Output")
    print(f"Looking for image at: {output_path}")
    return send_from_directory(output_path, "SimpleDose.png")