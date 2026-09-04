-- 【自动兜底，勿改】主文件 sql/display.sql 报列/表不存在时程序才会尝试本文件。
-- 日常只维护 display.sql（含 ImageUrl，与 product_stock_price.sql 同源）。

SELECT
    w.Name AS WarehouseName,
    p.Sku,
    p.Name AS ProductName,
    CAST('' AS NVARCHAR(200)) AS ProductFamily,
    p.Name AS SubProductFamily,
    MAX(CASE WHEN ISNULL(p.IsDiscontinued, 0) = 1 THEN 1 ELSE 0 END) AS IsDiscontinued,
    s.StockStatus AS StockStatus,
    CAST('' AS NVARCHAR(500)) AS ImageUrl,
    SUM(s.Quantity) AS DisplayQty
FROM Stocks s
JOIN Warehouses w ON s.WarehouseId = w.Id
JOIN Products p ON s.ProductId = p.Id
WHERE w.Name LIKE '%Display%'
  AND s.StockStatus IN ('Normal', 'Clearance')
  AND (
      s.StockOnHoldStatus IS NULL
      OR LTRIM(RTRIM(s.StockOnHoldStatus)) = ''
  )
GROUP BY w.Name, p.Sku, p.Name, s.StockStatus
HAVING SUM(s.Quantity) > 0
ORDER BY w.Name, DisplayQty DESC;
