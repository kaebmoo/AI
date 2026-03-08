-- Migration 023: Create query_complexity_patterns table
-- Moves hardcoded classifier patterns to database for admin management

CREATE TABLE IF NOT EXISTS query_complexity_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier TEXT NOT NULL,              -- 'simple' or 'complex'
    pattern TEXT NOT NULL,
    description TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tier, pattern)
);

-- Seed complex patterns
INSERT OR IGNORE INTO query_complexity_patterns (tier, pattern, description) VALUES
    ('complex', 'เปรียบเทียบ', 'Comparison keyword'),
    ('complex', 'เทียบ', 'Comparison keyword short'),
    ('complex', 'แนวโน้ม', 'Trend keyword'),
    ('complex', 'trend', 'Trend keyword EN'),
    ('complex', 'ยอดสูงสุด.*ต่ำสุด', 'Max-min comparison'),
    ('complex', 'สัดส่วน', 'Proportion'),
    ('complex', 'ร้อยละ', 'Percentage TH'),
    ('complex', 'เปอร์เซ็นต์', 'Percentage TH alt'),
    ('complex', 'year.over.year', 'YoY'),
    ('complex', 'month.over.month', 'MoM'),
    ('complex', 'yoy', 'YoY abbrev'),
    ('complex', 'mom', 'MoM abbrev'),
    ('complex', 'การเปลี่ยนแปลง', 'Change keyword'),
    ('complex', 'เพิ่มขึ้น.*ลดลง', 'Increase-decrease'),
    ('complex', 'ลดลง.*เพิ่มขึ้น', 'Decrease-increase'),
    ('complex', 'วิเคราะห์', 'Analysis keyword'),
    ('complex', 'สรุป.*แยกตาม.*แยกตาม', 'Multiple dimensions'),
    ('complex', 'top\s*\d+', 'Top N'),
    ('complex', 'อันดับ', 'Ranking'),
    ('complex', 'pivot', 'Pivot'),
    ('complex', 'cross.tab', 'Crosstab'),
    ('complex', 'subquery', 'Subquery'),
    ('complex', 'nested', 'Nested query');

-- Seed simple patterns
INSERT OR IGNORE INTO query_complexity_patterns (tier, pattern, description) VALUES
    ('simple', '^รายได้\s*เดือน', 'Revenue by month'),
    ('simple', '^ค่าใช้จ่าย\s*เดือน', 'Expense by month'),
    ('simple', '^ยอดรวม', 'Total sum'),
    ('simple', '^ทั้งหมด', 'All total'),
    ('simple', '^รายได้\s*ปี', 'Revenue by year'),
    ('simple', '^ค่าใช้จ่าย\s*ปี', 'Expense by year'),
    ('simple', 'รายได้รวม', 'Total revenue'),
    ('simple', 'ค่าใช้จ่ายรวม', 'Total expense'),
    ('simple', 'เท่าไหร่$', 'How much suffix'),
    ('simple', 'เท่าไร$', 'How much suffix alt'),
    ('simple', 'กี่บาท$', 'How many baht suffix');
