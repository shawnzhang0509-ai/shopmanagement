-- ============================================================
-- Display 库 SQL 模板
-- 用法：在 SSMS / Azure Data Studio 里跑这条 SQL，
--       结果导出为 display.xlsx，放到项目根目录即可。
--       程序启动时自动读取，和 roi.xlsx 一样。
-- ============================================================

-- 按你们实际表名改 FROM / JOIN；下面只是示例结构。
SELECT
    p.ProductCode   AS product_code,
    p.ProductName   AS product_name,
    p.ProductFamily AS product_family,
    s.StockDetails  AS stock_details
FROM dbo.YourProductTable AS p
INNER JOIN dbo.YourStockView AS s ON s.ProductCode = p.ProductCode
WHERE s.StockDetails LIKE '%Display%'
  AND s.StockDetails NOT LIKE '%No longer available%'
ORDER BY p.ProductFamily, p.ProductName;

-- Excel 列名（第一行表头）支持以下任意写法，程序会自动识别：
--   product_code / code / sku
--   product_name / name
--   product_family / family
--   stock_details / stock / Stock Details
