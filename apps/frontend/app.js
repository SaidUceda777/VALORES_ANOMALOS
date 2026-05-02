/**
 * app.js — Lógica del frontend de detección de outliers
 * Proyecto: Detección de variaciones en valor unitario — SUNAT
 * Autor: Said Leonardo Uceda Paredes · UNI FIIS · 2026
 */

const API_URL = 'http://localhost:8000';

/** @type {Array<Object>} Últimos outliers recibidos para exportar */
let ultimo_resultado = [];

// ── Referencias al DOM ─────────────────────────────────────────────────────
const form            = document.getElementById('form-analisis');
const btn_analizar    = document.getElementById('btn-analizar');
const btn_limpiar     = document.getElementById('btn-limpiar');
const btn_exportar    = document.getElementById('btn-exportar');
const loader          = document.getElementById('loader');
const mensaje_error   = document.getElementById('mensaje-error');
const seccion_resumen = document.getElementById('seccion-resumen');
const seccion_tabla   = document.getElementById('seccion-tabla');

// ── Estadísticas ───────────────────────────────────────────────────────────
const stat_total    = document.getElementById('stat-total');
const stat_outliers = document.getElementById('stat-outliers');
const stat_pct      = document.getElementById('stat-pct');
const stat_partidas = document.getElementById('stat-partidas');
const ind_grid      = document.getElementById('indicadores-grid');
const tabla_body    = document.getElementById('tabla-body');
const tabla_nota    = document.getElementById('tabla-nota');

/**
 * Muestra u oculta el loader y deshabilita el botón de análisis.
 * @param {boolean} activo
 */
const set_cargando = (activo) => {
  loader.classList.toggle('oculto', !activo);
  btn_analizar.disabled = activo;
};

/**
 * Muestra un mensaje de error en pantalla.
 * @param {string} texto - Descripción del error.
 */
const mostrar_error = (texto) => {
  mensaje_error.textContent = texto;
  mensaje_error.classList.remove('oculto');
};

/** Limpia todos los resultados y mensajes de la pantalla. */
const limpiar_resultados = () => {
  mensaje_error.classList.add('oculto');
  seccion_resumen.classList.add('oculto');
  seccion_tabla.classList.add('oculto');
  tabla_body.innerHTML = '';
  ind_grid.innerHTML   = '';
  ultimo_resultado     = [];
};

/**
 * Formatea un número con separador de miles y decimales.
 * @param {number} valor
 * @param {number} decimales
 * @returns {string}
 */
const fmt_numero = (valor, decimales = 0) => {
  try {
    return Number(valor).toLocaleString('es-PE', {
      minimumFractionDigits: decimales,
      maximumFractionDigits: decimales,
    });
  } catch {
    return String(valor);
  }
};

/**
 * Renderiza las tarjetas de indicadores (IND_IQR, IND_ZSCORE, etc.).
 * @param {Object} indicadores - { nombre: conteo }
 */
const renderizar_indicadores = (indicadores) => {
  ind_grid.innerHTML = '';
  const etiquetas = {
    IND_IQR        : 'IQR',
    IND_ZSCORE     : 'Z-Score',
    IND_ZSCORE_ROB : 'Z-Score Rob.',
    IND_IFOREST    : 'Isolation Forest',
    IND_LOF        : 'LOF',
    IND_DBSCAN     : 'DBSCAN',
    IND_HBOS       : 'HBOS',
  };
  Object.entries(indicadores).forEach(([clave, conteo]) => {
    const chip = document.createElement('div');
    chip.className = 'ind-chip';
    chip.innerHTML = `
      <span class="ind-nombre">${etiquetas[clave] ?? clave}</span>
      <span class="ind-conteo">${fmt_numero(conteo)}</span>
    `;
    ind_grid.appendChild(chip);
  });
};

/**
 * Renderiza la tabla de outliers con sus indicadores individuales.
 * @param {Array<Object>} outliers - Lista de registros con ES_OUTLIER = 1.
 */
const renderizar_tabla = (outliers) => {
  tabla_body.innerHTML = '';
  const MAX_FILAS = 500;
  const filas     = outliers.slice(0, MAX_FILAS);

  const campos_ind = [
    'IND_IQR', 'IND_ZSCORE', 'IND_ZSCORE_ROB',
    'IND_IFOREST', 'IND_LOF', 'IND_DBSCAN', 'IND_HBOS',
  ];

  filas.forEach((fila, idx) => {
    const votos = campos_ind.reduce((s, k) => s + (Number(fila[k]) || 0), 0);
    const tr    = document.createElement('tr');

    const celdas_ind = campos_ind
      .map(k => {
        const val = Number(fila[k]) || 0;
        return `<td class="${val ? 'ind-si' : 'ind-no'}">${val ? '✓' : '–'}</td>`;
      })
      .join('');

    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td title="${fila['NUM_SPN_R'] ?? ''}">${(fila['NUM_SPN_R'] ?? '').slice(0, 40)}</td>
      <td>${fila['ANIO_C'] ?? '—'}</td>
      <td>${fmt_numero(fila['MTO_VALOR_UNTARIO_V'], 4)}</td>
      ${celdas_ind}
      <td><span class="votos-chip">${votos}/7</span></td>
    `;
    tabla_body.appendChild(tr);
  });

  tabla_nota.textContent = outliers.length > MAX_FILAS
    ? `Mostrando ${MAX_FILAS} de ${fmt_numero(outliers.length)} registros. Exportar CSV para ver todos.`
    : `${fmt_numero(outliers.length)} registro(s) con ES_OUTLIER = 1.`;
};

/**
 * Descarga los outliers actuales como archivo CSV.
 */
const exportar_csv = () => {
  if (!ultimo_resultado.length) return;

  const columnas = Object.keys(ultimo_resultado[0]);
  const filas    = ultimo_resultado.map(r =>
    columnas.map(c => JSON.stringify(r[c] ?? '')).join(',')
  );
  const contenido = [columnas.join(','), ...filas].join('\n');
  const blob       = new Blob([contenido], { type: 'text/csv;charset=utf-8;' });
  const url        = URL.createObjectURL(blob);

  const enlace     = document.createElement('a');
  enlace.href      = url;
  enlace.download  = `outliers_${Date.now()}.csv`;
  document.body.appendChild(enlace);
  enlace.click();
  document.body.removeChild(enlace);
  URL.revokeObjectURL(url);
};

/**
 * Llama al endpoint POST /analizar de la API FastAPI y renderiza los resultados.
 * @param {string} cod_analisis
 * @param {string} fec_ini
 * @param {string} fec_fin
 */
const ejecutar_analisis = async (cod_analisis, fec_ini, fec_fin) => {
  limpiar_resultados();
  set_cargando(true);

  try {
    const respuesta = await fetch(`${API_URL}/analizar`, {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ cod_analisis, fec_ini, fec_fin }),
    });

    if (!respuesta.ok) {
      const error = await respuesta.json().catch(() => ({ detail: respuesta.statusText }));
      throw new Error(error.detail ?? `Error ${respuesta.status}`);
    }

    const datos = await respuesta.json();

    // ── Estadísticas resumen ───────────────────────────────────────────
    stat_total.textContent    = fmt_numero(datos.total_registros);
    stat_outliers.textContent = fmt_numero(datos.total_outliers);
    stat_pct.textContent      = `${Number(datos.pct_outlier).toFixed(2)} %`;

    const partidas_unicas = new Set(
      (datos.outliers ?? []).map(o => o['NUM_SPN_R'])
    ).size;
    stat_partidas.textContent = fmt_numero(partidas_unicas);

    renderizar_indicadores(datos.indicadores ?? {});
    seccion_resumen.classList.remove('oculto');

    // ── Tabla de outliers ──────────────────────────────────────────────
    ultimo_resultado = datos.outliers ?? [];
    if (ultimo_resultado.length) {
      renderizar_tabla(ultimo_resultado);
      seccion_tabla.classList.remove('oculto');
    }

  } catch (exc) {
    mostrar_error(
      `Error al conectar con la API (${API_URL}).\n` +
      `Detalle: ${exc.message}\n\n` +
      `Verificar que el servidor FastAPI está corriendo:\n` +
      `  uvicorn main:app --host 0.0.0.0 --port 8000`
    );
  } finally {
    set_cargando(false);
  }
};

// ── Eventos ────────────────────────────────────────────────────────────────
form.addEventListener('submit', (evento) => {
  evento.preventDefault();
  const cod = document.getElementById('cod_analisis').value.trim().toUpperCase();
  const ini = document.getElementById('fec_ini').value;
  const fin = document.getElementById('fec_fin').value;

  if (!cod || !ini || !fin) {
    mostrar_error('Completar todos los campos antes de ejecutar.');
    return;
  }
  if (ini > fin) {
    mostrar_error('La fecha de inicio no puede ser posterior a la fecha fin.');
    return;
  }

  ejecutar_analisis(cod, ini, fin);
});

btn_limpiar.addEventListener('click', limpiar_resultados);
btn_exportar.addEventListener('click', exportar_csv);
