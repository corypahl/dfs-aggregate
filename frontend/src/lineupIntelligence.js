import { buildStrategyBadgesByName, computeBlendedProjection, isEligibleForSlot } from "./utils.js";

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

function playerSalary(record) {
  return numericValue(record?.salary) || 0;
}

function lineupSalary(lineup) {
  return lineup.reduce((sum, lineupSlot) => sum + playerSalary(lineupSlot.player), 0);
}

function selectedNames(lineup) {
  return new Set(lineup.map((lineupSlot) => lineupSlot.player?.name).filter(Boolean));
}

function getCandidateBadges(record, selectedPlayers, sport) {
  return buildStrategyBadgesByName([record], selectedPlayers, sport)[record.name] || [];
}

function contextPenaltyForBadges(badges) {
  return badges.reduce((sum, badge) => {
    if (badge.className === "name-badge-warning") {
      return sum + 9;
    }
    return sum - (STRATEGY_BADGE_BOOSTS[badge.key] ?? DEFAULT_STRATEGY_BADGE_BOOST);
  }, 0);
}

function candidateContextScore(record, selectedPlayers, sport) {
  return -contextPenaltyForBadges(getCandidateBadges(record, selectedPlayers, sport));
}

function evaluateLineup(lineup, scorePlayer, sport) {
  const players = lineup.map((lineupSlot) => lineupSlot.player).filter(Boolean);
  const playerScore = players.reduce((sum, player) => sum + scorePlayer(player), 0);
  const totalProjection = players.reduce((sum, player) => sum + Number(computeBlendedProjection(player) || 0), 0);
  const warningPenalty = players.reduce((sum, player) => {
    const otherPlayers = players.filter((otherPlayer) => otherPlayer.name !== player.name);
    const badges = getCandidateBadges(player, otherPlayers, sport);
    return sum + contextPenaltyForBadges(badges);
  }, 0);

  return playerScore + totalProjection * 0.15 - warningPenalty;
}

function uniqueTopCandidates(candidates, scorePlayer) {
  const byScore = [...candidates].sort((left, right) => scorePlayer(right) - scorePlayer(left));
  const byValue = [...candidates].sort((left, right) => {
    const leftValue = numericValue(left.avg_value) ?? scorePlayer(left);
    const rightValue = numericValue(right.avg_value) ?? scorePlayer(right);
    return rightValue - leftValue;
  });
  const bySalary = [...candidates].sort((left, right) => playerSalary(left) - playerSalary(right));
  const seen = new Set();
  const merged = [];

  [...byScore.slice(0, CANDIDATE_LIMIT), ...byValue.slice(0, 10), ...bySalary.slice(0, 8)].forEach((candidate) => {
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

  const scorePlayer = createCashScorer(records);
  const salaryCap = numericValue(slate?.salary_cap) || 0;
  const startingLineup = lineupTemplate.slots.map((slot, index) => ({
    slot,
    player: preserveCurrent ? lineup[index]?.player || null : null,
  }));
  const startingSalary = lineupSalary(startingLineup);
  if (salaryCap > 0 && startingSalary > salaryCap) {
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
      score: startingLineup.reduce((sum, lineupSlot) => sum + scorePlayer(lineupSlot.player), 0),
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
        const nextSalary = partial.salary + playerSalary(candidate);
        if (salaryCap > 0 && nextSalary > salaryCap) {
          return;
        }
        const nextLineup = partial.lineup.map((lineupSlot, index) =>
          index === openSlot.index ? { ...lineupSlot, player: candidate } : lineupSlot,
        );
        const nextNames = new Set(partial.names);
        nextNames.add(candidate.name);
        nextPartials.push({
          lineup: nextLineup,
          names: nextNames,
          salary: nextSalary,
          score: partial.score + scorePlayer(candidate) + candidateContextScore(candidate, selectedPlayers, sport),
        });
      });
    });

    partials = nextPartials.sort((left, right) => right.score - left.score).slice(0, BEAM_SIZE);
  });

  const completeLineups = partials.filter((partial) => partial.lineup.every((lineupSlot) => lineupSlot.player));
  if (!completeLineups.length) {
    return null;
  }

  const best = completeLineups
    .map((partial) => ({
      ...partial,
      finalScore: evaluateLineup(partial.lineup, scorePlayer, sport),
    }))
    .sort((left, right) => right.finalScore - left.finalScore)[0];

  return {
    lineup: best.lineup,
    salary: best.salary,
    score: best.finalScore,
    projection: best.lineup.reduce((sum, lineupSlot) => sum + Number(computeBlendedProjection(lineupSlot.player) || 0), 0),
  };
}

export function buildBestAvailableBySlot({ records = [], lineup = [], slate, sport }) {
  const lineupTemplate = slate?.lineup_template;
  if (!lineupTemplate?.slots?.length) {
    return [];
  }
  const scorePlayer = createCashScorer(records);
  const currentNames = selectedNames(lineup);
  const selectedPlayers = lineup.map((lineupSlot) => lineupSlot.player).filter(Boolean);
  const remainingSalary =
    (numericValue(slate?.salary_cap) || 0) > 0 ? (numericValue(slate?.salary_cap) || 0) - lineupSalary(lineup) : null;
  const openSlotLabels = [...new Set(lineup.filter((lineupSlot) => !lineupSlot.player).map((lineupSlot) => lineupSlot.slot))];

  return openSlotLabels
    .map((slot) => {
      const best = records
        .filter((record) => !currentNames.has(record.name) && isEligibleForSlot(record, slot, lineupTemplate))
        .filter((record) => remainingSalary === null || playerSalary(record) <= remainingSalary)
        .map((record) => {
          const badges = getCandidateBadges(record, selectedPlayers, sport);
          const cashScore = scorePlayer(record) + candidateContextScore(record, selectedPlayers, sport);
          return {
            slot,
            player: record,
            cashScore,
            projection: computeBlendedProjection(record),
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

  const scorePlayer = createCashScorer(records);
  const salaryCap = numericValue(slate?.salary_cap) || 0;
  const currentSalary = lineupSalary(lineup);
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
      const currentProjection = Number(computeBlendedProjection(currentPlayer) || 0);
      const currentScore =
        scorePlayer(currentPlayer) + candidateContextScore(currentPlayer, selectedWithoutCurrent, sport);
      const availableSalary = salaryCap > 0 ? salaryCap - (currentSalary - playerSalary(currentPlayer)) : null;

      const bestReplacement = records
        .filter((record) => record.name !== currentPlayer.name && !currentNames.has(record.name))
        .filter((record) => isEligibleForSlot(record, lineupSlot.slot, lineupTemplate))
        .filter((record) => availableSalary === null || playerSalary(record) <= availableSalary)
        .map((record) => {
          const nextProjection = Number(computeBlendedProjection(record) || 0);
          const nextScore = scorePlayer(record) + candidateContextScore(record, selectedWithoutCurrent, sport);
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
