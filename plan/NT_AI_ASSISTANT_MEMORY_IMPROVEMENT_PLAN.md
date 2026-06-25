# แผนปรับปรุง Memory & Chat History — AI Assistant
# สำหรับ Claude Code Execution

> **Project Path**: `/Users/seal/Documents/GitHub/AI`
> **Stack**: FastAPI + PostgreSQL + React + TypeScript + Ant Design
> **GitHub**: https://github.com/kaebmoo/AI

---

## ปัญหาปัจจุบัน

1. **Refresh = หายหมด** — Frontend ไม่เก็บ conversation state ใน persistent storage เมื่อ refresh browser สิ่งที่คุยหายทั้งหมด
2. **ไม่มีปุ่ม New Chat** — ไม่สามารถเริ่มสนทนาใหม่ได้ ต้อง refresh หน้า (แล้วก็หายหมด)
3. **ไม่มี Conversation List** — ไม่มี sidebar แสดงรายการ conversations ที่เคยคุย
4. **ไม่มี Conversation Title** — ไม่มีชื่อให้ conversation ทำให้หาสนทนาเก่ายาก

## สิ่งที่มีอยู่แล้ว (ห้าม break)

- `app/models/chat.py`: ChatHistory model มี `conversation_id` field อยู่แล้ว
- `app/models/chat_session.py`: ChatSessionData สำหรับ cache ผล query
- `app/api/v1/chat.py`: มีฟังก์ชัน `_get_conversation_history()`, `_save_history()`, `_resolve_context_with_history()` ทำงานอยู่แล้ว
- `frontend/services/chat.ts`: มี `getHistory()` API call อยู่แล้ว
- `frontend/services/storage.ts`: มี localStorage management อยู่แล้ว
- ระบบ rate limiting, audit logs, authentication ทั้งหมดต้องทำงานเหมือนเดิม

---

## Phase 1: Backend — Conversations Table + API

### Task 1.1: สร้าง Conversations Model

**สร้างไฟล์ใหม่**: `app/models/conversation.py`

```python
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship
from app.db.base import Base
import uuid
from datetime import datetime

def generate_conversation_id():
    return str(uuid.uuid4())

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=generate_conversation_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=True)  # auto-generated จากข้อความแรก
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_archived = Column(Boolean, default=False)
    message_count = Column(Integer, default=0)

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("ChatHistory", back_populates="conversation",
                          order_by="ChatHistory.created_at",
                          foreign_keys="ChatHistory.conversation_id")
```

**แก้ไขไฟล์ที่มีอยู่:**

1. เพิ่ม `conversations = relationship("Conversation", back_populates="user")` ใน User model
2. เพิ่ม `conversation = relationship("Conversation", back_populates="messages")` ใน ChatHistory model (ต้องตรวจสอบว่า ChatHistory.conversation_id เป็น FK ไปที่ conversations.id หรือยัง — ถ้ายังไม่เป็น FK ให้เพิ่ม ForeignKey constraint)

**หมายเหตุสำคัญ:**
- ตรวจสอบก่อนว่า `ChatHistory.conversation_id` เป็น Column type อะไร (String หรือ Integer) และมี ForeignKey constraint หรือยัง
- ถ้า conversation_id เป็นแค่ String ธรรมดา (ไม่มี FK) ให้เพิ่ม FK แต่ต้องทำ data migration ก่อน
- ดูไฟล์ `app/models/chat.py` จริงก่อนแก้ เพื่อให้แน่ใจว่า type ตรงกัน

### Task 1.2: Alembic Migration

สร้าง migration ใหม่:

```bash
cd /Users/seal/Documents/GitHub/AI
alembic revision --autogenerate -m "add conversations table"
```

**Migration ต้องทำ 3 อย่าง:**

1. สร้างตาราง `conversations`
2. ถ้า ChatHistory.conversation_id ยังไม่มี FK → เพิ่ม FK constraint (อาจต้อง nullable=True เพราะ old records อาจไม่มี conversation_id)
3. **Data migration**: query distinct `conversation_id` จาก `chat_history` ที่ไม่ใช่ NULL แล้วสร้าง record ใน `conversations` table โดย:
   - `id` = conversation_id จาก chat_history
   - `user_id` = user_id จาก record แรกของ conversation นั้น
   - `title` = ตัดเอา 50 ตัวอักษรแรกของ `question` จาก record แรก
   - `created_at` = created_at ของ record แรก
   - `updated_at` = created_at ของ record สุดท้าย
   - `message_count` = count ของ records ใน conversation นั้น

### Task 1.3: สร้าง Conversations API

**สร้างไฟล์ใหม่**: `app/api/v1/conversations.py`

Endpoints ที่ต้องสร้าง:

```
GET  /api/v1/conversations
     Query params: page (int, default 1), page_size (int, default 20), search (str, optional)
     Filter: user_id = current_user.id, is_archived = False
     Order: updated_at DESC
     Return: {
       items: [{ id, title, updated_at, message_count, preview }],
       total: int,
       page: int,
       page_size: int
     }
     โดย preview = ตัด 80 ตัวอักษรแรกของ question ล่าสุดใน conversation นั้น

GET  /api/v1/conversations/{conversation_id}
     Return: {
       id, title, created_at, updated_at, message_count,
       messages: [{ id, question, ai_response, created_at, generated_sql, tokens_used }]
     }
     messages เรียงตาม created_at ASC
     ใช้สำหรับ load conversation เก่ากลับมาแสดง

POST /api/v1/conversations
     Body: {} (ว่างเปล่า)
     สร้าง conversation ใหม่ด้วย title = null (จะ auto-generate ทีหลัง)
     Return: { id, title, created_at }

PATCH /api/v1/conversations/{conversation_id}
     Body: { title?: string, is_archived?: boolean }
     Return: { id, title, updated_at }
     ใช้สำหรับ: rename conversation, archive conversation

DELETE /api/v1/conversations/{conversation_id}
     Soft delete: set is_archived = True
     Return: { success: true }
```

**Register router** ใน app/main.py หรือ app/api/v1/__init__.py (ดูจาก pattern ที่ใช้อยู่)

### Task 1.4: แก้ไข Chat API ให้ Auto-create Conversation + Auto-generate Title

**แก้ไขไฟล์**: `app/api/v1/chat.py`

ใน chat endpoint ปัจจุบัน (POST /api/v1/chat) ปรับ logic ดังนี้:

1. **ถ้า request ไม่มี conversation_id:**
   - สร้าง Conversation record ใหม่
   - ใช้ conversation.id เป็น conversation_id

2. **ถ้า request มี conversation_id:**
   - ตรวจสอบว่า conversation นั้นเป็นของ current_user หรือไม่ (ป้องกัน unauthorized access)
   - ถ้าไม่ใช่ → return 403
   - ถ้าใช่ → ใช้ต่อตามเดิม

3. **Auto-generate title:**
   - หลังจากได้ ai_response แล้ว ตรวจสอบว่า conversation.title ยังเป็น NULL หรือไม่
   - ถ้าเป็น NULL (= message แรกของ conversation) → generate title
   - วิธี generate title: ตัดเอา 60 ตัวอักษรแรกของ user question ถ้ายาวกว่า 60 ตัวอักษรให้ตัดแล้วต่อด้วย "..."
   - (Optional ขั้นสูง: ใช้ LLM generate title สั้นๆ 5-10 คำ แต่จะเสีย token เพิ่ม ให้ตัดสินใจเอง ถ้าจะทำให้ใช้ model ราคาถูกที่สุดที่มี)

4. **อัปเดต Conversation metadata:**
   - หลัง `_save_history()` ให้ update conversation.updated_at = now() และ conversation.message_count += 1

---

## Phase 2: Frontend — Conversation Persistence + Sidebar + New Chat

### Task 2.1: เก็บ conversation_id ใน URL

**เป้าหมาย:** เมื่อ refresh browser แล้ว conversation กลับมาแสดงเหมือนเดิม

**แนวทาง:** ใช้ URL parameter เก็บ conversation_id

- URL pattern: `/chat/{conversation_id}` หรือ `/chat?c={conversation_id}`
- เมื่อ user เปิดหน้า chat:
  1. ตรวจสอบว่ามี conversation_id ใน URL หรือไม่
  2. ถ้ามี → เรียก `GET /api/v1/conversations/{conversation_id}` เพื่อ load messages กลับมาแสดง
  3. ถ้าไม่มี → แสดงหน้า chat ว่างเปล่า (new chat state)
- เมื่อ user ส่ง message แรก:
  1. เรียก `POST /api/v1/chat` (ไม่มี conversation_id)
  2. รับ conversation_id จาก response
  3. อัปเดต URL เป็น `/chat/{conversation_id}` โดยใช้ `window.history.replaceState()` (ไม่ trigger page reload)
- เมื่อ user ส่ง message ถัดไป:
  1. ส่ง conversation_id ที่ได้จาก message แรกไปด้วย

**ไฟล์ที่ต้องแก้:**
- `frontend/services/chat.ts` — เพิ่ม function `getConversation(conversationId)` ที่เรียก GET /api/v1/conversations/{id}
- Component หลักของ Chat page — เพิ่ม logic อ่าน conversation_id จาก URL + load messages
- React Router config (ถ้าใช้) — เพิ่ม route `/chat/:conversationId?`

**ข้อควรระวัง:**
- ตรวจสอบก่อนว่า project ใช้ React Router หรือ Next.js Router หรืออะไร ก่อนเขียน code
- ดู pattern การจัดการ routing ที่ใช้อยู่ แล้วทำตาม pattern เดิม
- อย่าเปลี่ยน router library

### Task 2.2: ปุ่ม New Chat (+)

**เป้าหมาย:** user กดปุ่ม "+" แล้วเริ่มสนทนาใหม่ สนทนาเก่ายังอยู่ใน sidebar

**Behavior:**
1. กดปุ่ม "+" → clear messages ในหน้า chat ปัจจุบัน
2. Reset state: conversation_id = null, messages = []
3. เปลี่ยน URL เป็น `/chat` (ไม่มี conversation_id)
4. Focus ไปที่ input box
5. ไม่สร้าง conversation record ใน DB ตอนกด "+" (สร้างเมื่อส่ง message แรก)

**ตำแหน่งปุ่ม:**
- ที่ header ของ sidebar (ข้างชื่อ app) หรือที่ top ของ chat area
- ดู layout ที่มีอยู่ก่อน แล้ววางให้เข้ากับ design pattern เดิม

**ไฟล์ที่ต้องแก้:**
- Chat page component — เพิ่มปุ่มและ handler
- ดู design pattern ที่ใช้ (Ant Design) แล้วใช้ component ที่เหมาะสม เช่น `Button` with `PlusOutlined` icon

### Task 2.3: Sidebar — Conversation List

**เป้าหมาย:** แสดงรายการ conversations ที่เคยคุยไว้ด้านซ้ายของหน้า chat

**Behavior:**
1. เมื่อเปิดหน้า chat → เรียก `GET /api/v1/conversations?page=1&page_size=20`
2. แสดงรายการใน sidebar เรียงตาม updated_at DESC
3. แต่ละ item แสดง: title + relative time (เช่น "2 ชั่วโมงที่แล้ว")
4. Conversation ที่กำลังดูอยู่ → highlight
5. กด conversation item → เรียก `GET /api/v1/conversations/{id}` แล้ว render messages
6. อัปเดต URL เป็น `/chat/{conversation_id}`
7. Infinite scroll หรือ "Load more" ที่ bottom ของ list

**Layout:**
- ตรวจสอบว่าหน้า chat ปัจจุบันมี sidebar อยู่แล้วหรือไม่
- ถ้ามี sidebar อยู่แล้ว → เพิ่ม conversation list เข้าไป
- ถ้ายังไม่มี → สร้าง sidebar ใหม่ ใช้ Ant Design `Layout.Sider` (width 260-300px, collapsible)
- Mobile responsive: ซ่อน sidebar เป็น drawer บน mobile

**ไฟล์ที่ต้องสร้าง/แก้:**
- สร้าง component ใหม่: `frontend/components/Chat/ConversationList.tsx` (หรือตาม structure ที่มีอยู่)
- แก้ Chat page layout เพิ่ม sidebar
- เพิ่ม `getConversations()` ใน `frontend/services/chat.ts`

**Ant Design components ที่ควรใช้:**
- `Layout.Sider` สำหรับ sidebar container
- `List` สำหรับ conversation items
- `Typography.Text` + `Typography.Paragraph` สำหรับ title + time
- `Skeleton` สำหรับ loading state
- `Empty` สำหรับ empty state ("ยังไม่มีประวัติสนทนา")

### Task 2.4: Conversation Actions

**เป้าหมาย:** user สามารถ rename และ delete conversation ได้

**Behavior:**
1. Hover conversation item ใน sidebar → แสดง "..." (more) icon
2. กด "..." → dropdown menu: "เปลี่ยนชื่อ", "ลบ"
3. เปลี่ยนชื่อ → inline edit (กด Enter save, กด Escape cancel) → เรียก `PATCH /api/v1/conversations/{id}`
4. ลบ → confirm dialog "ต้องการลบสนทนานี้?" → เรียก `DELETE /api/v1/conversations/{id}`
5. หลังลบ: ถ้า conversation ที่ลบคือ conversation ที่กำลังดูอยู่ → redirect ไป `/chat` (new chat state)

---

## Phase 3: Frontend — Load Messages on Refresh

### Task 3.1: Restore Chat State After Refresh

**เป้าหมาย:** เมื่อ user refresh หน้า browser ที่ URL `/chat/{conversation_id}` แล้ว messages กลับมาแสดงครบเหมือนเดิม

**Implementation:**

ใน Chat page component (useEffect on mount หรือ equivalent):

```
1. อ่าน conversation_id จาก URL params
2. ถ้ามี conversation_id:
   a. set loading = true
   b. เรียก GET /api/v1/conversations/{conversation_id}
   c. ถ้าสำเร็จ: set messages จาก response, set conversation_id ใน state
   d. ถ้า 404 หรือ 403: redirect ไป /chat (conversation ถูกลบหรือไม่ใช่ของ user)
   e. set loading = false
3. ถ้าไม่มี conversation_id:
   a. แสดง new chat state (messages = [], input focused)
```

**สิ่งที่ต้องระวัง:**
- Messages จาก API จะเป็น format `{ question, ai_response }` (1 record = 1 QA pair)
- ต้อง transform เป็น format ที่ Chat UI ใช้ (ตรวจสอบ ChatBubble.tsx ว่ารับ props อะไร)
- ถ้า ChatBubble.tsx รับแค่ `{ role, content }` ต้อง flatten: 1 QA pair → 2 messages (role=user + role=assistant)
- ตรวจสอบว่า DataChart.tsx / DataTable.tsx ต้องการ data จาก ChatSessionData ไหม ถ้าต้องการ ต้อง re-fetch หรือ re-parse จาก ai_response

**ไฟล์ที่ต้องแก้:**
- Chat page component — เพิ่ม useEffect สำหรับ load initial data
- อาจต้องสร้าง utility function `transformApiMessages(apiMessages) → chatBubbleMessages`

---

## Phase 4: ปรับปรุง Memory Quality (Optional / Future)

### Task 4.1: Token-Aware Context Window

ปัจจุบัน `_get_conversation_history()` limit 10 messages โดยไม่สนใจขนาด เปลี่ยนเป็น:

1. นับ token ของแต่ละ message (ประมาณ: 1 token ≈ 4 characters สำหรับภาษาอังกฤษ, ≈ 1-2 characters สำหรับภาษาไทย)
2. เริ่มจาก message ล่าสุด เพิ่มย้อนไปเรื่อยๆ จนชน budget (เช่น 4000 tokens)
3. ป้องกันไม่ให้ context กิน token เกิน budget

**แก้ไขไฟล์:** `app/api/v1/chat.py` ฟังก์ชัน `_get_conversation_history()`

### Task 4.2: Conversation Summary

เมื่อ conversation ยาวเกิน threshold (เช่น 20 messages):
1. สรุป messages เก่า (ก่อน 20 ล่าสุด) ด้วย LLM model ราคาถูก
2. เก็บ summary ใน Conversation model (เพิ่ม column `summary`)
3. ส่ง summary + 20 messages ล่าสุดเป็น context แทนการส่งแค่ 10 messages

---

## ลำดับการ Implement

```
Phase 1 (Backend)  → สามารถ test ด้วย curl/Postman ได้เลย
  1.1 Conversation Model
  1.2 Migration + Data Migration
  1.3 Conversations API
  1.4 แก้ Chat API

Phase 2 (Frontend) → ต้อง Phase 1 เสร็จก่อน
  2.1 URL-based conversation persistence
  2.2 New Chat button
  2.3 Conversation List sidebar
  2.4 Conversation actions (rename, delete)

Phase 3 (Frontend) → ต้อง Phase 2.1 เสร็จก่อน
  3.1 Restore chat state after refresh

Phase 4 (Optional) → ทำเมื่อไหร่ก็ได้
  4.1 Token-aware context window
  4.2 Conversation summary
```

## คำเตือนสำหรับ Claude Code

1. **อ่านไฟล์จริงก่อนแก้เสมอ** — ดูว่า import path, model structure, API pattern เป็นอย่างไร แล้วทำตาม pattern เดิม
2. **ห้าม break ของเดิม** — ทุก endpoint เดิมต้องทำงานเหมือนเดิม ทั้ง chat, history, bookmark
3. **ดู frontend framework ให้ชัดก่อน** — React + Ant Design + TypeScript แต่ต้องตรวจสอบว่าใช้ React Router หรือ routing แบบไหน
4. **Test หลังแก้ทุก Phase** — Backend: ทดสอบด้วย curl, Frontend: ทดสอบด้วย browser
5. **Migration ต้อง reversible** — Alembic migration ต้องมี downgrade() ที่ทำงานได้
6. **ChatHistory.conversation_id** — ตรวจสอบ type จริงในไฟล์ `app/models/chat.py` ก่อนสร้าง FK relationship ถ้า type ไม่ตรงกับ conversations.id ต้องจัดการให้ compatible
