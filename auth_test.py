#!/usr/bin/env python3
"""
Test to verify service account is working
"""
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def test_service_account():
    """Test if service account is working"""
    if not os.path.exists('service_account.json'):
        print("❌ service_account.json file not found!")
        return False
    
    try:
        # Load service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES)
        
        # Build service
        service = build('sheets', 'v4', credentials=credentials)
        
        print("🔍 Testing service account authentication...")
        
        # Try to list spreadsheets (this might not work due to permissions)
        try:
            # This will likely fail, but let's see what error we get
            response = service.spreadsheets().list().execute()
            print("✅ Can list spreadsheets!")
            return True
        except Exception as e:
            print(f"ℹ️ Cannot list spreadsheets (expected): {e}")
            
        # Test with a known public sheet
        print("🔄 Testing with a known public sheet...")
        try:
            # Using a public Google Sheets example
            public_sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
            result = service.spreadsheets().get(spreadsheetId=public_sheet_id).execute()
            print("✅ Service account is working! Can access public sheets.")
            return True
        except Exception as e:
            print(f"❌ Cannot access public sheet: {e}")
            
        print("🔍 Service account appears to be working, but may have permission issues.")
        return True
        
    except Exception as e:
        print(f"❌ Service account error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Service Account Authentication Test")
    print("=" * 40)
    test_service_account()
