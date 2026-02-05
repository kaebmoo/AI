
from app.services.schema_service import SchemaService
import json

def verify():
    service = SchemaService()
    
    # 1. Simulate creating "Transfer Price" Context
    print("Creating 'Transfer Price' context...")
    payload = {
        "name": "transfer_price",
        "display_name": "ราคาโอน (Transfer Price)",
        "description": "Information about transfer pricing between BUs",
        "main_view": "v_transfer_price",
        "is_active": True,
        "priority": 10,
        "keywords": ["tp", "transfer price", "ราคาโอน"],
        "instruction_th": """
    - **กฎสำคัญ (Transfer Price):**
      - ห้ามเปิดเผย Margin แก่บุคคลภายนอก
      - ราคาโอนมี 2 แบบ: `cost_plus` และ `market_price`
      - หน่วยเป็น **บาท** เสมอ
        """.strip(),
        "instruction_en": """
    - **Important Rule (Transfer Price):**
      - margin is confidential.
      - 2 Types: `cost_plus` and `market_price`
      - Unit is always **THB**
        """.strip()
    }
    
    # Check if exists first to avoid duplicate error
    existing = service.get_context_info("transfer_price")
    if existing:
        print("Context exists, updating...")
        service.update_context(existing['id'], payload)
    else:
        service.create_context(payload)
        
    print("✅ Context created/updated.")
    
    # 2. Verify Thai Prompt
    print("\n--- Verifying THAI Prompt ---")
    prompt_th = service.build_system_prompt(context_name="transfer_price", language="thai")
    
    if "ห้ามเปิดเผย Margin" in prompt_th:
        print("✅ Found Thai instruction: 'ห้ามเปิดเผย Margin'")
    else:
        print("❌ Thai instruction NOT found!")
        
    if "หน่วยเป็น **บาท** เสมอ" in prompt_th:
        print("✅ Found Thai instruction: 'หน่วยเป็น **บาท** เสมอ'")
    else:
        print("❌ Thai instruction NOT found!")

    # 3. Verify English Prompt
    print("\n--- Verifying ENGLISH Prompt ---")
    prompt_en = service.build_system_prompt(context_name="transfer_price", language="english")
    
    if "margin is confidential" in prompt_en:
        print("✅ Found English instruction: 'margin is confidential'")
    else:
        print("❌ English instruction NOT found!")
        
    print("\nVerification Complete.")

if __name__ == "__main__":
    verify()
