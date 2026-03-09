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

// Metadata dinámica (se carga vía /api/init)
let TARJETAS_DEF = [];
let SUPERMERCADOS_DEF = [];
let FIDELIDAD_DEF = {};

let selTarjetas  = new Set();
let selSupers    = new Set();
let selFidelidad = new Set();


// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', initApp);

async function initApp() {
  // Auth check (best-effort: don't block the rest of the UI)
  try {
    const me = await fetch('/auth/me', { credentials: 'same-origin' }).then(r => r.json());
    renderAuthHeader(me);
  } catch { /* ignore */ }

  try {
    const data = await apiFetch('/api/init');
    
    // 1. Cargar Metadata
    TARJETAS_DEF = data.metadata.tarjetas;
    FIDELIDAD_DEF = data.metadata.fidelidad;
    SUPERMERCADOS_DEF = data.cadenas.map(c => ({ id: c.cadena_id, label: c.nombre || c.cadena_id }));
    
    // 2. Cargar Wallet (Preferencias guardadas + todas las cadenas activas por defecto)
    selTarjetas = new Set(data.wallet.tarjetas);
    if (selTarjetas.size === 0) selTarjetas = new Set(TARJETAS_DEF.map(t => t.id));
    
    selFidelidad = new Set(data.wallet.programas_fidelidad);
    selSupers = new Set(SUPERMERCADOS_DEF.map(s => s.id));
    
    // 3. Renderizar UI Inicial
    renderWallet();
    renderStats(data.stats);
    renderCadenaFilter(data.cadenas);
    
    // 4. Cargar datos
    loadProducts();
    loadHarvesterStatus();
    
    // 5. Polls
    setInterval(loadStats, 30_000);
    setInterval(loadHarvesterStatus, 15_000);
    updateClock();
    setInterval(updateClock, 1000);
    
  } catch (e) {
    console.error('Init error:', e);
    showToast('Error de conexión con el servidor', true);
  }
}

function renderStats(data) {
  document.getElementById('stat-productos').textContent = data.total_productos?.toLocaleString('es-AR') ?? '—';
  document.getElementById('stat-reglas').textContent = data.total_reglas_descuento?.toLocaleString('es-AR') ?? '—';
  const ciclo = data.ultimo_ciclo;
  document.getElementById('stat-ciclo').textContent = ciclo?.estado ? `${ciclo.estado} (${formatDate(ciclo.iniciado)})` : 'Sin datos';
}

function renderCadenaFilter(cadenas) {
  const select = document.getElementById('cadena-filter');
  if (!select) return;
  select.innerHTML = '<option value="">Todas las cadenas</option>' +
    cadenas.map(c => `<option value="${escHtml(c.cadena_id)}">${escHtml(c.nombre || c.cadena_id)}</option>`).join('');
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
// Stats (Legacy, keep for interval)
// ---------------------------------------------------------------------------
async function loadStats() {
  try {
    const data = await apiFetch('/api/stats');
    renderStats(data);
  } catch { /* silencioso */ }
}

// ---------------------------------------------------------------------------
// Auth UI
// ---------------------------------------------------------------------------
function renderAuthHeader(me) {
  const el = document.getElementById('auth-status');
  if (!el) return;
  if (me?.authenticated) {
    el.innerHTML = `<span style="color:var(--muted);font-size:12px">${escHtml(me.email)}</span>
      <button class="cart-btn" onclick="doLogout()" style="margin-left:8px">Salir</button>`;
  } else {
    el.innerHTML = `<a href="/auth/login" style="font-size:13px;color:var(--accent)">Iniciar sesión</a>`;
  }
}

async function doLogout() {
  await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });
  window.location.reload();
}

// ---------------------------------------------------------------------------
// Wallet
// ---------------------------------------------------------------------------
function renderWallet() {
  document.getElementById('chips-tarjetas').innerHTML = TARJETAS_DEF.map(t =>
    `<div class="wallet-chip ${selTarjetas.has(t.id) ? 'on' : ''}" onclick="toggleTarjeta('${t.id}')">${t.label}</div>`
  ).join('');

  document.getElementById('chips-supermercados').innerHTML = SUPERMERCADOS_DEF.map(s =>   
    `<div class="wallet-chip ${selSupers.has(s.id) ? 'on' : ''}" onclick="toggleSuper('${s.id}')">${s.label}</div>`
  ).join('');

  // Fidelidad específica de cadenas seleccionadas + GLOBAL (La Nacion/365)
  const fidelChips = SUPERMERCADOS_DEF
    .filter(s => selSupers.has(s.id) && FIDELIDAD_DEF[s.id]?.length)
    .flatMap(s => FIDELIDAD_DEF[s.id])
    .concat(FIDELIDAD_DEF['GLOBAL'] || []);

  const fidelEl = document.getElementById('chips-fidelidad');
  if (fidelChips.length) {
    fidelEl.innerHTML = `<div class="wallet-group" style="margin-top:10px">
      <div class="wallet-group-label">Programas Especiales / Fidelidad</div>
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

  const cadenaCols = activeCadenas.map(id => {
    const c = item.cadenas.find(x => x.cadena_id === id);
    return `<td>${fmtPrice(c)}</td>`;
  }).join('');

  const unitPrice = mejor?.precio_por_unidad
    ? `<small class="price-unit">${fmtARS(mejor.precio_por_unidad)}/${mejor.unidad_medida}</small>`
    : '—';

  const cartItem = cart.find(c => c.ean === item.ean);
  const inCart = !!cartItem;
  const cartLabel = cartItem ? `&#x2713; (${cartItem.qty})` : '+';
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
          onclick="addToCart('${item.ean}')">${cartLabel}</button>
    </td>
  </tr>`;
}

function renderPagination(total) {
  const container = document.getElementById('pagination');
  if (totalPages <= 1) { container.innerHTML = ''; return; }

  let html = `<button onclick="goPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>â†</button>`;
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  for (let i = start; i <= end; i++) {
    html += `<button onclick="goPage(${i})" class="${i === currentPage ? 'active' : ''}">${i}</button>`;
  }
  html += `<button onclick="goPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>â†’</button>`;
  container.innerHTML = html;
}

function goPage(page) {
  if (page < 1 || page > totalPages) return;
  currentPage = page;
  loadProducts();
}

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
        ${c.reglas_aplicadas.length ? `<div class="reglas-list">â“˜ ${c.reglas_aplicadas.join(' Â· ')}</div>` : ''}
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

async function loadHarvesterStatus() {
  const el = document.getElementById('harvester-status-content');
  try {
    const log = await apiFetch('/clock/last-log');
    const cancelBtn = document.getElementById('cancel-btn');

    if (log.message) {
      el.innerHTML = '<span class="h-status-none">Sin ejecuciones registradas. Usá ⚡ para iniciar un ciclo.</span>';
      if (cancelBtn) cancelBtn.style.display = 'none';
      return;
    }

    if (cancelBtn) cancelBtn.style.display = log.status === 'running' ? 'inline-block' : 'none';

    const statusClass = `h-status-${log.status ?? 'none'}`;
    const statusLabel = {
      running: 'âŒ› En ejecución',
      completed: '✓ Completado',
      partial: '⚠ Parcial',
      failed: 'âœ– Fallido',
    }[log.status] ?? log.status ?? '—';

    const started = formatDate(log.started_at);
    const finished = log.finished_at ? formatDate(log.finished_at) : '—';

    const checkpointsHtml = Object.entries(log.checkpoints ?? {}).map(([cadena, state]) => {
      const cpClass = state === 'ok' ? 'cp-ok' : state === 'pending' ? 'cp-pending' : 'cp-error';
      return `<span class="checkpoint ${cpClass}">${cadena}: ${state}</span>`;
    }).join('');

    const errorHtml = log.error ? `<div class="h-error-msg">Error: ${escHtml(log.error)}</div>` : '';

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

async function triggerManual() {
  const status = document.getElementById('cycle-status');
  status.textContent = 'âŒ› Iniciando ciclo...';
  try {
    const data = await apiFetch('/clock/trigger', { method: 'POST' });
    status.textContent = data.status === 'started' ? '✓ Ciclo iniciado. Puede tardar varios minutos.' : `⚠ ${data.message}`;
    setTimeout(loadHarvesterStatus, 2000);
  } catch {
    status.textContent = 'âœ– Error al iniciar el ciclo.';
  }
}

async function cancelScraping() {
  const status = document.getElementById('cycle-status');
  status.textContent = 'âŒ› Cancelando...';
  try {
    const data = await apiFetch('/clock/cancel', { method: 'POST' });
    status.textContent = data.status === 'cancelling' ? '⚠ Cancelando — el ciclo se detendrá pronto.' : data.message;
    setTimeout(loadHarvesterStatus, 2000);
  } catch {
    status.textContent = 'âœ– Error al cancelar.';
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
  const existing = cart.find(c => c.ean === ean);
  if (existing) {
    existing.qty += 1;
    renderCartItems();
    renderCartCalc();
    updateCartBadge();
    _refreshRowButtons(ean, '&#x2713; (' + existing.qty + ')', 'btn btn-secondary');
    return;
  }
  const item = productCache.get(ean);
  if (!item) return;
  cart.push({ ean: item.ean, nombre: item.nombre, cadenas: item.cadenas, qty: 1 });
  renderCartItems();
  renderCartCalc();
  updateCartBadge();
  _refreshRowButtons(ean, '&#x2713; (1)', 'btn btn-secondary');
}

function changeQty(ean, delta) {
  const item = cart.find(c => c.ean === ean);
  if (!item) return;
  item.qty += delta;
  if (item.qty <= 0) { removeFromCart(ean); return; }
  renderCartItems();
  renderCartCalc();
  updateCartBadge();
  _refreshRowButtons(ean, '&#x2713; (' + item.qty + ')', 'btn btn-secondary');
}

function removeFromCart(ean) {
  cart = cart.filter(c => c.ean !== ean);
  renderCartItems();
  renderCartCalc();
  updateCartBadge();
  _refreshRowButtons(ean, '+', 'btn btn-primary');
}

function _refreshRowButtons(ean, text, className) {
  const rows = document.querySelectorAll('#products-tbody tr');
  rows.forEach(row => {
    const eanCell = row.querySelector('.ean');
    if (eanCell && eanCell.textContent === ean) {
      const btn = row.querySelectorAll('button')[1];
      if (btn) { btn.textContent = text; btn.className = className; }
    }
  });
}

function updateCartBadge() {
  document.getElementById('cart-count').textContent = cart.reduce((s, c) => s + c.qty, 0);
}

function renderCartItems() {
  const el = document.getElementById('cart-items-list');
  if (!cart.length) {
    el.innerHTML = '<div class="cart-empty">El carrito está vacío.<br>Agregá productos desde la tabla.</div>';
    return;
  }
  el.innerHTML = cart.map(item => {
    const prices = item.cadenas.map(c => `${c.cadena_id}: ${fmtARS(c.precio_neto)}`).join(' &middot; ');
    return `<div class="cart-item-row">
      <div style="flex:1;min-width:0">
        <div class="cart-item-name">${escHtml(item.nombre)}</div>
        <div class="cart-item-prices">${prices}</div>
      </div>
      <div style="display:flex;align-items:center;gap:5px;flex-shrink:0">
        <button class="btn btn-secondary" style="padding:2px 8px;font-size:13px;line-height:1" onclick="changeQty('${item.ean}',-1)">&#x2212;</button>
        <span style="min-width:22px;text-align:center;font-weight:600">${item.qty}</span>
        <button class="btn btn-secondary" style="padding:2px 8px;font-size:13px;line-height:1" onclick="changeQty('${item.ean}',1)">+</button>
        <button class="cart-remove" onclick="removeFromCart('${item.ean}')" title="Quitar">&#x2715;</button>
      </div>
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

  if (cartMode === 'single') resultEl.innerHTML = _calcSingle();
  else if (cartMode === 'split') resultEl.innerHTML = _calcSplit();
  else resultEl.innerHTML = _calcMax();
}

function _calcSingle() {
  const cadenas = [...new Set(cart.flatMap(item => item.cadenas.map(c => c.cadena_id)))];
  const results = cadenas.map(cadenaId => {
    let total = 0; const missing = [];
    cart.forEach(item => {
      const c = item.cadenas.find(x => x.cadena_id === cadenaId);
      if (c) total += c.precio_neto * (item.qty || 1);
      else missing.push(item.nombre);
    });
    return { cadenaId, total, missing };
  }).sort((a, b) => (a.missing.length - b.missing.length) || (a.total - b.total));

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
  const cadenas = [...new Set(cart.flatMap(item => item.cadenas.map(c => c.cadena_id)))];
  if (cadenas.length <= 2) return _calcMax();
  let bestTotal = Infinity, bestPair = null, bestBreakdown = null;
  for (let i = 0; i < cadenas.length; i++) {
    for (let j = i + 1; j < cadenas.length; j++) {
      const pair = [cadenas[i], cadenas[j]];
      let total = 0;
      const breakdown = cart.map(item => {
        const opts = item.cadenas.filter(c => pair.includes(c.cadena_id));
        if (!opts.length) return null;
        const best = opts.reduce((a, b) => a.precio_neto <= b.precio_neto ? a : b);
        total += best.precio_neto * (item.qty || 1);
        return { nombre: item.nombre, cadenaId: best.cadena_id, precio: best.precio_neto * (item.qty || 1), qty: item.qty || 1 };
      });
      if (breakdown.some(b => b === null)) continue;
      if (total < bestTotal) { bestTotal = total; bestPair = pair; bestBreakdown = breakdown; }
    }
  }
  return bestBreakdown ? _renderMaxBreakdown(bestBreakdown, bestTotal, `Mejor combinación de 2: ${bestPair.join(' + ')}`) : _calcMax();
}

function _calcMax() {
  const breakdown = cart.map(item => {
    if (!item.cadenas.length) return null;
    const best = item.cadenas.reduce((a, b) => a.precio_neto <= b.precio_neto ? a : b);
    return { nombre: item.nombre, cadenaId: best.cadena_id, precio: best.precio_neto * (item.qty || 1), qty: item.qty || 1 };
  }).filter(Boolean);
  const total = breakdown.reduce((s, b) => s + b.precio, 0);
  return _renderMaxBreakdown(breakdown, total, 'Ahorro m&aacute;ximo &mdash; compr&aacute;s cada producto donde es m&aacute;s barato');
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
      <div class="store-block-items">${data.items.map(i => escHtml(i.nombre) + (i.qty > 1 ? ' &times;' + i.qty : '')).join(' &middot; ')}</div>
    </div>`).join('');
  return `<div class="cart-result-title">${escHtml(subtitle)}</div>
    ${blocks}
    <div class="cart-grand-total"><span>Total</span><span>${fmtARS(total)}</span></div>`; 
}

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------
async function apiFetch(url, options = {}, _isRetry = false) {
  const res = await fetch(API + url, { credentials: 'same-origin', ...options });
  if (res.status === 401 && !_isRetry) {
    const r = await fetch('/auth/refresh', { method: 'POST', credentials: 'same-origin' });
    if (r.ok) return apiFetch(url, options, true);
    window.location.href = '/auth/login';
    throw new Error('Sesión expirada');
  }
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
  let t = document.getElementById('toast') || (function() {
    const el = document.createElement('div'); el.id = 'toast';
    el.style.cssText = 'position:fixed;bottom:24px;right:24px;padding:10px 18px;border-radius:8px;font-size:13px;z-index:200;transition:opacity .3s';
    document.body.appendChild(el); return el;
  })();
  t.textContent = msg;
  t.style.background = error ? '#7f1d1d' : '#14532d';
  t.style.color = error ? '#fca5a5' : '#86efac';
  t.style.opacity = '1';
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { t.style.opacity = '0'; }, 3000);
}
function updateClock() {
  const el = document.getElementById('ar-clock');
  if (!el) return;
  el.textContent = new Date().toLocaleString('es-AR', {
    timeZone: 'America/Argentina/Buenos_Aires',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  }) + ' AR';
}

