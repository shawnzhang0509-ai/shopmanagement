-- 兜底 SQL：不含 ImageUrl / ProductFamily 列（当 Products 表没有图片字段时使用）
-- grabber 会在 display.sql 报「Invalid object/column name」时自动尝试本文件。

SELECT
    w.Name AS WarehouseName,
    p.Sku,
    p.Name AS ProductName,
    CAST('' AS NVARCHAR(200)) AS ProductFamily,
    p.Name AS SubProductFamily,
    CAST('' AS NVARCHAR(500)) AS ImageUrl,
    SUM(s.Quantity) AS DisplayQty
FROM Stocks s
JOIN Warehouses w ON s.WarehouseId = w.Id
JOIN Products p ON s.ProductId = p.Id
WHERE w.Name LIKE '%Display%'
  AND p.IsDiscontinued = 0
GROUP BY w.Name, p.Sku, p.Name
HAVING SUM(s.Quantity) > 0
ORDER BY w.Name, DisplayQty DESC;
