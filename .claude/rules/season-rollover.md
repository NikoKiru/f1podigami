---
paths:
  - "src/check_update_due.py"
  - "src/compute/compute_podigami.py"
  - "src/compute/compute_scorecard.py"
  - "src/fetch/fetch_schedule.py"
  - "src/fetch/fetch_constructor_standings.py"
  - "src/fetch/fetch_current_drivers.py"
  - "src/build/team_colors.py"
---

## The season boundary

The site first crossed a season boundary going into 2027, so none of this has been seen live yet. It was rehearsed on 2026-11-01 by faking the rest of 2026 and the start of 2027 on a copy of `data/` and running the compute steps and the build at each stage.

What happens by itself, in order:

1. **The final race lands.** `pick_next_race` returns None. Nothing is due: no session is pending.
2. **The calendar lands.** `is_calendar_due` is the only thing that can start a run now. Each scheduled tick looks up next season's calendar, standard library only, and a difference starts a normal pipeline. `wait_for_results.py` reports `true` rather than `none`, or the pipeline would be skipped. `fetch_schedule.choose_season_races` moves on once every date of the old season has passed. On 2026-11-01 OpenF1 already had 2027's meetings and Jolpica didn't, so expect Jolpica to be the late one.
3. **Before the opener** the same lookup catches moved dates and newly published session times, which is what arms the guard.
4. **Opener qualifying** arms like any other. `postQuali` is built from the session's own entrants, so a rookie or a driver in a new car is right from here on. `pending_qualifiers` adds new names to the grid.
5. **After the opener** `current_drivers.json` narrows to the real field, and seats come from `race_results.json`. Cars must never depend on the standings: with empty standings every driver used to be predicted in an unknown car, which showed a brand-new trio at 83%.

Each stage fails towards the old season's data, never towards an empty file, because an empty schedule or standings file breaks the page and CI.

### What needs a person

None of these stop the site. Each degrades one thing until it's done:

- **`DATA_PUSH_TOKEN`** was last set on 2026-06-27 and lasts a year at most, so it runs out during the 2027 season at the latest. When it lapses, data updates stop silently. Rotate it before the season.
- **New or renamed team:** add it to `TEAM_COLORS` (`src/build/team_colors.py`; unknown teams show grey) and `TEAM_TO_CONSTRUCTOR` (`src/fetch/fetch_openf1.py`; an unknown name fails the fast lane closed, so results wait for Jolpica).
- **New race name:** add it to `ACCEPTABLE_SLUGS` (`src/fetch/race_identity.py`; unknown names link to Wikipedia instead of F1).
- **New host country:** check it has a flag (`src/build/flags.py`).
- **New regulations:** add the season to `REG_RESET_SEASONS` (`src/compute/model_v2.py`) in a year the cars change, so the ratings widen. 2027 isn't one.

### Rehearsing

Fake the results on a copy of `data/`, run the compute steps in `src/update.py`'s order, then `src/build_site.py`, and read the page. `python src/check_update_due.py --now <ISO>` shows what the guard would do on any date.
