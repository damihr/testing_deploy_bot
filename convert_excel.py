#!/usr/bin/env python3
"""
Script to convert Excel data to JavaScript format for the web interface
"""

import pandas as pd
import json
import os

def convert_excel_to_js():
    """Convert Excel file to JavaScript data format"""
    
    # Load the Excel file
    df = pd.read_excel('Расходники 9 октября.xlsx')
    
    print(f"📊 Loaded Excel file with shape: {df.shape}")
    print(f"📋 Columns: {list(df.columns)}")
    
    # Convert to JavaScript format - only real instruments with names
    data = []
    actual_instruments = df[df.iloc[:, 2].notna() & (df.iloc[:, 2] != '')]  # Column 2 is 'Наименование'
    
    for idx, (original_idx, row) in enumerate(actual_instruments.iterrows()):
        item = {
            'id': idx + 1,  # Sequential ID starting from 1
            'name': str(row.iloc[2]) if pd.notna(row.iloc[2]) else 'Неизвестно',
            'model': str(row.iloc[3]) if pd.notna(row.iloc[3]) else '',
            'manufacturer': str(row.iloc[4]) if pd.notna(row.iloc[4]) else 'Неизвестно',
            'quantity': float(row.iloc[6]) if pd.notna(row.iloc[6]) else 0,
            'characteristics': str(row.iloc[5]) if pd.notna(row.iloc[5]) else '',
            'category': str(row.iloc[1]) if pd.notna(row.iloc[1]) else 'Общее',
            'unit': 'шт.',
            'location': 'Склад',
            'notes': 'В наличии'
        }
        data.append(item)
    
    print(f"✅ Processed {len(data)} instruments")
    
    # Generate JavaScript code
    js_code = f"""
// Auto-generated data from Excel file
const REAL_INVENTORY_DATA = {json.dumps(data, ensure_ascii=False, indent=2)};

// Function to load real data
function loadRealData() {{
    inventoryData = [...REAL_INVENTORY_DATA];
    filteredData = [...inventoryData];
    updateFilters();
    updateDashboard();
    updateInventoryTable();
    updateAnalytics();
    
    console.log(`✅ Loaded ${{inventoryData.length}} real instruments from Excel file`);
}}
"""
    
    # Write to file
    with open('real_data.js', 'w', encoding='utf-8') as f:
        f.write(js_code)
    
    print("📝 Generated real_data.js file")
    
    # Show sample data
    if data:
        print("\n🔧 Sample instruments:")
        for i, item in enumerate(data[:5]):
            print(f"{i+1}. {item['name']} - {item['quantity']} {item['unit']}")
    
    return len(data)

if __name__ == "__main__":
    count = convert_excel_to_js()
    print(f"\n🎉 Successfully converted {count} instruments to JavaScript format!")
