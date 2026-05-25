# Price Checker 2 (PC2) - Análisis Completo

> **Fuente:** [Daily Source Tools](https://www.dailysourcetools.com) — Software de análisis de listas wholesale para vendedores de Amazon.
> **Empresa:** Cave Capital Inc. (fundada 2013 por James y Fiona Rugg, California)
> **Primera versión:** Enero 2015 (Price Checker 1), Noviembre 2015 (Price Checker 2)

---

## Visión General

Price Checker 2 (PC2) es un software de escritorio que permite a vendedores de Amazon analizar listas de productos de proveedores wholesale en bulk para identificar productos rentables para reventa. Procesa hasta **18,000 items por hora** y maneja listas de hasta **500,000 items**. Usa la **Amazon SP-API** (Selling Partner API) para obtener datos 100% precisos de pricing y fees.

El software procesa **todo localmente** en el computador del usuario — no almacena copias de los datos accedidos.

---

## 3 Modos de Análisis

| Modo | Descripción |
|------|-------------|
| **File-based** | Procesa productos desde un archivo (CSV, XLS, XLSX, TAB) |
| **Amazon Browser** | Escanea resultados de búsqueda, tiendas de marca o storefronts de competidores directamente en Amazon |
| **Quick Lookup** | Verificación rápida de un solo código de producto o keyword |

---

## Planes y Precios

| Plan | Precio | Límites | Marketplaces |
|------|--------|---------|-------------|
| **Free Demo** | Gratis | 1 ejecución, hasta 20K items | Amazon.com/.ca, Amazon.co.uk/.de/.fr/.es/.it |
| **Monthly** | $148/mes | Tamaño de archivo ilimitado, hasta 18K/hora | Amazon.com/.ca/.mx/.br/.au, Amazon.co.uk/.de/.fr/.es/.it |

**Características incluidas en todos los planes:**
- 99%+ precisión en cálculos de fees de Amazon
- Corrección automática de UPC
- Soporte CSV, XLS, XLSX
- Detección de multipacks
- Filtrado y ordenamiento en tiempo real
- Conversión de monedas con tasas de mercado actualizadas

---

## Product IDs Soportados

| Tipo | Formato | Método de búsqueda |
|------|---------|-------------------|
| **ASIN** | 10 dígitos alfanuméricos | ID Lookup (más rápido) |
| **EAN** | 13 dígitos numéricos con check digit | ID Lookup |
| **UPC** | 12 dígitos numéricos con check digit | ID Lookup |
| **ISBN** | 10 o 13 dígitos (check digit puede ser X) | ID Lookup |
| **Keyword** | Cualquier texto alfanumérico | Keyword Search (más lento) |
| **SellerSKU** | SKU propio del vendedor | SKU Lookup (solo productos ya listados) |

**Corrección automática:** Agrega ceros iniciales faltantes y calcula check digits faltantes. Tolera espacios dentro de los IDs. Múltiples tipos de ID pueden coexistir en una sola columna.

---

## Requisitos de Archivo de Entrada

**Formatos soportados:** `.xls`, `.xlsx`, `.csv`, `.tab` (tab delimited)

**Flexibilidad:**
- El orden de columnas es irrelevante
- Headers opcionales (no requeridos)
- Check digits faltantes se calculan automáticamente
- Separadores decimales: comas o puntos
- Símbolos de moneda de un dígito se ignoran automáticamente
- Múltiples tipos de ID pueden coexistir en una columna

**Recomendaciones:**
- Eliminar headers de empresa y filas de formato de marca
- Eliminar columnas en blanco a la izquierda

---

## Configuración de Run Settings

### Inputs Principales

| Setting | Descripción |
|---------|-------------|
| **Input List** | Archivo seleccionado con conteo estimado de registros |
| **Product ID Type** | Auto-detectado (ASIN, EAN, UPC, ISBN, Keywords, SellerSKU) |
| **File Has Headers** | Checkbox para tratar primera fila como títulos |
| **Product ID Column** | Columna con identificadores (auto-detectada) |
| **Remove Duplicates** | Activado por defecto; desactivar para lotes de liquidación con costos separados |

### Costos

| Setting | Descripción |
|---------|-------------|
| **Cost Column** | Columna de costos unitarios (opcional, habilita cálculos de profit/ROI) |
| **Supplier Multipack Column** | Ajusta costos para case-packs, cartons o pallets |
| **Costs Currency Input** | Moneda de los costos (tasas de cambio descargadas varias veces al día) |
| **Return Profits In** | Moneda de salida para profits (conversión multi-paso) |

### Marketplace y Procesamiento

| Setting | Descripción |
|---------|-------------|
| **Marketplace** | Marketplace objetivo (requiere SP-API keys válidas) |
| **Cost Profile** | Perfil de costos adicionales (prep, shipping, VAT) |
| **Historical Data** | Activado por defecto; proporciona promedios históricos y datos editoriales |
| **Get Variation Reviews** | Reviews individuales por variación (desactivado, lento) |
| **Grab All Variations** | Descubre todas las variaciones del producto (desactivado, lento) |

---

## Marketplaces Soportados

Los marketplaces están agrupados por región — PC2 activa todos los mercados accesibles con las mismas keys.

| Región | Marketplaces |
|--------|-------------|
| **Norteamérica** | Amazon.com, Amazon.ca, Amazon.mx, Amazon.com.br |
| **Europa** | Amazon.co.uk, Amazon.de, Amazon.fr, Amazon.es, Amazon.it |
| **Otros** | Amazon.com.au (requiere autorización separada) |

**Requisitos de cuenta:**
- Pro Seller Account en buen estado
- KYC (Know Your Customer) completado
- Cuentas de financiamiento y pago activas
- Marketplaces activados bajo "Selling Globally"

---

## Columnas de Datos (Output)

### Datos de Input
| Columna | Descripción |
|---------|-------------|
| Input ID | UPC u otro ID del archivo de entrada |
| Cost $USD | Costo por unidad del archivo |
| Wholesale Pack Qty | Cantidad de empaque del proveedor |
| Original Data | Datos originales sin procesar |

### Atributos Core de Amazon
| Columna | Descripción |
|---------|-------------|
| ASIN | Identificador Amazon o "Product not found" |
| Amazon Title | Título del producto en Amazon |
| No# of sellers | Total de vendedores ofreciendo el producto |
| AMZ Multi Pack Qty | Cantidad de paquete según Amazon API |
| Product Group | Clasificador de categoría de la API |
| Multi ASIN? | Indica múltiples ASINs encontrados |
| Product Type Name | Clasificador de tipo de producto |
| Parent ASIN | ASIN padre si aplica |
| Hazmat | Flag que previene envío FBA |
| Image | URL de imagen pequeña |
| Shipment Restrictions | Flags de errores de envío FBA |
| Trade-in Eligible | Estado de elegibilidad de trade-in |
| Trade-in Price $USD | Valor de trade-in |
| Brand | Marca del producto |
| Major Brand? | Clasificación de la lista de marcas del usuario |
| List Price $USD | MSRP mostrado en Amazon |
| No# of variations | Conteo de variantes del producto |
| Inactive/Redirects? | Flags de ASINs inactivos o redirigidos |

### Atributos Adicionales
50+ atributos adicionales de la Amazon SP-API:
- Actor, Artist, Aspect Ratio, Audience Rating, Author
- Binding, Color, Department, Director, Edition
- Format, Genre, Manufacturer, Material Type, Model
- Y muchos más atributos específicos por producto

### Columnas Personalizadas
Los usuarios pueden crear columnas custom usando fórmulas de spreadsheet.

---

## Cost Profiles (Perfiles de Costo)

### Tipos de Fulfillment

| Tipo | Descripción | Fees | Shipping |
|------|-------------|------|---------|
| **FBA** | Fulfillment by Amazon | Fees de FBA aplicadas | Shipping "to Amazon" |
| **MFN** | Merchant Fulfilled Network | Sin fees FBA | Shipping "to the customer" |
| **EFN** | European Fulfillment Network | Fees FBA locales o cross-border | Shipping al mercado fuente |

### Small & Light
Cuando los items califican por peso y dimensiones, los fees de Small & Light reemplazan los fees estándar de FBA.

### Componentes de Costo

| Componente | Detalle |
|-----------|---------|
| **Prep Costs** | Por item individual o por unidad dentro de multipacks. Soporta múltiples monedas con conversión automática |
| **Shipping from Supplier** | Calculado como % del costo del producto o por item/peso. Incluido en COGS total |
| **Shipping to Amazon** | Costo secundario (warehouse → Amazon). Aparece en columna separada, NO en COGS |
| **VAT** | Vendedores registrados: VAT deducido de precios Amazon. No registrados: VAT sumado a fees. Aplicado a tasa especificada |

---

## Sistema de Filtros

### Filtros de UPC/EAN/ISBN Lookup
- Retornar todos los resultados (max 10 de la API)
- Retornar top N por Best Seller Rank
- Retornar primeros N items por relevancia/featured

### Major Brands (Marcas Principales)
- Lista pre-instalada de marcas gated que requieren aprobación
- Archivo editable (un brand por línea, no case-sensitive)
- Soporta comentarios con `#`
- Se puede editar mientras una ejecución está en progreso
- Variaciones de marca deben agregarse individualmente (Disney, Disney's, Disney World)

### Custom Filters
Filtros automáticos que descartan items que no cumplen criterios durante el análisis.

**Campos filtrables:** Cualquier atributo que PC2 soporta, incluyendo datos históricos custom.

**Operadores disponibles:**

| Operador | Tipos de datos |
|----------|---------------|
| Is/Is Not Blank | Todos |
| Equal/Not Equal To | Todos |
| Starts/Doesn't Start With | Texto |
| Ends/Doesn't End With | Texto |
| Contains/Doesn't Contain | Texto |
| Contains/Doesn't Contain Any | Texto (múltiples valores) |
| Matches Regular Expression | Texto (POSIX regex) |
| Greater/Lower Than | Números, %, precios |
| Greater or Equal/Lower or Equal | Números, %, precios |
| Is True/Is False | Campos booleanos |

**Comportamiento:** Los filtros se ejecutan inmediatamente cuando los datos están disponibles, descartando items antes de completar todas las descargas. El sistema evita aplicar filtros prematuramente.

---

## Amazon Browser

**Disponible solo en suscripción pagada.** Usa Chrome/Chromium local (incluido desde v3.1.0+).

### Tipos de Páginas Soportadas
1. **Brand Stores** — Páginas oficiales de marca (ej. Lego Store)
2. **Search Results** — Resultados de búsqueda casi arbitrarios en Amazon
3. **Seller Storefronts** — Catálogos de vendedores individuales

### Flujo de Trabajo
1. Lanzar browser vía botón naranja en PC2
2. Navegar a la página deseada
3. Click "Check Page for Products" → Deep Scan
4. Click "Analyse [título]"
5. Configurar run settings y ejecutar

### Características
| Feature | Detalle |
|---------|---------|
| Cost Percentage | Usa % del precio Amazon como costo estimado (default: 50%) |
| Prime Detection | Columna "Prime?" mostrando elegibilidad Prime |
| Multipack Support | Ajusta cantidades de empaque para pricing per-unit |
| Sponsored Content | Filtrado automáticamente (solo resultados orgánicos) |

---

## ASIN Scoring

Sistema de puntuación ponderada que asigna puntos a atributos de datos, creando priorización de productos más allá del filtrado simple.

---

## Análisis Settings Avanzados

| Setting | Descripción |
|---------|-------------|
| **MFN BuyBox Premium** | Agrega premium a productos solo-MFN vs FBA |
| **Reference Offer Selection** | Prioriza qué price feed alimenta los cálculos de profit |
| **In-Stock Filter** | Ignora ofertas no disponibles para envío inmediato |
| **Sales Rank Ordering** | Determina qué rank genera estimaciones de ventas |
| **Packaging Overrides** | Corrige cantidades multi-pack del catálogo Amazon por ASIN/marketplace |

---

## Currency Exchange (Conversión de Monedas)

- Tasas de cambio descargadas en vivo múltiples veces al día
- Tasas embebidas directamente en fórmulas de Excel como valores numéricos
- Headers de columna se actualizan dinámicamente para reflejar la moneda

### Configuración
| Opción | Descripción |
|--------|-------------|
| Default list & shipping currency | Moneda base de entrada |
| Operating currency | Moneda default para cálculos de profit |
| Commission % | Porcentaje fijo aplicado a todos los pares de monedas |
| Individual Rate Overrides | Comisiones custom por par de moneda específico |

Muestra tasas aplicadas junto a tasas mid-market y timestamps de actualización.

---

## Color Highlights

### Highlights de Fila (Automáticos)

| Condición | Tipo |
|-----------|------|
| Amazon tiene el Buy Box | Requiere datos históricos |
| Amazon es vendedor pero no en Buy Box | Requiere datos históricos |
| ROI positivo | Financiero |
| ROI negativo | Financiero |
| MFN Premium aplicado | Condicional |
| Precios en USD, GBP, EUR, CAD | Condicional |

### Highlights de Header (Por Columna)

| Color | Significado |
|-------|------------|
| **Azul** | Columnas generadas por PC2 (incluyendo ID, Cost, Wholesale Pack) |
| **Amarillo** | Columnas de significancia especial para la mayoría de usuarios |
| **Gris** | Datos originales que PC2 no ha interpretado |

---

## Command Line Interface (CLI)

Permite automatización completa vía terminal (Windows cmd o Mac Terminal).

### Estructura Básica

**Windows:**
```
"C:\Program Files\Price Checker 2\pc2cmd.exe" [options] "file_or_url"
```

**Mac:**
```
"/Applications/Price Checker 2.app/Contents/Resources/app/pc2cmd" [options] "file_or_url"
```

### Parámetros Comunes (Todos los tipos de ejecución)

| Parámetro | Descripción |
|-----------|-------------|
| `-autostart` / `-auto` | Ejecutar sin mostrar diálogo de settings |
| `-costProfile "name"` | Especificar perfil de cálculo de costos |
| `-currency` | Moneda de salida (USD, EUR, etc.) |
| `-grabAllVariations` | Habilitar colección de variaciones |
| `-immediate` | Procesar en paralelo a jobs en cola |
| `-keepDuplicates` | Deshabilitar eliminación de duplicados |
| `-outFile` / `-out` | Path personalizado de archivo de salida |
| `-outType` | Formato de archivo (xls, xlsx, csv, tab) |
| `-reviews` | Descargar reviews de variaciones |
| `-silent` | Suprimir diálogos modales |

### Parámetros de Archivo

| Parámetro | Descripción |
|-----------|-------------|
| `-headers` | Indica que el archivo tiene headers |
| `-idType` / `-it` | Tipo de Product ID (ASIN, EAN, UPC, GTIN, ISBN, Keywords) |
| `-id` | Índice de columna para Product IDs (base 0) |
| `-cost` | Índice de columna para costos |
| `-pack` | Índice de columna para wholesale packaging |
| `-costCurrency` | Moneda de interpretación de costos |
| `-mkt` | Marketplace objetivo (UK, DE, US, etc.) |

### Parámetros de Browser/URL

| Parámetro | Descripción |
|-----------|-------------|
| `-deepScan` | Análisis comprehensivo |
| `-extract` | Solo extraer productos (saltar análisis) |
| `-visual` | Mostrar ventana del browser durante ejecución |

---

## Cache Control

### Datos Cacheados

| Tipo | Descripción | Retención Default |
|------|-------------|-------------------|
| **Reviews** | Conteo y rating por variación o producto | Configurable |
| **Historical Data** | Descargas previas por ASIN (promedios, % stock) | 3 días |
| **Inbound Eligibility/Hazmat** | Estado de elegibilidad de envío y clasificaciones hazmat | Configurable |
| **ASIN Listing Restrictions** | Requisitos de autorización por producto específicos del vendedor | Configurable |
| **Brand Listing Restrictions** | Estado de autorización por marca completa | Configurable |

### Configuración
| Opción | Descripción |
|--------|-------------|
| Retention Duration | Edad máxima antes de eliminar items cacheados |
| Max Size | Límite de espacio en disco (LRU eviction) |
| Manual Clearing | Botón de trash por tipo de cache (sin confirmación) |

**Importante:** El mapeo de product codes y la información de ofertas en vivo SIEMPRE se obtienen fresh (nunca cacheados).

---

## Datos de Amazon Accedidos

**API utilizada:** Amazon SP-API (Selling Partner API)

**Datos NO accedidos:**
- Datos de órdenes o clientes (PII - Personally Identifiable Information)

**Manejo de datos:**
- PC2 NO almacena copias de los datos accedidos
- Opera como intermediario facilitando acceso a la API vía la cuenta del vendedor
- El usuario es responsable de la seguridad de los datos descargados

---

## Integraciones Externas

| Servicio | Tipo | Uso |
|----------|------|-----|
| Amazon SP-API | API | Datos de productos, precios, fees, offers |
| CamelCamelCamel | Link | Historial de precios (clickable URL en output) |
| Keepa | Link | Historial de precios y sales rank (clickable URL en output) |
| Alibaba | Link | Búsqueda de proveedores (clickable URL en output) |
| Google | Link | Búsqueda general del producto (clickable URL en output) |

---

## Capacidades Clave de Análisis

| Capacidad | Detalle |
|-----------|---------|
| **Velocidad** | 17,000-18,000 items/hora |
| **Volumen** | Listas de 50K a 500K items |
| **Precisión de fees** | 99%+ en cálculos de fees de Amazon |
| **Corrección de UPC** | Auto-inserta ceros faltantes, calcula check digits |
| **Detección de multipacks** | Detecta y ajusta cantidades automáticamente |
| **Buy Box Contenders** | Identifica vendedores competitivos reales |
| **Profit/ROI** | Cálculo de profit neto y % ROI con todos los costos |
| **Dimensional weight** | Integra peso dimensional en cálculos |
| **Shipping costs** | Incorpora costos de envío en análisis de profit |
| **Live filtering** | Filtrado en tiempo real por rank, ROI%, peso, reviews |
| **Export** | Exportación en vivo a Excel |

---

## Resumen Comparativo: PC2 vs FlipIQ

| Aspecto | Price Checker 2 (PC2) | FlipIQ |
|---------|----------------------|--------|
| **Tipo** | Desktop app (Windows/Mac) | API web (FastAPI) |
| **Target** | Wholesale list analysis en bulk | Análisis individual por barcode/keyword |
| **Volumen** | 500K items por ejecución | 1 producto a la vez (con rate limits) |
| **Marketplaces** | Amazon multi-región (10+ mercados) | eBay + Amazon |
| **Data source** | Amazon SP-API directa | eBay scraper + Keepa API |
| **Pricing** | $148/mes flat | Tiers free/starter/pro |
| **Decisión** | Datos crudos (profit, ROI, rank) | Recomendación automatizada (buy/watch/pass) |
| **AI** | No | Sí (Gemini/GPT para explanations) |
| **Velocidad** | 18K items/hora | 1 análisis en ~5-15 segundos |
| **CLI** | Sí (automatización completa) | No (solo API) |
| **Browser** | Sí (escaneo de storefronts) | No |
