-- 诊断：某 SKU 为何没进 Display 抓取（在 SSMS 运行，改 @Sku 后执行）
-- 用法：把 @Sku 改成 918-072，逐段运行，看哪一步被过滤掉

DECLARE @Sku NVARCHAR(64) = N'918-072';

-- 1) 产品是否存在
SELECT p.Id, p.Sku, p.Name, p.ProductFamily, p.ProductFamilyId, p.IsDiscontinued
FROM dbo.Products p
WHERE LTRIM(RTRIM(p.Sku)) = @Sku;

-- 2) 该 SKU 的全部库存行（不加任何 Display 过滤）
SELECT
    p.Sku,
    w.Name AS WarehouseName,
    s.Quantity,
    s.StockStatus,
    s.StockOnHoldStatus,
    s.*
FROM dbo.Stocks s
JOIN dbo.Products p ON s.ProductId = p.Id
JOIN dbo.Warehouses w ON s.WarehouseId = w.Id
WHERE LTRIM(RTRIM(p.Sku)) = @Sku
  AND s.Quantity > 0
ORDER BY w.Name, s.StockStatus;

-- 3) 仅「仓库名含 Display」的库存（当前抓取 SQL 的仓库条件）
SELECT
    p.Sku,
    w.Name AS WarehouseName,
    s.Quantity,
    s.StockStatus,
    s.StockOnHoldStatus
FROM dbo.Stocks s
JOIN dbo.Products p ON s.ProductId = p.Id
JOIN dbo.Warehouses w ON s.WarehouseId = w.Id
WHERE LTRIM(RTRIM(p.Sku)) = @Sku
  AND w.Name LIKE N'%Display%'
  AND s.Quantity > 0
ORDER BY w.Name;

-- 4) 加上抓取 SQL 的全部过滤条件（注意：不含 IsDiscontinued 过滤，停产 Demo 也应出现）
SELECT
    p.Sku,
    w.Name AS WarehouseName,
    s.Quantity,
    s.StockStatus,
    s.StockOnHoldStatus,
    p.IsDiscontinued
FROM dbo.Stocks s
JOIN dbo.Products p ON s.ProductId = p.Id
JOIN dbo.Warehouses w ON s.WarehouseId = w.Id
WHERE LTRIM(RTRIM(p.Sku)) = @Sku
  AND w.Name LIKE N'%Display%'
  AND s.StockStatus IN (N'Normal', N'Clearance')
  AND (s.StockOnHoldStatus IS NULL OR LTRIM(RTRIM(s.StockOnHoldStatus)) = N'')
  AND s.Quantity > 0
ORDER BY w.Name;

-- 5) Stocks 表有哪些列（若 Demo 在 Location 字段，把列名发我们）
SELECT COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = N'Stocks'
ORDER BY ORDINAL_POSITION;

-- 6) 所有含 Display 的仓库名（核对 ERP 里 Demo Units 的仓库名是否匹配）
SELECT Id, Name
FROM dbo.Warehouses
WHERE Name LIKE N'%Display%' OR Name LIKE N'%display%'
ORDER BY Name;
