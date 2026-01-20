
export async function fetchDoseData() {
    console.log("Running fetchDoseData");
    try {
        const response = await fetch('/plotly/compute_dose');

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const data = await response.json();

        console.log("Received dose data:", data);

        const ct = data.ct_slice;
        const mask = data.mask_slice;
        const dose = data.dose_slice;
        const dvh = data.dvh;

        const layout1 = {
            title: 'CT with ROI',
            xaxis: { title: 'X Axis' },
            yaxis: {
                title: 'Y Axis',
                scaleanchor: 'x',
                scaleratio: 1,
                autorange: 'reversed'
            },
            showlegend: false
        };
        

        const heatmap = {
            z: ct,
            type: 'heatmap',
            zmin: -1000,
            zmax: 0,
            colorscale: [
                [0, 'white'],   // -1000 HU = air
                [1, 'black']    // 0 HU = water/soft tissue
            ],
            showscale: false,
            opacity: 1.0
        };
        
        

        const doseMap = {
            z: dose,
            type: 'heatmap',
            colorscale: 'Jet',
            opacity: 0.5
        };

        const maskContour = {
            z: mask,
            type: 'contour',
            line: { color: 'red', width: 2 },
            showscale: false
        };

        Plotly.newPlot('plotly-ct-dose', [heatmap, maskContour, doseMap], layout1);

        const layout2 = {
            title: 'Dose Volume Histogram',
            xaxis: { title: 'Dose (Gy)' },
            yaxis: { title: 'Volume (%)' }
        };

        const dvhPlot = {
            x: dvh.dose_values,
            y: dvh.volume_percentages,
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Target ROI'
        };

        Plotly.newPlot('plotly-dvh', [dvhPlot], layout2);

        const layoutDoseOverlay = {
            title: 'CT Slice + Dose Distribution + ROI Contour',
            xaxis: { title: 'X Axis', showgrid: false },
            yaxis: {
                title: 'Y Axis',
                showgrid: false,
                scaleanchor: 'x',
                scaleratio: 1,
                autorange: 'reversed'
            },
            showlegend: false
        };
        
        
        const ctLayer = {
            z: ct,
            type: 'heatmap',
            colorscale: 'Greys',
            showscale: false,
            opacity: 1.0,
            hoverinfo: 'skip'
        };
        
        const maskLayer = {
            z: mask,
            type: 'heatmap',
            colorscale: [[0, 'rgba(0,0,0,0)'], [1, 'rgba(255,0,0,0.4)']],  // transparent red
            showscale: false,
            opacity: 1.0,
            hoverinfo: 'skip'
        };
        
        const doseLayer = {
            z: dose,
            type: 'heatmap',
            colorscale: 'Jet',
            showscale: true,
            opacity: 0.4,
            colorbar: {
                title: 'Dose (Gy)'
            },
            hoverinfo: 'skip'
        };
        
        Plotly.newPlot('plotly-ct-overlay', [ctLayer, doseLayer, maskLayer], layoutDoseOverlay);

        console.log("Finished plotting dose data");

    } catch (error) {
        console.error("Error fetching dose data:", error);
    }
}

export async function uploadDicomFolder() {
    const input = document.getElementById("dicom-folder");
    const formData = new FormData();
    for (let file of input.files) {
        formData.append("dicom_folder", file);
    }

    const res = await fetch("/roi/upload_dicom", {
        method: "POST",
        body: formData
    });

    const data = await res.json();
    const ul = document.getElementById("roi-list");
    ul.innerHTML = "";
    if (data.roi_names) {
        data.roi_names.forEach(name => {
            const li = document.createElement("li");
            li.textContent = name;
            ul.appendChild(li);
        });
    } else {
        ul.innerHTML = `<li>Error: ${data.error}</li>`;
    }
}

export async function loadDatasets() {
    const ul = document.getElementById("dataset-list");
    ul.innerHTML = "Loading...";

    try {
        const res = await fetch("/load_data/datasets");
        const data = await res.json();

        ul.innerHTML = ""; // Clear loading message

        if (data.datasets) {
            data.datasets.forEach(name => {
                const li = document.createElement("li");
                li.textContent = name;
                li.onclick = () => alert(`Selected dataset: ${name}`);
                ul.appendChild(li);
            });
        } else {
            ul.innerHTML = `<li>Error: ${data.error}</li>`;
        }
    } catch (err) {
        console.error("Failed to load datasets", err);
        ul.innerHTML = `<li>Fetch error</li>`;
    }
}

export async function listDatasets() {
    const response = await fetch('/load_data/datasets');
    const data = await response.json();
  
    const dropdown = document.getElementById("datasetDropdown");
    dropdown.innerHTML = "";

    // Default placeholder option
    const defaultOption = document.createElement("option");
    defaultOption.value = "";
    defaultOption.textContent = "-- Select a dataset --";
    defaultOption.disabled = true;
    defaultOption.selected = true;
    defaultOption.hidden = true;
    dropdown.appendChild(defaultOption);
  
    if (data.datasets) {
      data.datasets.forEach(name => {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        dropdown.appendChild(option);
      });
    } else {
      console.error("Error loading datasets:", data.error);
    }
  }
  

  export async function loadSelectedDataset() {
    const dropdown = document.getElementById("datasetDropdown");
    const dataset = dropdown.value;

    if (!dataset) {
        alert("Please select a dataset.");
        return;
    }

    const response = await fetch(`/load_data/${dataset}`);
    const data = await response.json();

    const ul = document.getElementById("roi-list");
    ul.innerHTML = "";

    if (data.roi_names) {
        data.roi_names.forEach(name => {
            const li = document.createElement("li");
            li.textContent = name;
            ul.appendChild(li);
        });
    } else {
        ul.innerHTML = `<li>Error: ${data.error}</li>`;
    }
}

export function toggleCreatePatientForm() {
    const form = document.getElementById("create-patient-form");
    if (form.style.display === "none" || form.style.display === "") {
      form.style.display = "block";
    } else {
      form.style.display = "none";
    }
  }

  export async function createPatient() {
    const id = document.getElementById("patient-id").value.trim();
    const first = document.getElementById("patient-first-name").value.trim();
    const middle = document.getElementById("patient-middle-name").value.trim();
    const last = document.getElementById("patient-last-name").value.trim();
    const birthDate = document.getElementById("patient-dob").value;
    const sex = document.getElementById("patient-sex").value;

    // Validation
    if (!id) {
        alert("Error: Patient ID is required.");
        return;
    }
    if (!first || !last) {
        alert("Error: First name and last name are required.");
        return;
    }

    const name = `${first} ${middle} ${last}`.replace(/\s+/g, ' ').trim();

    const payload = { id, name, birthDate, sex };

    try {
        const response = await fetch("/patients/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        // Check if response has content
        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            const text = await response.text();
            console.error("Non-JSON response:", text);
            alert(`Error: Server returned non-JSON response. Status: ${response.status}`);
            return;
        }

        // Check if response body is empty
        const text = await response.text();
        if (!text || text.trim() === "") {
            console.error("Empty response from server");
            alert(`Error: Empty response from server. Status: ${response.status}`);
            return;
        }

        let data;
        try {
            data = JSON.parse(text);
        } catch (parseError) {
            console.error("JSON parse error:", parseError, "Response text:", text);
            alert(`Error: Invalid JSON response from server. Status: ${response.status}`);
            return;
        }

        if (response.ok) {
            alert("Patient created successfully!");
            loadPatients(); // reload patient list if visible
            // Reset form
            document.getElementById("patient-id").value = "";
            document.getElementById("patient-first-name").value = "";
            document.getElementById("patient-middle-name").value = "";
            document.getElementById("patient-last-name").value = "";
            document.getElementById("patient-dob").value = "";
            document.getElementById("patient-sex").value = "";
        } else {
            const errorMsg = data.error || data.message || `Error creating patient. Status: ${response.status}`;
            alert(`Error: ${errorMsg}`);
        }
    } catch (error) {
        console.error("Error creating patient:", error);
        alert(`Error: Failed to create patient. ${error.message}`);
    }
}


export async function loadPatients() {
    const response = await fetch("/patients/load");
    const patients = await response.json();
    const list = document.getElementById("patient-list");
    list.innerHTML = "";
    patients.forEach(p => {
        const li = document.createElement("li");
        li.textContent = `${p.name} (ID: ${p.id}, DOB: ${p.birthDate}, Sex: ${p.sex})`;
        list.appendChild(li);
    });
}
