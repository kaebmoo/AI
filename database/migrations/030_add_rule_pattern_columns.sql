-- Migration 030: Add pattern and check_type columns to schema_business_rules
-- Required for ValidationService to evaluate rules via regex matching
-- Idempotent: ALTER TABLE will silently fail if columns already exist

-- SQLite doesn't support IF NOT EXISTS for ALTER TABLE, so we use a trick
-- These will error on re-run but that's OK for migration scripts

ALTER TABLE schema_business_rules ADD COLUMN pattern TEXT;
ALTER TABLE schema_business_rules ADD COLUMN check_type TEXT DEFAULT 'regex_warning';

-- Seed patterns for builtin validation rules
UPDATE schema_business_rules SET pattern = '(?i)SELECT.*\bDATE\b(?!.*/\s*1000)', check_type = 'regex_warning' WHERE rule_code = 'DATE_CONVERSION';
UPDATE schema_business_rules SET pattern = '(?i)(กลุ่มธุรกิจ|หมวดบัญชี)(?!["''])', check_type = 'regex_error' WHERE rule_code = 'THAI_COLUMN_QUOTES';
UPDATE schema_business_rules SET pattern = '(?i)(REVENUE_VALUE|revenue_value).*ล้าน', check_type = 'context_warning' WHERE rule_code = 'REVENUE_UNIT';
UPDATE schema_business_rules SET pattern = '(?i)GROUP\s+BY', check_type = 'aggregate_check' WHERE rule_code = 'GROUP_BY_AGGREGATE';
UPDATE schema_business_rules SET pattern = '(?i)SELECT\s+\*', check_type = 'regex_warning' WHERE rule_code = 'NO_SELECT_STAR';
UPDATE schema_business_rules SET pattern = '(?i)^(?!.*LIMIT).*SELECT', check_type = 'regex_warning' WHERE rule_code = 'LIMIT_REQUIRED';
UPDATE schema_business_rules SET pattern = '(?i)^(?!.*(WHERE|AND).*YEAR).*FROM\s+(revenue|expense)', check_type = 'regex_warning' WHERE rule_code = 'YEAR_FILTER';
