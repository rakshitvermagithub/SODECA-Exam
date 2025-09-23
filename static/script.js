// Use a Map to store selected form IDs and their names for easy lookup
const selectedForms = new Map();

/**
 * Updates the selection state when a checkbox is clicked.
 * @param {HTMLInputElement} checkbox - The checkbox element that was changed.
 * @param {string} formId - The ID of the accordion item.
 * @param {string} formName - The display name of the form.
 */
function updateSelection(checkbox, formId, formName) {
    const item = document.getElementById(formId);
    if (checkbox.checked) {
        // Add to selection
        selectedForms.set(formId, formName);
        item.classList.add('selected');
    } else {
        // Remove from selection
        selectedForms.delete(formId);
        item.classList.remove('selected');
    }
    updateSummaryDisplay();
}

/**
 * Renders the list of selected forms in the summary box.
 */
function updateSummaryDisplay() {
    const summaryDiv = document.getElementById('selectedSummary');
    if (selectedForms.size === 0) {
        summaryDiv.innerHTML = '<span class="text-muted">No forms selected.</span>';
    } else {
        // Generate badges for each selected item from the Map's values
        summaryDiv.innerHTML = [...selectedForms.values()].map(name => {
            return `<span class="badge bg-primary fs-6 fw-normal me-2 mb-2">${name}</span>`;
        }).join('');
    }
}

/**
 * Handles the form submission, preventing it if no items are selected.
 */
document.getElementById('college-form').addEventListener('submit', function(event) {
    if (selectedForms.size === 0) {
        event.preventDefault(); // Stop the form from submitting
        alert('Please select at least one form before proceeding.');
        return;
    }
});

document.querySelectorAll('.process-btn').forEach(button => {
    button.addEventListener('click', function() {
        var row = this.closest('tr');
        var rowData = {
            form_name: row.dataset.formName,
            student_id: row.dataset.studentId,
        };
        
        fetch('/update_sheets', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(rowData)
        })
        .then(response => response.json())
        .then(data => {
            location.reload(); // refresh the page
        })
        .catch(error => {
            console.error('Error:', error);
        });
    });
});