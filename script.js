// Direct Excel Reader - No Server!
// Читаем Excel напрямую в браузере

let inventoryData = [];
let currentPage = 1;
const itemsPerPage = 12;
let manufacturerChart, stockChart;

// Fetch data from Excel
async function fetchDataFromGoogleSheets() {
    try {
        console.log('📡 Loading Excel file...');
        
        const response = await fetch('Расходники 9 октября.xlsx');
        const arrayBuffer = await response.arrayBuffer();
        const workbook = XLSX.read(arrayBuffer, { type: 'array' });
        const worksheet = workbook.Sheets[workbook.SheetNames[0]];
        const data = XLSX.utils.sheet_to_json(worksheet);
        
        const processedData = [];
        
        for (let idx = 0; idx < data.length; idx++) {
            const row = data[idx];
            
            const name = row['Наименование'] || '';
            const num = row['№'] || idx + 1;
            const model = row['Модель'] || 'Не указана';
            const manufacturer = row['Компания производителя'] || 'Не указан';
            const characteristics = row['Характеристика '] || 'Не указаны';
            const quantity = parseFloat(row['Количество']) || 0;
            const imageURL = row['ImageURL'] || '';
            
            if (name && name.toString().trim() !== '' && name.toString() !== 'nan') {
                processedData.push({
                    id: parseInt(num) || idx + 1,
                    name: name.toString().trim(),
                    model: model.toString().trim(),
                    manufacturer: manufacturer.toString().trim(),
                    characteristics: characteristics.toString().trim(),
                    quantity: isNaN(quantity) ? 0 : quantity,
                    imageURL: imageURL.toString().trim()
                });
            }
        }
        
        inventoryData = processedData;
        console.log(`✅ Loaded ${inventoryData.length} instruments from Excel`);
        
        displayInventory();
        updateStats();
        updateCharts();
        
        return processedData;
        
    } catch (error) {
        console.error('❌ Error fetching data:', error);
        alert('Не удалось загрузить данные из Excel файла.');
    }
}

// Tab switching
function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    document.getElementById(tabName).classList.add('active');
    document.querySelector(`[onclick="showTab('${tabName}')"]`).classList.add('active');
}

// Display inventory table
function displayInventory() {
    const tbody = document.getElementById('inventoryTableBody');
    if (!tbody) return;
    
    if (inventoryData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7">Инвентарь пуст</td></tr>';
        return;
    }
    
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const currentItems = inventoryData.slice(startIndex, endIndex);
    
    let html = '';
    
    currentItems.forEach(item => {
        html += `
            <tr>
                <td>${item.id}</td>
                <td>${item.name}</td>
                <td>${item.model}</td>
                <td>${item.manufacturer}</td>
                <td>${item.characteristics.substring(0, 50)}${item.characteristics.length > 50 ? '...' : ''}</td>
                <td><span class="quantity ${item.quantity > 0 ? 'in-stock' : 'out-of-stock'}">${item.quantity}</span></td>
                <td><button class="btn btn-sm btn-info" onclick="showDetails(${item.id})">Детали</button></td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
    
    // Pagination
    const totalPages = Math.ceil(inventoryData.length / itemsPerPage);
    let paginationHtml = '';
    
    if (currentPage > 1) {
        paginationHtml += `<button onclick="changePage(${currentPage - 1})" class="page-btn">⬅️ Предыдущая</button>`;
    }
    
    paginationHtml += `<span class="page-info">Страница ${currentPage} из ${totalPages}</span>`;
    
    if (currentPage < totalPages) {
        paginationHtml += `<button onclick="changePage(${currentPage + 1})" class="page-btn">Следующая ➡️</button>`;
    }
    
    document.getElementById('pagination').innerHTML = paginationHtml;
}

function changePage(page) {
    currentPage = page;
    displayInventory();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showDetails(id) {
    const item = inventoryData.find(i => i.id === id);
    if (!item) return;
    
    alert(`📋 ${item.name}\n\nМодель: ${item.model}\nПроизводитель: ${item.manufacturer}\nКоличество: ${item.quantity}\n\n${item.characteristics}`);
}

function filterInventory() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    // Simple filter - just refetch data
    fetchDataFromGoogleSheets();
}

// Update stats
function updateStats() {
    const total = inventoryData.length;
    const available = inventoryData.filter(i => i.quantity > 0).length;
    const lowStock = inventoryData.filter(i => i.quantity > 0 && i.quantity < 5).length;
    const manufacturers = new Set(inventoryData.map(i => i.manufacturer)).size;
    
    document.getElementById('totalInstruments').textContent = total;
    document.getElementById('availableInstruments').textContent = available;
    document.getElementById('lowStockInstruments').textContent = lowStock;
    document.getElementById('totalManufacturers').textContent = manufacturers;
}

// Update charts
function updateCharts() {
    // Manufacturer chart
    const manufacturers = {};
    inventoryData.forEach(item => {
        manufacturers[item.manufacturer] = (manufacturers[item.manufacturer] || 0) + 1;
    });
    
    if (manufacturerChart) {
        manufacturerChart.destroy();
    }
    
    const ctx1 = document.getElementById('manufacturerChart');
    if (ctx1) {
        manufacturerChart = new Chart(ctx1, {
            type: 'bar',
            data: {
                labels: Object.keys(manufacturers).slice(0, 10),
                datasets: [{
                    label: 'Количество инструментов',
                    data: Object.values(manufacturers).slice(0, 10),
                    backgroundColor: 'rgba(102, 126, 234, 0.6)'
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });
    }
    
    // Stock chart
    const stockStatus = {
        'Доступно': inventoryData.filter(i => i.quantity > 10).length,
        'Низкий запас': inventoryData.filter(i => i.quantity > 0 && i.quantity <= 10).length,
        'Нет в наличии': inventoryData.filter(i => i.quantity === 0).length
    };
    
    if (stockChart) {
        stockChart.destroy();
    }
    
    const ctx2 = document.getElementById('stockChart');
    if (ctx2) {
        stockChart = new Chart(ctx2, {
            type: 'pie',
            data: {
                labels: Object.keys(stockStatus),
                datasets: [{
                    data: Object.values(stockStatus),
                    backgroundColor: ['#4CAF50', '#FF9800', '#F44336']
                }]
            }
        });
    }
    
    // Top instruments
    const topInstruments = [...inventoryData]
        .sort((a, b) => b.quantity - a.quantity)
        .slice(0, 10);
    
    let html = '<ul>';
    topInstruments.forEach(item => {
        html += `<li>${item.name} - ${item.quantity} шт.</li>`;
    });
    html += '</ul>';
    document.getElementById('topInstruments').innerHTML = html;
    
    // Low stock
    const lowStock = inventoryData.filter(i => i.quantity > 0 && i.quantity < 5).slice(0, 10);
    html = '<ul>';
    lowStock.forEach(item => {
        html += `<li>${item.name} - ${item.quantity} шт.</li>`;
    });
    html += '</ul>';
    document.getElementById('lowStockList').innerHTML = html;
}

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    fetchDataFromGoogleSheets();
});
