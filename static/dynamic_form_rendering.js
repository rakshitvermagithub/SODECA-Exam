const loadingTableStructure = `
    <div class="table-responsive pt-2" id="dynamic_table">
        <table class = "table table-hover table-striped mt-3" id="loading_table">
            <tbody>
                 <tr>
                    <td class="d-flex justify-content-center">
                        <div class="spinner-border text-primary text-center" role="status">
                            <span class="sr-only">Loading...</span>
                        </div><span class="ms-2">Loading Data...</span>
                    </td>
                 </tr>
            </tbody>
        </table>
    </div>
`;

const noDataAvailableTableStructure = `
    <div class="table-responsive pt-2" id="dynamic_table">
        <table class = "table table-hover table-striped mt-3" id="empty_table">
            <thead class = "table-dark">
                    <tr>
                        <th class="text-center">No Data Available</th>
                    </tr>

            </thead>
            <tbody>
                 <tr>
                    <td class="text-center">No Data Available</td>
                 </tr>
            </tbody>
        </table>
    </div>
`

new DataTable(`#tb_blood_donor`, {
        paging: false,
        scrollY: '260px',
        scrollX: true
    });
function updateTable(row_values, sql_col, column_name, table_id) {
    const table_to_update = document.getElementById('dynamic_table');
    if (table_id === 'empty-table') {
        table_to_update.innerHTML = noDataAvailableTableStructure;
        new DataTable(`#empty_table`, {
            paging: false,
            scrollY: '260px',
            scrollX: true
        });
        return;
    }
    let table_html_structure = `
        <table class = "table table-hover table-striped mt-3" id="tb_${table_id}">
            <thead class = "table-dark">
                <tr>
    `;
    column_name.forEach((col) => {
        table_html_structure += `<th>${col}</th>`;
    })
    table_html_structure += `
            </tr>
        </thead>
        <tbody>
            <tr>
    `;
    row_values.forEach((row_val) => {
        sql_col.forEach((col_val) => {
            table_html_structure += `<td>${row_val[col_val]}</td>`;
        })
    })
    table_html_structure += `
                </tr>
            </tbody>
        </table>
    `
    table_to_update.innerHTML = table_html_structure;
    new DataTable(`#tb_${table_id}`, {
        paging: false,
        scrollY: '260px',
        scrollX: true
    });
}

function openTab(evt, containerId) {
    const targetContainerId = document.querySelector('.nav-link.active').id;
    const tableExist = document.getElementById(`tb_${targetContainerId}`);
    if (targetContainerId && tableExist) {
        const spinnerContainer = document.getElementById(`tb_${targetContainerId}`)
        spinnerContainer.innerHTML = loadingTableStructure;
    }
    fetch('/forms_report', {
        method: 'POST',
        headers: {
            'Content-type': 'application/json',
        },
        body: JSON.stringify({
            'form_id': containerId
        })
    })
    .then(response=>response.json())
    .then(responseData => {
        if(responseData.success) {
            updateTable(responseData.row_values, responseData.sql_col, responseData.column_name, containerId);
        } else {
            updateTable('', '', '', 'empty-table');
        }
    })
    .catch(error => console.error('Error during fetching data: ', error));

    document.querySelectorAll(".nav-link").forEach(btn => {
        btn.classList.remove("active");
    });

    const activeContainer = document.getElementById(containerId);
    activeContainer.classList.add("active");
    evt.currentTarget.classList.add("active");

    // const downloadButton = document.querySelector('[id^="download-button"]');
    // downloadButton.disabled = true;
    // downloadButton.id = 'download-button-'+containerId;
}