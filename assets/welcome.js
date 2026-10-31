// First-visit card: points a new visitor at the FAQ, once. The card sits hidden
// in the page, so without JS nobody sees it. Showing it counts as seen, dismissed
// or not, and a visitor we can't remember never gets it, because to them every
// page load would be a first visit.
(function () {
    var KEY = "welcomed";
    var DELAY_MS = 1000;
    var card = document.getElementById("welcome");
    var seen;

    if (!card || location.hash === "#faq") return;
    try {
        seen = localStorage.getItem(KEY);
    } catch (e) {
        return;
    }
    if (seen) return;

    function close() {
        card.hidden = true;
        document.removeEventListener("keydown", onKeydown);
    }

    function onKeydown(e) {
        if (e.key === "Escape") close();
    }

    card.querySelector(".welcome-close").addEventListener("click", close);
    // Closed here too: on the landing page this link only moves down the page.
    card.querySelector(".welcome-link").addEventListener("click", close);

    setTimeout(function () {
        try {
            localStorage.setItem(KEY, "1");
        } catch (e) {
            return;
        }
        card.hidden = false;
        document.addEventListener("keydown", onKeydown);
    }, DELAY_MS);
})();
