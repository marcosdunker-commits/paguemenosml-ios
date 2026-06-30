let todosResultados = [];
let queryAtual = '';

function fmt(valor) {
    return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function estrelas(rating) {
    if (!rating) return '';
    const cheias = Math.round(rating);
    let s = '';
    for (let i = 0; i < 5; i++) s += i < cheias ? '★' : '☆';
    return s;
}

function getQuery() {
    const hero = document.getElementById('searchInput');
    const header = document.getElementById('searchInputHeader');
    return (hero && hero.value.trim()) || (header && header.value.trim()) || '';
}

async function buscar(queryForced) {
    const q = queryForced || getQuery();
    if (!q) return;

    document.getElementById('hero').style.display = 'none';
    document.getElementById('loading').classList.add('ativo');
    document.getElementById('headerSearchBox').classList.add('visivel');

    window.location.href = `/api/redirecionar?q=${encodeURIComponent(q)}`;
}

function buscarCategoria(cat) {
    document.getElementById('searchInput').value = cat;
    buscar(cat);
}

function renderizar(items) {
    const grid = document.getElementById('grid');
    const info = document.getElementById('resultadosInfo');

    info.textContent = `${items.length} resultado${items.length !== 1 ? 's' : ''} para "${queryAtual}"`;

    if (!items.length) {
        grid.innerHTML = `
            <div class="sem-resultados" style="grid-column:1/-1">
                <p>😕 Nenhum resultado encontrado para "<strong>${queryAtual}</strong>"</p>
                <p style="margin-top:8px;font-size:0.9rem">Tente usar termos mais simples</p>
            </div>`;
    } else {
        grid.innerHTML = items.map(p => `
            <div class="card">
                <div class="card-img">
                    <img src="${p.imagem}" alt="${escapeHtml(p.nome)}" loading="lazy"
                         onerror="this.src='logo_transparent.png'">
                    ${p.desconto >= 5 ? `<span class="badge-desconto">-${p.desconto}%</span>` : ''}
                </div>
                <div class="card-body">
                    <p class="card-nome">${escapeHtml(p.nome)}</p>
                    ${p.rating ? `
                        <div class="card-rating">
                            <span class="estrelas">${estrelas(p.rating)}</span>
                            ${p.rating.toFixed(1)}
                            ${p.reviews ? `<span>(${p.reviews.toLocaleString('pt-BR')})</span>` : ''}
                        </div>` : ''}
                    ${p.preco_de ? `<p class="preco-de">${fmt(p.preco_de)}</p>` : ''}
                    <p class="preco-por">${fmt(p.preco)}</p>
                </div>
                <a href="${p.link}" target="_blank" rel="noopener noreferrer" class="card-btn">
                    🛒 VER MELHOR PREÇO
                </a>
            </div>
        `).join('');
    }

    document.getElementById('resultados').classList.add('ativo');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function reordenar() {
    const ordem = document.getElementById('ordenar').value;
    const sorted = [...todosResultados].sort((a, b) => {
        if (ordem === 'preco') return a.preco - b.preco;
        if (ordem === 'desconto') return (b.desconto || 0) - (a.desconto || 0);
        if (ordem === 'rating') return (b.rating || 0) - (a.rating || 0);
        return 0;
    });
    renderizar(sorted);
}

function escapeHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function abrirContato() {
    document.getElementById('modalContato').classList.add('ativo');
    document.getElementById('modalFeedback').textContent = '';
    document.getElementById('formContato').reset();
}

function fecharContato(event) {
    if (event && event.target !== document.getElementById('modalContato')) return;
    document.getElementById('modalContato').classList.remove('ativo');
}

async function enviarContato(e) {
    e.preventDefault();
    const btn = document.getElementById('btnEnviar');
    const feedback = document.getElementById('modalFeedback');
    btn.disabled = true;
    btn.textContent = 'Enviando...';
    feedback.style.color = '#aaa';
    feedback.textContent = '';

    try {
        const res = await fetch('/api/contato', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nome: document.getElementById('cNome').value.trim(),
                email: document.getElementById('cEmail').value.trim(),
                mensagem: document.getElementById('cMensagem').value.trim(),
            })
        });
        const data = await res.json();
        if (res.ok && data.ok) {
            feedback.style.color = '#4caf50';
            feedback.textContent = '✅ Mensagem enviada! Responderemos em breve.';
            document.getElementById('formContato').reset();
        } else {
            feedback.style.color = '#e53935';
            feedback.textContent = '❌ ' + (data.erro || 'Erro ao enviar. Tente novamente.');
        }
    } catch {
        feedback.style.color = '#e53935';
        feedback.textContent = '❌ Erro de conexão. Tente novamente.';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Enviar mensagem';
    }
}

async function carregarOfertas() {
    try {
        const res = await fetch('/api/ofertas?limit=14');
        if (!res.ok) return;
        const data = await res.json();
        const row = document.getElementById('ofertasRow');
        if (!row) return;
        const items = data.resultados || [];
        if (!items.length) { row.innerHTML = ''; return; }
        row.innerHTML = items.map(p => {
            const stars = p.rating > 0
                ? Array.from({length:5}, (_,i) => i < Math.round(p.rating) ? '★' : '☆').join('')
                : '';
            const reviews = p.reviews >= 1000
                ? (p.reviews/1000).toFixed(1).replace('.0','') + 'mil'
                : (p.reviews || '');
            return `
            <a href="${p.link}" target="_blank" rel="noopener noreferrer" class="oferta-card">
                <div class="oferta-card-img">
                    <img src="${p.imagem || 'logo_transparent.png'}" alt="${escapeHtml(p.nome)}" loading="lazy"
                         onerror="this.src='logo_transparent.png'">
                    ${p.desconto >= 5 ? `<span class="oferta-badge">-${p.desconto}%</span>` : ''}
                </div>
                <div class="oferta-card-body">
                    <p class="oferta-nome">${escapeHtml(p.nome)}</p>
                </div>
                ${p.rating > 0 ? `
                <div class="oferta-card-rating">
                    <span class="oferta-rating-num">${p.rating.toFixed(1)}</span>
                    <span class="oferta-rating-stars">${stars}</span>
                    ${reviews ? `<div class="oferta-rating-reviews"><span class="oferta-rating-count">${reviews}</span><span class="oferta-rating-label">AVAL.</span></div>` : ''}
                </div>` : ''}
                <div class="oferta-card-preco">
                    ${p.preco_de ? `<span class="oferta-preco-de">${fmt(p.preco_de)}</span>` : ''}
                    <span class="oferta-preco">${fmt(p.preco)}</span>
                </div>
                <div class="oferta-card-footer">
                    <span class="oferta-footer-marca">PAGUE MENOS.</span>
                    <span class="oferta-footer-sub">PRODUTO OFICIAL</span>
                </div>
            </a>`;
        }).join('');
    } catch (e) {
        const row = document.getElementById('ofertasRow');
        if (row) row.innerHTML = '';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    ['searchInput', 'searchInputHeader'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') buscar(); });
    });
    carregarOfertas();
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
});

function _restaurarHero() {
    document.getElementById('hero').style.display = '';
    document.getElementById('loading').classList.remove('ativo');
    document.getElementById('headerSearchBox').classList.remove('visivel');
    document.getElementById('searchInput').value = '';
    document.getElementById('searchInputHeader').value = '';
}

window.addEventListener('pageshow', (e) => {
    if (e.persisted) _restaurarHero();
});

document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        const hero = document.getElementById('hero');
        if (hero && hero.style.display === 'none') _restaurarHero();
    }
});
