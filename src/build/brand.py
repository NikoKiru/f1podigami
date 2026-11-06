"""The F1 Podigami brand: the red plate P mark and the stacked wordmark.

One source for the mark, so the header, the mobile drawer and the favicon can't
drift apart. The two cuts through the P's stem are an SVG mask, and a mask id
must be unique wherever the inline SVG appears more than once on a page.
"""

# Two lines to the right of the plate; styled by .brand-kicker / .brand-word.
BRAND_NAME_HTML = (
    '<span class="brand-name">'
    '<span class="brand-kicker">Formula 1</span>'
    '<span class="brand-word">Podigami</span>'
    "</span>"
)


def plate_svg(mask_id: str, css_class: str | None = None, *, standalone: bool = False) -> str:
    """Return the plate mark (64x64) with its mask named ``mask_id``.

    ``css_class`` makes it an inline decorative icon (class + aria-hidden).
    ``standalone`` makes it a self-contained file (xmlns, role, label, newline).
    """
    attrs = ""
    if standalone:
        attrs += ' xmlns="http://www.w3.org/2000/svg" role="img" aria-label="F1 Podigami"'
    if css_class:
        attrs += f' class="{css_class}" aria-hidden="true"'
    svg = (
        f'<svg{attrs} viewBox="0 0 64 64">'
        "<defs>"
        f'<mask id="{mask_id}" maskUnits="userSpaceOnUse" x="-20" y="-20" width="120" height="120">'
        '<rect x="-20" y="-20" width="120" height="120" fill="#fff"/>'
        '<rect x="9" y="44" width="21" height="3" fill="#000"/>'
        '<rect x="9" y="51" width="21" height="3" fill="#000"/>'
        "</mask>"
        "</defs>"
        '<rect width="64" height="64" rx="14" fill="#e10600"/>'
        '<g transform="translate(5 7) scale(.78)">'
        '<g transform="translate(8 0) skewX(-10)">'
        f'<path fill-rule="evenodd" fill="#fff" mask="url(#{mask_id})" '
        'd="M13 58V6H36C46.5 6 54 13.2 54 22.5C54 31.8 46.5 39 36 39H27V58Z '
        'M27 17.5H35.5C39 17.5 41.5 19.7 41.5 22.5C41.5 25.3 39 27.5 35.5 27.5H27Z"/>'
        "</g></g>"
        "</svg>"
    )
    return svg + "\n" if standalone else svg
