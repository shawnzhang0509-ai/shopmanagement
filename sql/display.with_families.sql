-- 可选：数据库有 ProductFamilies / ProductSubFamilies 查找表时使用
-- 在 grabber_config.json 里设置 "sql_file": "sql/display.with_families.sql"

SELECT
    w.Name AS WarehouseName,
    p.Sku,
    p.Name AS ProductName,
    ISNULL(pf.Name, '') AS ProductFamily,
    ISNULL(psf.Name, p.Name) AS SubProductFamily,
    COALESCE(p.ImageUrl, p.ImagePath, '') AS ImageUrl,
    SUM(s.Quantity) AS DisplayQty
FROM Stocks s
JOIN Warehouses w ON s.WarehouseId = w.Id
JOIN Products p ON s.ProductId = p.Id
LEFT JOIN ProductFamilies pf ON p.ProductFamilyId = pf.Id
LEFT JOIN ProductSubFamilies psf ON p.ProductSubFamilyId = psf.Id
WHERE w.Name LIKE '%Display%'
  AND p.IsDiscontinued = 0
GROUP BY w.Name, p.Sku, p.Name, pf.Name, psf.Name, p.ImageUrl, p.ImagePath
HAVING SUM(s.Quantity) > 0
ORDER BY w.Name, ProductFamily, SubProductFamily, DisplayQty DESC;
