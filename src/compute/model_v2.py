"""Dynamic Bayesian rating engine for podium prediction (model v2, pure math).

Every driver d and constructor c carries a Gaussian belief over its log-worth
(θ_d and β_c); a race entry's strength is s = θ_d + β_c. Race finishing order,
an attrition order (reverse Plackett-Luce over who failed first) and the
qualifying order are all observed through the same closed-form truncated
Plackett-Luce update (one Laplace/assumed-density-filtering step per session,
Weng-Lin style — no sampling), with per-channel power weights. Between races
the beliefs diffuse: a little every race, more at season boundaries, a lot for
constructors when the technical regulations reset.

The Hessian used for each state is the diagonal of the PL log-likelihood
(cross-terms dropped), the standard ADF simplification; a constructor shared
by several entries gets ONE update with its entries' gradients/Hessians summed.

Constructor identity follows team lineage across rebrands/purchases
(``CONSTRUCTOR_LINEAGE``), so e.g. Racing Bulls inherits AlphaTauri's state.
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model  # noqa: E402  (v1 module: the exact 6-permutation set-probability math)

__all__ = [
    "DEFAULT_PARAMS_V2",
    "REG_RESET_SEASONS",
    "CONSTRUCTOR_LINEAGE",
    "CircuitStats",
    "Gauss",
    "HistoryFilter",
    "RatingEngine",
    "ReliabilityTracker",
    "classify_status",
    "lineage_root",
    "model",
    "predict_race",
]

# Locked by the walk-forward tuner (backtest.py --tune-v2) on 2010-2018:
# coordinate descent on trio logLoss + novelty logLoss, J 4.628 -> 4.401.
# Notable: qualifying earns a large weight, the attrition channel earns none
# (reliability already carries the DNF signal), and a podium-focused
# truncation depth of 3 beats deeper race-order likelihoods.
DEFAULT_PARAMS_V2: dict = {
    "sigma0_drv": 0.5,  # prior std of a driver's log-worth
    "sigma0_con": 1.6,  # prior std of a constructor's log-worth (cars matter more)
    "rookie_mu": -0.8,  # prior mean for a debuting driver
    "newteam_mu": -1.2,  # prior mean for a brand-new constructor
    "tau_drv": 0.02,  # per-race diffusion (std) of driver states
    "tau_con": 0.08,  # per-race diffusion (std) of constructor states
    "season_var_drv": 0.03,  # variance added to drivers at each season boundary
    "season_var_con": 0.2,  # variance added to constructors at each season boundary
    "reg_var_con": 0.5,  # extra constructor variance when regulations reset
    "depth_race": 3,  # truncate the race-order likelihood to the top-N picks
    "w_attr": 0.0,  # power weight of the attrition (reverse-PL) channel
    "depth_qual": 6,  # truncation depth for the qualifying order
    "w_qual": 0.6,  # power weight of the qualifying channel
    "rel_half_life": 40.0,  # races for a DNF's reliability influence to halve
    "chaos_gamma": 1.0,  # weight of circuit DNF-rate delta on finish odds
    "chaos_eta": 0.7,  # exponent on the circuit displacement temperature
    "p_wild": 0.0,  # probability a race is "wild" (safety cars, rain, chaos)
    "t_wild": 2.5,  # temperature multiplier applied in a wild race
    # Post-quali grid term (grid_offsets): PROVISIONAL until backtest.py
    # --tune-v2-grid locks them on 2010-2018 (see the tuning task).
    "w_grid": 0.1,  # weight of the causal grid-position term
    "grid_circuit_beta": 0.5,  # circuit modulation: disp_ratio ** (-beta)
}

# Seasons whose technical regulations changed enough to scramble the car order.
REG_RESET_SEASONS = {1961, 1966, 1989, 2009, 2014, 2022, 2026}

# child constructorId -> lineage root id, so a rebrand/purchase keeps its rating.
# Where the modern id collides with an unrelated historic works team of the same
# name (mercedes, honda, alfa, aston_martin), the decades-long gap plus season and
# regulation variance resets make the conflation numerically irrelevant.
CONSTRUCTOR_LINEAGE: dict[str, str] = {
    # Minardi -> Toro Rosso -> AlphaTauri -> RB (Racing Bulls)
    "toro_rosso": "minardi",
    "alphatauri": "minardi",
    "rb": "minardi",
    # Jordan -> MF1 -> Spyker -> Force India -> Racing Point -> Aston Martin
    "mf1": "jordan",
    "spyker": "jordan",
    "spyker_mf1": "jordan",
    "force_india": "jordan",
    "racing_point": "jordan",
    "aston_martin": "jordan",
    # Tyrrell -> BAR -> Honda -> Brawn -> Mercedes
    "bar": "tyrrell",
    "honda": "tyrrell",
    "brawn": "tyrrell",
    "mercedes": "tyrrell",
    # Toleman -> Benetton -> Renault -> Lotus F1 -> Renault -> Alpine
    "benetton": "toleman",
    "renault": "toleman",
    "lotus_f1": "toleman",
    "alpine": "toleman",
    # Sauber -> BMW Sauber -> Sauber -> Alfa Romeo -> Sauber -> Audi
    "bmw_sauber": "sauber",
    "alfa": "sauber",
    "audi": "sauber",
    # Stewart -> Jaguar -> Red Bull
    "jaguar": "stewart",
    "red_bull": "stewart",
    # Ligier -> Prost
    "prost": "ligier",
    # Arrows ran as Footwork 1991-96
    "footwork": "arrows",
    # Virgin -> Marussia -> Manor
    "marussia": "virgin",
    "manor": "virgin",
    # Team Lotus (2010-11) -> Caterham
    "caterham": "lotus_racing",
}


def lineage_root(cid: str) -> str:
    return CONSTRUCTOR_LINEAGE.get(cid, cid)


# Status strings that indicate a driver-side racing incident (as opposed to a
# car failure, which is the default for anything unrecognised).
_INC_STATUSES = {
    "Accident",
    "Collision",
    "Collision damage",
    "Damage",
    "Debris",
    "Spun off",
    "Fatal accident",
    "Injury",
    "Injured",
    "Illness",
    "Driver unwell",
    "Eye injury",
    "Physical",
}

_DSQ_STATUSES = {"Disqualified", "Excluded"}

# Entries that never took the start: invisible to pace, attrition and reliability.
_EXCLUDED_STATUSES = {
    "Did not start",
    "Did not qualify",
    "Did not prequalify",
    "Withdrew",
    "Withdrawn",
    "107% Rule",
}


def classify_status(status: str) -> str:
    """Bucket a verbatim Ergast status string.

    'finished' | 'mech' (car failure) | 'inc' (driver incident) | 'dsq' | 'excluded'.
    Unknown strings default to 'mech': the long tail of statuses ("Halfshaft",
    "Fuel pipe", ...) is overwhelmingly component failures.
    """
    # "Lapped" / "Not classified" ran to the flag (too few laps to classify):
    # the car survived, so they count as finishes for reliability purposes.
    if status == "Finished" or status.startswith("+") or status in ("Lapped", "Not classified"):
        return "finished"
    if status in _INC_STATUSES:
        return "inc"
    if status in _DSQ_STATUSES:
        return "dsq"
    if status in _EXCLUDED_STATUSES:
        return "excluded"
    return "mech"


@dataclass
class Gauss:
    """A Gaussian belief over one latent log-worth."""

    mu: float
    var: float


_VAR_MIN = 1e-6
_VAR_MAX = 25.0


def _clamp_var(v: float) -> float:
    return min(_VAR_MAX, max(_VAR_MIN, v))


class RatingEngine:
    """Gaussian driver + constructor states with closed-form truncated-PL updates."""

    def __init__(self, params: dict):
        self.params = params
        self._drivers: dict[str, Gauss] = {}
        self._constructors: dict[str, Gauss] = {}

    def driver(self, did: str) -> Gauss:
        st = self._drivers.get(did)
        if st is None:
            p = self.params
            st = Gauss(p["rookie_mu"], _clamp_var(p["sigma0_drv"] ** 2))
            self._drivers[did] = st
        return st

    def constructor(self, cid: str) -> Gauss:
        root = lineage_root(cid)
        st = self._constructors.get(root)
        if st is None:
            p = self.params
            st = Gauss(p["newteam_mu"], _clamp_var(p["sigma0_con"] ** 2))
            self._constructors[root] = st
        return st

    def combined(self, did: str, cid: str) -> tuple[float, float]:
        """Mean and variance of the entry strength s = θ_d + β_c."""
        d, c = self.driver(did), self.constructor(cid)
        return d.mu + c.mu, d.var + c.var

    def advance_race(self) -> None:
        td2 = self.params["tau_drv"] ** 2
        tc2 = self.params["tau_con"] ** 2
        for st in self._drivers.values():
            st.var = _clamp_var(st.var + td2)
        for st in self._constructors.values():
            st.var = _clamp_var(st.var + tc2)

    def advance_season(self, new_season: int) -> None:
        p = self.params
        extra = p["reg_var_con"] if new_season in REG_RESET_SEASONS else 0.0
        for st in self._drivers.values():
            st.var = _clamp_var(st.var + p["season_var_drv"])
        for st in self._constructors.values():
            st.var = _clamp_var(st.var + p["season_var_con"] + extra)

    def observe_order(
        self,
        entries: list[tuple[str, str]],
        *,
        depth: int | None = None,
        weight: float = 1.0,
        sign: int = 1,
    ) -> None:
        """One ADF step on an observed decomposition order.

        ``entries`` lists (driverId, constructorId) in pick order — winner first
        for a finishing/qualifying order; first *failure* first with ``sign=-1``
        for the attrition channel. ``depth`` truncates the likelihood to the
        first N picks (the tail is treated as an unranked pool); ``weight`` is
        the channel's power weight κ.
        """
        m = len(entries)
        if m < 2 or weight <= 0.0:
            return
        r = m - 1 if depth is None else max(1, min(depth, m - 1))

        states = [(self.driver(d), self.constructor(c)) for d, c in entries]
        s = [max(-30.0, min(30.0, sign * (ds.mu + cs.mu))) for ds, cs in states]
        w = [math.exp(v) for v in s]
        Z = [0.0] * (m + 1)  # Z[j] = Σ_{i>=j} w_i (the stage-j normaliser)
        for j in range(m - 1, -1, -1):
            Z[j] = Z[j + 1] + w[j]

        pref1 = pref2 = 0.0
        grads: list[float] = []
        hesss: list[float] = []
        for i in range(m):
            if i < r:
                inv = 1.0 / Z[i]
                pref1 += inv
                pref2 += inv * inv
            g = (1.0 if i < r else 0.0) - w[i] * pref1
            h = w[i] * pref1 - w[i] * w[i] * pref2
            grads.append(sign * g)
            hesss.append(max(h, 0.0))

        # Drivers step individually; each constructor steps ONCE on its summed g/h.
        con_acc: dict[str, list[float]] = {}
        for ((d_st, _), (_, cid)), g, h in zip(
            zip(states, entries, strict=True), grads, hesss, strict=True
        ):
            self._nudge(d_st, g, h, weight)
            acc = con_acc.setdefault(lineage_root(cid), [0.0, 0.0])
            acc[0] += g
            acc[1] += h
        for root, (g, h) in con_acc.items():
            self._nudge(self._constructors[root], g, h, weight)

    @staticmethod
    def _nudge(st: Gauss, g: float, h: float, weight: float) -> None:
        """Scalar Kalman-style step: precision grows by κ·h, mean moves along κ·g."""
        denom = 1.0 + st.var * weight * h
        st.mu += st.var * weight * g / denom
        st.var = _clamp_var(st.var / denom)


# Era fallbacks for the very first race, before any hazard data exists.
_ERA_MECH_0 = 0.10
_ERA_INC_0 = 0.05


class ReliabilityTracker:
    """Exponentially-decayed, Beta-shrunk DNF hazards.

    Two channels: mechanical failures ('mech') are charged to the constructor
    lineage, incidents ('inc') to the driver. Every other outcome passed in
    ('finished', 'dsq') is a clean start. Each hazard is shrunk toward the
    current *decayed era rate*, so a fresh entrant inherits the era hazard and
    a lone old DNF fades with half-life ``half_life`` races.
    """

    def __init__(self, half_life: float, prior_k: float = 30.0):
        self.decay = 0.5 ** (1.0 / half_life)
        self.prior_k = prior_k
        self._con: dict[str, list[float]] = {}  # lineage root -> [mech events, starts]
        self._drv: dict[str, list[float]] = {}  # driverId -> [inc events, starts]
        self._era_mech = [0.0, 0.0]  # [events, starts], same decay
        self._era_inc = [0.0, 0.0]

    def observe_race(self, rows: list[tuple[str, str, str]]) -> None:
        """``rows``: (driverId, constructorId, outcome) for every entry that started."""
        d = self.decay
        for sums in self._con.values():
            sums[0] *= d
            sums[1] *= d
        for sums in self._drv.values():
            sums[0] *= d
            sums[1] *= d
        for sums in (self._era_mech, self._era_inc):
            sums[0] *= d
            sums[1] *= d
        for did, cid, outcome in rows:
            con = self._con.setdefault(lineage_root(cid), [0.0, 0.0])
            drv = self._drv.setdefault(did, [0.0, 0.0])
            con[1] += 1.0
            drv[1] += 1.0
            self._era_mech[1] += 1.0
            self._era_inc[1] += 1.0
            if outcome == "mech":
                con[0] += 1.0
                self._era_mech[0] += 1.0
            elif outcome == "inc":
                drv[0] += 1.0
                self._era_inc[0] += 1.0

    def _hazard(self, sums: list[float], era: list[float], era0: float) -> float:
        era_rate = era[0] / era[1] if era[1] > 0.0 else era0
        return (self.prior_k * era_rate + sums[0]) / (self.prior_k + sums[1])

    def p_finish(self, did: str, cid: str) -> float:
        mech = self._hazard(
            self._con.get(lineage_root(cid), [0.0, 0.0]), self._era_mech, _ERA_MECH_0
        )
        inc = self._hazard(self._drv.get(did, [0.0, 0.0]), self._era_inc, _ERA_INC_0)
        return (1.0 - mech) * (1.0 - inc)


_CIRCUIT_SHRINK_N = 8.0  # visits for a circuit's character to earn ~half weight


class CircuitStats:
    """Per-circuit chaos character: DNF propensity and grid->finish displacement.

    Both signals are expressed *relative to the global average* and shrunk
    toward neutral by n/(n+8) visits, so an unknown circuit is exactly neutral
    (temp 1.0, DNF delta 0).
    """

    def __init__(self):
        # circuit -> [visits, dnfs, starters, disp_sum, disp_races]
        self._c: dict[str, list[float]] = {}
        self._g = [0.0, 0.0, 0.0, 0.0, 0.0]

    def observe_race(
        self, circuit_id: str, starters: int, dnfs: int, mean_disp: float | None
    ) -> None:
        rec = self._c.setdefault(circuit_id, [0.0] * 5)
        for r in (rec, self._g):
            r[0] += 1.0
            r[1] += float(dnfs)
            r[2] += float(starters)
            if mean_disp is not None:
                r[3] += float(mean_disp)
                r[4] += 1.0

    def disp_ratio(self, circuit_id: str) -> float:
        """Shrunk grid->finish displacement ratio vs the global mean.

        1.0 = neutral/unknown; clamped to [0.5, 2.2]. Low = processional
        (finish follows the grid), high = high-churn.
        """
        rec = self._c.get(circuit_id)
        if not rec or rec[4] <= 0.0 or self._g[4] <= 0.0:
            return 1.0
        g_disp = self._g[3] / self._g[4]
        if g_disp <= 0.0:
            return 1.0
        w = rec[4] / (rec[4] + _CIRCUIT_SHRINK_N)
        ratio = 1.0 + w * (rec[3] / rec[4] / g_disp - 1.0)
        return min(2.2, max(0.5, ratio))

    def temp(self, circuit_id: str, eta: float) -> float:
        """Softmax temperature multiplier: >1 at high-churn circuits."""
        return self.disp_ratio(circuit_id) ** eta

    def dnf_logodds_delta(self, circuit_id: str) -> float:
        """Shrunk log-odds gap between this circuit's DNF rate and the global one."""
        rec = self._c.get(circuit_id)
        if not rec or rec[2] <= 0.0 or self._g[2] <= 0.0:
            return 0.0

        def logit(p: float) -> float:
            p = min(0.97, max(0.03, p))
            return math.log(p / (1.0 - p))

        w = rec[0] / (rec[0] + _CIRCUIT_SHRINK_N)
        return w * (logit(rec[1] / rec[2]) - logit(self._g[1] / self._g[2]))


class HistoryFilter:
    """Predict-then-update pass over the chronological race history.

    ``step`` first applies the between-race dynamics, then snapshots every
    entrant's (mu_s, var_s, p_finish) plus the circuit temperature *before*
    the race outcome touches any state — the snapshot is exactly what a
    forecast made on race morning could have known (leakage-free) — and only
    then feeds the outcome through the qualifying, pace, attrition,
    reliability and circuit channels.
    """

    def __init__(self, params: dict):
        self.params = params
        self.engine = RatingEngine(params)
        self.reliability = ReliabilityTracker(params["rel_half_life"])
        self.circuits = CircuitStats()
        self.season: int | None = None

    def step(self, race: dict, quali: dict | None = None) -> dict:
        p = self.params
        season = int(race["season"])
        if self.season is not None:
            if season != self.season:
                self.engine.advance_season(season)
            else:
                self.engine.advance_race()
        self.season = season

        circuit = race.get("circuitId", "")
        rows: list[dict] = []
        seen_dids: set[str] = set()
        for row in race["results"]:
            # DNS/DNQ/withdrawn entries never took the start: invisible everywhere.
            # Shared drives (1950s) keep only the driver's first row.
            if classify_status(row["status"]) == "excluded" or row["driverId"] in seen_dids:
                continue
            seen_dids.add(row["driverId"])
            rows.append(row)

        # ---- snapshot (strictly before any update) ----
        delta = p["chaos_gamma"] * self.circuits.dnf_logodds_delta(circuit)
        drivers = {
            row["driverId"]: (
                *self.engine.combined(row["driverId"], row["constructorId"]),
                self.p_finish_adjusted(row["driverId"], row["constructorId"], delta),
            )
            for row in rows
        }
        snapshot = {
            "drivers": drivers,
            "temp": self.circuits.temp(circuit, p["chaos_eta"]),
            "season": season,
        }

        # ---- channel 1: qualifying order ----
        if quali is not None and p["w_qual"] > 0.0:
            qentries: list[tuple[str, str]] = []
            qseen: set[str] = set()
            for q in sorted(quali["results"], key=lambda q: q["position"]):
                if q["driverId"] not in qseen:
                    qseen.add(q["driverId"])
                    qentries.append((q["driverId"], q["constructorId"]))
            self.engine.observe_order(qentries, depth=int(p["depth_qual"]), weight=p["w_qual"])

        # ---- channel 2: race pace (classified finishing order) ----
        classified = sorted(
            (r for r in rows if r["position"] is not None), key=lambda r: r["position"]
        )
        self.engine.observe_order(
            [(r["driverId"], r["constructorId"]) for r in classified],
            depth=int(p["depth_race"]),
            weight=1.0,
        )

        # ---- channel 3: attrition (reverse PL: first failure picked first) ----
        dnfs = sorted(
            (r for r in rows if classify_status(r["status"]) in ("mech", "inc")),
            key=lambda r: (r["laps"], r["driverId"]),
        )
        if dnfs and p["w_attr"] > 0.0:
            entries = [(r["driverId"], r["constructorId"]) for r in dnfs]
            entries += [(r["driverId"], r["constructorId"]) for r in reversed(classified)]
            self.engine.observe_order(entries, depth=len(dnfs), weight=p["w_attr"], sign=-1)

        # ---- reliability + circuit character ----
        outcomes = [(r["driverId"], r["constructorId"], classify_status(r["status"])) for r in rows]
        self.reliability.observe_race(outcomes)
        n_dnf = sum(1 for _, _, o in outcomes if o in ("mech", "inc"))
        disp = [abs(r["grid"] - r["position"]) for r in classified if r["grid"] > 0]
        self.circuits.observe_race(
            circuit,
            starters=len(rows),
            dnfs=n_dnf,
            mean_disp=(sum(disp) / len(disp)) if disp else None,
        )
        return snapshot

    def p_finish_adjusted(self, did: str, cid: str, circuit_delta: float = 0.0) -> float:
        """Clamped finish probability with the circuit's DNF log-odds shift applied."""
        p0 = min(0.995, max(0.02, self.reliability.p_finish(did, cid)))
        if circuit_delta:
            z = math.log(p0 / (1.0 - p0)) - circuit_delta
            p0 = 1.0 / (1.0 + math.exp(-z))
        return min(0.995, max(0.02, p0))


def predict_race(
    entrants: list[str],
    mu_var: dict[str, tuple[float, float]],
    p_fin: dict[str, float],
    temp: float,
    params: dict,
    seen: set[tuple[str, str, str]],
    *,
    n_draws: int = 512,
    seed: int = 20260704,
    screen: int = 250,
) -> dict:
    """Rao-Blackwellised podium-set distribution for one race.

    Each deterministic-seed draw samples skill noise, survivor Bernoullis and a
    wild-race temperature flag, then adds the *exact* conditional PL trio
    probabilities (no top-3 sampling noise). P(new trio) is the exact
    complement of the tracked seen trios, so only unseen trios need screening
    (closed-form top-``screen`` at the mean).
    """
    rng = random.Random(seed)
    ids = sorted(entrants)
    id_set = set(ids)
    seen_here = {t for t in seen if all(d in id_set for d in t)}

    lam0 = {d: math.exp(max(-30.0, min(30.0, mu_var[d][0]))) for d in ids}
    base = model.all_set_probs(lam0, ids)  # screening only: rank plausible unseen trios
    screened = [t for t, _ in sorted(base.items(), key=lambda kv: -kv[1]) if t not in seen_here][
        :screen
    ]
    track = dict.fromkeys(screened, 0.0) | dict.fromkeys(sorted(seen_here), 0.0)

    used = 0
    for _ in range(n_draws):
        s = {d: mu_var[d][0] + rng.gauss(0.0, 1.0) * math.sqrt(mu_var[d][1]) for d in ids}
        alive = [d for d in ids if rng.random() < p_fin[d]]
        t_eff = temp * (params["t_wild"] if rng.random() < params["p_wild"] else 1.0)
        if len(alive) < 3:
            continue
        used += 1
        w = {d: math.exp(max(-30.0, min(30.0, s[d] / t_eff))) for d in alive}
        tot = sum(w.values())
        aset = set(alive)
        for t in track:
            if t[0] in aset and t[1] in aset and t[2] in aset:
                track[t] += model.pl_set_prob(t, w, tot)

    probs = {t: v / max(used, 1) for t, v in track.items()}
    p_new = 1.0 - sum(probs[t] for t in sorted(seen_here))
    ranked_new = sorted(
        ((t, p) for t, p in probs.items() if t not in seen_here), key=lambda kv: (-kv[1], kv[0])
    )
    return {"trio_probs": probs, "p_new": p_new, "ranked_new": ranked_new, "draws_used": used}
