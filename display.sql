-- ============================================================
-- Display 库 SQL（iERP nz_ierp_live）
-- 用法：SSMS 执行 → 结果导出为 display.xlsx → 放到项目根目录
-- ============================================================

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

-- Excel 表头（程序自动识别）：
--   WarehouseName  → 门店 Display 仓库名
--   Sku            → 产品编码
--   ProductName    → 产品名称
--   DisplayQty     → Display 数量
--
-- 程序会按 Sku 合并多行，并按仓库名归类到 Onehunga / Westgate / Hamilton / CHCH 等 Tab
