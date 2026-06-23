// Podigami timeline: drag the slider (or click a sparkline bar) to show the
// trios that debuted on a podium in the selected season.
(function () {
    const blob = document.getElementById('podigami-data');
    if (!blob) return;
    const data = JSON.parse(blob.textContent);
    const bySeason = data.bySeason || {};

    const slider = document.getElementById('tl-slider');
    const select = document.getElementById('tl-select');
    const yearEl = document.getElementById('tl-year');
    const countEl = document.getElementById('tl-count');
    const listEl = document.getElementById('tl-list');
    const bars = Array.from(document.querySelectorAll('.tl-bar'));

    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // Broadcast-style full name: "First MIDDLE? LASTNAME" (surname uppercased).
    // On narrow screens, abbreviate to "F. LASTNAME" so trios fit.
    const narrowQ = window.matchMedia('(max-width: 600px)');
    let narrow = narrowQ.matches;
    narrowQ.addEventListener('change', e => {
        narrow = e.matches;
        render(slider.value);
    });

    function displayName(name) {
        const parts = name.trim().split(/\s+/);
        if (parts.length === 0) return name;
        const surname = parts[parts.length - 1].toUpperCase();
        if (narrow) return parts[0][0] + '. ' + surname;
        parts[parts.length - 1] = surname;
        return parts.join(' ');
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
                .map(n => `<span class="pdriver">${esc(displayName(n))}</span>`)
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
        if (select) select.value = year;
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

    if (select) {
        select.addEventListener('change', () => {
            slider.value = select.value;
            render(select.value);
        });
    }

    render(slider.value);
})();

// Info tooltips: desktop reveals on hover (CSS), but touch has no hover, so a
// tap toggles the .open class here. Tapping outside, tapping the same icon, or
// pressing Escape all dismiss it — so a bubble is never stuck open on mobile.
(function () {
    const tips = Array.from(document.querySelectorAll('.info-tip'));
    if (!tips.length) return;

    function closeAll(except) {
        tips.forEach(t => {
            if (t !== except) {
                t.classList.remove('open');
                t.setAttribute('aria-expanded', 'false');
            }
        });
    }

    tips.forEach(tip => {
        tip.setAttribute('role', 'button');
        tip.setAttribute('aria-expanded', 'false');

        tip.addEventListener('click', e => {
            e.stopPropagation(); // don't let the document handler close it instantly
            const willOpen = !tip.classList.contains('open');
            closeAll(tip);
            tip.classList.toggle('open', willOpen);
            tip.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
        });

        tip.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                tip.click();
            } else if (e.key === 'Escape') {
                closeAll(null);
                tip.blur();
            }
        });
    });

    document.addEventListener('click', () => closeAll(null));
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') closeAll(null);
    });
})();

// Next-race box: show the race time in the visitor's local timezone and tick a
// live countdown. Reads the ISO datetime baked into the box at build time.
(function () {
    const box = document.querySelector('.next-race[data-datetime]');
    if (!box) return;
    const when = new Date(box.getAttribute('data-datetime'));
    if (isNaN(when.getTime())) return;

    const dateEl = box.querySelector('.nr-date');
    const cdEl = box.querySelector('.nr-countdown');

    if (dateEl) {
        try {
            const local = when.toLocaleString(undefined, {
                weekday: 'short', day: 'numeric', month: 'short',
                hour: '2-digit', minute: '2-digit',
            });
            dateEl.textContent = `${local} (your time)`;
        } catch (e) { /* keep the server-rendered UTC fallback */ }
    }

    function tick() {
        let diff = Math.floor((when.getTime() - Date.now()) / 1000);
        if (diff <= 0) {
            if (cdEl) cdEl.textContent = 'Lights out — race underway';
            return false;
        }
        const d = Math.floor(diff / 86400); diff -= d * 86400;
        const h = Math.floor(diff / 3600); diff -= h * 3600;
        const m = Math.floor(diff / 60);
        const s = diff - m * 60;
        const pad = n => String(n).padStart(2, '0');
        if (cdEl) {
            cdEl.textContent =
                (d > 0 ? d + 'd ' : '') + pad(h) + 'h ' + pad(m) + 'm ' + pad(s) + 's';
        }
        return true;
    }

    if (tick()) {
        const id = setInterval(() => { if (!tick()) clearInterval(id); }, 1000);
    }
})();
