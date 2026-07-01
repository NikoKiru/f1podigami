"""Pydantic schemas — the data contracts for every committed ``data/*.json``.

Field names match the JSON keys verbatim (camelCase) so a load -> dump round-trip
reproduces each file byte-for-byte; see ``tests/test_datalib.py``. Every model
forbids unknown keys, so a typo or an unexpected field fails validation instead
of silently passing through.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    """Shared config: reject unknown keys to make each schema a strict contract."""

    model_config = ConfigDict(extra="forbid")


# --- Shared references -------------------------------------------------------


class RaceRef(_Base):
    season: str
    round: str
    raceName: str


class RaceLink(_Base):
    """Official F1 result-page identifiers for one race (see fetch_race_links)."""

    id: str
    slug: str


class DriverRef(_Base):
    driverId: str
    name: str


# --- podiums.json ------------------------------------------------------------


class Podium(_Base):
    season: str
    round: str
    raceName: str
    p1: DriverRef
    p2: DriverRef
    p3: DriverRef


# --- combos.json -------------------------------------------------------------


class Combo(_Base):
    drivers: list[str]
    driverIds: list[str]
    count: int
    lastRace: RaceRef
    firstRace: RaceRef
    lastRaceKey: int
    races: list[RaceRef]


# --- soulmates.json ----------------------------------------------------------


class SoulmateDriver(_Base):
    name: str
    total: int
    medianYear: int


class SoulmatePair(_Base):
    a: str
    b: str
    count: int
    firstYear: int
    lastYear: int


class Soulmates(_Base):
    drivers: list[SoulmateDriver]
    matrix: list[list[int]]
    max: int
    topPairs: list[SoulmatePair]


# --- current_drivers.json ----------------------------------------------------


class CurrentDriver(_Base):
    driverId: str
    name: str
    # code (3-letter TLA) and number (permanent car number) come straight from the API
    # and either may be absent for some drivers, so fetch_current_drivers omits them.
    code: str | None = None
    number: str | None = None


class CurrentDrivers(_Base):
    season: str
    drivers: list[CurrentDriver]


# --- driver_races.json -------------------------------------------------------


class DriverRaceRow(_Base):
    name: str
    starts: int
    races: list[int]


class DriverRaces(_Base):
    drivers: dict[str, DriverRaceRow]


# --- overdue.json ------------------------------------------------------------


class OverduePerDriver(_Base):
    name: str
    podiums: int
    starts: int
    rate: float


class OverdueTrio(_Base):
    driverIds: list[str]
    names: list[str]
    racesTogether: int
    score: float
    perDriver: list[OverduePerDriver]


class OverdueParams(_Base):
    poolN: int
    topN: int


class Overdue(_Base):
    params: OverdueParams
    asOf: RaceRef
    allTime: list[OverdueTrio]
    currentGrid: list[OverdueTrio]


# --- unlikeliest.json --------------------------------------------------------


class UnlikeliestPerDriver(_Base):
    name: str
    podiums: int
    starts: int
    rate: float


class UnlikeliestTrio(_Base):
    driverIds: list[str]
    names: list[str]
    racesTogether: int
    score: float
    count: int
    happened: RaceRef
    perDriver: list[UnlikeliestPerDriver]


class UnlikeliestParams(_Base):
    topN: int


class Unlikeliest(_Base):
    params: UnlikeliestParams
    asOf: RaceRef
    trios: list[UnlikeliestTrio]


# --- schedule.json -----------------------------------------------------------


class ScheduleRace(_Base):
    round: str
    raceName: str
    date: str
    time: str
    circuitId: str
    circuitName: str
    locality: str
    country: str
    lat: str
    long: str
    url: str
    # Track-outline fields: present for ~all circuits, but absent ones are tolerated
    # (see the >=80% coverage check in tests/test_data_integrity.py).
    trackPath: str | None = None
    trackViewBox: str | None = None
    lengthKm: float | None = None


class Schedule(_Base):
    season: str
    totalRounds: int
    races: list[ScheduleRace]


# --- podigami.json -----------------------------------------------------------


class PodigamiParams(_Base):
    model: str
    alpha: float
    halfLife: float
    offSeason: float
    seasonBoost: float
    temperature: float
    usingConstructors: bool
    carOverlay: bool


class DriverStrength(_Base):
    """A driver's modelled strength — shared by ``candidates[].perDriver`` and ``driverForm``.

    ``constructor``/``constructorStrength`` exist only when the live constructor overlay is
    active; compute omits them off-season (see ``compute_podigami._driver_entry``), so they
    are optional.
    """

    driverId: str
    name: str
    weight: float
    seasonPodiums: int
    recentPodiums: int
    constructorId: str
    constructor: str | None = None
    constructorStrength: float | None = None


class PodigamiCandidate(_Base):
    driverIds: list[str]
    names: list[str]
    prob: float
    perDriver: list[DriverStrength]


class RoundRace(_Base):
    """A race reference without the season (the season is the ``bySeason`` key)."""

    round: str
    raceName: str


class SeasonDebut(_Base):
    driverIds: list[str]
    names: list[str]
    firstRace: RoundRace


class Podigami(_Base):
    currentSeason: str
    asOf: RaceRef
    params: PodigamiParams
    gridSize: int
    chanceNextRaceNew: float
    candidates: list[PodigamiCandidate]
    driverForm: list[DriverStrength]
    bySeason: dict[str, list[SeasonDebut]]
    seasonCounts: dict[str, int]
    seasonRange: list[int]


# --- model_eval.json ---------------------------------------------------------


class EvalWindow(_Base):
    validation: list[int]
    test: list[int]


class ModelParams(_Base):
    halfLife: float
    offSeason: float
    seasonBoost: float
    posWeights: list[float]
    temperature: float


class LadderRow(_Base):
    model: str
    n: int
    top1: float
    top3: float
    top5: float
    logLoss: float
    brierSet: float
    brierNew: float


class Chosen(_Base):
    n: int
    top1: float
    top3: float
    top5: float
    logLoss: float
    brierSet: float
    brierNew: float
    baseRateNew: float
    brierNewBaseRate: float
    ece: float


class CalibrationBin(_Base):
    lo: float
    hi: float
    n: int
    meanPred: float | None = None
    obsRate: float | None = None


class ModelEval(_Base):
    evalWindow: EvalWindow
    modelParams: ModelParams
    ladder: list[LadderRow]
    chosen: Chosen
    calibration: list[CalibrationBin]
    poolNote: str


# --- constructor_standings.json ----------------------------------------------


class Constructor(_Base):
    constructorId: str
    name: str
    points: float
    position: int
    wins: int


class ConstructorStandings(_Base):
    season: str
    round: str
    constructors: list[Constructor]
    driverConstructor: dict[str, str]
