-- Display 库：各门店 Display 库存
-- 由 grab_display.bat / scripts/grab_display.py 自动执行
--
-- ProductFamily / SubProductFamily 来自 iERP 产品表。
-- 若 JOIN 表名与你们库不一致，请在 SSMS 中调整后保存本文件。

SELECT
    w.Name AS WarehouseName,
    p.Sku,
    p.Name AS ProductName,
    ISNULL(pf.Name, '') AS ProductFamily,
    ISNULL(psf.Name, p.Name) AS SubProductFamily,
    SUM(s.Quantity) AS DisplayQty
FROM Stocks s
JOIN Warehouses w ON s.WarehouseId = w.Id
JOIN Products p ON s.ProductId = p.Id
LEFT JOIN ProductFamilies pf ON p.ProductFamilyId = pf.Id
LEFT JOIN ProductSubFamilies psf ON p.ProductSubFamilyId = psf.Id
WHERE w.Name LIKE '%Display%'
  AND p.IsDiscontinued = 0
GROUP BY w.Name, p.Sku, p.Name, pf.Name, psf.Name
HAVING SUM(s.Quantity) > 0
ORDER BY w.Name, ProductFamily, SubProductFamily, DisplayQty DESC;
