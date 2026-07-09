// Overdue page: reveal a card's stat cells on mobile via the "Details" toggle.
// Desktop keeps the stats visible (CSS hides the button), so this is a no-op there.
document.querySelectorAll('.od-toggle').forEach(btn => {
    const card = btn.closest('.odcard');
    if (!card) return;
    btn.addEventListener('click', () => {
        const open = card.classList.toggle('od-open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
});
