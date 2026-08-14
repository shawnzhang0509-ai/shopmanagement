-- Display 库：各门店 Display 库存
-- 由 grab_display.bat / grab_display_gui.py 自动执行
--
-- 说明：多数 iERP 库没有 ProductFamilies 查找表，本文件只查 Products 上的字段。
-- 若你的库有 family 查找表，可改用 sql/display.with_families.sql
-- 若 ImageUrl 列名不对，在 SSMS 运行 sql/discover_schema.sql 查列名后改下面 COALESCE 一行。

SELECT
    w.Name AS WarehouseName,
    p.Sku,
    p.Name AS ProductName,
    CAST('' AS NVARCHAR(200)) AS ProductFamily,
    p.Name AS SubProductFamily,
    COALESCE(p.ImageUrl, p.ImagePath, '') AS ImageUrl,
    SUM(s.Quantity) AS DisplayQty
FROM Stocks s
JOIN Warehouses w ON s.WarehouseId = w.Id
JOIN Products p ON s.ProductId = p.Id
WHERE w.Name LIKE '%Display%'
  AND p.IsDiscontinued = 0
GROUP BY w.Name, p.Sku, p.Name, p.ImageUrl, p.ImagePath
HAVING SUM(s.Quantity) > 0
ORDER BY w.Name, DisplayQty DESC;
