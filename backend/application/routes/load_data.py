from flask import Blueprint, request, jsonify
import os

# OpenTPS import (optional)
try:
    from opentps.core.io.dataLoader import readData
    OPENTPS_AVAILABLE = True
except ImportError:
    OPENTPS_AVAILABLE = False
    readData = None

load_data = Blueprint("load_data", __name__)

@load_data.route("/<dataset_name>", methods=["GET"])
def load_specific_dataset(dataset_name):  # ✅ Renamed
    if not OPENTPS_AVAILABLE:
        return jsonify({"error": "OpenTPS not available. Please install OpenTPS to use this feature."}), 503
    try:
        dataset_dir = os.path.join(os.getcwd(), "datasets", dataset_name)
        data = readData(dataset_dir)

        if len(data) < 2:
            return jsonify({"error": "Dataset missing RT Struct or CT"}), 400

        rt_struct = next((d for d in data if d.__class__.__name__ == "RTStruct"), None)

        roi_names = [contour.name for contour in rt_struct.contours]

        return jsonify({
            "dataset": dataset_name,
            "roi_names": roi_names,
            "message": f"{dataset_name} loaded successfully!"
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@load_data.route("/datasets", methods=["GET"])
def list_datasets():
    datasets_path = os.path.join(os.getcwd(), "datasets")
    try:
        folders = [f for f in os.listdir(datasets_path) if os.path.isdir(os.path.join(datasets_path, f))]
        return jsonify({"datasets": folders})
    except Exception as e:
        return jsonify({"error": str(e)})

@load_data.route("/datasets/<dataset_name>/rois", methods=["GET"])
def get_rois_for_dataset(dataset_name):
    if not OPENTPS_AVAILABLE:
        return jsonify({"error": "OpenTPS not available. Please install OpenTPS to use this feature."}), 503
    dataset_path = os.path.join(os.getcwd(), "datasets", dataset_name)
    try:
        data = readData(dataset_path)
        rt_struct = next((d for d in data if d.__class__.__name__ == "RTStruct"), None)
        if not rt_struct:
            return jsonify({"error": "RT Struct not found in dataset"}), 400

        roi_names = [contour.name for contour in rt_struct.contours]
        return jsonify({"roi_names": roi_names})
    except Exception as e:
        return jsonify({"error": str(e)})

