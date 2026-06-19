const tbody = document.querySelector('tbody');
const comboRows = Array.from(tbody.querySelectorAll('tr.combo'));
const filterInputs = Array.from(document.querySelectorAll('.filters input[data-filter]'));
const clearBtn = document.getElementById('clear-filters');
const headers = document.querySelectorAll('th[data-sort]');
const mobileSortSel = document.getElementById('mobile-sort');
const visibleEl = document.getElementById('visible-count');
const totalEl = document.getElementById('total-count');
const emptyEl = document.getElementById('empty-state');
const totalRows = comboRows.length;
totalEl.textContent = totalRows;

let currentSort = { key: 'count', dir: 'desc' };

function applySort() {
    const { key, dir } = currentSort;
    const mult = dir === 'asc' ? 1 : -1;
    const sorted = comboRows.slice().sort((a, b) => {
        if (key === 'count') return (Number(a.dataset.count) - Number(b.dataset.count)) * mult;
        if (key === 'last') return (Number(a.dataset.last) - Number(b.dataset.last)) * mult;
        return a.dataset.drivers.localeCompare(b.dataset.drivers) * mult;
    });
    sorted.forEach((row, i) => {
        row.querySelector('.rank').textContent = i + 1;
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

function applyFilter() {
    const filters = filterInputs.map(i => i.value.trim().toLowerCase()).filter(v => v);
    let visible = 0;
    comboRows.forEach(row => {
        const drivers = row.dataset.drivers.split(' | ');
        const match = matchesFilters(drivers, filters);
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
    emptyEl.style.display = visible === 0 ? '' : 'none';
    clearBtn.disabled = filters.length === 0;
}

filterInputs.forEach(i => i.addEventListener('input', applyFilter));
clearBtn.addEventListener('click', () => {
    filterInputs.forEach(i => { i.value = ''; });
    applyFilter();
    filterInputs[0].focus();
});

applySort();
applyFilter();
