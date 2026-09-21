-- 诊断/兜底：含 On Hold 的 Display 库存（Demo Prepared 可能被 StockOnHoldStatus 挡住时用）
-- 在 grabber_config.json 临时改 "sql_file": "sql/display.include_on_hold.sql" 测试
-- 确认 918-072 能出现后，请在 SSMS 运行 sql/discover_display_stock.sql 看 StockOnHoldStatus 实际值

SELECT
    w.Name AS WarehouseName,
    p.Sku,
    p.Name AS ProductName,
    COALESCE(
        NULLIF(LTRIM(RTRIM(pf.Name)), N''),
        NULLIF(LTRIM(RTRIM(p.ProductFamily)), N''),
        N''
    ) AS ProductFamily,
    COALESCE(
        NULLIF(LTRIM(RTRIM(psf.Name)), N''),
        p.Name
    ) AS SubProductFamily,
    MAX(CASE WHEN ISNULL(p.IsDiscontinued, 0) = 1 THEN 1 ELSE 0 END) AS IsDiscontinued,
    s.StockStatus AS StockStatus,
    ISNULL(CAST(s.StockOnHoldStatus AS NVARCHAR(64)), N'') AS StockOnHoldStatus,
    MAX(
        CASE
            WHEN img.RelativeFilePath IS NOT NULL
            THEN N'https://ierpapi.ifurniture.co.nz/' + REPLACE(img.RelativeFilePath, N'\', N'/')
            ELSE N''
        END
    ) AS ImageUrl,
    SUM(s.Quantity) AS DisplayQty
FROM [dbo].[Products] p

LEFT JOIN [dbo].[ProductFamilies] pf
    ON p.ProductFamilyId = pf.Id
LEFT JOIN [dbo].[ProductSubFamilies] psf
    ON p.ProductSubFamilyId = psf.Id

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
        WHERE NULLIF(LTRIM(RTRIM(D.RelativeFilePath)), N'') IS NOT NULL
    ) t
    WHERE rn = 1
) img
    ON img.ProductId = p.Id

INNER JOIN [dbo].[Stocks] s
    ON s.ProductId = p.Id
    AND s.StockStatus IN (N'Normal', N'Clearance')

INNER JOIN [dbo].[Warehouses] w
    ON s.WarehouseId = w.Id

WHERE w.Name LIKE N'%Display%'

GROUP BY
    w.Name,
    p.Sku,
    p.Name,
    pf.Name,
    psf.Name,
    p.ProductFamily,
    s.StockStatus,
    s.StockOnHoldStatus

HAVING SUM(s.Quantity) > 0

ORDER BY
    w.Name,
    ProductFamily,
    SubProductFamily,
    DisplayQty DESC;
