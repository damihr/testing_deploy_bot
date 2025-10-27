#!/usr/bin/env python3
"""
Script to manually create Google Sheet with proper permissions
"""
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

def create_google_sheet():
    """Create Google Sheet manually"""
    if not os.path.exists('service_account.json'):
        print("❌ service_account.json not found!")
        return
    
    try:
        credentials = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES)
        
        sheets_service = build('sheets', 'v4', credentials=credentials)
        drive_service = build('drive', 'v3', credentials=credentials)
        
        print("🔍 Creating Google Sheet...")
        
        # Create spreadsheet
        spreadsheet_body = {
            'properties': {
                'title': 'Inventory Bot Sheet'
            }
        }
        
        spreadsheet = sheets_service.spreadsheets().create(
            body=spreadsheet_body,
            fields='spreadsheetId'
        ).execute()
        
        sheet_id = spreadsheet.get('spreadsheetId')
        print(f"✅ Created Google Sheet: {sheet_id}")
        print(f"🔗 URL: https://docs.google.com/spreadsheets/d/{sheet_id}")
        
        # Save the sheet ID
        with open('google_sheet_id.txt', 'w') as f:
            f.write(sheet_id)
        
        print("💾 Saved sheet ID to google_sheet_id.txt")
        
        return sheet_id
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    create_google_sheet()
