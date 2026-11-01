const tbody = document.querySelector('tbody');
const comboRows = Array.from(tbody.querySelectorAll('tr.combo'));
const filterInputs = Array.from(document.querySelectorAll('.filters input[data-filter]'));
const clearBtn = document.getElementById('clear-filters');
const headers = document.querySelectorAll('th[data-sort]');
const mobileSortSel = document.getElementById('mobile-sort');
const visibleEl = document.getElementById('visible-count');
const totalEl = document.getElementById('total-count');
const emptyEl = document.getElementById('empty-state');
const emptyTitleEl = document.getElementById('empty-title');
const emptyTextEl = document.getElementById('empty-text');
const totalRows = comboRows.length;
totalEl.textContent = totalRows;

// ── Season range ───────────────────────────────────────────────────────────
// One state, two controls: a dual-handle slider (widescreen) and a pair of
// From/To selects (mobile). Both render from — and write to — {seasonFrom, seasonTo}.
const rangeEl = document.querySelector('.season-range');
const fromSlider = document.getElementById('season-from');
const toSlider = document.getElementById('season-to');
const fromSel = document.getElementById('season-from-sel');
const toSel = document.getElementById('season-to-sel');
const trackEl = document.getElementById('season-track');
const fillEl = document.getElementById('season-fill');
const readoutEl = document.getElementById('season-readout');
const ofTotalEl = document.getElementById('of-total');
const rangeNoteEl = document.getElementById('range-note');
const THUMB = 16; // keep in sync with .sr-input thumb width in index.css

const SMIN = rangeEl ? Number(rangeEl.dataset.min) : 0;
const SMAX = rangeEl ? Number(rangeEl.dataset.max) : 0;
let seasonFrom = SMIN;
let seasonTo = SMAX;

const fullRange = () => !rangeEl || (seasonFrom === SMIN && seasonTo === SMAX);
const clampSeason = v => Math.min(SMAX, Math.max(SMIN, v));

// Per-row race list, parsed once from data-races ("season|round|raceName;...").
const raceCache = new Map();
function racesOf(row) {
    let races = raceCache.get(row);
    if (!races) {
        races = (row.dataset.races || '').split(';').filter(Boolean).map(entry => {
            const a = entry.indexOf('|');
            const b = entry.indexOf('|', a + 1);
            return {
                season: Number(entry.slice(0, a)),
                round: Number(entry.slice(a + 1, b)),
                name: entry.slice(b + 1),
            };
        });
        raceCache.set(row, races);
    }
    return races;
}

// Lifetime Count / Last seen cells, restored whenever the range goes back to full.
const lifetimeCells = new Map();
comboRows.forEach(row => {
    lifetimeCells.set(row, {
        count: row.querySelector('.count').innerHTML,
        last: row.querySelector('.last').innerHTML,
        dataCount: row.dataset.count,
        dataLast: row.dataset.last,
    });
});

function positionFill() {
    if (!fillEl || !trackEl) return;
    const width = trackEl.clientWidth;
    if (!width) return; // hidden (mobile) — recomputed on resize
    const span = SMAX - SMIN || 1;
    const at = v => ((v - SMIN) / span) * (width - THUMB) + THUMB / 2;
    fillEl.style.left = at(seasonFrom) + 'px';
    fillEl.style.width = Math.max(0, at(seasonTo) - at(seasonFrom)) + 'px';
}

function syncSeasonUI() {
    if (!rangeEl) return;
    fromSlider.value = seasonFrom;
    toSlider.value = seasonTo;
    if (fromSel) fromSel.value = seasonFrom;
    if (toSel) toSel.value = seasonTo;
    // With both handles pinned right they overlap; lift the "from" input so it
    // stays grabbable. Everywhere else "to" sits on top.
    fromSlider.style.zIndex = seasonFrom >= SMAX - 1 ? 5 : 3;
    readoutEl.textContent = fullRange()
        ? 'All seasons'
        : seasonFrom === seasonTo
            ? String(seasonFrom)
            : seasonFrom + ' – ' + seasonTo;
    positionFill();
}

function setRange(from, to) {
    seasonFrom = clampSeason(from);
    seasonTo = clampSeason(to);
    if (seasonFrom > seasonTo) seasonTo = seasonFrom;
    syncSeasonUI();
    refresh();  // applyFilter() writes the URL for both controls
}

// ── Sorting ────────────────────────────────────────────────────────────────

let currentSort = { key: 'count', dir: 'desc' };

function applySort() {
    const { key, dir } = currentSort;
    const mult = dir === 'asc' ? 1 : -1;
    const sorted = comboRows.slice().sort((a, b) => {
        if (key === 'count') return (Number(a.dataset.count) - Number(b.dataset.count)) * mult;
        if (key === 'last') return (Number(a.dataset.last) - Number(b.dataset.last)) * mult;
        return a.dataset.drivers.localeCompare(b.dataset.drivers) * mult;
    });
    sorted.forEach(row => {
        const detail = row.nextElementSibling;
        tbody.appendChild(row);
        if (detail && detail.classList.contains('detail')) tbody.appendChild(detail);
    });
    headers.forEach(h => {
        const isActive = h.dataset.sort === key;
        h.classList.toggle('active', isActive);
        h.classList.toggle('dir-asc', isActive && dir === 'asc');
        h.classList.toggle('dir-desc', isActive && dir === 'desc');
    });
    if (mobileSortSel) mobileSortSel.value = key + '-' + dir;
}

headers.forEach(h => {
    h.addEventListener('click', () => {
        const key = h.dataset.sort;
        if (currentSort.key === key) {
            currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
        } else {
            currentSort.key = key;
            currentSort.dir = (key === 'count' || key === 'last') ? 'desc' : 'asc';
        }
        applySort();
    });
});

if (mobileSortSel) {
    mobileSortSel.addEventListener('change', () => {
        const [key, dir] = mobileSortSel.value.split('-');
        currentSort.key = key;
        currentSort.dir = dir;
        applySort();
    });
}

comboRows.forEach(row => {
    row.addEventListener('click', () => {
        const detail = row.nextElementSibling;
        if (!detail || !detail.classList.contains('detail')) return;
        const open = detail.classList.toggle('open');
        row.classList.toggle('expanded', open);
    });
});

// ── Filtering ──────────────────────────────────────────────────────────────

// "raikkonen" has to find Räikkönen: both sides lose case and accents.
const fold = text => text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

const rowDrivers = new Map(comboRows.map(row => [row, fold(row.dataset.drivers).split(' | ')]));

// Everyone a filter can name: folded name -> display name. The grid counts too, so
// a driver yet to reach a podium is still a real driver.
const gridNames = (emptyEl.dataset.grid || '').split('|').filter(Boolean);
const gridDrivers = new Set(gridNames.map(fold));
const knownDrivers = new Map(gridNames.map(name => [fold(name), name]));
comboRows.forEach(row => {
    row.querySelectorAll('.dn-full').forEach(el => {
        knownDrivers.set(fold(el.textContent), el.textContent);
    });
});

// Each non-empty filter must match a DISTINCT driver in the combo (substring, case-insensitive).
function matchesFilters(driverNames, filters) {
    if (filters.length === 0) return true;
    if (filters.length > driverNames.length) return false;
    function dfs(idx, usedMask) {
        if (idx >= filters.length) return true;
        for (let d = 0; d < driverNames.length; d++) {
            if (usedMask & (1 << d)) continue;
            if (driverNames[d].includes(filters[idx])) {
                if (dfs(idx + 1, usedMask | (1 << d))) return true;
            }
        }
        return false;
    }
    return dfs(0, 0);
}

// Can each filter take a driver of its own? ``options`` holds each filter's matches.
function canBeDistinct(options, taken = new Set()) {
    if (!options.length) return true;
    return options[0].some(name => (
        !taken.has(name) && canBeDistinct(options.slice(1), new Set(taken).add(name))
    ));
}

function listNames(names) {
    if (names.length < 2) return names.join('');
    return names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
}

// An empty table means one of three things: nobody by that name, a window too narrow,
// or the best answer the page has: these drivers have never shared a podium. Typed
// text only ever reaches the page through textContent.
function renderEmptyState(filters, typed, shown) {
    emptyEl.style.display = shown ? '' : 'none';
    emptyEl.classList.remove('never');
    if (!shown) return;

    const options = filters.map(f => [...knownDrivers.keys()].filter(name => name.includes(f)));
    let title = 'No matches';
    let text = 'Try a different driver name.';
    if (comboRows.some(row => matchesFilters(rowDrivers.get(row), filters))) {
        title = 'Not in these seasons';
        text = 'Widen the season range to see them.';
    } else if (filters.length > 1 && options.every(o => o.length) && canBeDistinct(options)) {
        // One match, or one still racing ("Verstappen" means Max), gets the full
        // name. Otherwise the sentence holds for each match but can't pick one, so
        // the visitor's word stands.
        const picks = options.map(o => {
            const racing = o.filter(name => gridDrivers.has(name));
            if (o.length === 1) return o[0];
            return racing.length === 1 ? racing[0] : null;
        });
        const clear = picks.filter(Boolean).length === new Set(picks.filter(Boolean)).size;
        const names = picks.map((pick, i) => (
            pick && clear ? knownDrivers.get(pick) : '“' + typed[i] + '”'
        ));
        const onGrid = clear && picks.every(pick => gridDrivers.has(pick));
        const who = names.length === 3 ? 'All three are' : 'Both are';
        title = 'Never happened';
        text = listNames(names) + ' have never shared a podium.'
            + (onGrid ? ' ' + who + ' on the grid this season, so it could still be a podigami.' : '');
        emptyEl.classList.add('never');
    }
    emptyTitleEl.textContent = title;
    emptyTextEl.textContent = text;
}

// Count / Last seen are lifetime figures until a range narrows the window, at
// which point they (and the sort keys behind them) describe that window only.
function renderRowStats(row, inRange) {
    const countCell = row.querySelector('.count');
    const lastCell = row.querySelector('.last');
    if (!inRange) {
        const lifetime = lifetimeCells.get(row);
        countCell.innerHTML = lifetime.count;
        lastCell.innerHTML = lifetime.last;
        row.dataset.count = lifetime.dataCount;
        row.dataset.last = lifetime.dataLast;
        return;
    }
    countCell.textContent = inRange.length;
    if (!inRange.length) {
        // Row is about to be hidden; zeroed keys keep it out of the sorted run.
        lastCell.textContent = '—';
        row.dataset.count = 0;
        row.dataset.last = 0;
        return;
    }
    const latest = inRange.reduce(
        (best, r) => (r.season * 1000 + r.round > best.season * 1000 + best.round ? r : best),
        inRange[0]
    );
    const year = document.createElement('span');
    year.className = 'year';
    year.textContent = latest.season;
    const name = document.createElement('span');
    name.className = 'race-name';
    name.textContent = latest.name;
    lastCell.replaceChildren(year, name);
    row.dataset.count = inRange.length;
    row.dataset.last = latest.season * 1000 + latest.round;
}

// The expanded detail shows only the seasons the range covers, so the pills
// always add up to the Count beside them.
function renderDetailSeasons(row, full) {
    const detail = row.nextElementSibling;
    if (!detail || !detail.classList.contains('detail')) return;
    detail.querySelectorAll('.season-row').forEach(sr => {
        const season = Number(sr.dataset.season);
        sr.style.display = full || (season >= seasonFrom && season <= seasonTo) ? '' : 'none';
    });
}

function applyFilter() {
    const typed = filterInputs.map(i => i.value.trim()).filter(v => v);
    const filters = typed.map(fold);
    const full = fullRange();
    let visible = 0;
    comboRows.forEach(row => {
        const inRange = full
            ? null
            : racesOf(row).filter(r => r.season >= seasonFrom && r.season <= seasonTo);
        const match = matchesFilters(rowDrivers.get(row), filters) && (full || inRange.length > 0);

        renderRowStats(row, inRange);
        renderDetailSeasons(row, full);

        row.style.display = match ? '' : 'none';
        const detail = row.nextElementSibling;
        if (detail && detail.classList.contains('detail')) {
            if (!match) {
                detail.classList.remove('open');
                row.classList.remove('expanded');
                detail.style.display = 'none';
            } else {
                detail.style.display = '';
            }
        }
        if (match) visible++;
    });
    visibleEl.textContent = visible;
    renderEmptyState(filters, typed, visible === 0);
    clearBtn.disabled = filters.length === 0 && full;
    syncFilterSummary(filters.length + (full ? 0 : 1), visible);
    writeParams();

    if (ofTotalEl && rangeNoteEl) {
        ofTotalEl.style.display = full ? '' : 'none';
        rangeNoteEl.textContent = full
            ? ''
            : seasonFrom === seasonTo
                ? ' from ' + seasonFrom
                : ' from ' + seasonFrom + '–' + seasonTo;
    }
}

// Sort keys change with the window, so a filter pass is always followed by a sort.
function refresh() {
    applyFilter();
    applySort();
}

filterInputs.forEach(i => i.addEventListener('input', applyFilter));
clearBtn.addEventListener('click', () => {
    filterInputs.forEach(i => { i.value = ''; });
    setRange(SMIN, SMAX);
    filterInputs[0].focus();
});

// ── Season control wiring ──────────────────────────────────────────────────

if (rangeEl) {
    // Sliders: a handle stops at its neighbour rather than pushing it.
    fromSlider.addEventListener('input', () => {
        setRange(Math.min(Number(fromSlider.value), seasonTo), seasonTo);
    });
    toSlider.addEventListener('input', () => {
        setRange(seasonFrom, Math.max(Number(toSlider.value), seasonFrom));
    });
    // Selects: picking past the other end pushes it along, since a select has
    // no drag to stop short.
    if (fromSel) {
        fromSel.addEventListener('change', () => {
            const v = Number(fromSel.value);
            setRange(v, Math.max(v, seasonTo));
        });
    }
    if (toSel) {
        toSel.addEventListener('change', () => {
            const v = Number(toSel.value);
            setRange(Math.min(v, seasonFrom), v);
        });
    }
    window.addEventListener('resize', positionFill);
}

// ── Mobile filter panel ────────────────────────────────────────────────────
// Below 720px the whole .filters block lives in a slide-out panel behind the
// "Filters" trigger, so the table (not the controls) owns the top of a phone
// screen. The checkbox hack in index.css does the opening and closing on its
// own; this layer only adds aria state, Escape-to-close, a scroll lock, and
// the badge that reports how many filters are on while the panel is shut.

const panelToggle = document.getElementById('filter-toggle');
const panelEl = document.getElementById('filter-panel');
const toggleLabel = document.querySelector('.filter-toggle');
const countEl = document.getElementById('filter-count');
const doneEl = document.getElementById('filter-done');
const navToggle = document.getElementById('nav-drawer-toggle');

function syncPanel(moveFocus) {
    const open = panelToggle.checked;
    if (toggleLabel) toggleLabel.setAttribute('aria-expanded', String(open));
    document.documentElement.classList.toggle(
        'drawer-open',
        open || !!(navToggle && navToggle.checked)
    );
    if (!moveFocus) return;
    // Focus the panel itself rather than the first input: landing on a text
    // field would raise the on-screen keyboard over the filters.
    if (open) panelEl.focus();
    else if (toggleLabel) toggleLabel.focus();
}

// Reported on the trigger while the panel is shut: each filled driver box
// counts as one, a narrowed season range as one more.
function syncFilterSummary(active, visible) {
    if (toggleLabel) {
        toggleLabel.classList.toggle('has-active', active > 0);
        toggleLabel.setAttribute('aria-label', active ? 'Filters (' + active + ' active)' : 'Filters');
    }
    if (countEl) countEl.textContent = active;
    if (doneEl) {
        doneEl.textContent = visible === 0
            ? 'No matches'
            : 'Show ' + visible + ' trio' + (visible === 1 ? '' : 's');
    }
}

if (panelToggle) {
    panelToggle.addEventListener('change', () => syncPanel(true));
    [toggleLabel, doneEl, document.querySelector('.fp-close')].forEach(el => {
        if (!el) return;
        el.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                panelToggle.checked = !panelToggle.checked;
                syncPanel(true);
            }
        });
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && panelToggle.checked) {
            panelToggle.checked = false;
            syncPanel(true);
        }
    });
    // Past the breakpoint the filters are inline again; a panel left "open"
    // would otherwise keep the page scroll-locked behind an invisible scrim.
    window.addEventListener('resize', () => {
        if (panelToggle.checked && window.innerWidth > 720) {
            panelToggle.checked = false;
            syncPanel(false);
        }
    });
    syncPanel(false);
}

// ── Deep links ─────────────────────────────────────────────────────────────

// ?d=Name&d=Name&d=Name (e.g. from a trio elsewhere on the site) pre-fills the
// driver filters; ?from=2001&to=2003 pre-sets the season range.
//
// The URL mirrors BOTH controls, and is rewritten after every filter pass. It
// used to carry only the season range, so the driver names a visitor arrived
// with survived everything they did next: Clear emptied the three inputs and
// left ?d= standing, and the next reload (or a shared link) silently put the
// filter back on a table that showed no sign of it.
function writeParams() {
    try {
        const params = new URLSearchParams(location.search);
        params.delete('d');
        filterInputs.forEach(i => { if (i.value.trim()) params.append('d', i.value.trim()); });
        if (!rangeEl || fullRange()) {
            params.delete('from');
            params.delete('to');
        } else {
            params.set('from', seasonFrom);
            params.set('to', seasonTo);
        }
        const query = params.toString();
        if (query === location.search.replace(/^\?/, '')) return;
        history.replaceState(null, '', query ? '?' + query : location.pathname);
    } catch {
        /* replaceState can be blocked (e.g. file://); the filter still works */
    }
}

const params = new URLSearchParams(location.search);

const presetDrivers = params.getAll('d');
if (presetDrivers.length) {
    presetDrivers.slice(0, filterInputs.length).forEach((v, i) => { filterInputs[i].value = v; });
}

if (rangeEl) {
    const from = parseInt(params.get('from'), 10);
    const to = parseInt(params.get('to'), 10);
    if (Number.isFinite(from) || Number.isFinite(to)) {
        let lo = Number.isFinite(from) ? clampSeason(from) : SMIN;
        let hi = Number.isFinite(to) ? clampSeason(to) : SMAX;
        if (lo > hi) [lo, hi] = [hi, lo];
        seasonFrom = lo;
        seasonTo = hi;
    }
    syncSeasonUI();
}

refresh();
