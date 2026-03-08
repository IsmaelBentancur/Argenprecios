// Argenprecios Dashboard — Vanilla JS
const API = '';  // mismo origen

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------
let currentPage = 1;
let totalPages = 1;
let searchTimeout = null;
let activeCadenas = []; // cadena_ids presentes en los resultados actuales

// Cart
let cart = [];           // [{ean, nombre, cadenas: [{cadena_id, precio_neto, ...}]}]
let cartMode = 'single'; // 'single' | 'split' | 'max'
const productCache = new Map(); // ean -> item (for quick add-to-cart)
// Wallet — datos predefinidos
const TARJETAS_DEF = [
  { id: 'Visa',         label: 'Visa Crédito' },
  { id: 'Mastercard',   label: 'Mastercard' },
  { id: 'Débito',       label: 'Débito' },
  { id: 'MODO',         label: 'MODO' },
  { id: 'Naranja',      label: 'Naranja X' },
  { id: 'Mercado Pago', label: 'Mercado Pago' },
  { id: 'ANSES',        label: 'ANSES' },
  { id: 'Jubilados',    label: 'Jubilados' },
];
const SUPERMERCADOS_DEF = [
  { id: 'COTO',      label: 'Coto' },
  { id: 'CARREFOUR', label: 'Carrefour' },
];
const FIDELIDAD_DEF = {
  COTO:      [{ id: 'Comunidad Coto', label: 'Comunidad Coto' }],
  CARREFOUR: [{ id: 'Mi Carrefour',   label: 'Mi Carrefour' }],
};

let selTarjetas  = new Set(TARJETAS_DEF.map(t => t.id));
let selSupers    = new Set(SUPERMERCADOS_DEF.map(s => s.id));
let selFidelidad = new Set([].concat.apply([], Object.values(FIDELIDAD_DEF)).map(f => f.id));


// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  renderWallet();
  loadStats();
  loadWallet();
  loadCadenaFilter();
  loadProducts();
  loadHarvesterStatus();
  setInterval(loadStats, 30_000);
  setInterval(loadHarvesterStatus, 15_000);
});

async function loadCadenaFilter() {
  try {
    const cadenas = await apiFetch('/api/cadenas');
    const select = document.getElementById('cadena-filter');
    if (!select || !cadenas?.length) return;
    select.innerHTML = '<option value="">Todas las cadenas</option>' +
      cadenas.map(c => `<option value="${escHtml(c.cadena_id)}">${escHtml(c.nombre || c.cadena_id)}</option>`).join('');
  } catch { /* mantiene el select estático como fallback */ }
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById(`tab-${name}`).classList.add('active');
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------
async function loadStats() {
  try {
    const data = await apiFetch('/api/stats');
    document.getElementById('stat-productos').textContent =
      data.total_productos?.toLocaleString('es-AR') ?? '—';
    document.getElementById('stat-reglas').textContent =
      data.total_reglas_descuento?.toLocaleString('es-AR') ?? '—';
    const ciclo = data.ultimo_ciclo;
    document.getElementById('stat-ciclo').textContent =
      ciclo?.estado ? `${ciclo.estado} (${formatDate(ciclo.iniciado)})` : 'Sin datos';
  } catch { /* silencioso */ }
}

// ---------------------------------------------------------------------------
// Wallet
// ---------------------------------------------------------------------------
async function loadWallet() {
  try {
    const data = await apiFetch('/api/wallet');
    if (data.tarjetas?.length)            selTarjetas  = new Set(data.tarjetas);
    if (data.programas_fidelidad?.length) selFidelidad = new Set(data.programas_fidelidad);
  } catch { /* silencioso */ }
  renderWallet();
}

function renderWallet() {
  document.getElementById('chips-tarjetas').innerHTML = TARJETAS_DEF.map(t =>
    `<div class="wallet-chip ${selTarjetas.has(t.id) ? 'on' : ''}" onclick="toggleTarjeta('${t.id}')">${t.label}</div>`
  ).join('');

  document.getElementById('chips-supermercados').innerHTML = SUPERMERCADOS_DEF.map(s =>
    `<div class="wallet-chip ${selSupers.has(s.id) ? 'on' : ''}" onclick="toggleSuper('${s.id}')">${s.label}</div>`
  ).join('');

  const fidelChips = SUPERMERCADOS_DEF
    .filter(s => selSupers.has(s.id) && FIDELIDAD_DEF[s.id]?.length)
    .flatMap(s => FIDELIDAD_DEF[s.id]);
  const fidelEl = document.getElementById('chips-fidelidad');
  if (fidelChips.length) {
    fidelEl.innerHTML = `<div class="wallet-group" style="margin-top:10px">
      <div class="wallet-group-label">Fidelidad</div>
      <div class="wallet-chips">${fidelChips.map(f =>
        `<div class="wallet-chip ${selFidelidad.has(f.id) ? 'on' : ''}" onclick="toggleFidelidad('${f.id}')">${f.label}</div>`
      ).join('')}</div>
    </div>`;
  } else {
    fidelEl.innerHTML = '';
  }
}

function toggleTarjeta(id) {
  selTarjetas.has(id) ? selTarjetas.delete(id) : selTarjetas.add(id);
  renderWallet();
}

function toggleSuper(id) {
  if (selSupers.has(id)) {
    selSupers.delete(id);
    FIDELIDAD_DEF[id]?.forEach(f => selFidelidad.delete(f.id));
  } else {
    selSupers.add(id);
    FIDELIDAD_DEF[id]?.forEach(f => selFidelidad.add(f.id));
  }
  renderWallet();
}

function toggleFidelidad(id) {
  selFidelidad.has(id) ? selFidelidad.delete(id) : selFidelidad.add(id);
  renderWallet();
}

async function saveWallet() {
  try {
    await apiFetch('/api/wallet', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tarjetas: [...selTarjetas], programas_fidelidad: [...selFidelidad] }),
    });
    showToast('✓ Billetera guardada. Recargando precios...');
    loadProducts();
  } catch (e) {
    showToast('Error al guardar billetera', true);
  }
}

// ---------------------------------------------------------------------------
// Productos
// ---------------------------------------------------------------------------
function debounceSearch() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => { currentPage = 1; loadProducts(); }, 400);
}

async function loadProducts() {
  const q = document.getElementById('search-input').value;
  const cadena = document.getElementById('cadena-filter').value;
  const tbody = document.getElementById('products-tbody');
  tbody.innerHTML = '<tr><td colspan="7" class="no-data">Cargando...</td></tr>';

  try {
    const params = new URLSearchParams({ q, cadena, page: currentPage, limit: 20 });
    const data = await apiFetch(`/api/productos?${params}`);

    if (!data.items?.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="no-data">No se encontraron productos. Ejecutá el scraping primero.</td></tr>';
      renderPagination(0);
      return;
    }

    totalPages = Math.ceil(data.total / data.limit);
    data.items.forEach(item => productCache.set(item.ean, item));

    // Detectar cadenas presentes en los resultados y actualizar encabezados
    const cadenesEnResultados = [...new Set(data.items.flatMap(i => i.cadenas.map(c => c.cadena_id)))].sort();
    if (cadenesEnResultados.join(',') !== activeCadenas.join(',')) {
      activeCadenas = cadenesEnResultados;
      renderTableHeaders();
    }

    tbody.innerHTML = data.items.map(renderProductRow).join('');
    renderPagination(data.total);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="no-data">Error al cargar datos: ${e.message}</td></tr>`;
  }
}

function renderTableHeaders() {
  const thead = document.getElementById('products-thead');
  if (!thead) return;
  const cadenaCols = activeCadenas.map(id => `<th>${id}</th>`).join('');
  thead.innerHTML = `<tr>
    <th>EAN</th>
    <th>Producto</th>
    ${cadenaCols}
    <th>Mejor precio</th>
    <th>Precio/unidad</th>
    <th></th>
  </tr>`;
}

function renderProductRow(item) {
  const mejor = item.cadenas.find(c => c.cadena_id === item.mejor_cadena);

  const fmtPrice = (c) => {
    if (!c) return '<span style="color:var(--muted)">—</span>';
    const isBest = c.cadena_id === item.mejor_cadena;
    const hasDiscount = c.precio_lista > c.precio_neto;
    const original = hasDiscount
      ? `<small style="color:var(--muted);text-decoration:line-through;display:block;font-weight:400">${fmtARS(c.precio_lista)}</small>`
      : '';
    const badge = c.ahorro_pct > 0 ? `<span class="savings">-${c.ahorro_pct}%</span>` : '';
    return `<span class="price-cell ${isBest ? 'price-best' : ''}">
        ${fmtARS(c.precio_neto)}${badge}
        ${original}
       </span>`;
  };

  // Columnas dinámicas por cadena
  const cadenaCols = activeCadenas.map(id => {
    const c = item.cadenas.find(x => x.cadena_id === id);
    return `<td>${fmtPrice(c)}</td>`;
  }).join('');

  const unitPrice = mejor?.precio_por_unidad
    ? `<small class="price-unit">${fmtARS(mejor.precio_por_unidad)}/${mejor.unidad_medida}</small>`
    : '—';

  const inCart = cart.some(c => c.ean === item.ean);
  return `<tr>
    <td class="ean">${item.ean}</td>
    <td class="nombre">${escHtml(item.nombre)}</td>
    ${cadenaCols}
    <td>
      ${fmtPrice(mejor)}
      <span class="badge-cadena badge-${item.mejor_cadena}">${item.mejor_cadena}</span>
    </td>
    <td>${unitPrice}</td>
    <td style="white-space:nowrap">
      <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px"
          onclick="openComparativa('${item.ean}')">Ver</button>
      <button class="btn ${inCart ? 'btn-secondary' : 'btn-primary'}" style="padding:4px 10px;font-size:12px;margin-left:4px"
          onclick="addToCart('${item.ean}')">${inCart ? '✓' : '+'}</button>
    </td>
  </tr>`;
}

// ---------------------------------------------------------------------------
// Paginación
// ---------------------------------------------------------------------------
function renderPagination(total) {
  const container = document.getElementById('pagination');
  if (totalPages <= 1) { container.innerHTML = ''; return; }

  let html = `<button onclick="goPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>←</button>`;
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  for (let i = start; i <= end; i++) {
    html += `<button onclick="goPage(${i})" class="${i === currentPage ? 'active' : ''}">${i}</button>`;
  }
  html += `<button onclick="goPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>→</button>`;
  container.innerHTML = html;
}

function goPage(page) {
  if (page < 1 || page > totalPages) return;
  currentPage = page;
  loadProducts();
}

// ---------------------------------------------------------------------------
// Modal de comparativa
// ---------------------------------------------------------------------------
async function openComparativa(ean) {
  document.getElementById('modal').classList.add('open');
  document.getElementById('modal-title').textContent = `Comparando EAN: ${ean}`;
  document.getElementById('modal-body').innerHTML = '<p style="color:var(--muted)">Cargando...</p>';

  try {
    const data = await apiFetch(`/api/comparar/${ean}`);
    document.getElementById('modal-title').textContent = escHtml(data.nombre);

    const html = data.cadenas.map(c => `
      <div class="cadena-card ${c.cadena_id === data.mejor_cadena ? 'best' : ''}">
        <div class="cadena-header">
          <span class="badge-cadena badge-${c.cadena_id}">${c.cadena_id}</span>
          ${c.cadena_id === data.mejor_cadena ? '<span class="badge-cadena badge-best">✓ Mejor precio</span>' : ''}
        </div>
        <div class="cadena-prices">
          <div>
            <div class="price-label">Precio actual</div>
            <div class="price-value price-best">${fmtARS(c.precio_neto)}</div>
            ${c.precio_lista > c.precio_neto ? `<div class="price-label" style="text-decoration:line-through">${fmtARS(c.precio_lista)}</div>` : ''}
          </div>
          <div><div class="price-label">Ahorro</div><div class="price-value" style="color:var(--yellow)">${c.ahorro_pct}%</div></div>
        </div>
        ${c.precio_por_unidad ? `<div class="price-label" style="margin-top:6px">${fmtARS(c.precio_por_unidad)}/${c.unidad_medida}</div>` : ''}
        ${c.reglas_aplicadas.length ? `<div class="reglas-list">🏷 ${c.reglas_aplicadas.join(' · ')}</div>` : ''}
      </div>
    `).join('');
    document.getElementById('modal-body').innerHTML = html;
  } catch (e) {
    document.getElementById('modal-body').innerHTML = `<p style="color:var(--red)">Error: ${e.message}</p>`;
  }
}

function closeModal(event) {
  if (event.target === document.getElementById('modal')) {
    document.getElementById('modal').classList.remove('open');
  }
}

// ---------------------------------------------------------------------------
// Harvester status panel
// ---------------------------------------------------------------------------
async function loadHarvesterStatus() {
  const el = document.getElementById('harvester-status-content');
  try {
    const log = await apiFetch('/clock/last-log');

    const cancelBtn = document.getElementById('cancel-btn');

    if (log.message) {
      // No runs yet
      el.innerHTML = '<span class="h-status-none">Sin ejecuciones registradas. Usá ⚡ para iniciar un ciclo.</span>';
      if (cancelBtn) cancelBtn.style.display = 'none';
      return;
    }

    // Show cancel button only when a cycle is actively running
    if (cancelBtn) cancelBtn.style.display = log.status === 'running' ? 'inline-block' : 'none';

    const statusClass = `h-status-${log.status ?? 'none'}`;
    const statusLabel = {
      running: '⏳ En ejecución',
      completed: '✓ Completado',
      partial: '⚠ Parcial',
      failed: '✗ Fallido',
    }[log.status] ?? log.status ?? '—';

    const started = formatDate(log.started_at);
    const finished = log.finished_at ? formatDate(log.finished_at) : '—';

    const checkpointsHtml = Object.entries(log.checkpoints ?? {}).map(([cadena, state]) => {
      const cpClass = state === 'ok' ? 'cp-ok'
        : state === 'pending' ? 'cp-pending'
        : 'cp-error';
      return `<span class="checkpoint ${cpClass}">${cadena}: ${state}</span>`;
    }).join('');

    const errorHtml = log.error
      ? `<div class="h-error-msg">Error: ${escHtml(log.error)}</div>`
      : '';

    el.innerHTML = `
      <div class="harvester-row">
        <div class="harvester-field">
          <span class="hf-label">Estado</span>
          <span class="hf-value ${statusClass}">${statusLabel}</span>
        </div>
        <div class="harvester-field">
          <span class="hf-label">Iniciado</span>
          <span class="hf-value">${started}</span>
        </div>
        <div class="harvester-field">
          <span class="hf-label">Finalizado</span>
          <span class="hf-value">${finished}</span>
        </div>
        <div class="harvester-field">
          <span class="hf-label">Cadenas</span>
          <div class="checkpoint-list">${checkpointsHtml || '<span style="color:var(--muted)">—</span>'}</div>
        </div>
      </div>
      ${errorHtml}`;
  } catch {
    el.innerHTML = '<span style="color:var(--muted);font-size:12px;">No disponible</span>';
  }
}

// ---------------------------------------------------------------------------
// Trigger manual
// ---------------------------------------------------------------------------
async function triggerManual() {
  const status = document.getElementById('cycle-status');
  status.textContent = '⏳ Iniciando ciclo...';
  try {
    const data = await apiFetch('/clock/trigger', { method: 'POST' });
    status.textContent = data.status === 'started'
      ? '✓ Ciclo iniciado. Puede tardar varios minutos.'
      : `⚠ ${data.message}`;
    setTimeout(loadHarvesterStatus, 2000);
  } catch {
    status.textContent = '✗ Error al iniciar el ciclo.';
  }
}

async function cancelScraping() {
  const status = document.getElementById('cycle-status');
  status.textContent = '⏳ Cancelando...';
  try {
    const data = await apiFetch('/clock/cancel', { method: 'POST' });
    status.textContent = data.status === 'cancelling'
      ? '⚠ Cancelando — el ciclo se detendrá pronto.'
      : data.message;
    setTimeout(loadHarvesterStatus, 2000);
  } catch {
    status.textContent = '✗ Error al cancelar.';
  }
}

// ---------------------------------------------------------------------------
// Carrito
// ---------------------------------------------------------------------------

function toggleCart() {
  const panel = document.getElementById('cart-panel');
  const overlay = document.getElementById('cart-overlay');
  panel.classList.toggle('open');
  overlay.classList.toggle('open');
}

function addToCart(ean) {
  if (cart.some(c => c.ean === ean)) {
    removeFromCart(ean);
    return;
  }
  const item = productCache.get(ean);
  if (!item) return;
  cart.push({ ean: item.ean, nombre: item.nombre, cadenas: item.cadenas });
  renderCartItems();
  renderCartCalc();
  updateCartBadge();
  // Refresh row button state
  const rows = document.querySelectorAll('#products-tbody tr');
  rows.forEach(row => {
    const eanCell = row.querySelector('.ean');
    if (eanCell && eanCell.textContent === ean) {
      const btn = row.querySelectorAll('button')[1];
      if (btn) { btn.textContent = '✓'; btn.className = 'btn btn-secondary'; btn.style.cssText = 'padding:4px 10px;font-size:12px;margin-left:4px'; }
    }
  });
}

function removeFromCart(ean) {
  cart = cart.filter(c => c.ean !== ean);
  renderCartItems();
  renderCartCalc();
  updateCartBadge();
  // Refresh row button state
  const rows = document.querySelectorAll('#products-tbody tr');
  rows.forEach(row => {
    const eanCell = row.querySelector('.ean');
    if (eanCell && eanCell.textContent === ean) {
      const btn = row.querySelectorAll('button')[1];
      if (btn) { btn.textContent = '+'; btn.className = 'btn btn-primary'; btn.style.cssText = 'padding:4px 10px;font-size:12px;margin-left:4px'; }
    }
  });
}

function updateCartBadge() {
  document.getElementById('cart-count').textContent = cart.length;
}

function renderCartItems() {
  const el = document.getElementById('cart-items-list');
  if (!cart.length) {
    el.innerHTML = '<div class="cart-empty">El carrito está vacío.<br>Agregá productos desde la tabla.</div>';
    return;
  }
  el.innerHTML = cart.map(item => {
    const prices = item.cadenas.map(c =>
      `${c.cadena_id}: ${fmtARS(c.precio_neto)}`
    ).join(' · ');
    return `<div class="cart-item-row">
      <div>
        <div class="cart-item-name">${escHtml(item.nombre)}</div>
        <div class="cart-item-prices">${prices}</div>
      </div>
      <button class="cart-remove" onclick="removeFromCart('${item.ean}')" title="Quitar">✕</button>
    </div>`;
  }).join('');
}

function setCartMode(mode) {
  cartMode = mode;
  document.querySelectorAll('.cart-mode-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`mode-btn-${mode}`).classList.add('active');
  renderCartCalc();
}

function renderCartCalc() {
  const calcEl = document.getElementById('cart-calc');
  const resultEl = document.getElementById('cart-result');
  if (!cart.length) { calcEl.style.display = 'none'; return; }
  calcEl.style.display = 'block';

  if (cartMode === 'single') {
    resultEl.innerHTML = _calcSingle();
  } else if (cartMode === 'split') {
    resultEl.innerHTML = _calcSplit();
  } else {
    resultEl.innerHTML = _calcMax();
  }
}

function _allCadenas() {
  const set = new Set();
  cart.forEach(item => item.cadenas.forEach(c => set.add(c.cadena_id)));
  return [...set];
}

function _calcSingle() {
  const cadenas = _allCadenas();
  const results = cadenas.map(cadenaId => {
    let total = 0; const missing = [];
    cart.forEach(item => {
      const c = item.cadenas.find(x => x.cadena_id === cadenaId);
      if (c) total += c.precio_neto;
      else missing.push(item.nombre);
    });
    return { cadenaId, total, missing };
  }).sort((a, b) => {
    if (a.missing.length !== b.missing.length) return a.missing.length - b.missing.length;
    return a.total - b.total;
  });

  const best = results[0];
  return '<div class="cart-result-title">Total por supermercado</div>' +
    results.map((r, i) => `
      <div class="store-block ${i === 0 ? 'best' : ''}">
        <div class="store-block-header">
          <span class="store-block-name">${r.cadenaId}${i === 0 ? ' ✓' : ''}</span>
          <span class="store-block-total">${r.missing.length ? '?' : fmtARS(r.total)}</span>
        </div>
        ${r.missing.length ? `<div class="store-block-items" style="color:var(--red)">Sin stock: ${r.missing.map(escHtml).join(', ')}</div>` : ''}
      </div>`).join('') +
    (best.missing.length === 0 ? `<div style="font-size:11px;color:var(--muted);margin-top:4px">Comprás todo en ${best.cadenaId}</div>` : '');
}

function _calcSplit() {
  // With 2 stores: same as max savings but show per-store breakdown
  // With N stores: find best pair of stores, assign each product to cheaper of the 2
  const cadenas = _allCadenas();
  if (cadenas.length <= 2) return _calcMax();

  // Try all pairs
  let bestTotal = Infinity, bestPair = null, bestBreakdown = null;
  for (let i = 0; i < cadenas.length; i++) {
    for (let j = i + 1; j < cadenas.length; j++) {
      const pair = [cadenas[i], cadenas[j]];
      let total = 0;
      const breakdown = cart.map(item => {
        const opts = item.cadenas.filter(c => pair.includes(c.cadena_id));
        if (!opts.length) return null;
        const best = opts.reduce((a, b) => a.precio_neto <= b.precio_neto ? a : b);
        total += best.precio_neto;
        return { nombre: item.nombre, cadenaId: best.cadena_id, precio: best.precio_neto };
      });
      if (breakdown.some(b => b === null)) continue;
      if (total < bestTotal) { bestTotal = total; bestPair = pair; bestBreakdown = breakdown; }
    }
  }
  if (!bestBreakdown) return _calcMax();
  return _renderMaxBreakdown(bestBreakdown, bestTotal, `Mejor combinación de 2: ${bestPair.join(' + ')}`);
}

function _calcMax() {
  const breakdown = cart.map(item => {
    if (!item.cadenas.length) return null;
    const best = item.cadenas.reduce((a, b) => a.precio_neto <= b.precio_neto ? a : b);
    return { nombre: item.nombre, cadenaId: best.cadena_id, precio: best.precio_neto };
  }).filter(Boolean);
  const total = breakdown.reduce((s, b) => s + b.precio, 0);
  return _renderMaxBreakdown(breakdown, total, 'Ahorro máximo — comprás cada producto donde es más barato');
}

function _renderMaxBreakdown(breakdown, total, subtitle) {
  const byCadena = {};
  breakdown.forEach(b => {
    if (!byCadena[b.cadenaId]) byCadena[b.cadenaId] = { items: [], total: 0 };
    byCadena[b.cadenaId].items.push(b);
    byCadena[b.cadenaId].total += b.precio;
  });
  const blocks = Object.entries(byCadena).map(([cid, data]) => `
    <div class="store-block best">
      <div class="store-block-header">
        <span class="store-block-name">${cid}</span>
        <span class="store-block-total">${fmtARS(data.total)}</span>
      </div>
      <div class="store-block-items">${data.items.map(i => escHtml(i.nombre)).join(' · ')}</div>
    </div>`).join('');
  return `<div class="cart-result-title">${escHtml(subtitle)}</div>
    ${blocks}
    <div class="cart-grand-total"><span>Total</span><span>${fmtARS(total)}</span></div>`;
}

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------
async function apiFetch(url, options = {}) {
  const res = await fetch(API + url, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.json();
}

function fmtARS(n) {
  if (n == null) return '—';
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 2 }).format(n);
}

function formatDate(str) {
  if (!str) return '—';
  try { return new Date(str).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }); }
  catch { return str; }
}

function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}


let toastTimeout;
function showToast(msg, error = false) {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    t.style.cssText = 'position:fixed;bottom:24px;right:24px;padding:10px 18px;border-radius:8px;font-size:13px;z-index:200;transition:opacity .3s';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.background = error ? '#7f1d1d' : '#14532d';
  t.style.color = error ? '#fca5a5' : '#86efac';
  t.style.opacity = '1';
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { t.style.opacity = '0'; }, 3000);
}

// Render wallet chips immediately (script is at bottom of body, DOM already ready)
renderWallet();
