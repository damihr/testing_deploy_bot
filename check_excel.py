#!/usr/bin/env python3
"""
Quick script to check Excel file structure
"""
import pandas as pd

try:
    df = pd.read_excel("Расходники 9 октября.xlsx")
    print(f"Excel file loaded successfully!")
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(f"First few rows:")
    print(df.head())
    
    print(f"\nFirst column values (first 10):")
    print(df.iloc[:10, 0].tolist())
    
except Exception as e:
    print(f"Error: {e}")
