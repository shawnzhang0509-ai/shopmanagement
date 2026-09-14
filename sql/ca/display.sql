-- ═══════════════════════════════════════════════════════════════
-- Display 大库 · 唯一维护文件
-- grabber_config.json → "sql_file": "sql/display.sql" → data/display.xlsx
--
-- ImageUrl / ProductFamily / IsDiscontinued 与 product_stock_price.sql 同源：
--   图片 = ProductDocuments + Documents（默认图优先）
--   系列 = Products.ProductFamily
--   停产 = 仅导出标记，WHERE 中不过滤（勿加 IsDiscontinued = 0）
--
-- 其它 display*.sql 为程序自动兜底，日常只改本文件。
-- Display 库存：仓库名含 Display，StockStatus Normal/Clearance
-- ═══════════════════════════════════════════════════════════════

SELECT
    w.Name AS WarehouseName,
    p.Sku,
    p.Name AS ProductName,
    ISNULL(p.ProductFamily, '') AS ProductFamily,
    p.Name AS SubProductFamily,
    CAST(p.IsDiscontinued AS INT) AS IsDiscontinued,
    s.StockStatus AS StockStatus,
    MAX(
        CASE
            WHEN img.RelativeFilePath IS NOT NULL
            THEN 'https://ierpapi.ifurniture.co.nz/' + REPLACE(img.RelativeFilePath, '\', '/')
            ELSE ''
        END
    ) AS ImageUrl,
    SUM(s.Quantity) AS DisplayQty
FROM [dbo].[Products] p

-- ↓ 与 sql/product_stock_price.sql 中 img 子查询保持同步 ↓
LEFT JOIN (
    SELECT ProductId, RelativeFilePath
    FROM (
        SELECT
            PD.ProductId,
            D.RelativeFilePath,
            ROW_NUMBER() OVER (
                PARTITION BY PD.ProductId
                ORDER BY
                    CASE WHEN PD.IsDefaultProductPicture = 1 THEN 0 ELSE 1 END,
                    D.DateUploadedOnUtc DESC
            ) AS rn
        FROM dbo.ProductDocuments PD
        INNER JOIN dbo.Documents D
            ON PD.DocumentId = D.Id
        WHERE NULLIF(LTRIM(RTRIM(D.RelativeFilePath)), '') IS NOT NULL
    ) t
    WHERE rn = 1
) img
    ON img.ProductId = p.Id

INNER JOIN [dbo].[Stocks] s
    ON s.ProductId = p.Id
    AND s.StockStatus IN ('Normal', 'Clearance')
    AND (
        s.StockOnHoldStatus IS NULL
        OR LTRIM(RTRIM(s.StockOnHoldStatus)) = ''
    )

INNER JOIN [dbo].[Warehouses] w
    ON s.WarehouseId = w.Id

WHERE w.Name LIKE '%Display%'

GROUP BY
    w.Name,
    p.Sku,
    p.Name,
    p.ProductFamily,
    p.IsDiscontinued,
    s.StockStatus

HAVING SUM(s.Quantity) > 0

ORDER BY
    w.Name,
    ProductFamily,
    SubProductFamily,
    DisplayQty DESC;
