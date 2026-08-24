-- Display 库：各门店 Display 库存
-- 由 grab_display.bat / grab_display_gui.py 自动执行
--
-- 图片逻辑与库存 stock SQL 一致：ProductDocuments + Documents → RelativeFilePath
-- ProductFamily 直接读 Products 表字段（无 ProductFamilies 查找表）
-- Display 库存含 Normal + Clearance（清仓 Demo 仍在门店 Display 上）

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

-- 产品默认图：优先 IsDefaultProductPicture=1，否则取最新上传图
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
    AND s.StockOnHoldStatus IS NULL

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
