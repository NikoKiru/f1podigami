// Light/dark theme toggle. The initial theme is applied by a tiny inline
// script in <head> (to avoid a flash); this wires up the nav toggle button
// and keeps the browser chrome colour (theme-color meta) in sync.
(function () {
    var root = document.documentElement;
    var btn = document.getElementById("theme-toggle");
    var meta = document.querySelector('meta[name="theme-color"]');

    function apply(theme) {
        root.setAttribute("data-theme", theme);
        if (meta) {
            meta.setAttribute(
                "content",
                getComputedStyle(root).getPropertyValue("--bg").trim()
            );
        }
        if (btn) {
            btn.setAttribute("aria-pressed", String(theme === "light"));
        }
    }

    // The head script already set data-theme; resync the meta colour to it.
    apply(root.getAttribute("data-theme") === "light" ? "light" : "dark");

    if (btn) {
        btn.addEventListener("click", function () {
            var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
            try {
                localStorage.setItem("theme", next);
            } catch (e) {
                /* storage unavailable — toggle still works for the session */
            }
            apply(next);
        });
    }
})();
