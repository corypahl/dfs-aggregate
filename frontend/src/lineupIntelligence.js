import {
  buildStrategyBadgesByName,
  computeBlendedProjection,
  computeSlotProjection,
  computeSlotSalary,
  getSlotPointMultiplier,
  isEligibleForSlot,
} from "./utils.js";

const CASH_COMPONENTS = [
  { key: "avg_projection", weight: 0.34 },
  { key: "grade", weight: 0.32 },
  { key: "avg_value", weight: 0.18 },
  { key: "implied_team_total", weight: 0.07, normalized: true },
  { key: "moneyline", weight: 0.04, normalized: true, lowerIsBetter: true },
  { key: "anytime_goal_odds", weight: 0.05, normalized: true, lowerIsBetter: true },
];

const BEAM_SIZE = 1600;
const CANDIDATE_LIMIT = 28;
const DEFAULT_STRATEGY_BADGE_BOOST = 1.5;
const STRATEGY_BADGE_BOOSTS = {
  "mlb-team-bat": 0.35,
};

function numericValue(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function clampScore(value) {
  return Math.max(0, Math.min(100, value));
}

function buildStats(records) {
  return CASH_COMPONENTS.reduce((stats, component) => {
    if (!component.normalized) {
      return stats;
    }
    const values = records.map((record) => numericValue(record[component.key])).filter((value) => value !== null);
    stats[component.key] = {
      min: values.length ? Math.min(...values) : null,
      max: values.length ? Math.max(...values) : null,
    };
    return stats;
  }, {});
}

function normalizedScore(value, stats, lowerIsBetter = false) {
  const numeric = numericValue(value);
  if (numeric === null || !stats || stats.min === null || stats.max === null) {
    return null;
  }
  if (stats.max <= stats.min) {
    return 100;
  }
  const ratio = (numeric - stats.min) / (stats.max - stats.min);
  const adjustedRatio = lowerIsBetter ? 1 - ratio : ratio;
  return clampScore(adjustedRatio * 100);
}

export function createCashScorer(records = []) {
  const stats = buildStats(records);
  const scoreCache = new Map();

  return function scorePlayer(record) {
    if (!record) {
      return 0;
    }
    if (scoreCache.has(record)) {
      return scoreCache.get(record);
    }

    let weightedTotal = 0;
    let totalWeight = 0;
    CASH_COMPONENTS.forEach((component) => {
      const componentScore = component.normalized
        ? normalizedScore(record[component.key], stats[component.key], component.lowerIsBetter)
        : numericValue(record[component.key]);
      if (componentScore === null) {
        return;
      }
      weightedTotal += clampScore(componentScore) * component.weight;
      totalWeight += component.weight;
    });

    const score = totalWeight ? weightedTotal / totalWeight : 0;
    scoreCache.set(record, score);
    return score;
  };
}

function isSingleGameSlate(slate) {
  return String(slate?.contest_type || "").replace(/[^a-z]/gi, "").toLowerCase() === "singlegame";
}

function createSingleGameScorer(records = []) {
  const projections = records
    .map((record) => numericValue(computeBlendedProjection(record)))
    .filter((value) => value !== null);
  const projectionStats = {
    min: projections.length ? Math.min(...projections) : null,
    max: projections.length ? Math.max(...projections) : null,
  };

  return function scoreSingleGamePlayer(record) {
    if (!record) {
      return 0;
    }
    const projectionScore = normalizedScore(computeBlendedProjection(record), projectionStats) ?? 0;
    const gradeScore = numericValue(record.grade) ?? projectionScore;
    const valueScore = numericValue(record.avg_value) ?? projectionScore;
    return projectionScore * 0.7 + gradeScore * 0.2 + valueScore * 0.1;
  };
}

function createLineupScorer(records, slate) {
  if (!isSingleGameSlate(slate)) {
    return createCashScorer(records);
  }
  const lineupTemplate = slate?.lineup_template;
  const eligibleRecords = records.filter((record) =>
    (lineupTemplate?.slots || []).some((slot) => isEligibleForSlot(record, slot, lineupTemplate)),
  );
  return createSingleGameScorer(eligibleRecords);
}

function playerSalary(record) {
  return numericValue(record?.salary) || 0;
}

function lineupSalary(lineup, lineupTemplate) {
  return lineup.reduce(
    (sum, lineupSlot) => sum + computeSlotSalary(lineupSlot.player, lineupSlot.slot, lineupTemplate),
    0,
  );
}

function selectedNames(lineup) {
  return new Set(lineup.map((lineupSlot) => lineupSlot.player?.name).filter(Boolean));
}

function getCandidateBadges(record, selectedPlayers, sport, slate) {
  return buildStrategyBadgesByName([record], selectedPlayers, sport, slate?.contest_type)[record.name] || [];
}

function contextPenaltyForBadges(badges) {
  return badges.reduce((sum, badge) => {
    if (badge.className === "name-badge-warning") {
      return sum + 9;
    }
    return sum - (STRATEGY_BADGE_BOOSTS[badge.key] ?? DEFAULT_STRATEGY_BADGE_BOOST);
  }, 0);
}

function candidateContextScore(record, selectedPlayers, sport, slate) {
  return -contextPenaltyForBadges(getCandidateBadges(record, selectedPlayers, sport, slate));
}

function singleGameScriptScore(lineup) {
  const counts = lineup.reduce((byTeam, lineupSlot) => {
    const team = String(lineupSlot.player?.team || "").trim().toUpperCase();
    if (team) {
      byTeam.set(team, (byTeam.get(team) || 0) + 1);
    }
    return byTeam;
  }, new Map());
  if (counts.size !== 2) {
    return 0;
  }

  const split = [...counts.values()].sort((left, right) => right - left).join("-");
  if (split === "4-2") {
    return 5;
  }
  if (split === "3-3") {
    return 3;
  }
  if (split === "5-1") {
    return 1;
  }
  return 0;
}

function respectsTeamRules(lineup, lineupTemplate, requireMinimumTeams = false) {
  const teamCounts = lineup.reduce((counts, lineupSlot) => {
    const team = String(lineupSlot.player?.team || "").trim().toUpperCase();
    if (team) {
      counts.set(team, (counts.get(team) || 0) + 1);
    }
    return counts;
  }, new Map());
  const maxPlayersPerTeam = numericValue(lineupTemplate?.max_players_per_team);
  if (maxPlayersPerTeam !== null && [...teamCounts.values()].some((count) => count > maxPlayersPerTeam)) {
    return false;
  }
  const minimumTeams = numericValue(lineupTemplate?.min_teams);
  return !requireMinimumTeams || minimumTeams === null || teamCounts.size >= minimumTeams;
}

function evaluateLineup(lineup, scorePlayer, sport, slate) {
  const players = lineup.map((lineupSlot) => lineupSlot.player).filter(Boolean);
  const lineupTemplate = slate?.lineup_template;
  const playerScore = lineup.reduce(
    (sum, lineupSlot) => sum + scorePlayer(lineupSlot.player) * getSlotPointMultiplier(lineupSlot.slot, lineupTemplate),
    0,
  );
  const totalProjection = lineup.reduce(
    (sum, lineupSlot) => sum + computeSlotProjection(lineupSlot.player, lineupSlot.slot, lineupTemplate),
    0,
  );
  const warningPenalty = players.reduce((sum, player) => {
    const otherPlayers = players.filter((otherPlayer) => otherPlayer.name !== player.name);
    const badges = getCandidateBadges(player, otherPlayers, sport, slate);
    return sum + contextPenaltyForBadges(badges);
  }, 0);
  const gameScriptScore = isSingleGameSlate(slate) ? singleGameScriptScore(lineup) : 0;

  return playerScore + totalProjection * 0.15 - warningPenalty + gameScriptScore;
}

function uniqueTopCandidates(candidates, scorePlayer) {
  const byScore = [...candidates].sort((left, right) => scorePlayer(right) - scorePlayer(left));
  const byValue = [...candidates].sort((left, right) => {
    const leftValue = numericValue(left.avg_value) ?? scorePlayer(left);
    const rightValue = numericValue(right.avg_value) ?? scorePlayer(right);
    return rightValue - leftValue;
  });
  const bySalary = [...candidates].sort((left, right) => playerSalary(left) - playerSalary(right));
  const byProjection = [...candidates].sort(
    (left, right) => Number(computeBlendedProjection(right) || 0) - Number(computeBlendedProjection(left) || 0),
  );
  const seen = new Set();
  const merged = [];

  [
    ...byScore.slice(0, CANDIDATE_LIMIT),
    ...byProjection.slice(0, 12),
    ...byValue.slice(0, 10),
    ...bySalary.slice(0, 8),
  ].forEach((candidate) => {
    if (!seen.has(candidate.name)) {
      seen.add(candidate.name);
      merged.push(candidate);
    }
  });

  return merged;
}

function buildCandidateSlots(records, lineup, lineupTemplate, scorePlayer) {
  const usedNames = selectedNames(lineup);
  return lineup
    .map((lineupSlot, index) => ({ ...lineupSlot, index }))
    .filter((lineupSlot) => !lineupSlot.player)
    .map((lineupSlot) => {
      const candidates = records.filter(
        (record) => !usedNames.has(record.name) && isEligibleForSlot(record, lineupSlot.slot, lineupTemplate),
      );
      return {
        index: lineupSlot.index,
        slot: lineupSlot.slot,
        candidates: uniqueTopCandidates(candidates, scorePlayer),
        candidateCount: candidates.length,
      };
    })
    .sort((left, right) => left.candidateCount - right.candidateCount || left.index - right.index);
}

export function optimizeLineup({
  records = [],
  slate,
  lineup = [],
  sport,
  preserveCurrent = true,
}) {
  const lineupTemplate = slate?.lineup_template;
  if (!lineupTemplate?.slots?.length) {
    return null;
  }

  const scorePlayer = createLineupScorer(records, slate);
  const salaryCap = numericValue(slate?.salary_cap) || 0;
  const startingLineup = lineupTemplate.slots.map((slot, index) => ({
    slot,
    player: preserveCurrent ? lineup[index]?.player || null : null,
  }));
  const startingSalary = lineupSalary(startingLineup, lineupTemplate);
  if ((salaryCap > 0 && startingSalary > salaryCap) || !respectsTeamRules(startingLineup, lineupTemplate)) {
    return null;
  }

  const openSlots = buildCandidateSlots(records, startingLineup, lineupTemplate, scorePlayer);
  if (openSlots.some((slot) => !slot.candidates.length)) {
    return null;
  }

  let partials = [
    {
      lineup: startingLineup,
      names: selectedNames(startingLineup),
      salary: startingSalary,
      score: startingLineup.reduce(
        (sum, lineupSlot) => sum + scorePlayer(lineupSlot.player) * getSlotPointMultiplier(lineupSlot.slot, lineupTemplate),
        0,
      ),
    },
  ];

  openSlots.forEach((openSlot) => {
    const nextPartials = [];
    partials.forEach((partial) => {
      const selectedPlayers = partial.lineup.map((lineupSlot) => lineupSlot.player).filter(Boolean);
      openSlot.candidates.forEach((candidate) => {
        if (partial.names.has(candidate.name)) {
          return;
        }
        const nextSalary = partial.salary + computeSlotSalary(candidate, openSlot.slot, lineupTemplate);
        if (salaryCap > 0 && nextSalary > salaryCap) {
          return;
        }
        const nextLineup = partial.lineup.map((lineupSlot, index) =>
          index === openSlot.index ? { ...lineupSlot, player: candidate } : lineupSlot,
        );
        const nextNames = new Set(partial.names);
        nextNames.add(candidate.name);
        if (!respectsTeamRules(nextLineup, lineupTemplate)) {
          return;
        }
        nextPartials.push({
          lineup: nextLineup,
          names: nextNames,
          salary: nextSalary,
          score:
            partial.score +
            scorePlayer(candidate) * getSlotPointMultiplier(openSlot.slot, lineupTemplate) +
            candidateContextScore(candidate, selectedPlayers, sport, slate),
        });
      });
    });

    partials = nextPartials.sort((left, right) => right.score - left.score).slice(0, BEAM_SIZE);
  });

  const completeLineups = partials.filter(
    (partial) =>
      partial.lineup.every((lineupSlot) => lineupSlot.player) &&
      respectsTeamRules(partial.lineup, lineupTemplate, true),
  );
  if (!completeLineups.length) {
    return null;
  }

  const best = completeLineups
    .map((partial) => ({
      ...partial,
      finalScore: evaluateLineup(partial.lineup, scorePlayer, sport, slate),
    }))
    .sort((left, right) => right.finalScore - left.finalScore)[0];

  return {
    lineup: best.lineup,
    salary: best.salary,
    score: best.finalScore,
    projection: best.lineup.reduce(
      (sum, lineupSlot) => sum + computeSlotProjection(lineupSlot.player, lineupSlot.slot, lineupTemplate),
      0,
    ),
  };
}

export function buildBestAvailableBySlot({ records = [], lineup = [], slate, sport }) {
  const lineupTemplate = slate?.lineup_template;
  if (!lineupTemplate?.slots?.length) {
    return [];
  }
  const scorePlayer = createLineupScorer(records, slate);
  const currentNames = selectedNames(lineup);
  const selectedPlayers = lineup.map((lineupSlot) => lineupSlot.player).filter(Boolean);
  const remainingSalary =
    (numericValue(slate?.salary_cap) || 0) > 0
      ? (numericValue(slate?.salary_cap) || 0) - lineupSalary(lineup, lineupTemplate)
      : null;
  const openSlotLabels = [...new Set(lineup.filter((lineupSlot) => !lineupSlot.player).map((lineupSlot) => lineupSlot.slot))];

  return openSlotLabels
    .map((slot) => {
      const targetIndex = lineup.findIndex((lineupSlot) => !lineupSlot.player && lineupSlot.slot === slot);
      const best = records
        .filter((record) => !currentNames.has(record.name) && isEligibleForSlot(record, slot, lineupTemplate))
        .filter((record) => remainingSalary === null || computeSlotSalary(record, slot, lineupTemplate) <= remainingSalary)
        .filter((record) => {
          const nextLineup = lineup.map((lineupSlot, index) =>
            index === targetIndex ? { ...lineupSlot, player: record } : lineupSlot,
          );
          return respectsTeamRules(nextLineup, lineupTemplate);
        })
        .map((record) => {
          const badges = getCandidateBadges(record, selectedPlayers, sport, slate);
          const cashScore =
            scorePlayer(record) * getSlotPointMultiplier(slot, lineupTemplate) +
            candidateContextScore(record, selectedPlayers, sport, slate);
          return {
            slot,
            player: record,
            cashScore,
            projection: computeSlotProjection(record, slot, lineupTemplate),
            badges,
          };
        })
        .sort((left, right) => right.cashScore - left.cashScore)[0];
      return best || null;
    })
    .filter(Boolean);
}

export function buildSwapSuggestions({ records = [], lineup = [], slate, sport, limit = 3 }) {
  const lineupTemplate = slate?.lineup_template;
  if (!lineupTemplate?.slots?.length) {
    return [];
  }

  const scorePlayer = createLineupScorer(records, slate);
  const salaryCap = numericValue(slate?.salary_cap) || 0;
  const currentSalary = lineupSalary(lineup, lineupTemplate);
  const currentNames = selectedNames(lineup);

  return lineup
    .map((lineupSlot, index) => {
      if (!lineupSlot.player) {
        return null;
      }
      const selectedWithoutCurrent = lineup
        .filter((_, lineupIndex) => lineupIndex !== index)
        .map((slot) => slot.player)
        .filter(Boolean);
      const currentPlayer = lineupSlot.player;
      const currentProjection = computeSlotProjection(currentPlayer, lineupSlot.slot, lineupTemplate);
      const currentScore =
        scorePlayer(currentPlayer) * getSlotPointMultiplier(lineupSlot.slot, lineupTemplate) +
        candidateContextScore(currentPlayer, selectedWithoutCurrent, sport, slate);
      const availableSalary =
        salaryCap > 0
          ? salaryCap - (currentSalary - computeSlotSalary(currentPlayer, lineupSlot.slot, lineupTemplate))
          : null;

      const bestReplacement = records
        .filter((record) => record.name !== currentPlayer.name && !currentNames.has(record.name))
        .filter((record) => isEligibleForSlot(record, lineupSlot.slot, lineupTemplate))
        .filter(
          (record) => availableSalary === null || computeSlotSalary(record, lineupSlot.slot, lineupTemplate) <= availableSalary,
        )
        .filter((record) => {
          const nextLineup = lineup.map((slot, lineupIndex) =>
            lineupIndex === index ? { ...slot, player: record } : slot,
          );
          const requireMinimumTeams = nextLineup.every((slot) => slot.player);
          return respectsTeamRules(nextLineup, lineupTemplate, requireMinimumTeams);
        })
        .map((record) => {
          const nextProjection = computeSlotProjection(record, lineupSlot.slot, lineupTemplate);
          const nextScore =
            scorePlayer(record) * getSlotPointMultiplier(lineupSlot.slot, lineupTemplate) +
            candidateContextScore(record, selectedWithoutCurrent, sport, slate);
          return {
            out: currentPlayer,
            in: record,
            slot: lineupSlot.slot,
            scoreDelta: nextScore - currentScore,
            projectionDelta: nextProjection - currentProjection,
          };
        })
        .sort((left, right) => right.scoreDelta - left.scoreDelta || right.projectionDelta - left.projectionDelta)[0];

      return bestReplacement && (bestReplacement.scoreDelta > 0.1 || bestReplacement.projectionDelta > 0.1)
        ? bestReplacement
        : null;
    })
    .filter(Boolean)
    .sort((left, right) => right.scoreDelta - left.scoreDelta || right.projectionDelta - left.projectionDelta)
    .slice(0, limit);
}
