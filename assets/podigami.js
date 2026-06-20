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

    // Wikipedia race-report URL — same source the Ergast/Jolpica API cites.
    function wikiUrl(season, name) {
        return 'https://en.wikipedia.org/wiki/' +
            encodeURIComponent((season + ' ' + name).replace(/ /g, '_'));
    }

    const prefersReduced =
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let settleTimer = null;

    // Swap the list content + readout for a season (no animation).
    function applyContent(year) {
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
            const url = wikiUrl(year, fr.raceName);
            return `<li class="tl-item">
                <span class="trio trio-sm">${names}</span>
                <a class="tl-where" href="${url}" target="_blank" rel="noopener"
                   title="${esc(year + ' ' + fr.raceName)} &mdash; race report">R${esc(fr.round)} &middot; ${esc(fr.raceName)}</a>
            </li>`;
        }).join('');

        bars.forEach(b => b.classList.toggle('on', b.dataset.season === year));
    }

    // Render a season, easing the list height from its current size to the new
    // one so seasons with very different trio counts don't snap the layout.
    function render(year) {
        year = String(year);
        if (prefersReduced) {
            applyContent(year);
            return;
        }

        const startH = listEl.getBoundingClientRect().height;
        // Drop any in-flight animation so we can measure the natural target.
        listEl.style.transition = 'none';
        listEl.style.height = 'auto';
        applyContent(year);
        const endH = listEl.getBoundingClientRect().height;

        if (startH === endH) {
            listEl.style.height = '';
            return;
        }

        // Pin to the old height, then transition to the new one. All of this is
        // synchronous, so the browser never paints the intermediate snap.
        listEl.style.height = startH + 'px';
        listEl.style.overflow = 'hidden';
        void listEl.offsetHeight; // force reflow so the next change animates
        listEl.style.transition = 'height 0.28s cubic-bezier(0.22, 0.61, 0.36, 1)';
        listEl.style.height = endH + 'px';

        clearTimeout(settleTimer);
        settleTimer = setTimeout(() => {
            // Release to natural height once settled (handles late reflows).
            listEl.style.transition = '';
            listEl.style.height = '';
            listEl.style.overflow = '';
        }, 300);
    }

    // Coalesce the slider's rapid input events to one render per frame, always
    // using the latest value — keeps scrubbing smooth instead of thrashing.
    let pending = false;
    slider.addEventListener('input', () => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => {
            pending = false;
            render(slider.value);
        });
    });

    bars.forEach(b => b.addEventListener('click', () => {
        slider.value = b.dataset.season;
        render(b.dataset.season);
    }));

    render(slider.value);
})();
