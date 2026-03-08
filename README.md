# 🛒 Argenprecios — Sistema de Inteligencia de Precios en Tiempo Real

Sistema de scraping, comparación y gestión de precios minoristas en Argentina.

---

## Requisitos previos

| Herramienta | Versión mínima | Descarga |
|---|---|---|
| Python | 3.12+ | https://www.python.org/downloads/ |
| Docker Desktop | Cualquiera | https://www.docker.com/products/docker-desktop/ |
| Git (opcional) | Cualquiera | https://git-scm.com/ |

---

## Instalación paso a paso

### Paso 1 — Abrir una terminal en el directorio del proyecto

```bash
cd C:\Users\Isma\Downloads\argenprecios
```

### Paso 2 — Crear el archivo de configuración

```bash
copy .env.example .env
```

Editá `.env` si necesitás cambiar puertos o límites de concurrencia.

### Paso 3 — Levantar MongoDB con Docker

```bash
docker-compose up -d
```

Verificar que esté corriendo:
```bash
docker ps
# Debería verse: argenprecios_db   mongo:7.0   Up
```

### Paso 4 — Crear entorno virtual e instalar dependencias

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Paso 5 — Instalar Playwright (navegador headless)

```bash
playwright install chromium
```

### Paso 6 — Cargar datos de ejemplo (seed)

```bash
python scripts/seed_demo.py
```

Esto carga 10 productos de canasta básica con precios de Coto y Carrefour,
inventario de ejemplo y reglas de descuento bancarias para poder usar el
Dashboard inmediatamente sin esperar el scraping real.

### Paso 7 — Iniciar el sistema

```bash
python main.py
```

### Paso 8 — Abrir el Dashboard

Abrí tu navegador en: **http://localhost:8000**

---

## Uso del Dashboard

### Pestaña 📊 Comparador de Precios
- Configurá tu **billetera** (tarjetas y programas de fidelidad que usás)
- Buscá productos por nombre
- Filtrá por cadena (Coto / Carrefour)
- Hacé clic en **"Ver detalle"** para comparar precios con tus descuentos aplicados
- Botón **"⚡ Disparar scraping ahora"** para ejecutar el Harvester manualmente

### Pestaña 📦 Inventario
- Agregá tus productos con costo, precio de venta y stock mínimo
- El sistema muestra tu **margen de ganancia** y lo compara con el mercado
- Alertas automáticas:
  - 🟢 Oportunidad de compra si el mercado vende más barato que tu costo
  - 🔴 Alerta si el mercado está >15% por debajo de tu precio de venta
  - 🟡 Atención si la brecha es entre 5% y 15%

### Pestaña 🛒 POS — Punto de Venta
- Escribí o escaneá el EAN del producto
- El sistema muestra: tu precio, tu margen, stock disponible y el mejor precio del mercado
- Agregá ítems al carrito y seleccioná el medio de pago
- Confirmá la venta → el stock se descuenta automáticamente
- Reporte del día con total recaudado y ranking de productos más vendidos

---

## API REST (para integraciones)

| Endpoint | Método | Descripción |
|---|---|---|
| `/api/productos` | GET | Lista productos con comparativa |
| `/api/comparar/{ean}` | GET | Comparativa detallada por EAN |
| `/api/wallet` | GET/POST | Billetera del usuario |
| `/api/inventario` | GET/POST | CRUD inventario |
| `/api/inventario/{ean}` | GET/DELETE | Item individual |
| `/api/inventario/{ean}/stock` | PATCH | Ajuste de stock |
| `/api/pos/scan/{ean}` | GET | Escaneo de producto |
| `/api/pos/venta` | POST | Registrar venta |
| `/api/pos/ventas` | GET | Historial de ventas |
| `/api/pos/reporte/diario` | GET | Reporte del día |
| `/api/pos/reporte/rotacion` | GET | Top productos (30 días) |
| `/api/stats` | GET | Estadísticas del sistema |
| `/clock/trigger` | POST | Disparo manual de scraping |
| `/clock/status` | GET | Estado del planificador |
| `/docs` | GET | Documentación Swagger |

---

## Configuración avanzada (.env)

```env
# Límite de scrapers simultáneos (ajustar según hardware)
MAX_CONCURRENT_SCRAPERS=2    # VPS 2GB RAM
MAX_CONCURRENT_SCRAPERS=12   # PC de escritorio

# Horarios de scraping automático (hora Argentina)
SCHEDULE_HOUR_1=6            # 06:00 AM
SCHEDULE_HOUR_2=12           # 12:00 PM

# Retención de datos históricos
TTL_DAYS=30                  # borrar precios de más de 30 días

# Reintentos si un sitio falla
RETRY_INTERVAL_MINUTES=15
MAX_RETRIES=3
```

---

## Estructura del proyecto

```
argenprecios/
├── main.py                          # Punto de entrada
├── docker-compose.yml               # MongoDB
├── requirements.txt
├── .env                             # Tu configuración (no commitear)
├── config/settings.py               # Variables de entorno
├── db/client.py                     # Conexión MongoDB + índices
├── scripts/
│   └── seed_demo.py                 # Datos de ejemplo
├── static/
│   ├── index.html                   # Dashboard
│   └── app.js                       # Lógica frontend
└── modules/
    ├── clock/scheduler.py           # Módulo 1: Planificador
    ├── harvester/
    │   ├── adapters/
    │   │   ├── base_adapter.py      # Base scraper
    │   │   ├── coto_adapter.py      # Adaptador Coto
    │   │   └── carrefour_adapter.py # Adaptador Carrefour (VTEX)
    │   ├── models.py                # ProductData
    │   └── user_agents.py           # Rotación de User-Agents
    ├── promo_engine/
    │   ├── models.py                # ReglaDescuento
    │   └── parser.py                # Parser NLP/Regex de promos
    ├── brain/calculator.py          # Módulo 4: Inteligencia de precios
    ├── operation/
    │   ├── inventory.py             # CRUD inventario + alertas
    │   └── pos.py                   # POS: ventas + reportes
    └── control/__init__.py          # Módulo 6: API REST completa
```

---

## Comandos útiles

```bash
# Ver logs en tiempo real
docker logs argenprecios_db -f

# Acceder a MongoDB desde terminal
docker exec -it argenprecios_db mongosh argenprecios

# Detener el sistema
Ctrl+C  (en la terminal de python main.py)
docker-compose down  (para bajar MongoDB)

# Reiniciar desde cero (borra todos los datos)
docker-compose down -v
docker-compose up -d
python scripts/seed_demo.py
python main.py
```

---

## Próximas mejoras planeadas

- [ ] Adaptadores para Jumbo, DIA, ChangoMás, La Anónima
- [ ] Mapa de calor (heatmap) por categoría vs. cadena
- [ ] Alertas por Telegram cuando un precio baja
- [ ] Exportación de reportes a Excel/PDF
- [ ] Autenticación de usuario para el Dashboard
- [ ] Modo multi-local (varios puntos de venta)
