const cards = Array.from(document.querySelectorAll('.season-card'));
const sortSel = document.getElementById('sort-by');
const minLen = document.getElementById('min-len');
const visEl = document.getElementById('visible-count');
const totalEl = document.getElementById('total-count');
const list = document.getElementById('season-list');
const emptyEl = document.getElementById('global-empty');
const totalCards = cards.length;
totalEl.textContent = totalCards;

cards.forEach(card => {
    const head = card.querySelector('.season-head');
    head.addEventListener('click', () => card.classList.toggle('expanded'));
});

document.querySelectorAll('.champ-toggle').forEach(btn => {
    btn.addEventListener('click', e => {
        e.stopPropagation();
        const list = btn.previousElementSibling;
        const open = list.classList.toggle('expanded');
        btn.textContent = open ? 'Show less' : btn.dataset.label;
    });
});

function applySort() {
    const key = sortSel.value;
    const sorted = cards.slice().sort((a, b) => {
        const aS = Number(a.dataset.season);
        const bS = Number(b.dataset.season);
        const aB = Number(a.dataset.best);
        const bB = Number(b.dataset.best);
        const aP = Number(a.dataset.perfect3);
        const bP = Number(b.dataset.perfect3);
        const aR = Number(a.dataset.rate);
        const bR = Number(b.dataset.rate);
        if (key === 'season-desc') return bS - aS;
        if (key === 'season-asc')  return aS - bS;
        if (key === 'best-desc')   return (bB - aB) || (bS - aS);
        if (key === 'perfect-desc') return (bP - aP) || (bS - aS);
        if (key === 'rate-desc')   return (bR - aR) || (bS - aS);
        return 0;
    });
    sorted.forEach(c => list.appendChild(c));
}

function applyFilter() {
    const min = Number(minLen.value) || 0;
    let v = 0;
    cards.forEach(card => {
        const best = Number(card.dataset.best);
        const show = best >= min;
        card.style.display = show ? '' : 'none';
        if (show) v++;
    });
    visEl.textContent = v;
    emptyEl.style.display = v === 0 ? '' : 'none';
}

sortSel.addEventListener('change', applySort);
minLen.addEventListener('input', applyFilter);

applySort();
applyFilter();
