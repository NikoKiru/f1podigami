// Podigami timeline: drag the slider (or click a sparkline bar) to show the
// trios that debuted on a podium in the selected season.
(function () {
    const blob = document.getElementById('podigami-data');
    if (!blob) return;
    const data = JSON.parse(blob.textContent);
    const bySeason = data.bySeason || {};

    const slider = document.getElementById('tl-slider');
    const yearEl = document.getElementById('tl-year');
    const countEl = document.getElementById('tl-count');
    const listEl = document.getElementById('tl-list');
    const bars = Array.from(document.querySelectorAll('.tl-bar'));

    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function render(year) {
        year = String(year);
        const entries = bySeason[year] || [];
        yearEl.textContent = year;
        countEl.textContent = entries.length
            ? `${entries.length} new tri${entries.length === 1 ? 'o' : 'os'}`
            : 'no new trios';

        listEl.innerHTML = entries.map(e => {
            const names = e.names
                .map(n => `<span class="pdriver">${esc(n)}</span>`)
                .join('<span class="sep">/</span>');
            const fr = e.firstRace;
            return `<li class="tl-item">
                <span class="trio trio-sm">${names}</span>
                <span class="tl-where">R${esc(fr.round)} &middot; ${esc(fr.raceName)}</span>
            </li>`;
        }).join('');

        bars.forEach(b => b.classList.toggle('on', b.dataset.season === year));
    }

    slider.addEventListener('input', () => render(slider.value));
    bars.forEach(b => b.addEventListener('click', () => {
        slider.value = b.dataset.season;
        render(b.dataset.season);
    }));

    render(slider.value);
})();
