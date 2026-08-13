-- Display 库：各门店 Display 库存
-- 由 scripts/grab_display.py 自动执行，无需 SSMS 手工导出

SELECT
    w.Name AS WarehouseName,
    p.Sku,
    p.Name AS ProductName,
    SUM(s.Quantity) AS DisplayQty
FROM Stocks s
JOIN Warehouses w ON s.WarehouseId = w.Id
JOIN Products p ON s.ProductId = p.Id
WHERE w.Name LIKE '%Display%'
  AND p.IsDiscontinued = 0
GROUP BY w.Name, p.Sku, p.Name
HAVING SUM(s.Quantity) > 0
ORDER BY w.Name, DisplayQty DESC;
