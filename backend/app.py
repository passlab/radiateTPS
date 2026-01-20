import os
from flask import Flask, send_from_directory, send_file
from flask_cors import CORS
from application.config import config
from application.models import db
from application.routes.main import main
from application.routes.tutorial1 import tutorial
from application.routes.plotly_tutorial import plotly_tutorial
from application.routes.patient_routes import patient_routes

# Get absolute path to the frontend folder
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))
print(f"📁 Frontend path: {frontend_path}")
print(f"📁 Frontend exists: {os.path.exists(frontend_path)}")
if os.path.exists(frontend_path):
    print(f"📁 Files in frontend: {os.listdir(frontend_path)[:5]}")

# Use Flask's default static file serving
app = Flask(__name__, 
            static_folder=frontend_path, 
            static_url_path="/static")

# Load configuration
app.config.from_object(config)

# Enable CORS for frontend access
CORS(app)

# Initialize database
db.init_app(app)

# Create tables on first run
with app.app_context():
    db.create_all()
    print("✅ Database initialized")

# Test route to verify server is working
@app.route("/test")
def test_route():
    return "Server is working! Static folder: " + str(app.static_folder)

# Serve index.html at root
@app.route("/")
def serve_index():
    try:
        index_path = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_path):
            return send_file(index_path, mimetype='text/html')
        return f"Index.html not found at {index_path}", 404
    except Exception as e:
        return f"Error: {str(e)}", 500

# Register blueprints (before static file route to avoid conflicts)
app.register_blueprint(main)
app.register_blueprint(tutorial, url_prefix="/tutorial")
app.register_blueprint(plotly_tutorial, url_prefix="/plotly")
app.register_blueprint(patient_routes, url_prefix="/patients")

# Register other blueprints
from application.routes.load_data import load_data
app.register_blueprint(load_data, url_prefix="/load_data")

from application.routes.upload_routes import upload_routes
app.register_blueprint(upload_routes, url_prefix="/uploads")

# IMPORTANT: Define explicit HTML routes BEFORE the catch-all route
# Flask processes routes in order, so specific routes must come first!

# Serve HTML pages - use frontend_path directly to avoid any static_folder issues
@app.route("/tutorial.html")
def tutorial_page():
    try:
        return send_file(os.path.join(frontend_path, "tutorial.html"), mimetype='text/html')
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route("/dashboard.html")
def dashboard_page():
    try:
        return send_file(os.path.join(frontend_path, "dashboard.html"), mimetype='text/html')
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route("/viewer-ct.html")
def viewer_ct_page():
    try:
        return send_file(os.path.join(frontend_path, "viewer-ct.html"), mimetype='text/html')
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route("/plan-create.html")
def plan_create_page():
    try:
        return send_file(os.path.join(frontend_path, "plan-create.html"), mimetype='text/html')
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route("/plan-results.html")
def plan_results_page():
    try:
        return send_file(os.path.join(frontend_path, "plan-results.html"), mimetype='text/html')
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route("/plan-compute.html")
def plan_compute_page():
    try:
        return send_file(os.path.join(frontend_path, "plan-compute.html"), mimetype='text/html')
    except Exception as e:
        return f"Error: {str(e)}", 500

# Serve all other static files (must be last to catch remaining routes)
# Exclude API routes and known endpoints
@app.route("/<path:path>")
def serve_static_files(path):
    # Don't serve API routes as static files - let them 404 if not found
    api_prefixes = ["api", "patients", "ct", "roi", "dose", "results", "plans", "load_data", "uploads", "tutorial", "plotly"]
    if any(path.startswith(prefix + "/") or path == prefix for prefix in api_prefixes):
        from flask import abort
        abort(404)
    
    # Don't serve .html files through catch-all (they have explicit routes above)
    if path.endswith('.html'):
        from flask import abort
        abort(404)
    
    try:
        file_path = os.path.join(frontend_path, path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_file(file_path)
        from flask import abort
        abort(404)
    except Exception as e:
        print(f"Error serving static file {path}: {e}")
        from flask import abort
        abort(404)




if __name__ == "__main__":
    # Use port 5001 instead of 5000 to avoid conflict with macOS AirPlay Receiver
    app.run(debug=True, host='127.0.0.1', port=5001)
