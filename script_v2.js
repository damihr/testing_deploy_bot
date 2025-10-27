// DIRECT Google Sheets Fetcher - No Server Needed!
// Напрямую читаем из Google Sheets без сервера

const SHEET_ID = '1McGe_kQVIonC4soSTi1nPjH4WlGI0vlS';
const SHEET_GID = '1496744611'; // gid parameter
const SHEET_NAME = 'Sheet1'; // or the actual sheet name

let inventoryData = [];
let currentPage = 1;
const itemsPerPage = 12;

// Fetch data directly from Excel file
async function fetchDataFromGoogleSheets() {
    try {
        console.log('📡 Loading Excel file...');
        
        // Read Excel file directly using XLSX.js
        const response = await fetch('Расходники 9 октября.xlsx');
        const arrayBuffer = await response.arrayBuffer();
        const workbook = XLSX.read(arrayBuffer, { type: 'array' });
        const worksheet = workbook.Sheets[workbook.SheetNames[0]];
        const data = XLSX.utils.sheet_to_json(worksheet);
        
        // Process data
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
        
        // Update UI
        displayInventory();
        updateStats();
        
        return processedData;
        
    } catch (error) {
        console.error('❌ Error fetching data:', error);
        showError('Не удалось загрузить данные из Excel файла.');
    }
}

// Display inventory with pagination
function displayInventory() {
    const container = document.getElementById('inventory-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (inventoryData.length === 0) {
        container.innerHTML = '<p class="text-center text-gray-600">Инвентарь пуст</p>';
        return;
    }
    
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const currentItems = inventoryData.slice(startIndex, endIndex);
    
    let html = '';
    
    currentItems.forEach(item => {
        const imageSrc = item.imageURL ? item.imageURL : `image${item.id}.png`;
        
        html += `
            <div class="card">
                <div class="card-image">
                    ${item.imageURL ? 
                        `<img src="${imageSrc}" alt="${item.name}" onerror="this.onerror=null; this.src='https://via.placeholder.com/200x200?text=No+Image';" />` :
                        `<div class="placeholder-image">
                            <span class="placeholder-text">🖼️</span>
                        </div>`
                    }
                </div>
                <div class="card-content">
                    <h3 class="card-title">${item.name}</h3>
                    <div class="card-info">
                        <p><strong>Модель:</strong> ${item.model}</p>
                        <p><strong>Производитель:</strong> ${item.manufacturer}</p>
                        <p><strong>Количество:</strong> <span class="quantity ${item.quantity > 0 ? 'in-stock' : 'out-of-stock'}">${item.quantity} шт.</span></p>
                        ${item.characteristics && item.characteristics !== 'Не указаны' ? 
                            `<p><strong>Характеристики:</strong> ${item.characteristics.substring(0, 100)}${item.characteristics.length > 100 ? '...' : ''}</p>` : 
                            ''
                        }
                    </div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
    
    // Update pagination
    updatePagination();
}

// Update pagination controls
function updatePagination() {
    const totalPages = Math.ceil(inventoryData.length / itemsPerPage);
    const pagination = document.getElementById('pagination');
    
    if (!pagination) return;
    
    let html = '';
    
    // Previous button
    html += `
        <button id="prevBtn" class="btn-pagination" ${currentPage === 1 ? 'disabled' : ''}>
            ← Назад
        </button>
    `;
    
    // Page numbers
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentPage - 1 && i <= currentPage + 1)) {
            html += `
                <button class="btn-page ${i === currentPage ? 'active' : ''}" data-page="${i}">
                    ${i}
                </button>
            `;
        } else if (i === currentPage - 2 || i === currentPage + 2) {
            html += '<span class="ellipsis">...</span>';
        }
    }
    
    // Next button
    html += `
        <button id="nextBtn" class="btn-pagination" ${currentPage === totalPages ? 'disabled' : ''}>
            Вперед →
        </button>
    `;
    
    pagination.innerHTML = html;
    
    // Add event listeners
    document.querySelectorAll('.btn-page').forEach(btn => {
        btn.addEventListener('click', () => {
            currentPage = parseInt(btn.dataset.page);
            displayInventory();
        });
    });
    
    document.getElementById('prevBtn')?.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            displayInventory();
        }
    });
    
    document.getElementById('nextBtn')?.addEventListener('click', () => {
        const totalPages = Math.ceil(inventoryData.length / itemsPerPage);
        if (currentPage < totalPages) {
            currentPage++;
            displayInventory();
        }
    });
}

// Update statistics
function updateStats() {
    const totalInstruments = inventoryData.length;
    const totalQuantity = inventoryData.reduce((sum, item) => sum + (item.quantity || 0), 0);
    const inStock = inventoryData.filter(item => item.quantity > 0).length;
    
    const statsElement = document.getElementById('stats');
    if (statsElement) {
        statsElement.innerHTML = `
            <div class="stat-card">
                <div class="stat-icon">📦</div>
                <div class="stat-info">
                    <p class="stat-label">Всего инструментов</p>
                    <p class="stat-value">${totalInstruments}</p>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">✅</div>
                <div class="stat-info">
                    <p class="stat-label">В наличии</p>
                    <p class="stat-value">${inStock}</p>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">📊</div>
                <div class="stat-info">
                    <p class="stat-label">Общее количество</p>
                    <p class="stat-value">${totalQuantity}</p>
                </div>
            </div>
        `;
    }
}

// Search functionality
function searchInventory(query) {
    const searchTerm = query.toLowerCase();
    
    if (!searchTerm) {
        displayInventory();
        return;
    }
    
    const filtered = inventoryData.filter(item => 
        item.name.toLowerCase().includes(searchTerm) ||
        item.model.toLowerCase().includes(searchTerm) ||
        item.manufacturer.toLowerCase().includes(searchTerm)
    );
    
    // Display filtered results
    const container = document.getElementById('inventory-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (filtered.length === 0) {
        container.innerHTML = '<p class="text-center text-gray-600">Ничего не найдено</p>';
        return;
    }
    
    let html = '';
    filtered.forEach(item => {
        const imageSrc = item.imageURL ? item.imageURL : `image${item.id}.png`;
        
        html += `
            <div class="card">
                <div class="card-image">
                    ${item.imageURL ? 
                        `<img src="${imageSrc}" alt="${item.name}" onerror="this.onerror=null; this.src='https://via.placeholder.com/200x200?text=No+Image';" />` :
                        `<div class="placeholder-image">
                            <span class="placeholder-text">🖼️</span>
                        </div>`
                    }
                </div>
                <div class="card-content">
                    <h3 class="card-title">${item.name}</h3>
                    <div class="card-info">
                        <p><strong>Модель:</strong> ${item.model}</p>
                        <p><strong>Производитель:</strong> ${item.manufacturer}</p>
                        <p><strong>Количество:</strong> <span class="quantity ${item.quantity > 0 ? 'in-stock' : 'out-of-stock'}">${item.quantity} шт.</span></p>
                    </div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// Show error message
function showError(message) {
    const container = document.getElementById('inventory-container');
    if (container) {
        container.innerHTML = `
            <div class="error-message">
                <p>❌ ${message}</p>
                <button class="btn-retry" onclick="fetchDataFromGoogleSheets()">Попробовать снова</button>
            </div>
        `;
    }
}

// Auto-refresh every 30 seconds
let autoRefreshInterval;
function startAutoRefresh() {
    autoRefreshInterval = setInterval(() => {
        fetchDataFromGoogleSheets();
    }, 30000); // 30 seconds
    
    console.log('🔄 Auto-refresh started (every 30 seconds)');
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        console.log('⏸️ Auto-refresh stopped');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Initializing inventory page...');
    
    // Fetch data immediately
    fetchDataFromGoogleSheets();
    
    // Start auto-refresh
    startAutoRefresh();
    
    // Add search functionality
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            searchInventory(e.target.value);
        });
    }
    
    // Add manual sync button
    const syncButton = document.getElementById('syncButton');
    if (syncButton) {
        syncButton.addEventListener('click', () => {
            console.log('🔄 Manual sync triggered');
            fetchDataFromGoogleSheets();
        });
    }
});

