// Select the checked radio button within the group
document.addEventListener('DOMContentLoaded', function() {
    let checkedRadioAcadmeicSession = document.querySelector('input[name="academic_sessions"]:checked');
    if (checkedRadioAcadmeicSession) {
        // Get the value of the checked radio button
        document.getElementById('session_btn').textContent = checkedRadioAcadmeicSession.value;
    }
    document.getElementById('session_dropdown').addEventListener('click', function () {
        checkedRadioAcadmeicSession = document.querySelector('input[name="academic_sessions"]:checked');
        if (checkedRadioAcadmeicSession) {
            // Get the value of the checked radio button
            document.getElementById('session_btn').textContent = checkedRadioAcadmeicSession.value;
        }
    })
    document.getElementById('even_odd').addEventListener('click', function () {
        const checkedRadioEvenOdd = document.querySelector('input[name="academic_terms"]:checked');
        if (checkedRadioEvenOdd) {
            // Get the value of the checked radio button
            document.getElementById('even_odd_btn').textContent = checkedRadioEvenOdd.value;
            if (checkedRadioEvenOdd.value === 'Odd') {
                document.querySelectorAll('.even_sem').forEach(element => {
                    element.style.display = 'None';
                })
                document.querySelectorAll('.odd_sem').forEach(element => {
                    element.style.display = 'block';
                })
            } else if (checkedRadioEvenOdd.value === 'Even') {
                document.querySelectorAll('.odd_sem').forEach(element => {
                    element.style.display = 'None';
                })
                document.querySelectorAll('.even_sem').forEach(element => {
                    element.style.display = 'block';
                })
            }
        }
    })
    document.getElementById('par_ach').addEventListener('click', function () {
        const checkedRadioParAch = document.querySelector('input[name="submission_categories"]:checked');
        if (checkedRadioParAch) {
            // Get the value of the checked radio button
            document.getElementById('par_ach_btn').textContent = checkedRadioParAch.value;
        }
    })
    document.getElementById('form_dropdown').addEventListener('click', function() {
        const checkedForms = Array.from(document.querySelectorAll('input[name="forms[]"]:checked')).map(cb => cb.value);
        if (checkedForms.length > 0) {
            // Get the value of the checked radio button
            document.getElementById('form_type_btn').textContent = (checkedForms.length > 1) ? checkedForms[0] + ` + ${checkedForms.length - 1} more` : checkedForms[0];
        } else {
            document.getElementById('form_type_btn').textContent = "Select...";
        }
    })
    document.getElementById('semester_dropdown').addEventListener('click', function() {
        const checkedSemester = Array.from(document.querySelectorAll('input[name="semesters[]"]:checked')).map(cb => cb.value);
        if (checkedSemester.length > 0) {
            // Get the value of the checked radio button
            document.getElementById('semester_btn').textContent = (checkedSemester.length > 1) ? checkedSemester[0] + ` + ${checkedSemester.length - 1} more` : checkedSemester[0];
        } else {
            document.getElementById('semester_btn').textContent = "Select...";
        }
    })
    document.getElementById('branch_dropdown').addEventListener('click', function() {
        const checkedBranches = Array.from(document.querySelectorAll('input[name="branches[]"]:checked')).map(cb => cb.value);
        if (checkedBranches.length > 0) {
            // Get the value of the checked radio button
            document.getElementById('branch_btn').textContent = (checkedBranches.length > 1) ? checkedBranches[0] + ` + ${checkedBranches.length - 1} more` : checkedBranches[0];
        } else {
            document.getElementById('branch_btn').textContent = "Select...";
        }
    })
    document.getElementById('section_dropdown').addEventListener('click', function() {
        const checkedSections = Array.from(document.querySelectorAll('input[name="sections[]"]:checked')).map(cb => cb.value);
        if (checkedSections.length > 0) {
            // Get the value of the checked radio button
            document.getElementById('section_btn').textContent = (checkedSections.length > 1) ? checkedSections[0] + ` + ${checkedSections.length - 1} more` : checkedSections[0];
        } else {
            document.getElementById('section_btn').textContent = "Select...";
        }
    })

});

function fetchFilteredData() {
    const academic_session_data = document.querySelector('input[name="academic_sessions"]:checked')?.value || null;
    const form_type_data = Array.from(document.querySelectorAll('input[name="forms[]"]:checked')).map(cb => cb.value);
    const even_odd_data = document.querySelector('input[name="academic_terms"]:checked')?.value || null;
    const event_nature_data = Array.from(document.querySelectorAll('input[name="event_natures[]"]:checked')).map(cb => cb.value);
    const semester_data = Array.from(document.querySelectorAll('input[name="semesters[]"]:checked')).map(cb => cb.value);
    const branch_data = Array.from(document.querySelectorAll('input[name="branches[]"]:checked')).map(cb => cb.value);
    const section_data = Array.from(document.querySelectorAll('input[name="sections[]"]:checked')).map(cb => cb.value);
    const certification_type_data = document.querySelector('input[name="certification_type"]:checked')?.value || null;

    fetch('/student_report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            academic_session_data,
            form_type_data,
            even_odd_data,
            semester_data,
            branch_data,
            section_data,
            certification_type_data,
            event_nature_data
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Server returned HTTP ${response.status}`);
        }
        return response.json();
    })
    .then(payload => {
        const tableBody = document.getElementById('data-table-body-report');
        
        // Safe check for data array existence
        const reports = Array.isArray(payload?.data) ? payload.data : [];

        if (reports.length === 0) { 
            tableBody.innerHTML = typeof noDataAvailableTableStructure !== 'undefined' 
                ? noDataAvailableTableStructure 
                : '<tr><td colspan="8" class="text-center">No data available</td></tr>';
        } else {
            tableBody.innerHTML = reports.map((data) => {

                const driveLink = data.google_file_id === 'pending'
                    ? 'Pending'
                    : `<a href="https://drive.google.com/file/d/${data.google_file_id}" target="_blank">
                            https://drive.google.com/file/d/${data.google_file_id}
                       </a>`;

                return `
                    <tr data-certificate="${data.certificate || ''}">
                        <td>${data.entry_id}</td>
                        <td>${data.academic_session}</td>
                        <td>${data.academic_term}</td>
                        <td>${data.student_name || ''}</td>
                        <td>${data.university_roll_no || ''}</td>
                        <td>${data.sem || ''}-${data.branch || ''}-${data.section || ''}</td>
                        <td>${data.category || ''}</td>
                        <td>${driveLink}</td>
                        <td>
                            <button type="button" 
                                class="btn btn-outline-primary"
                                data-bs-toggle="modal"
                                data-bs-target="#submissionDetailsModal"
                                data-entry-id="${data.entry_id || ''}"
                                data-form-name="${data.category || ''}">
                                Open
                            </button>
                        </td>
                        <td>${data.submitted_at || ''}</td>
                    </tr>
                `;
            }).join('');
        }

        // Pass the safely parsed array into updateChart
        updateChart(reports);
    })
    .catch(error => {
        console.error('Error fetching details:', error);
        // Fallback to update chart safely on error
        updateChart([]);
    });
}