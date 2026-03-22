#!/usr/bin/env python3
"""
Script ตรวจสอบ database structure จริง
"""

import sqlite3

from runtime_config import get_business_db_path

def check_database_structure(database_path):
    """ตรวจสอบ structure ของ database"""
    
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    
    print("=== ตรวจสอบ Database Structure ===")
    
    # 1. แสดงทุก tables
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print("Tables ที่พบ:")
    for table in tables:
        print(f"  - {table['name']}")
    
    # 2. ตรวจสอบแต่ละ table
    for table in tables:
        table_name = table['name']
        print(f"\n=== Table: {table_name} ===")
        
        # Schema
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        print("Columns:")
        for col in columns:
            print(f"  {col['name']}: {col['type']} (nullable: {not col['notnull']})")
        
        # Sample data (ถ้ามี)
        try:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            count = cursor.fetchone()['count']
            print(f"  Records: {count}")
            
            if count > 0:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
                samples = cursor.fetchall()
                print("  Sample data:")
                for sample in samples:
                    print(f"    {dict(sample)}")
        except sqlite3.Error:
            print("  (ไม่สามารถอ่านข้อมูล)")
    
    # 3. ตรวจสอบ Views
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='view'")
    views = cursor.fetchall()
    
    print("\n=== Views ===")
    for view in views:
        print(f"  - {view['name']}")
        print(f"    SQL: {view['sql'][:200]}...")
    
    conn.close()

def check_semantic_mappings(database_path):
    """ตรวจสอบ semantic mappings ที่มีอยู่"""
    
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    
    print("\n=== Semantic Mappings ===")
    
    # ตรวจสอบ schema_semantic_mapping
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schema_semantic_mapping WHERE is_active = 1")
        mappings = cursor.fetchall()
        
        print("Active mappings:")
        for mapping in mappings:
            print(f"  {mapping['keyword']} -> {mapping['target_column']} {mapping['target_condition']}")
    except sqlite3.OperationalError:
        print("  Table schema_semantic_mapping ไม่พบ")
    
    conn.close()

if __name__ == "__main__":
    database_path = get_business_db_path()
    check_database_structure(database_path)
    check_semantic_mappings(database_path)