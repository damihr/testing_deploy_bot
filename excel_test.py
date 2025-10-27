#!/usr/bin/env python3
"""
Test with different approaches for Excel files
"""
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests

# Configuration
GOOGLE_SHEETS_ID = "1McGe_kQVIonC4soSTi1nPjH4WlGI0vlS"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def test_excel_file():
    """Test different approaches for Excel files"""
    if not os.path.exists('service_account.json'):
        print("❌ service_account.json file not found!")
        return False
    
    try:
        # Load service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES)
        
        # Build service
        service = build('sheets', 'v4', credentials=credentials)
        
        print("🔍 Testing different approaches for Excel file...")
        
        # Try 1: Direct values access with different sheet names
        sheet_names_to_try = ["Расходники", "Sheet1", "Sheet2", "Sheet3"]
        
        for sheet_name in sheet_names_to_try:
            print(f"🔄 Trying sheet: {sheet_name}")
            try:
                result = service.spreadsheets().values().get(
                    spreadsheetId=GOOGLE_SHEETS_ID, 
                    range=f'{sheet_name}!A1:Z10'
                ).execute()
                
                values = result.get('values', [])
                print(f"✅ Success with sheet '{sheet_name}'! Found {len(values)} rows")
                if values:
                    print(f"📋 Headers: {values[0]}")
                    print(f"📊 Sample data: {values[1] if len(values) > 1 else 'No data'}")
                return True
                
            except Exception as e:
                print(f"❌ Failed with sheet '{sheet_name}': {e}")
        
        # Try 2: Export as CSV approach
        print("🔄 Trying export approach...")
        try:
            # This might work for Excel files
            result = service.spreadsheets().values().get(
                spreadsheetId=GOOGLE_SHEETS_ID, 
                range='A1:Z100'  # Try without sheet name
            ).execute()
            
            values = result.get('values', [])
            print(f"✅ Export approach worked! Found {len(values)} rows")
            if values:
                print(f"📋 Headers: {values[0]}")
            return True
            
        except Exception as e:
            print(f"❌ Export approach failed: {e}")
        
        print("❌ All approaches failed. The file might not be compatible with Google Sheets API.")
        return False
        
    except Exception as e:
        print(f"❌ General error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Excel File Compatibility Test")
    print("=" * 40)
    test_excel_file()
