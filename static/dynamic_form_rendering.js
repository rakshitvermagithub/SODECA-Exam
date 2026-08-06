const loadingTableStructure = `
    <div class="table-responsive pt-2" id="dynamic_table">
        <table class = "table table-striped table-bordered display nowrap" id="loading_table">
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
     <tr>
        <td class="noDataClass" style="width: 100%">
            <div class="d-flex justify-content-center">
                No Data Available
            </div>
        </td> 
     </tr>   
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
        <table class="table table-striped table-bordered display nowrap" id="tb_${table_id}" style="width: 100%;">
            <thead class="table-dark">
                <tr>
    `;
    
    column_name.forEach((col) => {
        table_html_structure += `<th>${col}</th>`;
    });
    
    table_html_structure += `
                </tr>
            </thead>
            <tbody>
    `;
    
    row_values.forEach((row_val) => {
        table_html_structure += `<tr>`;
        
        sql_col.forEach((col_val) => {
            let cell_data = row_val[col_val];
            
            // Check if the current column is the Google File ID
            if (col_val === 'google_file_id' && cell_data != 'pending') {
                // Wrap the ID in a clickable Google Drive link
                cell_data = `<a href="https://drive.google.com/file/d/${cell_data}/view" target="_blank" 
                class="text-primary">Drive link</a>`;
            } else if (cell_data === null || cell_data === undefined) {
                // Handle null/undefined values to prevent 'null' text in the table
                cell_data = 'Pending';
            }
            
            table_html_structure += `<td>${cell_data}</td>`;
        });
        
        table_html_structure += `</tr>`;
    });
    
    table_html_structure += `
            </tbody>
        </table>
    `;
    
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
    fetch('/batch_report', {
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
let myPieChart;
Chart.register(ChartDataLabels);

function updateChart(filtered_data) {
    let dataChart = new Map();
    if (filtered_data.length === 0) {
        document.getElementById('chart-container').innerHTML = `
            <h5 class="text-center">No data Available</h5>
        `;
        return;
    }
    document.getElementById('chart-container').innerHTML = `
        <canvas id="categoryPieChart"></canvas>
    `;
    filtered_data.forEach((row) => {
       if (!dataChart.get(row['category'])) dataChart.set(row['category'], 1);
       else dataChart.set(row['category'], dataChart.get(row['category']) + 1);
    });

    const ctx = document.getElementById('categoryPieChart').getContext('2d');
    if(myPieChart) myPieChart.destroy();

    myPieChart = new Chart(ctx, {
        type: 'pie', // Changed to standard Pie chart
        data: {
            labels: [...dataChart.keys()],
            datasets: [{
                data: [...dataChart.values()], // Dummy percentages
                backgroundColor: [
                    'rgba(44, 127, 184, 0.7)', // Primary blue
                    '#3498db', // Light blue
                    '#2ecc71', // Green
                    '#f1c40f', // Yellow
                    '#e74c3c', // Red
                    'rgba(255, 152, 150, 0.7)',
                    'rgba(158, 218, 229, 0.7)',
                    'rgba(140, 86, 75, 0.7)',
                    'rgba(247, 182, 210, 0.7)',
                    'rgba(255, 215, 0, 0.7)'
                ],
                borderWidth: 2,
                borderColor: '#ffffff',
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'top', // Moves it to the right side of the pie
                    labels: {
                        font: {
                            family: "'Poppins', sans-serif",
                            size: 11 // Reduced from 13 for smaller text
                        },
                        color: '#1a1a1a',
                        padding: 12, // Reduced padding to tighten the list
                        boxWidth: 12 // Makes the colored squares smaller
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return ' ' + context.label + ': ' + context.raw + '%';
                        }
                    }
                },
                datalabels: {
                    formatter: (value, context) => {
                        return value;
                    },
                    color: '#444', // Color of the text on the chart
                    font: {
                        weight: 'bold',
                        size: 14
                    },
                    anchor: 'center', // Position: 'start', 'center', or 'end'
                    align: 'center'
                }
            }
            // cutout property removed so it fills the center
        }
    });

    // fetch('/visual_report', {
    //     method: 'POST',
    //     headers: {
    //         'Content-type': 'application/json',
    //     }
    // })
    // .then(response=>response.json())
    // .then(responseData => {
    //     dataChart = responseData.chartData;
    //     labelsChart = responseData.labelData;
    //
    //     console.log("Chart Labels values are: ", labelsChart);
    //     console.log("Chart data values are: ", dataChart);
    //
    // })
    // .catch(error => console.error('Error during fetching data: ', error));
}