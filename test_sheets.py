#!/usr/bin/env python3
"""
Test script to verify Google Sheets access
"""
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
GOOGLE_SHEETS_ID = "1Ak041uMcAIZTYYFXRnhrzhl0MBV544mV7RpTcly-Ylg"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def test_service_account():
    """Test service account access"""
    if not os.path.exists('service_account.json'):
        print("❌ service_account.json file not found!")
        print("Please place your service account JSON file in this directory and rename it to 'service_account.json'")
        return False
    
    try:
        # Load service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES)
        
        # Build service
        service = build('sheets', 'v4', credentials=credentials)
        
        # Test access
        print("🔍 Testing service account access...")
        spreadsheet = service.spreadsheets().get(spreadsheetId=GOOGLE_SHEETS_ID).execute()
        
        # Get sheet names
        sheet_names = [sheet['properties']['title'] for sheet in spreadsheet['sheets']]
        print(f"✅ Success! Available sheets: {sheet_names}")
        
        # Test reading data from first sheet
        if sheet_names:
            first_sheet = sheet_names[0]
            print(f"📊 Testing data read from '{first_sheet}'...")
            
            result = service.spreadsheets().values().get(
                spreadsheetId=GOOGLE_SHEETS_ID, 
                range=f'{first_sheet}!A1:Z10'
            ).execute()
            
            values = result.get('values', [])
            if values:
                print(f"✅ Data found! {len(values)} rows")
                print(f"📋 Headers: {values[0] if values else 'None'}")
            else:
                print("⚠️ No data found in sheet")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Google Sheets Service Account Test")
    print("=" * 40)
    test_service_account()
