# Eval Report — 20260711_2149 (provider: default)

**Accuracy (strict): 3/51 = 0.0588** | incl. value_match: 0.3529 (value_match: 15, golden_broken: 12 — excluded)

## Per-context

| Context | Match | Total |
|---|---|---|
| Expense Optimization | 0 | 1 |
| Monthly Trends | 0 | 1 |
| Revenue | 0 | 1 |
| Top-N with Breakdown | 0 | 4 |
| comparison | 0 | 2 |
| expense | 0 | 8 |
| feed_revenue | 0 | 14 |
| pl_half_year_pivot | 0 | 1 |
| pl_monthly_by_bu | 0 | 1 |
| pl_operating_results | 0 | 1 |
| pl_product_performance | 0 | 2 |
| pl_service_group_performance | 0 | 1 |
| pl_yoy_comparison | 0 | 1 |
| product performance  | 0 | 1 |
| profit and loss | 0 | 2 |
| revenue | 3 | 7 |
| semantic_mapping_example | 0 | 2 |
| transfer price | 0 | 1 |

## Value match (ค่าตรงแต่ชื่อคอลัมน์ต่าง — ตรวจ projection ด้วยตา)

- [38] รายได้กลุ่มธุรกิจ และ กลุ่มบริการ
- [51] รายได้รวมทั้งบริษัทเดือนมกราคม 2567 เท่าไร
- [52] รายได้ของกลุ่มธุรกิจ 1.Hard Infrastructure เดือนมกราคม 2567 เท่าไร
- [53] รายได้ของกลุ่มธุรกิจ 7.กลุ่มบริการอื่นไม่ใช่โทรคมนาคม เดือนมกราคม 2567
- [54] รายได้รวมทั้งบริษัทเดือนสิงหาคม 2567 เท่าไร
- [55] รายได้ของกลุ่มธุรกิจ 1.Hard Infrastructure เดือนสิงหาคม 2567 เท่าไร
- [56] รายได้ของกลุ่มธุรกิจ 7.กลุ่มบริการอื่นไม่ใช่โทรคมนาคม เดือนสิงหาคม 256
- [57] รายได้รวมทั้งบริษัทเดือนมีนาคม 2568 เท่าไร
- [58] รายได้ของกลุ่มธุรกิจ 1.Hard Infrastructure เดือนมีนาคม 2568 เท่าไร
- [59] รายได้ของกลุ่มธุรกิจ 7.กลุ่มบริการอื่นไม่ใช่โทรคมนาคม เดือนมีนาคม 2568
- [60] รายได้รวมทั้งบริษัทเดือนพฤษภาคม 2569 เท่าไร
- [61] รายได้ของกลุ่มธุรกิจ 1.Hard Infrastructure เดือนพฤษภาคม 2569 เท่าไร
- [62] รายได้ของกลุ่มธุรกิจ 7.กลุ่มบริการอื่นไม่ใช่โทรคมนาคม เดือนพฤษภาคม 256
- [63] รายได้สะสม (YTD) ของกลุ่มธุรกิจ 8.รายได้อื่น ณ เดือนพฤษภาคม 2569 เท่าไ
- [64] รายได้สะสมทั้งบริษัทตั้งแต่ต้นปีถึงเดือนพฤษภาคม 2569 เท่าไร

## Failures

### [1] หน่วยงานไหนมีรายได้มากที่สุด 5 อันดับแรก และน้อยที่สุด 5 อันดับแรก — `mismatch`
- detail: expected 10 rows, got 10
```sql
-- expected
SELECT 'มากสุด' as category, department, total FROM (
    SELECT department, SUM(revenue) as total 
    FROM revenue_search 
    GROUP BY department 
    ORDER BY total DESC 
    LIMIT 5
)
UNION ALL
SELECT 'น้อยสุด' as category, department, total FROM (
    SELECT department, SUM(revenue) as total 
    FROM revenue_search 
    GROUP BY department 
    ORDER BY total ASC 
    LIMIT 5
)
-- generated
SELECT
  'Top 5' AS category,
  department,
  "รายได้รวม"
FROM (
  SELECT
    department,
    SUM(COALESCE(revenue, 0)) AS "รายได้รวม"
  FROM revenue_search
  WHERE
    BUSINESS_GROUP != 'รายได้อื่น' AND year = 2025
  GROUP BY
    department
  ORDER BY
    "รายได้รวม" DESC
  LIMIT 5
)
UNION ALL
SELECT
  'Bottom 5' AS category,
  department,
  "รายได้รวม"
FROM (
  SELECT
    department,
    SUM(COALESCE(revenue, 0)) AS "รายได้รวม"
  FROM revenue_search
  WHERE
    BUSINESS_GROUP != 'รายได้อื่น' AND year = 2025
  GROUP BY
    department
  ORDER BY
    "รายได้รวม" ASC
  LIMIT 5
);
```

### [2] ฝ่ายไหนมีรายได้จากอสังหาริมทรัพย์มากที่สุด 5 อันดับแรก และน้อยที่สุด 5 อันดับแรก — `mismatch`
- detail: expected 10 rows, got 10
```sql
-- expected
SELECT 'มากสุด' as category, department, total FROM (
    SELECT department, SUM(revenue) as total 
    FROM revenue_search 
    WHERE SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'
    GROUP BY department 
    ORDER BY total DESC 
    LIMIT 5
)
UNION ALL
SELECT 'น้อยสุด' as category, department, total FROM (
    SELECT department, SUM(revenue) as total 
    FROM revenue_search 
    WHERE SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'
    GROUP BY department 
    ORDER BY total ASC 
    LIMIT 5
)
-- generated
SELECT 'มากที่สุด 5 อันดับแรก' AS "ประเภท", "ฝ่าย", "รายได้รวม" FROM (
    SELECT
        department AS "ฝ่าย",
        SUM(COALESCE(revenue, 0)) AS "รายได้รวม"
    FROM
        revenue_search
    WHERE
        service_group LIKE '%กลุ่มบริการพัฒนาสินทรัพย์%'
        AND BUSINESS_GROUP != 'รายได้อื่น'
        AND year = 2025
    GROUP BY
        department
    ORDER BY
        "รายได้รวม" DESC
    LIMIT 5
)
UNION ALL
SELECT 'น้อยที่สุด 5 อันดับแรก' AS "ประเภท", "ฝ่าย", "รายได้รวม" FROM (
    SELECT
        department AS "ฝ่าย",
        SUM(COALESCE(revenue, 0)) AS "รายได้รวม"
    FROM
        revenue_search
    WHERE
        service_group LIKE '%กลุ่มบริการพัฒนาสินทรัพย์%'
        AND BUSINESS_GROUP != 'รายได้อื่น'
        AND year = 2025
    GROUP BY
        department
    ORDER BY
        "รายได้รวม" ASC
    LIMIT 5
);
```

### [3] แบ่งกลุ่มรายได้ของ น่าน ให้ด้วย เป็น สามระดับ มาก ปานกลาง น้อย ว่ามาจากบริการอะไรบ้าง — `mismatch`
- detail: expected 15 rows, got 38
```sql
-- expected
WITH ServiceSummary AS (
    -- ขั้นตอนที่ 1: สรุปรายได้แยกตามกลุ่มบริการในพื้นที่น่าน
    SELECT 
        SERVICE_GROUP,
        SUM(revenue) AS total_revenue
    FROM revenue_search
    WHERE section LIKE '%น่าน%'
      AND BUSINESS_GROUP != 'รายได้อื่น'
    GROUP BY SERVICE_GROUP
),
RankedService AS (
    -- ขั้นตอนที่ 2: ใช้ NTILE เพื่อแบ่งกลุ่มบริการออกเป็น 3 ระดับเท่าๆ กันตามรายได้
    SELECT 
        SERVICE_GROUP,
        total_revenue,
        NTILE(3) OVER (ORDER BY total_revenue DESC) as rank_group
    FROM ServiceSummary
)
-- ขั้นตอนที่ 3: แสดงผลลัพธ์พร้อมระบุระดับ มาก ปานกลาง น้อย
SELECT 
    CASE 
        WHEN rank_group = 1 THEN 'มาก'
        WHEN rank_group = 2 THEN 'ปานกลาง'
        ELSE 'น้อย'
    END AS ระดับรายได้,
    SERVICE_GROUP AS กลุ่มบริการ,
    total_revenue AS รายได้_บาท
FROM RankedService
ORDER BY rank_group, total_revenue DESC;
-- generated
WITH NanRevenue AS (
    SELECT
        PRODUCT_NAME,
        SUM(COALESCE(revenue, 0)) AS product_total_revenue
    FROM
        revenue_search
    WHERE
        section LIKE '%น่าน%'
        AND year = 2025
        AND BUSINESS_GROUP != 'รายได้อื่น'
    GROUP BY
        PRODUCT_NAME
),
RevenueStats AS (
    SELECT
        AVG(product_total_revenue) AS avg_revenue
    FROM
        NanRevenue
)
SELECT
    nr.PRODUCT_NAME AS "บริการ",
    nr.product_total_revenue AS "รายได้รวม",
    CASE
        WHEN nr.product_total_revenue >= (SELECT avg_revenue FROM RevenueStats) * 1.5 THEN 'มาก'
        WHEN nr.product_total_revenue <= (SELECT avg_revenue FROM RevenueStats) * 0.5 THEN 'น้อย'
        ELSE 'ปานกลาง'
    END AS "ระดับรายได้"
FROM
    NanRevenue nr
ORDER BY
    nr.product_total_revenue DESC;
```

### [4] ถ้าไม่นับการโอนเองในสายงาน ช่วยสรุป การโอนกันระหว่างสายงานให้ด้วย — `mismatch`
- detail: expected 71 rows, got 71
```sql
-- expected
SELECT 
    owner_division AS สายงานผู้ให้บริการ, 
    user_division AS สายงานผู้รับบริการ, 
    SUM(total_price_value) / 1000000.0 AS total_price_million_baht
FROM v_transfer_price
WHERE owner_division != user_division
AND year = 2025
GROUP BY owner_division, user_division
ORDER BY total_price_million_baht DESC;
-- generated
SELECT
  owner_division AS "สายงานผู้ให้บริการ",
  user_division AS "สายงานผู้รับบริการ",
  SUM(total_price_value) AS "มูลค่าการโอนรวม"
FROM v_transfer_price
WHERE
  owner_division != user_division AND year = 2025
GROUP BY
  owner_division,
  user_division
ORDER BY
  "สายงานผู้ให้บริการ",
  "สายงานผู้รับบริการ";
```

### [5] ขอรายได้รายกลุ่มบริการ แบบรายเดือน — `mismatch`
- detail: expected 317 rows, got 317
```sql
-- expected
SELECT 
  year, 
  CAST(month AS INTEGER) AS month, 
  SERVICE_GROUP, 
  SUM(revenue) AS revenue_baht
FROM revenue_search
WHERE BUSINESS_GROUP != 'รายได้อื่น'
GROUP BY year, CAST(month AS INTEGER), SERVICE_GROUP
ORDER BY year, CAST(month AS INTEGER), SERVICE_GROUP
-- generated
SELECT
  SERVICE_GROUP AS "กลุ่มบริการ",
  year AS "ปี",
  CAST(month AS INTEGER) AS "เดือน",
  SUM(COALESCE(revenue, 0)) AS "รายได้รวม"
FROM revenue_search
WHERE
  BUSINESS_GROUP != 'รายได้อื่น' AND year = 2025
GROUP BY
  SERVICE_GROUP,
  year,
  CAST(month AS INTEGER)
ORDER BY
  SERVICE_GROUP,
  year,
  CAST(month AS INTEGER);
```

### [6] ถ้าตัดค่าใช้จ่ายที่สูงเกิน 75 percentile ออก ค่าใช้จ่าย 20 อันดับแรกเป็น GL อะไร แยกตามฝ่าย — `mismatch`
- detail: expected 20 rows, got 20
```sql
-- expected
WITH expense_ranked AS (
      SELECT
          expense,
          ROW_NUMBER() OVER (ORDER BY expense) AS rn,
          COUNT(*) OVER () AS total_count
      FROM v_expense_mart
  ),
  percentile_75 AS (
      SELECT
          expense AS p75_expense
      FROM expense_ranked
      WHERE rn = CAST(total_count * 0.75 AS INTEGER)
  ),
  filtered_expense AS (
      SELECT *
      FROM v_expense_mart
      WHERE expense <= (SELECT p75_expense FROM percentile_75)
  )
  SELECT
      department,
      gl_code || ': ' || account_name AS gl_account,
      SUM(expense) AS total_expense
  FROM filtered_expense
  GROUP BY department, gl_code, account_name
  ORDER BY total_expense DESC
  LIMIT 20
-- generated
WITH Percentile75 AS (
    SELECT
        expense
    FROM
        v_expense_mart
    WHERE
        year = 2025
        AND expense IS NOT NULL
    ORDER BY
        expense
    LIMIT 1
    OFFSET (SELECT CAST(COUNT(*) * 0.75 AS INTEGER) FROM v_expense_mart WHERE year = 2025 AND expense IS NOT NULL)
)
SELECT
    T1.gl_code,
    T1.account_name,
    T1.department,
    SUM(COALESCE(T1.expense, 0)) AS "ค่าใช้จ่ายรวม"
FROM
    v_expense_mart AS T1,
    Percentile75 AS P75
WHERE
    T1.year = 2025
    AND T1.expense <= P75.expense
GROUP BY
    T1.gl_code,
    T1.account_name,
    T1.department
ORDER BY
    "ค่าใช้จ่ายรวม" DESC
LIMIT 20;
```

### [7] ขอข้อมูลผลดำเนินงานกลุ่มธุรกิจ ปี 2568 — `mismatch`
- detail: expected 14 rows, got 14
```sql
-- expected
SELECT 
    main_group,
    ROUND(SUM(CASE WHEN UPPER(business_unit) LIKE '%HARD INFRASTRUCTURE%' 
          THEN amount_value ELSE 0 END) / 1e6, 2) AS hard_infra_mb,
    ROUND(SUM(CASE WHEN UPPER(business_unit) LIKE '%INTERNATIONAL%' 
          THEN amount_value ELSE 0 END) / 1e6, 2) AS intl_mb,
    ROUND(SUM(CASE WHEN UPPER(business_unit) LIKE '%MOBILE%' 
          THEN amount_value ELSE 0 END) / 1e6, 2) AS mobile_mb,
    ROUND(SUM(CASE WHEN UPPER(business_unit) LIKE '%FIXED LINE%' 
          THEN amount_value ELSE 0 END) / 1e6, 2) AS fixed_bb_mb,
    ROUND(SUM(CASE WHEN UPPER(business_unit) LIKE '%DIGITAL%' 
          THEN amount_value ELSE 0 END) / 1e6, 2) AS digital_mb,
    ROUND(SUM(CASE WHEN UPPER(business_unit) LIKE '%ICT SOLUTION%' 
          THEN amount_value ELSE 0 END) / 1e6, 2) AS ict_sol_mb,
    ROUND(SUM(amount_value) / 1e6, 2) AS total_mb
FROM v_pl_costtype_nt_mth_clean
WHERE report_year = 2025
  AND main_group != ''
  AND business_unit != ''
GROUP BY main_group
ORDER BY main_group;
-- generated
WITH NormalizedData AS (
  SELECT
    CASE
      WHEN UPPER(business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
      WHEN UPPER(business_unit) LIKE '%INTERNATIONAL%' THEN 'International'
      WHEN UPPER(business_unit) LIKE '%MOBILE%' THEN 'Mobile'
      WHEN UPPER(business_unit) LIKE '%FIXED LINE%' THEN 'Fixed Line & Broadband'
      WHEN UPPER(business_unit) LIKE '%DIGITAL%' THEN 'Digital'
      WHEN UPPER(business_unit) LIKE '%ICT SOLUTION%' THEN 'ICT Solution'
      WHEN UPPER(business_unit) LIKE '%ไม่ใช่โทรคมนาคม%' THEN 'บริการอื่นไม่ใช่โทรคมนาคม'
      WHEN UPPER(business_unit) LIKE '%รายได้อื่น%' THEN 'รายได้อื่น/ค่าใช้จ่ายอื่น'
      WHEN UPPER(business_unit) LIKE '%นโยบายภาครัฐ%' THEN 'บริการตามนโยบายภาครัฐ'
      ELSE business_unit
    END AS business_unit_name,
    CASE
      WHEN main_group = '01.รายได้' THEN '01. รายได้'
      WHEN main_group = '02.ต้นทุนบริการและต้นทุนขาย :' THEN '02. ต้นทุนบริการและต้นทุนขาย'
      WHEN main_group = '03.กำไรขั้นต้น' THEN '03. กำไรขั้นต้น'
      WHEN main_group = '08.กำไรก่อนต้นทุนจัดหาเงินฯ' THEN '08. กำไรก่อนต้นทุนจัดหาเงินฯ'
      WHEN main_group = '12.กำไรก่อนภาษี' THEN '12. กำไรก่อนภาษี'
      WHEN main_group = '14.กำไรสุทธิ' THEN '14. กำไรสุทธิ'
      ELSE main_group
    END AS pl_item,
    amount_value
  FROM v_pl_costtype_nt_mth_clean
  WHERE
    report_year = 2025 -- ปี พ.ศ. 2568 แปลงเป็น ค.ศ. 2025
    AND main_group IN (
      '01.รายได้',
      '02.ต้นทุนบริการและต้นทุนขาย :',
      '03.กำไรขั้นต้น',
      '08.กำไรก่อนต้นทุนจัดหาเงินฯ',
      '12.กำไรก่อนภาษี',
      '14.กำไรสุทธิ'
    )
    AND main_group != ''
    AND business_unit != ''
    AND alliance_flag = 'N'
),
BusinessUnitTotalRevenue AS (
  SELECT
    business_unit_name,
    SUM(CASE WHEN pl_item LIKE '01.%' THEN amount_value ELSE 0 END) AS total_revenue_for_ordering
  FROM NormalizedData
  GROUP BY business_unit_name
)
SELECT
  nd.business_unit_name AS "กลุ่มธุรกิจ",
  nd.pl_item AS "รายการ",
  ROUND(SUM(nd.amount_value) / 1000000.0, 2) AS "มูลค่า (ล้านบาท)"
FROM NormalizedData nd
JOIN BusinessUnitTotalRevenue butr ON nd.business_unit_name = butr.business_unit_name
GROUP BY
  nd.business_unit_name,
  nd.pl_item
ORDER BY
  butr.total_revenue_for_ordering DESC,
  nd.pl_item ASC;
```

### [8] ขอข้อมูลผลดำเนินงานกลุ่มธุรกิจ ปี 2568 — `mismatch`
- detail: expected 8 rows, got 14
```sql
-- expected
SELECT 
    CASE 
        WHEN UPPER(business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
        WHEN UPPER(business_unit) LIKE '%INTERNATIONAL%'       THEN 'International'
        WHEN UPPER(business_unit) LIKE '%MOBILE%'              THEN 'Mobile'
        WHEN UPPER(business_unit) LIKE '%FIXED LINE%'          THEN 'Fixed Line & Broadband'
        WHEN UPPER(business_unit) LIKE '%DIGITAL%'             THEN 'Digital'
        WHEN UPPER(business_unit) LIKE '%ICT SOLUTION%'        THEN 'ICT Solution'
        WHEN UPPER(business_unit) LIKE '%ไม่ใช่โทรคมนาคม%'     THEN 'บริการอื่นไม่ใช่โทรคมนาคม'
        WHEN UPPER(business_unit) LIKE '%รายได้อื่น%'           THEN 'รายได้อื่น/ค่าใช้จ่ายอื่น'
        WHEN UPPER(business_unit) LIKE '%นโยบายภาครัฐ%'        THEN 'บริการตามนโยบายภาครัฐ'
        ELSE business_unit
    END AS business_unit_name,
    ROUND(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS revenue_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '02.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS cost_of_service_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS gross_profit_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '04.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS selling_expense_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '06.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS admin_expense_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '08.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS operating_profit_mb
FROM v_pl_costtype_nt_mth_clean
WHERE report_year = 2025
  AND business_unit != ''
  AND main_group != ''
GROUP BY business_unit_name
ORDER BY revenue_mb DESC
-- generated
WITH business_unit_revenue AS (
  SELECT
    CASE
      WHEN UPPER(business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
      WHEN UPPER(business_unit) LIKE '%INTERNATIONAL%' THEN 'International'
      WHEN UPPER(business_unit) LIKE '%MOBILE%' THEN 'Mobile'
      WHEN UPPER(business_unit) LIKE '%FIXED LINE%' THEN 'Fixed Line & Broadband'
      WHEN UPPER(business_unit) LIKE '%DIGITAL%' THEN 'Digital'
      WHEN UPPER(business_unit) LIKE '%ICT SOLUTION%' THEN 'ICT Solution'
      WHEN UPPER(business_unit) LIKE '%ไม่ใช่โทรคมนาคม%' THEN 'บริการอื่นไม่ใช่โทรคมนาคม'
      WHEN UPPER(business_unit) LIKE '%รายได้อื่น%' THEN 'รายได้อื่น/ค่าใช้จ่ายอื่น'
      WHEN UPPER(business_unit) LIKE '%นโยบายภาครัฐ%' THEN 'บริการตามนโยบายภาครัฐ'
      ELSE business_unit
    END AS normalized_business_unit,
    SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END) AS total_revenue_for_ordering
  FROM v_pl_costtype_nt_mth_clean
  WHERE
    report_year = 2025
    AND main_group LIKE '01.%'
    AND business_unit != ''
  GROUP BY normalized_business_unit
)
SELECT
  CASE
    WHEN UPPER(t1.business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
    WHEN UPPER(t1.business_unit) LIKE '%INTERNATIONAL%' THEN 'International'
    WHEN UPPER(t1.business_unit) LIKE '%MOBILE%' THEN 'Mobile'
    WHEN UPPER(t1.business_unit) LIKE '%FIXED LINE%' THEN 'Fixed Line & Broadband'
    WHEN UPPER(t1.business_unit) LIKE '%DIGITAL%' THEN 'Digital'
    WHEN UPPER(t1.business_unit) LIKE '%ICT SOLUTION%' THEN 'ICT Solution'
    WHEN UPPER(t1.business_unit) LIKE '%ไม่ใช่โทรคมนาคม%' THEN 'บริการอื่นไม่ใช่โทรคมนาคม'
    WHEN UPPER(t1.business_unit) LIKE '%รายได้อื่น%' THEN 'รายได้อื่น/ค่าใช้จ่ายอื่น'
    WHEN UPPER(t1.business_unit) LIKE '%นโยบายภาครัฐ%' THEN 'บริการตามนโยบายภาครัฐ'
    ELSE t1.business_unit
  END AS "กลุ่มธุรกิจ",
  t1.main_group AS "รายการ",
  ROUND(SUM(t1.amount_value) / 1000000.0, 2) AS "มูลค่า (ล้านบาท)"
FROM v_pl_costtype_nt_mth_clean AS t1
JOIN business_unit_revenue AS t2
  ON (CASE
        WHEN UPPER(t1.business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
        WHEN UPPER(t1.business_unit) LIKE '%INTERNATIONAL%' THEN 'International'
        WHEN UPPER(t1.business_unit) LIKE '%MOBILE%' THEN 'Mobile'
        WHEN UPPER(t1.business_unit) LIKE '%FIXED LINE%' THEN 'Fixed Line & Broadband'
        WHEN UPPER(t1.business_unit) LIKE '%DIGITAL%' THEN 'Digital'
        WHEN UPPER(t1.business_unit) LIKE '%ICT SOLUTION%' THEN 'ICT Solution'
        WHEN UPPER(t1.business_unit) LIKE '%ไม่ใช่โทรคมนาคม%' THEN 'บริการอื่นไม่ใช่โทรคมนาคม'
        WHEN UPPER(t1.business_unit) LIKE '%รายได้อื่น%' THEN 'รายได้อื่น/ค่าใช้จ่ายอื่น'
        WHEN UPPER(t1.business_unit) LIKE '%นโยบายภาครัฐ%' THEN 'บริการตามนโยบายภาครัฐ'
        ELSE t1.business_unit
      END) = t2.normalized_business_unit
WHERE
  t1.report_year = 2025
  AND t1.main_group IN (
    '01.รายได้',
    '02.ต้นทุนบริการและต้นทุนขาย :',
    '03.กำไรขั้นต้น',
    '08.กำไรก่อนต้นทุนจัดหาเงินฯ',
    '12.กำไรก่อนภาษี',
    '14.กำไรสุทธิ'
  )
  AND t1.main_group != ''
  AND t1.business_unit != ''
GROUP BY
  "กลุ่มธุรกิจ",
  "รายการ"
ORDER BY
  t2.total_revenue_for_ordering DESC,
  t1.main_group ASC;
```

### [9] เทียบผลดำเนินงานกลุ่มธุรกิจของปี 2567 และ 2568 ขอผลต่างด้วย ทั้งกำไร รายได้ ค่าใช้จ่าย — `mismatch`
- detail: expected 8 rows, got 1
```sql
-- expected
SELECT 
    CASE 
        WHEN UPPER(business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
        WHEN UPPER(business_unit) LIKE '%INTERNATIONAL%'       THEN 'International'
        WHEN UPPER(business_unit) LIKE '%MOBILE%'              THEN 'Mobile'
        WHEN UPPER(business_unit) LIKE '%FIXED LINE%'          THEN 'Fixed Line & Broadband'
        WHEN UPPER(business_unit) LIKE '%DIGITAL%'             THEN 'Digital'
        WHEN UPPER(business_unit) LIKE '%ICT SOLUTION%'        THEN 'ICT Solution'
        WHEN UPPER(business_unit) LIKE '%ไม่ใช่โทรคมนาคม%'     THEN 'บริการอื่นไม่ใช่โทรคมนาคม'
        WHEN UPPER(business_unit) LIKE '%รายได้อื่น%'           THEN 'รายได้อื่น/ค่าใช้จ่ายอื่น'
        WHEN UPPER(business_unit) LIKE '%นโยบายภาครัฐ%'        THEN 'บริการตามนโยบายภาครัฐ'
        ELSE business_unit
    END AS business_unit_name,
    -- รายได้
    ROUND(SUM(CASE WHEN main_group LIKE '01.%' AND report_year = 2024 THEN amount_value ELSE 0 END) / 1e6, 2) AS revenue_2567,
    ROUND(SUM(CASE WHEN main_group LIKE '01.%' AND report_year = 2025 THEN amount_value ELSE 0 END) / 1e6, 2) AS revenue_2568,
    ROUND((SUM(CASE WHEN main_group LIKE '01.%' AND report_year = 2025 THEN amount_value ELSE 0 END) 
         - SUM(CASE WHEN main_group LIKE '01.%' AND report_year = 2024 THEN amount_value ELSE 0 END)) / 1e6, 2) AS revenue_diff,
    -- ค่าใช้จ่ายรวม (02+04+06)
    ROUND((SUM(CASE WHEN main_group LIKE '02.%' AND report_year = 2024 THEN amount_value ELSE 0 END)
         + SUM(CASE WHEN main_group LIKE '04.%' AND report_year = 2024 THEN amount_value ELSE 0 END)
         + SUM(CASE WHEN main_group LIKE '06.%' AND report_year = 2024 THEN amount_value ELSE 0 END)) / 1e6, 2) AS expense_2567,
    ROUND((SUM(CASE WHEN main_group LIKE '02.%' AND report_year = 2025 THEN amount_value ELSE 0 END)
         + SUM(CASE WHEN main_group LIKE '04.%' AND report_year = 2025 THEN amount_value ELSE 0 END)
         + SUM(CASE WHEN main_group LIKE '06.%' AND report_year = 2025 THEN amount_value ELSE 0 END)) / 1e6, 2) AS expense_2568,
    ROUND(((SUM(CASE WHEN main_group LIKE '02.%' AND report_year = 2025 THEN amount_value ELSE 0 END)
          + SUM(CASE WHEN main_group LIKE '04.%' AND report_year = 2025 THEN amount_value ELSE 0 END)
          + SUM(CASE WHEN main_group LIKE '06.%' AND report_year = 2025 THEN amount_value ELSE 0 END))
         -(SUM(CASE WHEN main_group LIKE '02.%' AND report_year = 2024 THEN amount_value ELSE 0 END)
          + SUM(CASE WHEN main_group LIKE '04.%' AND report_year = 2024 THEN amount_value ELSE 0 END)
          + SUM(CASE WHEN main_group LIKE '06.%' AND report_year = 2024 THEN amount_value ELSE 0 END))) / 1e6, 2) AS expense_diff,
    -- กำไรสุทธิ
    ROUND(SUM(CASE WHEN main_group LIKE '14.%' AND report_year = 2024 THEN amount_value ELSE 0 END) / 1e6, 2) AS net_profit_2567,
    ROUND(SUM(CASE WHEN main_group LIKE '14.%' AND report_year = 2025 THEN amount_value ELSE 0 END) / 1e6, 2) AS net_profit_2568,
    ROUND((SUM(CASE WHEN main_group LIKE '14.%' AND report_year = 2025 THEN amount_value ELSE 0 END)
         - SUM(CASE WHEN main_group LIKE '14.%' AND report_year = 2024 THEN amount_value ELSE 0 END)) / 1e6, 2) AS net_profit_diff
FROM v_pl_costtype_nt_mth_clean
WHERE main_group != ''
  AND business_unit != ''
  AND report_year IN (2024, 2025)
GROUP BY business_unit_name
ORDER BY revenue_2568 DESC
-- generated
SELECT
    bg.business_group AS "กลุ่มธุรกิจ",
    COALESCE(e2024.total_expense, 0) AS "ค่าใช้จ่ายปี 2567",
    COALESCE(e2025.total_expense, 0) AS "ค่าใช้จ่ายปี 2568",
    (COALESCE(e2025.total_expense, 0) - COALESCE(e2024.total_expense, 0)) AS "ผลต่างค่าใช้จ่าย (2568 - 2567)"
FROM
    (SELECT DISTINCT business_group FROM v_expense_mart WHERE year IN (2024, 2025)) AS bg
LEFT JOIN
    (SELECT business_group, SUM(COALESCE(expense, 0)) AS total_expense FROM v_expense_mart WHERE year = 2024 GROUP BY business_group) AS e2024
ON
    bg.business_group = e2024.business_group
LEFT JOIN
    (SELECT business_group, SUM(COALESCE(expense, 0)) AS total_expense FROM v_expense_mart WHERE year = 2025 GROUP BY business_group) AS e2025
ON
    bg.business_group = e2025.business_group
ORDER BY
    bg.business_group;
```

### [11] บริการใดที่มีผลประกอบการดี — `mismatch`
- detail: expected 15 rows, got 10
```sql
-- expected
SELECT 
    product_name,
    ROUND(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS revenue_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '02.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS cost_of_service_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS gross_profit_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END) * 100.0 /
          NULLIF(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END), 0), 1) AS gross_margin_pct
FROM v_pl_costtype_nt_mth_clean
WHERE report_year = 2025
  AND main_group != ''
  AND product_name != ''
GROUP BY product_name
HAVING SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END) > 0
ORDER BY gross_profit_mb DESC
LIMIT 15
-- generated
SELECT
  PRODUCT_NAME,
  SUM(COALESCE(revenue, 0)) AS "รายได้รวม"
FROM revenue_search
WHERE
  BUSINESS_GROUP != 'รายได้อื่น' AND year = 2025
GROUP BY
  PRODUCT_NAME
ORDER BY
  "รายได้รวม" DESC
LIMIT 10;
```

### [12] บริการใดที่ขาดทุน — `generation_failed`
- detail: Max retries exceeded
```sql
-- expected
SELECT 
    product_name,
    ROUND(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS revenue_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '02.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS cost_of_service_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS gross_profit_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END) * 100.0 /
          NULLIF(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END), 0), 1) AS gross_margin_pct
FROM v_pl_costtype_nt_mth_clean
WHERE report_year = 2025
  AND main_group != ''
  AND product_name != ''
GROUP BY product_name
HAVING SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END) < 0
ORDER BY gross_profit_mb ASC
-- generated
ite
SELECT
  product_name AS "บริการ",
  ROUND(SUM(amount_value) / 1000000.0, 2) AS "กำไรสุทธิ (ล้านบาท)"
FROM v_pl_costtype_nt_mth_clean
WHERE
  report_year = 2025 AND
  main_group LIKE '14.%' AND
  main_group != '' AND
  product_name != ''
GROUP BY
  product_name
HAVING
  SUM(amount_value) < 0
ORDER BY
  "กำไรสุทธิ (ล้านบาท)" ASC
LIMIT 10;
```

### [13] กลุ่มบริการใดมีรายได้สูงสุด — `mismatch`
- detail: expected 10 rows, got 1
```sql
-- expected
SELECT 
    service_group,
    ROUND(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS revenue_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS gross_profit_mb,
    ROUND(SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END) * 100.0 /
          NULLIF(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END), 0), 1) AS gross_margin_pct
FROM v_pl_costtype_nt_mth
WHERE report_year = 2025
  AND main_group != ''
  AND service_group != ''
GROUP BY service_group
ORDER BY revenue_mb DESC
LIMIT 10
-- generated
SELECT
  SERVICE_GROUP,
  SUM(COALESCE(revenue, 0)) AS "รายได้รวม"
FROM revenue_search
WHERE
  BUSINESS_GROUP != 'รายได้อื่น' AND year = 2025
GROUP BY
  SERVICE_GROUP
ORDER BY
  "รายได้รวม" DESC
LIMIT 1;
```

### [14] ผลดำเนินงานของ บริการ NT HOME PHONE — `mismatch`
- detail: expected 10 rows, got 2
```sql
-- expected
SELECT 
    main_group, 
    ROUND(SUM(amount_value) / 1000000.0, 2) AS value_million_baht
FROM v_pl_costtype_nt_mth_clean
WHERE 
    report_year = 2025 
    AND main_group != '' 
    AND UPPER(product_name) LIKE '%NT HOME PHONE%'
GROUP BY main_group
ORDER BY main_group;
-- generated
SELECT
  product_name AS "ผลิตภัณฑ์",
  main_group AS "รายการ",
  ROUND(SUM(amount_value) / 1000000.0, 2) AS "มูลค่า (ล้านบาท)"
FROM v_pl_costtype_nt_mth_clean
WHERE
  report_year = 2025
  AND product_name LIKE '%NT HOME PHONE%'
  AND main_group IN ('01.รายได้', '02.ต้นทุนบริการและต้นทุนขาย :', '03.กำไรขั้นต้น', '08.กำไรก่อนต้นทุนจัดหาเงินฯ', '14.กำไรสุทธิ')
  AND main_group != ''
  AND business_unit != ''
  AND product_name != ''
GROUP BY
  product_name,
  main_group
ORDER BY
  main_group;
```

### [15] ผลดำเนินงาน 6 เดือนแรกของปี แยกกลุ่มธุรกิจและกลุ่มบริการ — `mismatch`
- detail: expected 30 rows, got 30
```sql
-- expected
SELECT
    CASE
        WHEN UPPER(business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
        WHEN UPPER(business_unit) LIKE '%INTERNATIONAL%' THEN 'International'
        WHEN UPPER(business_unit) LIKE '%MOBILE%' THEN 'Mobile'
        WHEN UPPER(business_unit) LIKE '%FIXED LINE%' THEN 'Fixed Line & Broadband'
        WHEN UPPER(business_unit) LIKE '%DIGITAL%' THEN 'Digital'
        WHEN UPPER(business_unit) LIKE '%ICT SOLUTION%' THEN 'ICT Solution'
        ELSE business_unit
    END AS business_unit_name,
    service_group,
    ROUND(SUM(CASE WHEN report_month = 1 THEN CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END ELSE 0 END)/1e6, 2) AS "ม.ค._revenue",
    ROUND(SUM(CASE WHEN report_month = 2 THEN CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END ELSE 0 END)/1e6, 2) AS "ก.พ._revenue",
    ROUND(SUM(CASE WHEN report_month = 3 THEN CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END ELSE 0 END)/1e6, 2) AS "มี.ค._revenue",
    ROUND(SUM(CASE WHEN report_month = 4 THEN CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END ELSE 0 END)/1e6, 2) AS "เม.ย._revenue",
    ROUND(SUM(CASE WHEN report_month = 5 THEN CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END ELSE 0 END)/1e6, 2) AS "พ.ค._revenue",
    ROUND(SUM(CASE WHEN report_month = 6 THEN CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END ELSE 0 END)/1e6, 2) AS "มิ.ย._revenue",
    ROUND(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END)/1e6, 2) AS "รวม_revenue",
    ROUND(SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END)/1e6, 2) AS "รวม_gross_profit"
FROM v_pl_costtype_nt_mth_clean
WHERE report_year = 2024
  AND report_month BETWEEN 1 AND 6
  AND main_group != ''
  AND business_unit != ''
GROUP BY business_unit_name, service_group
ORDER BY "รวม_revenue" DESC
-- generated
WITH NormalizedData AS (
  SELECT
    report_year,
    report_month,
    CASE
      WHEN UPPER(business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
      WHEN UPPER(business_unit) LIKE '%INTERNATIONAL%' THEN 'International'
      WHEN UPPER(business_unit) LIKE '%MOBILE%' THEN 'Mobile'
      WHEN UPPER(business_unit) LIKE '%FIXED LINE%' THEN 'Fixed Line & Broadband'
      WHEN UPPER(business_unit) LIKE '%DIGITAL%' THEN 'Digital'
      WHEN UPPER(business_unit) LIKE '%ICT SOLUTION%' THEN 'ICT Solution'
      WHEN UPPER(business_unit) LIKE '%ไม่ใช่โทรคมนาคม%' THEN 'บริการอื่นไม่ใช่โทรคมนาคม'
      WHEN UPPER(business_unit) LIKE '%รายได้อื่น%' THEN 'รายได้อื่น/ค่าใช้จ่ายอื่น'
      WHEN UPPER(business_unit) LIKE '%นโยบายภาครัฐ%' THEN 'บริการตามนโยบายภาครัฐ'
      ELSE business_unit
    END AS business_unit_name,
    service_group,
    main_group,
    amount_value
  FROM v_pl_costtype_nt_mth_clean
  WHERE
    report_year = 2026
    AND CAST(report_month AS INTEGER) BETWEEN 1 AND 6
    AND main_group != ''
    AND business_unit != ''
    AND service_group != ''
)
SELECT
  business_unit_name AS "กลุ่มธุรกิจ",
  service_group AS "กลุ่มบริการ",
  ROUND(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END) / 1000000.0, 2) AS "รายได้ (ล้านบาท)",
  ROUND(SUM(CASE WHEN main_group LIKE '02.%' THEN amount_value ELSE 0 END) / 1000000.0, 2) AS "ต้นทุนบริการและต้นทุนขาย (ล้านบาท)",
  ROUND(SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END) / 1000000.0, 2) AS "กำไรขั้นต้น (ล้านบาท)",
  ROUND(SUM(CASE WHEN main_group LIKE '08.%' THEN amount_value ELSE 0 END) / 1000000.0, 2) AS "กำไรก่อนต้นทุนจัดหาเงินฯ (ล้านบาท)",
  ROUND(SUM(CASE WHEN main_group LIKE '12.%' THEN amount_value ELSE 0 END) / 1000000.0, 2) AS "กำไรก่อนภาษี (ล้านบาท)",
  ROUND(SUM(CASE WHEN main_group LIKE '14.%' THEN amount_value ELSE 0 END) / 1000000.0, 2) AS "กำไรสุทธิ (ล้านบาท)"
FROM NormalizedData
GROUP BY
  business_unit_name,
  service_group
ORDER BY
  business_unit_name ASC,
  service_group ASC;
```

### [16] รายได้ trunk radio ปี 2568 — `mismatch`
- detail: expected 1 rows, got 1
```sql
-- expected
SELECT report_year, SUM(amount_value) / 1000000.0 AS revenue_million_baht FROM v_pl_costtype_nt_mth_clean WHERE (UPPER(product_name) LIKE '%TRUNK%' OR UPPER(product_name) LIKE '%TRUNKED%' OR product_name LIKE '%วิทยุเฉพาะกิจ%') AND report_year = 2025 GROUP BY report_year
-- generated
SELECT
  SUM(COALESCE(revenue, 0)) AS "รายได้ Trunk Radio"
FROM revenue_search
WHERE
  (UPPER(product_name) LIKE '%TRUNK%' OR UPPER(product_name) LIKE '%TRUNKED%' OR product_name LIKE '%วิทยุเฉพาะกิจ%')
  AND year = 2025
  AND BUSINESS_GROUP != 'รายได้อื่น';
```

### [17] ค่าใช้จ่าย trunk radio ปี 2568 — `mismatch`
- detail: expected 24 rows, got 1
```sql
-- expected
SELECT sub_group, ROUND(SUM(amount_value) / 1000000.0, 2) AS expense_million_baht FROM v_pl_costtype_nt_mth_clean WHERE (UPPER(product_name) LIKE '%TRUNK%' OR UPPER(product_name) LIKE '%TRUNKED%' OR product_name LIKE '%วิทยุเฉพาะกิจ%') AND report_year = 2025 GROUP BY sub_group ORDER BY expense_million_baht DESC
-- generated
SELECT
  SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่าย Trunk Radio"
FROM v_expense_mart
WHERE
  (account_name LIKE '%TRUNK%' OR account_name LIKE '%TRUNKED%' OR account_name LIKE '%วิทยุเฉพาะกิจ%')
  AND year = 2025;
```

### [19] 20 อันดับแรก ฝ่ายที่มีรายได้สูงสุด รายไตรมาส — `mismatch`
- detail: expected 80 rows, got 80
```sql
-- expected
SELECT department as "ฝ่าย", CASE WHEN CAST(month AS INTEGER) IN (1,2,3) THEN 'Q1' WHEN CAST(month AS INTEGER) IN (4,5,6) THEN 'Q2' WHEN CAST(month AS INTEGER) IN (7,8,9) THEN 'Q3' ELSE 'Q4' END AS quarter, SUM(revenue) AS "รายได้รวม"
FROM revenue_search
WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'
  AND department IN (
    SELECT department FROM revenue_search
    WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'
    GROUP BY department ORDER BY SUM(revenue) DESC LIMIT 20
  )
GROUP BY department, quarter
ORDER BY SUM(revenue) DESC, quarter ASC
-- generated
SELECT
  t1.department AS "ฝ่าย",
  CASE
    WHEN CAST(t1.month AS INTEGER) IN (1, 2, 3) THEN 'Q1'
    WHEN CAST(t1.month AS INTEGER) IN (4, 5, 6) THEN 'Q2'
    WHEN CAST(t1.month AS INTEGER) IN (7, 8, 9) THEN 'Q3'
    ELSE 'Q4'
  END AS "ไตรมาส",
  SUM(COALESCE(t1.revenue, 0)) AS "รายได้รวม"
FROM
  revenue_search AS t1
WHERE
  t1.year = 2025 AND t1.BUSINESS_GROUP != 'รายได้อื่น' AND t1.department IN (
    SELECT
      department
    FROM
      revenue_search
    WHERE
      year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'
    GROUP BY
      department
    ORDER BY
      SUM(COALESCE(revenue, 0)) DESC
    LIMIT 20
  )
GROUP BY
  t1.department,
  "ไตรมาส"
ORDER BY
  "รายได้รวม" DESC;
```

### [20] 10 อันดับแรก กลุ่มบริการที่มีรายได้สูงสุด แยกรายเดือน — `mismatch`
- detail: expected 120 rows, got 0
```sql
-- expected
SELECT SERVICE_GROUP, CAST(month AS INTEGER) AS month, SUM(revenue) AS total_revenue
FROM revenue_search
WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'
  AND SERVICE_GROUP IN (
    SELECT SERVICE_GROUP FROM revenue_search
    WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'
    GROUP BY SERVICE_GROUP ORDER BY SUM(revenue) DESC LIMIT 10
  )
GROUP BY SERVICE_GROUP, month
ORDER BY SERVICE_GROUP, month
-- generated
SELECT
  T1.SERVICE_GROUP,
  CAST(T1.month AS INTEGER) AS month,
  SUM(COALESCE(T1.revenue, 0)) AS "รายได้รวม"
FROM
  revenue_search AS T1
WHERE
  T1.year = 2026
  AND T1.BUSINESS_GROUP != 'รายได้อื่น'
  AND T1.SERVICE_GROUP IN (
    SELECT
      SERVICE_GROUP
    FROM
      revenue_search
    WHERE
      year = 2026
      AND BUSINESS_GROUP != 'รายได้อื่น'
    GROUP BY
      SERVICE_GROUP
    ORDER BY
      SUM(COALESCE(revenue, 0)) DESC
    LIMIT 10
  )
GROUP BY
  T1.SERVICE_GROUP,
  CAST(T1.month AS INTEGER)
ORDER BY
  T1.SERVICE_GROUP,
  CAST(T1.month AS INTEGER);
```

### [21] 5 อันดับแรก บริการที่มีค่าใช้จ่ายสูงสุด แยกรายไตรมาส — `mismatch`
- detail: expected 19 rows, got 20
```sql
-- expected
SELECT account_name as "ชื่อบัญชี", CASE WHEN CAST(month AS INTEGER) IN (1,2,3) THEN 'Q1' WHEN CAST(month AS INTEGER) IN (4,5,6) THEN 'Q2' WHEN CAST(month AS INTEGER) IN (7,8,9) THEN 'Q3' ELSE 'Q4' END AS quarter, SUM(expense) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE year = 2025
  AND account_name IN (
    SELECT account_name FROM v_expense_mart
    WHERE year = 2025
    GROUP BY account_name ORDER BY SUM(expense) DESC LIMIT 5
  )
GROUP BY account_name, quarter
ORDER BY SUM(expense) DESC, quarter ASC
-- generated
WITH QuarterlyExpenses AS (
    SELECT
        account_name,
        CASE
            WHEN CAST(month AS INTEGER) IN (1, 2, 3) THEN 'Q1'
            WHEN CAST(month AS INTEGER) IN (4, 5, 6) THEN 'Q2'
            WHEN CAST(month AS INTEGER) IN (7, 8, 9) THEN 'Q3'
            ELSE 'Q4'
        END AS quarter,
        SUM(COALESCE(expense, 0)) AS total_expense
    FROM
        v_expense_mart
    WHERE
        year = 2025
        AND type LIKE '%ค่าใช้จ่าย%'
    GROUP BY
        account_name,
        quarter
),
RankedExpenses AS (
    SELECT
        account_name,
        quarter,
        total_expense,
        RANK() OVER (PARTITION BY quarter ORDER BY total_expense DESC) as rank_num
    FROM
        QuarterlyExpenses
)
SELECT
    quarter AS "ไตรมาส",
    account_name AS "ชื่อบัญชีแยกประเภท",
    total_expense AS "ค่าใช้จ่ายรวม"
FROM
    RankedExpenses
WHERE
    rank_num <= 5
ORDER BY
    quarter,
    total_expense DESC;
```

### [22] 20 อันดับแรก ฝ่ายที่มีรายได้สูงสุด ไม่รวม wholesale ไร้สาย รายไตรมาส — `mismatch`
- detail: expected 80 rows, got 0
```sql
-- expected
SELECT department, (CAST(month AS INTEGER) + 2) / 3 AS quarter, SUM(revenue) AS total_revenue
FROM revenue_search
WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'
  AND PRODUCT_NAME NOT LIKE '%Wholesale%'
  AND SERVICE_GROUP NOT LIKE '%ไร้สาย%'
  AND department IN (
    SELECT department FROM revenue_search
    WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'
      AND PRODUCT_NAME NOT LIKE '%Wholesale%'
      AND SERVICE_GROUP NOT LIKE '%ไร้สาย%'
    GROUP BY department ORDER BY SUM(revenue) DESC LIMIT 20
  )
GROUP BY department, quarter
ORDER BY SUM(revenue) DESC, quarter ASC
-- generated
SELECT
  T1.department,
  CASE
    WHEN CAST(T1.month AS INTEGER) IN (1, 2, 3)
    THEN 'Q1'
    WHEN CAST(T1.month AS INTEGER) IN (4, 5, 6)
    THEN 'Q2'
    WHEN CAST(T1.month AS INTEGER) IN (7, 8, 9)
    THEN 'Q3'
    ELSE 'Q4'
  END AS "ไตรมาส",
  SUM(COALESCE(T1.revenue, 0)) AS "รายได้รวม"
FROM
  revenue_search AS T1
WHERE
  T1.year = 2026 AND T1.SERVICE_GROUP != 'บริการโทรคมนาคมสื่อสารไร้สาย - กลุ่มค้าส่ง (Wholesale)' AND T1.BUSINESS_GROUP != 'รายได้อื่น' AND T1.department IN (
    SELECT
      department
    FROM
      revenue_search
    WHERE
      year = 2026 AND SERVICE_GROUP != 'บริการโทรคมคมสื่อสารไร้สาย - กลุ่มค้าส่ง (Wholesale)' AND BUSINESS_GROUP != 'รายได้อื่น'
    GROUP BY
      department
    ORDER BY
      SUM(COALESCE(revenue, 0)) DESC
    LIMIT 20
  )
GROUP BY
  T1.department,
  "ไตรมาส"
ORDER BY
  (
    SELECT
      SUM(COALESCE(r_sub.revenue, 0))
    FROM
      revenue_search AS r_sub
    WHERE
      r_sub.department = T1.department AND r_sub.year = 2026 AND r_sub.SERVICE_GROUP != 'บริการโทรคมคมสื่อสารไร้สาย - กลุ่มค้าส่ง (Wholesale)' AND r_sub.BUSINESS_GROUP != 'รายได้อื่น'
  ) DESC,
  "ไตรมาส";
```

### [23] ค่าใช้จ่าย ตบชง. รายหมวดบัญชี — `mismatch`
- detail: expected 4 rows, got 6
```sql
-- expected
SELECT 
    account_group_name AS "หมวดบัญชี", 
    SUM(expense) AS "ยอดค่าใช้จ่าย_บาท"
FROM v_expense_mart
WHERE section_abbr LIKE '%ตบชง.%'
  AND year = 2025
GROUP BY account_group_name
ORDER BY "ยอดค่าใช้จ่าย_บาท" DESC
-- generated
SELECT
  account_group_name AS "หมวดบัญชี",
  SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE
  department_abbr = 'บชง.' AND year = 2025
GROUP BY
  account_group_name
ORDER BY
  "ค่าใช้จ่ายรวม" DESC;
```

### [24] ค่าใช้จ่ายรายหมวดบัญชี รายไตรมาส — `mismatch`
- detail: expected 73 rows, got 73
```sql
-- expected
SELECT account_group_name as "หมวดบัญชี", CASE WHEN CAST(month AS INTEGER) IN (1,2,3) THEN 'Q1' WHEN CAST(month AS INTEGER) IN (4,5,6) THEN 'Q2' WHEN CAST(month AS INTEGER) IN (7,8,9) THEN 'Q3' ELSE 'Q4' END AS quarter, SUM(expense) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE year = 2025
GROUP BY account_group_name, quarter
ORDER BY quarter ASC, "ค่าใช้จ่ายรวม" DESC
-- generated
SELECT
  account_group_name AS "หมวดบัญชี",
  CASE
    WHEN CAST(month AS INTEGER) IN (1, 2, 3) THEN 'Q1'
    WHEN CAST(month AS INTEGER) IN (4, 5, 6) THEN 'Q2'
    WHEN CAST(month AS INTEGER) IN (7, 8, 9) THEN 'Q3'
    ELSE 'Q4'
  END AS "ไตรมาส",
  SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE
  year = 2025 AND type = 'ค่าใช้จ่าย'
GROUP BY
  account_group_name,
  "ไตรมาส"
ORDER BY
  account_group_name,
  "ไตรมาส";
```

### [25] รายได้รายสายงาน — `mismatch`
- detail: expected 11 rows, got 0
```sql
-- expected
SELECT DIVISION as "สายงาน", SUM(revenue) as "รายได้รวม" FROM revenue_search WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น' GROUP BY DIVISION ORDER BY "รายได้รวม" DESC
-- generated
SELECT
  division,
  SUM(COALESCE(revenue, 0)) AS "รายได้รวม"
FROM
  revenue_search
WHERE
  BUSINESS_GROUP != 'รายได้อื่น' AND year = 2026
GROUP BY
  division
ORDER BY
  "รายได้รวม" DESC;
```

### [26] ค่าใช้จ่ายรายสายงาน — `mismatch`
- detail: expected 12 rows, got 12
```sql
-- expected
SELECT division as "สายงาน", SUM(expense) as "ค่าใช้จ่ายรวม" FROM v_expense_mart WHERE year = 2025 GROUP BY division ORDER BY "ค่าใช้จ่ายรวม" DESC
-- generated
SELECT
  division,
  SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE
  type = 'ค่าใช้จ่าย' AND year = 2025
GROUP BY
  division
ORDER BY
  "ค่าใช้จ่ายรวม" DESC;
```

### [28] ค่าใช้จ่ายรายไตรมาส — `mismatch`
- detail: expected 4 rows, got 4
```sql
-- expected
SELECT CASE WHEN CAST(month AS INTEGER) IN (1,2,3) THEN 'Q1' WHEN CAST(month AS INTEGER) IN (4,5,6) THEN 'Q2' WHEN CAST(month AS INTEGER) IN (7,8,9) THEN 'Q3' ELSE 'Q4' END AS quarter, SUM(expense) as "ค่าใช้จ่ายรวม" FROM v_expense_mart WHERE year = 2025 GROUP BY quarter ORDER BY quarter
-- generated
SELECT
  year,
  CASE
    WHEN CAST(month AS INTEGER) IN (1, 2, 3) THEN 'Q1'
    WHEN CAST(month AS INTEGER) IN (4, 5, 6) THEN 'Q2'
    WHEN CAST(month AS INTEGER) IN (7, 8, 9) THEN 'Q3'
    ELSE 'Q4'
  END AS quarter,
  SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE
  TYPE = 'ค่าใช้จ่าย' AND year = 2025
GROUP BY
  year,
  quarter
ORDER BY
  year,
  quarter;
```

### [29] หน่วยงานที่ใช้ค่าใช้จ่ายมากสุด 10 อันดับแรก — `mismatch`
- detail: expected 10 rows, got 10
```sql
-- expected
SELECT department as "หน่วยงาน", SUM(expense) as "ค่าใช้จ่ายรวม" FROM v_expense_mart WHERE year = 2025 GROUP BY department ORDER BY "ค่าใช้จ่ายรวม" DESC LIMIT 10
-- generated
SELECT
  department,
  SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE
  year = 2025
GROUP BY
  department
ORDER BY
  "ค่าใช้จ่ายรวม" DESC
LIMIT 10;
```

### [31] สัดส่วนรายได้แต่ละกลุ่มธุรกิจ ปี 2568 — `mismatch`
- detail: expected 7 rows, got 7
```sql
-- expected
SELECT BUSINESS_GROUP AS "กลุ่มธุรกิจ", SUM(COALESCE(revenue, 0)) AS "รายได้รวม", ROUND(SUM(COALESCE(revenue, 0)) * 100.0 / NULLIF((SELECT SUM(COALESCE(revenue, 0)) FROM revenue_search WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'), 0), 2) AS "สัดส่วน_pct" FROM revenue_search WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น' GROUP BY BUSINESS_GROUP ORDER BY "รายได้รวม" DESC
-- generated
SELECT
  BUSINESS_GROUP,
  SUM(COALESCE(revenue, 0)) AS "รายได้รวม",
  (SUM(COALESCE(revenue, 0)) * 100.0 / NULLIF((
    SELECT SUM(COALESCE(revenue, 0))
    FROM revenue_search
    WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'
  ), 0)) AS "สัดส่วนรายได้ (%)"
FROM
  revenue_search
WHERE
  year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'
GROUP BY
  BUSINESS_GROUP
ORDER BY
  "สัดส่วนรายได้ (%)" DESC;
```

### [32] ค่าใช้จ่ายรายฝ่าย ปี 2568 — `mismatch`
- detail: expected 118 rows, got 118
```sql
-- expected
SELECT department AS "ฝ่าย", SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม" FROM v_expense_mart WHERE year = 2025 GROUP BY department ORDER BY "ค่าใช้จ่ายรวม" DESC
-- generated
SELECT
  department,
  SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE
  year = 2025
GROUP BY
  department
ORDER BY
  "ค่าใช้จ่ายรวม" DESC;
```

### [33] รายได้แยกตามกลุ่มธุรกิจ รายไตรมาส ปี 2568 — `mismatch`
- detail: expected 28 rows, got 28
```sql
-- expected
SELECT BUSINESS_GROUP AS "กลุ่มธุรกิจ", CASE WHEN CAST(month AS INTEGER) IN (1,2,3) THEN 'Q1' WHEN CAST(month AS INTEGER) IN (4,5,6) THEN 'Q2' WHEN CAST(month AS INTEGER) IN (7,8,9) THEN 'Q3' ELSE 'Q4' END AS quarter, SUM(COALESCE(revenue, 0)) AS "รายได้รวม" FROM revenue_search WHERE year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น' GROUP BY BUSINESS_GROUP, quarter ORDER BY BUSINESS_GROUP, quarter
-- generated
SELECT
  BUSINESS_GROUP AS "กลุ่มธุรกิจ",
  CASE
    WHEN CAST(month AS INTEGER) IN (1, 2, 3) THEN 'Q1'
    WHEN CAST(month AS INTEGER) IN (4, 5, 6) THEN 'Q2'
    WHEN CAST(month AS INTEGER) IN (7, 8, 9) THEN 'Q3'
    ELSE 'Q4'
  END AS "ไตรมาส",
  SUM(COALESCE(revenue, 0)) AS "รายได้รวม"
FROM revenue_search
WHERE
  year = 2025 AND BUSINESS_GROUP != 'รายได้อื่น'
GROUP BY
  BUSINESS_GROUP,
  "ไตรมาส"
ORDER BY
  "กลุ่มธุรกิจ",
  "ไตรมาส";
```

### [34] ค่าใช้จ่ายรายหมวดบัญชี รายไตรมาส ปี 2568 แบบ COALESCE — `mismatch`
- detail: expected 73 rows, got 73
```sql
-- expected
SELECT account_group_name AS "หมวดบัญชี", CASE WHEN CAST(month AS INTEGER) IN (1,2,3) THEN 'Q1' WHEN CAST(month AS INTEGER) IN (4,5,6) THEN 'Q2' WHEN CAST(month AS INTEGER) IN (7,8,9) THEN 'Q3' ELSE 'Q4' END AS quarter, SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม" FROM v_expense_mart WHERE year = 2025 GROUP BY account_group_name, quarter ORDER BY quarter ASC, "ค่าใช้จ่ายรวม" DESC
-- generated
SELECT
  account_group_name AS "หมวดบัญชี",
  CASE
    WHEN CAST(month AS INTEGER) IN (1, 2, 3) THEN 'Q1'
    WHEN CAST(month AS INTEGER) IN (4, 5, 6) THEN 'Q2'
    WHEN CAST(month AS INTEGER) IN (7, 8, 9) THEN 'Q3'
    ELSE 'Q4'
  END AS "ไตรมาส",
  SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE
  year = 2025 AND type = 'ค่าใช้จ่าย'
GROUP BY
  account_group_name,
  "ไตรมาส"
ORDER BY
  account_group_name,
  "ไตรมาส";
```

### [36] GL ที่มีค่าใช้จ่ายสูงสุด 10 อันดับ ปี 2568 — `mismatch`
- detail: expected 10 rows, got 10
```sql
-- expected
SELECT gl_code || ': ' || account_name AS "รหัสบัญชี", SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม" FROM v_expense_mart WHERE year = 2025 GROUP BY gl_code, account_name ORDER BY "ค่าใช้จ่ายรวม" DESC LIMIT 10
-- generated
SELECT
  gl_code,
  account_name,
  SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE
  year = 2025
GROUP BY
  gl_code,
  account_name
ORDER BY
  "ค่าใช้จ่ายรวม" DESC
LIMIT 10;
```

### [37] รายได้และค่าใช้จ่ายแยกตามกลุ่มธุรกิจ ปี 2568 — `mismatch`
- detail: expected 8 rows, got 1
```sql
-- expected
SELECT business_unit AS "กลุ่มธุรกิจ", ROUND(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS "รายได้_ลบ", ROUND(SUM(CASE WHEN main_group LIKE '02.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS "ต้นทุน_ลบ", ROUND(SUM(CASE WHEN main_group LIKE '03.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS "กำไรขั้นต้น_ลบ" FROM v_pl_costtype_nt_mth_clean WHERE report_year = 2025 AND main_group != '' AND business_unit != '' GROUP BY business_unit ORDER BY "รายได้_ลบ" DESC
-- generated
SELECT
  business_group,
  SUM(COALESCE(expense, 0)) AS "ค่าใช้จ่ายรวม"
FROM v_expense_mart
WHERE
  year = 2025
GROUP BY
  business_group
ORDER BY
  "ค่าใช้จ่ายรวม" DESC;
```

### [39] ผลดำเนินงานปี 2569 กลุ่มธุรกิจ รายเดือน — `mismatch`
- detail: expected 42 rows, got 14
```sql
-- expected
WITH bu_revenue AS (
    SELECT
        CASE
            WHEN UPPER(business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
            WHEN UPPER(business_unit) LIKE '%INTERNATIONAL%' THEN 'International'
            WHEN UPPER(business_unit) LIKE '%MOBILE%' THEN 'Mobile'
            WHEN UPPER(business_unit) LIKE '%FIXED LINE%' THEN 'Fixed Line & Broadband'
            WHEN UPPER(business_unit) LIKE '%DIGITAL%' THEN 'Digital'
            WHEN UPPER(business_unit) LIKE '%ICT SOLUTION%' THEN 'ICT Solution'
            WHEN UPPER(business_unit) LIKE '%ไม่ใช่โทรคมนาคม%' THEN 'บริการอื่นไม่ใช่โทรคมนาคม'
            WHEN UPPER(business_unit) LIKE '%รายได้อื่น%' THEN 'รายได้อื่น/ค่าใช้จ่ายอื่น'
            WHEN UPPER(business_unit) LIKE '%นโยบายภาครัฐ%' THEN 'บริการตามนโยบายภาครัฐ'
            ELSE business_unit
        END AS business_unit_name,
        ROUND(SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END) / 1e6, 2) AS total_rev
    FROM v_pl_costtype_nt_mth_clean
    WHERE report_year = 2026
      AND main_group != '' AND business_unit != ''
    GROUP BY business_unit_name
)
SELECT
    d.business_unit_name AS "กลุ่มธุรกิจ",
    d.pl_item AS "รายการ",
    d."ม.ค.", d."ก.พ.", d."มี.ค.", d."เม.ย.", d."พ.ค.", d."มิ.ย.",
    d."ก.ค.", d."ส.ค.", d."ก.ย.", d."ต.ค.", d."พ.ย.", d."ธ.ค.",
    d."รวมทั้งปี (ล้านบาท)"
FROM (
    SELECT
        CASE
            WHEN UPPER(business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
            WHEN UPPER(business_unit) LIKE '%INTERNATIONAL%' THEN 'International'
            WHEN UPPER(business_unit) LIKE '%MOBILE%' THEN 'Mobile'
            WHEN UPPER(business_unit) LIKE '%FIXED LINE%' THEN 'Fixed Line & Broadband'
            WHEN UPPER(business_unit) LIKE '%DIGITAL%' THEN 'Digital'
            WHEN UPPER(business_unit) LIKE '%ICT SOLUTION%' THEN 'ICT Solution'
            WHEN UPPER(business_unit) LIKE '%ไม่ใช่โทรคมนาคม%' THEN 'บริการอื่นไม่ใช่โทรคมนาคม'
            WHEN UPPER(business_unit) LIKE '%รายได้อื่น%' THEN 'รายได้อื่น/ค่าใช้จ่ายอื่น'
            WHEN UPPER(business_unit) LIKE '%นโยบายภาครัฐ%' THEN 'บริการตามนโยบายภาครัฐ'
            ELSE business_unit
        END AS business_unit_name,
        CASE
            WHEN main_group LIKE '01.%' THEN '01.รายได้'
            WHEN main_group LIKE '02.%' THEN '02.ต้นทุน'
            WHEN main_group LIKE '03.%' THEN '03.กำไรขั้นต้น'
            WHEN main_group LIKE '08.%' THEN '08.กำไรดำเนินงาน'
            WHEN main_group LIKE '12.%' THEN '12.EBT'
            WHEN main_group LIKE '14.%' THEN '14.กำไรสุทธิ'
        END AS pl_item,
        ROUND(SUM(CASE WHEN report_month = 1 THEN amount_value ELSE 0 END) / 1e6, 2) AS "ม.ค.",
        ROUND(SUM(CASE WHEN report_month = 2 THEN amount_value ELSE 0 END) / 1e6, 2) AS "ก.พ.",
        ROUND(SUM(CASE WHEN report_month = 3 THEN amount_value ELSE 0 END) / 1e6, 2) AS "มี.ค.",
        ROUND(SUM(CASE WHEN report_month = 4 THEN amount_value ELSE 0 END) / 1e6, 2) AS "เม.ย.",
        ROUND(SUM(CASE WHEN report_month = 5 THEN amount_value ELSE 0 END) / 1e6, 2) AS "พ.ค.",
        ROUND(SUM(CASE WHEN report_month = 6 THEN amount_value ELSE 0 END) / 1e6, 2) AS "มิ.ย.",
        ROUND(SUM(CASE WHEN report_month = 7 THEN amount_value ELSE 0 END) / 1e6, 2) AS "ก.ค.",
        ROUND(SUM(CASE WHEN report_month = 8 THEN amount_value ELSE 0 END) / 1e6, 2) AS "ส.ค.",
        ROUND(SUM(CASE WHEN report_month = 9 THEN amount_value ELSE 0 END) / 1e6, 2) AS "ก.ย.",
        ROUND(SUM(CASE WHEN report_month = 10 THEN amount_value ELSE 0 END) / 1e6, 2) AS "ต.ค.",
        ROUND(SUM(CASE WHEN report_month = 11 THEN amount_value ELSE 0 END) / 1e6, 2) AS "พ.ย.",
        ROUND(SUM(CASE WHEN report_month = 12 THEN amount_value ELSE 0 END) / 1e6, 2) AS "ธ.ค.",
        ROUND(SUM(amount_value) / 1e6, 2) AS "รวมทั้งปี (ล้านบาท)"
    FROM v_pl_costtype_nt_mth_clean
    WHERE report_year = 2026
      AND main_group != '' AND business_unit != ''
      AND (main_group LIKE '01.%' OR main_group LIKE '02.%' OR main_group LIKE '03.%'
           OR main_group LIKE '08.%' OR main_group LIKE '12.%' OR main_group LIKE '14.%')
    GROUP BY business_unit_name, pl_item
) d
JOIN bu_revenue r ON d.business_unit_name = r.business_unit_name
ORDER BY r.total_rev DESC, d.pl_item
-- generated
WITH normalized_data AS (
  SELECT
    report_year,
    CAST(report_month AS INTEGER) AS report_month,
    CASE 
      WHEN UPPER(business_unit) LIKE '%HARD INFRASTRUCTURE%' THEN 'Hard Infrastructure'
      WHEN UPPER(business_unit) LIKE '%INTERNATIONAL%' THEN 'International'
      WHEN UPPER(business_unit) LIKE '%MOBILE%' THEN 'Mobile'
      WHEN UPPER(business_unit) LIKE '%FIXED LINE%' THEN 'Fixed Line & Broadband'
      WHEN UPPER(business_unit) LIKE '%DIGITAL%' THEN 'Digital'
      WHEN UPPER(business_unit) LIKE '%ICT SOLUTION%' THEN 'ICT Solution'
      WHEN UPPER(business_unit) LIKE '%ไม่ใช่โทรคมนาคม%' THEN 'บริการอื่นไม่ใช่โทรคมนาคม'
      WHEN UPPER(business_unit) LIKE '%รายได้อื่น%' THEN 'รายได้อื่น/ค่าใช้จ่ายอื่น'
      WHEN UPPER(business_unit) LIKE '%นโยบายภาครัฐ%' THEN 'บริการตามนโยบายภาครัฐ'
      ELSE business_unit
    END AS business_unit_name,
    main_group,
    amount_value
  FROM v_pl_costtype_nt_mth_clean
  WHERE
    report_year = 2026
    AND main_group != ''
    AND business_unit != ''
    AND main_group IN (
      '01.รายได้',
      '02.ต้นทุนบริการและต้นทุนขาย :',
      '03.กำไรขั้นต้น',
      '08.กำไรก่อนต้นทุนจัดหาเงินฯ',
      '12.กำไรก่อนภาษี',
      '14.กำไรสุทธิ'
    )
),
bu_revenue_order AS (
  SELECT
    business_unit_name,
    SUM(CASE WHEN main_group LIKE '01.%' THEN amount_value ELSE 0 END) AS total_revenue_for_order
  FROM normalized_data
  GROUP BY business_unit_name
)
SELECT
  nd.business_unit_name AS "กลุ่มธุรกิจ",
  nd.main_group AS "รายการ",
  ROUND(SUM(CASE WHEN nd.report_month = 1 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "ม.ค.",
  ROUND(SUM(CASE WHEN nd.report_month = 2 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "ก.พ.",
  ROUND(SUM(CASE WHEN nd.report_month = 3 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "มี.ค.",
  ROUND(SUM(CASE WHEN nd.report_month = 4 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "เม.ย.",
  ROUND(SUM(CASE WHEN nd.report_month = 5 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "พ.ค.",
  ROUND(SUM(CASE WHEN nd.report_month = 6 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "มิ.ย.",
  ROUND(SUM(CASE WHEN nd.report_month = 7 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "ก.ค.",
  ROUND(SUM(CASE WHEN nd.report_month = 8 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "ส.ค.",
  ROUND(SUM(CASE WHEN nd.report_month = 9 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "ก.ย.",
  ROUND(SUM(CASE WHEN nd.report_month = 10 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "ต.ค.",
  ROUND(SUM(CASE WHEN nd.report_month = 11 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "พ.ย.",
  ROUND(SUM(CASE WHEN nd.report_month = 12 THEN nd.amount_value ELSE 0 END) / 1000000.0, 2) AS "ธ.ค.",
  ROUND(SUM(nd.amount_value) / 1000000.0, 2) AS "รวมทั้งปี (ล้านบาท)"
FROM normalized_data AS nd
JOIN bu_revenue_order AS bro
  ON nd.business_unit_name = bro.business_unit_name
GROUP BY
  nd.business_unit_name,
  nd.main_group
ORDER BY
  bro.total_revenue_for_order DESC,
  nd.main_group ASC;
```


## Golden broken (admin action needed)

- [10] บริการใดที่มีผลประกอบการดี — no such column: revenue
- [18] รายได้ mobile ปี 2568 — no such column: REVENUE_VALUE
- [41] รายได้รวม — no such table: test_revenue
- [42] รายได้รวม — no such table: test_revenue
- [43] รายได้รวม — no such table: test_revenue
- [44] รายได้รวม — no such table: test_revenue
- [45] รายได้รวม — no such table: test_revenue
- [46] รายได้รวม — no such table: test_revenue
- [47] รายได้รวม — no such table: test_revenue
- [48] รายได้รวม — no such table: test_revenue
- [49] รายได้รวม — no such table: test_revenue
- [50] รายได้รวม — no such table: test_revenue