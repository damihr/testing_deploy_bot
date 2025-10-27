#!/usr/bin/env python3
"""
Simple test to check sheet access
"""
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
GOOGLE_SHEETS_ID = "1McGe_kQVIonC4soSTi1nPjH4WlGI0vlS"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def test_simple_access():
    """Test simple sheet access"""
    if not os.path.exists('service_account.json'):
        print("❌ service_account.json file not found!")
        return False
    
    try:
        # Load service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES)
        
        # Build service
        service = build('sheets', 'v4', credentials=credentials)
        
        print("🔍 Testing simple sheet access...")
        
        # Try to get basic sheet info
        try:
            spreadsheet = service.spreadsheets().get(spreadsheetId=GOOGLE_SHEETS_ID).execute()
            print("✅ Successfully accessed spreadsheet!")
            print(f"📊 Title: {spreadsheet.get('properties', {}).get('title', 'Unknown')}")
            
            # Get sheet names
            sheets = spreadsheet.get('sheets', [])
            sheet_names = [sheet['properties']['title'] for sheet in sheets]
            print(f"📋 Available sheets: {sheet_names}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error accessing spreadsheet: {e}")
            
            # Try alternative approach - direct values access
            print("🔄 Trying alternative approach...")
            try:
                # Try to read from a specific range
                result = service.spreadsheets().values().get(
                    spreadsheetId=GOOGLE_SHEETS_ID, 
                    range='A1:Z10'
                ).execute()
                
                values = result.get('values', [])
                print(f"✅ Alternative approach worked! Found {len(values)} rows")
                if values:
                    print(f"📋 First row: {values[0]}")
                
                return True
                
            except Exception as e2:
                print(f"❌ Alternative approach also failed: {e2}")
                return False
        
    except Exception as e:
        print(f"❌ General error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Simple Google Sheets Access Test")
    print("=" * 40)
    test_simple_access()
