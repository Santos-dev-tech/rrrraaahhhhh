const HOST = window.location.hostname === '' ? '127.0.0.1' : window.location.hostname;
const BASE_URL = `http://${HOST}:5000/api`;

let chart, candlestickSeries, anchorLines = {}, lastBid = 0;
let pollPriceInterval, pollStrategyInterval, pollAccountInterval;

// ===== ADD ACCOUNT MODAL =====
function openAddModal() {
    document.getElementById('add-modal').classList.add('active');
    document.getElementById('add-error').innerText = '';
    document.getElementById('btn-add-acct').disabled = false;
    document.getElementById('btn-add-acct').innerText = 'Add Account';
}
function closeAddModal() {
    document.getElementById('add-modal').classList.remove('active');
}

async function handleAddAccount(e) {
    e.preventDefault();
    const btn = document.getElementById('btn-add-acct');
    const errEl = document.getElementById('add-error');
    errEl.innerText = '';
    btn.disabled = true;
    btn.innerText = 'Connecting...';

    const payload = {
        login: document.getElementById('inp-login').value,
        password: document.getElementById('inp-password').value,
        server: document.getElementById('inp-server').value,
        strategy: document.getElementById('inp-strategy').value,
        auto_trade: document.getElementById('inp-auto-trade').checked
    };

    try {
        const res = await fetch(`${BASE_URL}/accounts/add`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.error) {
            errEl.innerText = data.error;
            btn.disabled = false;
            btn.innerText = 'Add Account';
            return;
        }
        closeAddModal();
        document.getElementById('add-form').reset();
        refreshAccounts();
    } catch (err) {
        errEl.innerText = 'Network error. Is the server running on port 5000?';
        btn.disabled = false;
        btn.innerText = 'Add Account';
    }
}

// ===== ACCOUNTS GRID =====
async function refreshAccounts() {
    try {
        const res = await fetch(`${BASE_URL}/accounts`);
        const accounts = await res.json();
        renderAccounts(accounts);
    } catch (err) {}
}

function renderAccounts(accounts) {
    const grid = document.getElementById('accounts-grid');
    const empty = document.getElementById('empty-accounts');
    const summary = document.getElementById('nav-summary');

    if (!accounts || accounts.length === 0) {
        grid.innerHTML = '';
        grid.appendChild(createEmptyState());
        summary.innerText = 'No Accounts';
        return;
    }

    summary.innerText = `${accounts.length} Account${accounts.length > 1 ? 's' : ''} Active`;
    grid.innerHTML = accounts.map(a => {
        const stratLabel = a.strategy === '1255' ? '12:55' : '13:00';
        const autoClass = a.auto_trade ? 'auto-on' : 'auto-off';
        const autoText = a.auto_trade ? '⚡ AUTO PILOT' : 'MANUAL';
        const lastTrade = a.last_trade_result
            ? (a.last_trade_result.status === 'Success'
                ? `✅ #${a.last_trade_result.order} | ${a.last_trade_result.volume} lots @ ${a.last_trade_result.price.toFixed(2)}`
                : `❌ ${a.last_trade_result.error || 'Failed'}`)
            : 'No trades today';

        return `
        <div class="account-card">
            <div class="acct-header">
                <div class="acct-id">
                    <span class="acct-num">#${a.login}</span>
                    <span class="acct-name">${a.name || a.server}</span>
                </div>
                <span class="acct-badge ${autoClass}" onclick="toggleAuto(${a.login})">${autoText}</span>
            </div>
            <div class="acct-body">
                <div class="acct-stat">
                    <span class="acct-stat-label">Balance</span>
                    <span class="acct-stat-value">$${(a.balance || 0).toFixed(2)}</span>
                </div>
                <div class="acct-stat">
                    <span class="acct-stat-label">Strategy</span>
                    <span class="acct-stat-value">${stratLabel} UTC</span>
                </div>
                <div class="acct-stat">
                    <span class="acct-stat-label">Equity</span>
                    <span class="acct-stat-value">$${(a.equity || 0).toFixed(2)}</span>
                </div>
                <div class="acct-stat">
                    <span class="acct-stat-label">Last Trade</span>
                    <span class="acct-stat-value" style="font-size:0.75rem">${a.last_trade_date || '—'}</span>
                </div>
            </div>
            <div class="acct-footer">
                <span class="acct-trade-status">${lastTrade}</span>
                <div class="acct-actions">
                    <button class="btn-sm-exec" onclick="manualExecute(${a.login})" title="Manual Execute">▶</button>
                    <button class="btn-sm-remove" onclick="removeAccount(${a.login})" title="Remove">✕</button>
                </div>
            </div>
        </div>`;
    }).join('');
}

function createEmptyState() {
    const div = document.createElement('div');
    div.className = 'empty-accounts';
    div.id = 'empty-accounts';
    div.innerHTML = `
        <div class="empty-icon">🏦</div>
        <h3>No Accounts Connected</h3>
        <p>Add your MT5 funded accounts to start automated trading</p>
        <button class="btn-login" onclick="openAddModal()" style="padding:10px 24px; margin-top:12px">+ Add First Account</button>`;
    return div;
}

async function toggleAuto(login) {
    try {
        await fetch(`${BASE_URL}/accounts/toggle_auto`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ login })
        });
        refreshAccounts();
    } catch (err) {}
}

async function removeAccount(login) {
    if (!confirm(`Remove account #${login}?`)) return;
    try {
        await fetch(`${BASE_URL}/accounts/remove`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ login })
        });
        refreshAccounts();
    } catch (err) {}
}

async function manualExecute(login) {
    if (!confirm(`Manually execute trade on #${login}?`)) return;
    try {
        const res = await fetch(`${BASE_URL}/execute`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ login })
        });
        const data = await res.json();
        if (data.error) alert(`Failed: ${data.error}`);
        else alert(`✅ Order #${data.order} | ${data.volume} lots @ ${data.price.toFixed(2)}`);
        refreshAccounts();
    } catch (err) { alert('Network error'); }
}

// ===== NAVIGATION =====
function showPage(pageId, btn) {
    document.querySelectorAll('.page-section').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
    document.getElementById(pageId).classList.add('active');
    btn.classList.add('active');
    if (pageId === 'page-live' && !chart) initChart();
    if (pageId === 'page-live' && chart) setTimeout(() => chart.timeScale().fitContent(), 100);
    if (pageId === 'page-stats' && !window._statsLoaded) loadBacktestStats();
}

// ===== CHART =====
function initChart() {
    const container = document.getElementById('chart');
    chart = LightweightCharts.createChart(container, {
        layout: { textColor: '#d1d4dc', background: { type: 'solid', color: '#0b111a' } },
        grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#374151' },
        timeScale: { borderColor: '#374151', timeVisible: true, secondsVisible: false },
    });
    candlestickSeries = chart.addCandlestickSeries({
        upColor: '#10b981', downColor: '#ef4444', borderVisible: false,
        wickUpColor: '#10b981', wickDownColor: '#ef4444'
    });
    new ResizeObserver(entries => {
        if (entries.length === 0) return;
        const r = entries[0].contentRect;
        chart.applyOptions({ height: r.height, width: r.width });
    }).observe(container);
    fetchInitialCandles();
}

async function fetchInitialCandles() {
    try {
        const res = await fetch(`${BASE_URL}/candles`);
        const data = await res.json();
        if (data.error) {
            const overlay = document.getElementById('loading-overlay');
            const msg = overlay.querySelector('.status-msg');
            const sub = overlay.querySelector('.sub-msg');
            if (data.market_closed) {
                msg.innerText = '📅 Market is Closed';
                sub.innerText = 'Charts load automatically when market opens (Sunday 22:00 UTC)';
            } else {
                msg.innerText = 'Connecting to live data...';
                sub.innerText = 'Waiting for candle data from MT5';
            }
            setTimeout(fetchInitialCandles, 3000);
            return;
        }
        candlestickSeries.setData(data);
        document.getElementById('loading-overlay').style.display = 'none';
        document.getElementById('conn-status').innerText = 'Connected to MT5 — Live';
        document.getElementById('conn-status').style.color = '#10b981';
    } catch (err) { setTimeout(fetchInitialCandles, 3000); }
}

// ===== POLLING =====
async function pollPrice() {
    try {
        const res = await fetch(`${BASE_URL}/price`);
        const data = await res.json();
        if (data.market_closed) {
            setPrice('CLOSED', '#9ca3af', '--');
            return;
        }
        if (data.error || !data.bid) return;

        const cls = data.bid > lastBid ? 'price-up' : data.bid < lastBid ? 'price-down' : '';
        lastBid = data.bid;
        setPrice(data.bid.toFixed(2), '', data.spread.toFixed(1), cls);
    } catch (err) {}
}

function setPrice(bid, color, spread, cls) {
    ['live-bid', 'live-bid-chart'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.innerText = bid;
        if (color) el.style.color = color;
        else el.style.color = '';
        if (cls) el.className = 'current-price ' + cls;
        else if (!color) el.className = 'current-price';
    });
    ['live-spread', 'live-spread-chart'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerText = spread;
    });
}

async function pollStrategy() {
    for (const anchor of ['1300', '1255']) {
        try {
            const res = await fetch(`${BASE_URL}/strategy?anchor=${anchor}`);
            const data = await res.json();
            const label = anchor === '1255' ? '12:55' : '13:00';

            // Update accounts page signal cards
            const sigStatus = document.getElementById(`sig-${anchor}-status`);
            if (sigStatus) {
                if (data.status.includes('Triggered')) {
                    sigStatus.innerText = `🔥 ${data.direction} @ ${data.entry_price.toFixed(2)}`;
                    sigStatus.style.color = data.direction === 'Long' ? '#10b981' : '#ef4444';
                } else if (data.status.includes('Watching')) {
                    sigStatus.innerText = `👀 H:${data.anchor_high.toFixed(2)} L:${data.anchor_low.toFixed(2)}`;
                    sigStatus.style.color = '#3b82f6';
                } else {
                    sigStatus.innerText = data.status;
                    sigStatus.style.color = '#9ca3af';
                }
            }

            // Update chart page sidebar
            const indEl = document.getElementById(`strat-${anchor}-ind`);
            const textEl = document.getElementById(`strat-${anchor}-text`);
            const highEl = document.getElementById(`val-${anchor}-high`);
            const lowEl = document.getElementById(`val-${anchor}-low`);

            if (textEl) textEl.innerText = data.status;
            if (data.anchor_high && highEl) highEl.innerText = data.anchor_high.toFixed(2);
            if (data.anchor_low && lowEl) lowEl.innerText = data.anchor_low.toFixed(2);

            if (indEl) {
                if (data.status.includes('Triggered')) indEl.className = 'status-indicator triggered';
                else if (data.status.includes('Watching')) indEl.className = 'status-indicator active';
                else indEl.className = 'status-indicator';
            }

            // Draw anchor lines on chart
            if (data.anchor_high && data.anchor_low && candlestickSeries) {
                drawAnchorLine(anchor, 'high', data.anchor_high);
                drawAnchorLine(anchor, 'low', data.anchor_low);
            }
        } catch (err) {}
    }

    // Update candles on chart page
    if (candlestickSeries) {
        try {
            const cRes = await fetch(`${BASE_URL}/candles`);
            const cData = await cRes.json();
            if (!cData.error && Array.isArray(cData) && cData.length > 0) {
                candlestickSeries.update(cData[cData.length - 1]);
                if (document.getElementById('loading-overlay')?.style.display !== 'none') {
                    candlestickSeries.setData(cData);
                    document.getElementById('loading-overlay').style.display = 'none';
                    document.getElementById('conn-status').innerText = 'Connected to MT5 — Live';
                    document.getElementById('conn-status').style.color = '#10b981';
                }
            }
        } catch (err) {}
    }
}

function drawAnchorLine(anchor, side, price) {
    const key = `${anchor}_${side}`;
    const color = side === 'high' ? '#3b82f6' : '#f59e0b';
    const label = anchor === '1300' ? '13:00' : '12:55';
    const title = `${label} ${side === 'high' ? 'High' : 'Low'}`;

    if (!anchorLines[key]) {
        anchorLines[key] = candlestickSeries.createPriceLine({
            price, color, lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true, title
        });
    } else {
        anchorLines[key].applyOptions({ price });
    }
}

// ===== BACKTEST STATS =====
async function loadBacktestStats() {
    const container = document.getElementById('stats-container');
    container.innerHTML = '<div style="text-align:center;padding:60px;color:#9ca3af">Loading 1-Year Backtest Stats...</div>';
    try {
        const res = await fetch(`${BASE_URL}/backtest_stats`);
        const data = await res.json();
        if (data.error) { container.innerHTML = `<div style="text-align:center;padding:60px;color:#9ca3af">${data.error}</div>`; return; }

        const parser = new DOMParser();
        const doc = parser.parseFromString(data.html, 'text/html');
        const bodyContent = doc.querySelector('.container');
        if (bodyContent) {
            // Inject the original styles so stats render correctly
            let stylesHtml = '';
            doc.querySelectorAll('style').forEach(s => { stylesHtml += s.outerHTML; });
            container.innerHTML = stylesHtml + bodyContent.innerHTML;
            container.querySelectorAll('.tab-btn').forEach(btn => {
                const raw = btn.getAttribute('onclick') || '';
                const match = raw.match(/showTab\('(.+?)'\)/);
                const tabId = match ? match[1] : null;
                btn.removeAttribute('onclick');
                btn.addEventListener('click', function() {
                    if (!tabId) return;
                    container.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                    container.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
                    const target = container.querySelector('#' + tabId);
                    if (target) target.classList.add('active');
                    this.classList.add('active');
                });
            });
        } else {
            container.innerHTML = '<div style="text-align:center;padding:60px;color:#9ca3af">Could not parse stats.</div>';
        }
        window._statsLoaded = true;
    } catch (err) {
        container.innerHTML = '<div style="text-align:center;padding:60px;color:#9ca3af">Failed to load stats. Is the server running?</div>';
    }
}

// ===== INIT =====
window.addEventListener('DOMContentLoaded', () => {
    refreshAccounts();
    pollPrice();
    pollStrategy();
    pollPriceInterval = setInterval(pollPrice, 1000);
    pollStrategyInterval = setInterval(pollStrategy, 3000);
    pollAccountInterval = setInterval(refreshAccounts, 10000);
});
