# Datos que Keepa API nos Proporciona

> Análisis basado en llamada real con ASIN B0D1XD1ZV3 (Apple AirPods Pro 2)
> Plan actual: ~1200 tokens, refill rate: 20 tokens/minuto

---

## Rate Limits

| Campo | Valor |
|-------|-------|
| tokensLeft | 1199 (después de 1 request) |
| refillRate | 20 tokens/minuto |
| Costo por product request | ~5 tokens (con stats+offers+history) |
| Capacidad efectiva | ~240 productos/minuto = **14,400/hora** |

---

## 1. Datos Básicos del Producto

| Campo | Ejemplo | Uso |
|-------|---------|-----|
| `asin` | B0D1XD1ZV3 | Identificador único |
| `title` | "Apple AirPods Pro 2 Wireless Earbuds..." | Nombre del producto |
| `brand` | Apple | Marca |
| `manufacturer` | Apple | Fabricante |
| `model` | MTJV3LL/A | Número de modelo |
| `partNumber` | MTJV3LL/A | Part number |
| `color` | White | Color |
| `size` | One Size | Talla |
| `type` | HEADPHONES | Tipo de producto |
| `binding` | null | Encuadernación (libros) |
| `edition` | null | Edición |
| `format` | null | Formato |
| `packageQuantity` | 1 | Unidades por paquete |
| `numberOfItems` | 1 | Items incluidos |
| `department` | null | Departamento |
| `style` | "Without AppleCare+" | Estilo/variante |
| `material` | Plastic | Material |
| `recommendedUsesForProduct` | Exercising | Uso recomendado |
| `includedComponents` | "Wireless Charging Case, Cable" | Componentes incluidos |
| `description` | Texto completo del producto | Descripción |
| `features` | Array de 10 bullet points | Características |
| `specialFeatures` | Array de 5 features | Features especiales |

---

## 2. Identificadores

| Campo | Ejemplo | Uso |
|-------|---------|-----|
| `asin` | B0D1XD1ZV3 | ASIN del producto |
| `parentAsin` | B0FBXVLLQF | ASIN padre (para variaciones) |
| `upcList` | ["195949704529"] | Códigos UPC |
| `eanList` | ["0195949704529"] | Códigos EAN |
| `releaseDate` | 20240423 | Fecha de lanzamiento |
| `listedSince` | 7000320 (Keepa time) | Desde cuándo está listado |

---

## 3. Categorías

| Campo | Ejemplo | Uso |
|-------|---------|-----|
| `rootCategory` | 172282 | ID categoría raíz (Electronics) |
| `categoryTree` | [{catId: 172282, name: "Electronics"}, ..., {catId: 12097478011, name: "Earbud Headphones"}] | Árbol completo de categoría |
| `categories` | [12097478011] | ID de categoría leaf |
| `salesRankDisplayGroup` | "ce_display_on_website" | Grupo de display |
| `websiteDisplayGroupName` | "Premium Consumer Electronics Brands" | Nombre del grupo |
| `itemTypeKeyword` | "in-the-ear-headphones" | Keyword de tipo |

---

## 4. Fees (CRÍTICO para cálculos de profit)

| Campo | Ejemplo | Uso |
|-------|---------|-----|
| `referralFeePercentage` | 10.71 | **% de referral fee real** (10.71% para este producto) |
| `fbaFees.pickAndPackFee` | 447 (centavos = $4.47) | **Fee real de FBA fulfillment** |
| `fbaFees.lastUpdate` | 8096224 (Keepa time) | Última actualización de fees |
| `competitivePriceThreshold` | 24900 (centavos = $249) | Umbral de precio competitivo |
| `suggestedLowerPrice` | 24900 (centavos = $249) | Precio sugerido inferior |

---

## 5. Sales & Velocity (CRÍTICO para estimar ventas)

| Campo | Ejemplo | Uso |
|-------|---------|-----|
| `monthlySold` | 300 | **Unidades vendidas al mes** (dato directo de Amazon "300+ bought in past month") |
| `monthlySoldHistory` | [..., 8048988, 200, 8086396, 300] | Historial de unidades vendidas mensualmente |
| `salesRankDrops30` | 51 | **Drops de rank en 30 días** ≈ estimación de ventas |
| `salesRankDrops90` | 186 | Drops en 90 días |
| `salesRankDrops180` | 305 | Drops en 180 días |
| `salesRankDrops365` | 395 | Drops en 365 días |
| `salesRanks` | {172282: [800 entries], 12097478011: [402 entries]} | Historial de BSR por categoría |

**Interpretación de `monthlySold`:** Dato real de Amazon "X+ bought in past month". Mucho más preciso que la estimación por BSR que usa FlipIQ.

**`salesRankDrops`:** Cada drop de sales rank indica una venta. 51 drops en 30 días ≈ 51 ventas ≈ 1.7/día.

---

## 6. Buy Box (CRÍTICO para competitividad)

| Campo | Ejemplo | Uso |
|-------|---------|-----|
| `stats.buyBoxPrice` | -1 (out of stock) | Precio actual del Buy Box (centavos) |
| `stats.buyBoxShipping` | -1 | Shipping del Buy Box |
| `stats.buyBoxIsFBA` | false | ¿Buy Box es FBA? |
| `stats.buyBoxIsAmazon` | false | ¿Amazon tiene el Buy Box? |
| `stats.buyBoxSellerId` | null | Seller ID con el Buy Box |
| `stats.buyBoxCondition` | null | Condición del Buy Box |
| `stats.buyBoxIsUsed` | false | ¿Buy Box es used? |

### Buy Box Stats (por seller)
```json
{
  "A1KWJVS57NX03I": {
    "avgPrice": 21092,           // Precio promedio: $210.92
    "percentageWon": 16.47,      // % del tiempo con Buy Box
    "isFBA": true,
    "avgNewOfferCount": 2,
    "avgUsedOfferCount": 1,
    "lastSeen": 8095760
  },
  "ATVPDKIKX0DER": {            // Amazon mismo
    "avgPrice": 24900,           // $249.00
    "percentageWon": 12.31,      // Amazon gana 12.3% del tiempo
    "isFBA": true,
    "avgNewOfferCount": 2,
    "avgUsedOfferCount": 3
  }
}
```

### Buy Box Seller History
`buyBoxSellerIdHistory`: Array alternando [keepa_time, seller_id, ...] mostrando quién tiene el Buy Box en cada momento. Permite calcular Buy Box share por seller.

---

## 7. Ofertas de Sellers (hasta 20)

| Campo | Ejemplo | Uso |
|-------|---------|-----|
| `sellerId` | A2L77EE7U53NWQ | ID del seller |
| `condition` | 1=New, 2=Used-Like New, 3=Very Good, 4=Good, 5=Acceptable | Condición |
| `isFBA` | true/false | ¿Fulfillment by Amazon? |
| `isPrime` | true/false | ¿Elegible para Prime? |
| `isAmazon` | true/false | ¿Es Amazon directamente? |
| `isWarehouseDeal` | true/false | ¿Amazon Warehouse? |
| `isMAP` | true/false | ¿Minimum Advertised Price? |
| `shipsFromChina` | true/false | ¿Envía desde China? |
| `minOrderQty` | 1 | Cantidad mínima de orden |
| `offerCSV` | [keepa_time, price_cents, shipping_cents, ...] | **Historial de precios del seller** |
| `lastSeen` | Keepa time | Última vez visto |

---

## 8. Stock & Disponibilidad

| Campo | Ejemplo | Uso |
|-------|---------|-----|
| `availabilityAmazon` | -1 (out of stock) | Disponibilidad de Amazon |
| `outOfStockPercentage30` | [89, 0, 43, ...] | % fuera de stock por tipo (30d) |
| `outOfStockPercentage90` | Array | % fuera de stock (90d) |
| `outOfStockCountAmazon30` | 30 | Días OOS de Amazon en 30d |
| `outOfStockCountAmazon90` | 87 | Días OOS de Amazon en 90d |
| `stats.offerCountFBA` | 0 | Ofertas FBA activas |
| `stats.offerCountFBM` | 1 | Ofertas FBM activas |
| `stats.totalOfferCount` | 3 | Total de ofertas |

---

## 9. Historial de Precios (CSV arrays, 36 series)

| Índice | Nombre | Formato | Contenido |
|--------|--------|---------|-----------|
| 0 | AMAZON | pairs [time, price] | Precio de Amazon (centavos) |
| 1 | NEW | pairs | Precio más bajo New |
| 2 | USED | pairs | Precio más bajo Used |
| 3 | SALES_RANK | pairs | Historial de BSR |
| 4 | LIST_PRICE | pairs | MSRP/List price |
| 7 | NEW_FBM_SHIPPING | triples [time, price, shipping] | Precio New FBM + shipping |
| 9 | WAREHOUSE | pairs | Precio Amazon Warehouse |
| 10 | NEW_FBA | pairs | Precio más bajo New FBA |
| 11 | COUNT_NEW | pairs | Conteo de ofertas New |
| 12 | COUNT_USED | pairs | Conteo de ofertas Used |
| 16 | RATING | pairs | Rating (x10, ej: 46 = 4.6★) |
| 17 | COUNT_REVIEWS | pairs | Número de reviews |
| 18 | BUY_BOX_SHIPPING | triples | **Precio Buy Box + shipping** |
| 19-22 | USED_*_SHIPPING | triples | Precios Used por condición |

---

## 10. Dimensiones y Peso

| Campo | Valor | Unidad |
|-------|-------|--------|
| `itemHeight` | 31 | 1/100 pulgadas |
| `itemLength` | 24 | 1/100 pulgadas |
| `itemWidth` | 22 | 1/100 pulgadas |
| `itemWeight` | 45 | gramos |
| `packageHeight` | 47 | 1/100 pulgadas |
| `packageLength` | 99 | 1/100 pulgadas |
| `packageWidth` | 98 | 1/100 pulgadas |
| `packageWeight` | 231 | gramos |

**Útil para:** Calcular dimensional weight y estimar FBA fees cuando Keepa no los provee directamente.

---

## 11. Flags y Elegibilidad

| Campo | Valor | Uso |
|-------|-------|-----|
| `isAdultProduct` | false | Producto adulto |
| `isEligibleForTradeIn` | true | Elegible para trade-in |
| `isEligibleForSuperSaverShipping` | true | Super Saver shipping |
| `isRedirectASIN` | false | ASIN redirigido |
| `isSNS` | false | Subscribe & Save |
| `isHeatSensitive` | false | Sensible al calor (FBA) |
| `hazardousMaterials` | Array detallado | Info de materiales peligrosos |
| `launchpad` | false | Amazon Launchpad |

---

## 12. Variaciones

| Campo | Ejemplo | Uso |
|-------|---------|-----|
| `variations` | [{asin, attributes: [{dimension: "Style", value: "Without AppleCare+"}]}] | Variaciones del producto |
| `parentAsin` | B0FBXVLLQF | ASIN padre |
| `parentTitle` | Título del parent listing | Título del parent |

---

## 13. Reviews

| Campo | Ejemplo | Uso |
|-------|---------|-----|
| `hasReviews` | true | Tiene reviews |
| `csv[16]` RATING | 46 (= 4.6★) | Rating actual (x10) |
| `csv[17]` COUNT_REVIEWS | 46746 | Número de reviews |

---

## Datos que Keepa NO tiene (necesitan SP-API)

| Dato | Alternativa Keepa |
|------|-------------------|
| **Listing restrictions por seller** | No disponible — necesita SP-API `getListingRestrictions` |
| **Seller-specific fees exactos** | `referralFeePercentage` + `fbaFees` cubren el 95% |
| **Inbound eligibility** | `isHeatSensitive` + `hazardousMaterials` dan indicios |
| **Seller SKU lookup** | No disponible — necesita SP-API |
| **A-to-Z claim data** | No disponible |
| **Return rate real** | No disponible |

---

## Mejoras a Implementar en Nuestro KeepaProvider

Basado en estos datos reales, debemos actualizar `providers/keepa.py` para extraer:

1. **`monthlySold`** → Mucho mejor que la estimación por BSR
2. **`salesRankDrops30/90`** → Estimación precisa de ventas
3. **`buyBoxStats`** → % de Buy Box por seller, crucial para execution
4. **`outOfStockPercentage`** → Oportunidad cuando Amazon está OOS
5. **`outOfStockCountAmazon30/90`** → Días que Amazon estuvo fuera de stock
6. **Dimensiones y peso** → Para estimar FBA fees más precisos
7. **`stats.current[11]` (COUNT_NEW)** → Conteo real de sellers New
8. **`stats.current[16]` (RATING)** → Rating del producto (÷10)
9. **`stats.current[17]` (COUNT_REVIEWS)** → Número de reviews
10. **`hazardousMaterials`** → Flag de hazmat detallado

### Throughput Real
- 1 request con `offers=20` cuesta ~5 tokens
- Con 20 ASINs por request: ~5 tokens × 1 = 5 tokens
- Refill: 20 tokens/minuto → 4 batch requests/min → **80 ASINs/minuto = 4,800/hora**
- Con plan Keepa más alto → proporcional
