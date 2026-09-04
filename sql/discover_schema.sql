-- 在 SSMS 连接 nz_ierp_live 后运行，找出 Product Family / 图片 的正确表名和列名
-- 若某 SKU 进不了 Display，另运行 sql/discover_display_stock.sql（改 @Sku）

-- 1) Products 表上跟 family / image 相关的列
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'Products'
  AND (
    COLUMN_NAME LIKE '%Family%'
    OR COLUMN_NAME LIKE '%Range%'
    OR COLUMN_NAME LIKE '%Category%'
    OR COLUMN_NAME LIKE '%Image%'
    OR COLUMN_NAME LIKE '%Path%'
    OR COLUMN_NAME LIKE '%Photo%'
    OR COLUMN_NAME LIKE '%Picture%'
  )
ORDER BY COLUMN_NAME;

-- 2) 名字里带 Family / Range / Category 的表
SELECT TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND (
    TABLE_NAME LIKE '%Family%'
    OR TABLE_NAME LIKE '%Range%'
    OR TABLE_NAME LIKE '%Category%'
    OR TABLE_NAME LIKE '%Image%'
    OR TABLE_NAME LIKE '%Media%'
  )
ORDER BY TABLE_NAME;

-- 3) 随便看几条产品的图片字段（把下面列名改成你在第 1 步查到的）
-- SELECT TOP 5 Sku, Name, ImageUrl, ImagePath FROM Products WHERE ImageUrl IS NOT NULL OR ImagePath IS NOT NULL;
