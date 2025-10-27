#!/usr/bin/env python3
"""
Test script to verify Excel file updates
"""
import pandas as pd

def test_excel_update():
    """Test if Excel file can be updated"""
    try:
        # Load Excel file
        df = pd.read_excel("Расходники 9 октября.xlsx")
        print(f"✅ Excel file loaded successfully!")
        print(f"Shape: {df.shape}")
        
        # Check first few rows
        print(f"\nFirst 3 rows of 'Количество' column:")
        print(df.iloc[:3, 6].tolist())  # Column 6 is 'Количество'
        
        # Try to update a value
        original_value = df.iloc[0, 6]
        print(f"\nOriginal value at row 0: {original_value}")
        
        # Update the value
        df.iloc[0, 6] = 999.0
        print(f"Updated value to: {df.iloc[0, 6]}")
        
        # Save the file
        df.to_excel("Расходники 9 октября.xlsx", index=False)
        print(f"✅ File saved successfully!")
        
        # Reload to verify
        df2 = pd.read_excel("Расходники 9 октября.xlsx")
        print(f"Verification - value at row 0: {df2.iloc[0, 6]}")
        
        # Restore original value
        df2.iloc[0, 6] = original_value
        df2.to_excel("Расходники 9 октября.xlsx", index=False)
        print(f"✅ Restored original value: {original_value}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_excel_update()
