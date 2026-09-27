-- 澳洲 · 产品库存 + 原价/促销价（按 SKU 一行）
-- 抓取: python scripts/grab_stock_price.py（active_region=au）→ data/au/product_stock_price.xlsx
--
-- TotalWarehouseStock = 非 Display / Storage 库位的 Normal 库存合计（不含摆场库）
-- 界面侧栏/画布上的「场/储」来自 display.xlsx，与本表价格/仓库库存配合使用

DECLARE @SkuFilter VARCHAR(20) = '';

SELECT
    p.Sku,
    p.Name AS ProductName,
    ISNULL(p.ProductFamily, '') AS ProductFamily,
    p.PriceRadarVolume,
    CAST(p.IsDiscontinued AS INT) AS IsDiscontinued,
    p.UnitPrice,
    CASE
        WHEN promo.SalePrice IS NOT NULL
         AND promo.SalePrice > 0
         AND promo.SalePrice < p.UnitPrice
        THEN promo.SalePrice
        ELSE p.UnitPrice
    END AS SalePrice,
    CASE
        WHEN promo.SalePrice IS NOT NULL
         AND promo.SalePrice > 0
         AND promo.SalePrice < p.UnitPrice
        THEN 1
        ELSE 0
    END AS OnPromotion,
    MAX(
        CASE
            WHEN img.RelativeFilePath IS NOT NULL
            THEN '{{IMAGE_BASE_URL}}' + REPLACE(img.RelativeFilePath, '\', '/')
            ELSE ''
        END
    ) AS ImageUrl,
    SUM(
        CASE
            WHEN w.Name NOT LIKE '%Display%'
             AND w.Name NOT LIKE '%Storage%'
            THEN ISNULL(s.Quantity, 0)
            ELSE 0
        END
    ) AS TotalWarehouseStock,
    0 AS CarbineStock,
    0 AS WallsStock,
    0 AS NorthIslandTotal,
    0 AS GeraldConnellyStock
FROM [dbo].[Products] p

LEFT JOIN (
    SELECT ProductId, SalePrice, PromotionId
    FROM (
        SELECT
            pp.ProductId,
            pp.SalePrice,
            pp.PromotionId,
            ROW_NUMBER() OVER (
                PARTITION BY pp.ProductId
                ORDER BY pp.SalePrice ASC, pp.PromotionId ASC
            ) AS rn
        FROM dbo.ProductPromotions pp
        INNER JOIN dbo.Promotions pr
            ON pp.PromotionId = pr.Id
        WHERE pp.IsDisabled = 0
          AND pr.IsEnabled = 1
          AND GETUTCDATE() BETWEEN pr.StartTimeUtc AND pr.EndTimeUtc
          AND pp.SalePrice IS NOT NULL
          AND pp.SalePrice > 0
    ) t
    WHERE rn = 1
) promo
    ON promo.ProductId = p.Id

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

LEFT JOIN [dbo].[Stocks] s
    ON s.ProductId = p.Id
    AND s.StockStatus = 'Normal'
    AND (
        s.StockOnHoldStatus IS NULL
        OR LTRIM(RTRIM(s.StockOnHoldStatus)) = ''
    )

LEFT JOIN [dbo].[Warehouses] w
    ON s.WarehouseId = w.Id

WHERE (@SkuFilter = '' OR p.Sku LIKE @SkuFilter + '%')

GROUP BY
    p.Sku,
    p.Name,
    p.ProductFamily,
    p.PriceRadarVolume,
    p.IsDiscontinued,
    p.UnitPrice,
    promo.SalePrice

ORDER BY p.Sku;
