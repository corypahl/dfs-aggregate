export const COLUMN_DEFS = [
  { key: "name", label: "Name", type: "text" },
  { key: "rw_position", label: "RW Position", type: "text" },
  { key: "salary", label: "Salary", type: "number", currency: true },
  { key: "fd_projection", label: "FD Proj", type: "number", bar: true, fanduelOnly: true },
  { key: "fd_value", label: "FD Value", type: "number", bar: true, fanduelOnly: true },
  { key: "rw_projection", label: "RW Proj", type: "number", bar: true },
  { key: "rw_value", label: "RW Value", type: "number", bar: true },
  { key: "avg_projection", label: "Avg Proj", type: "number", bar: true, percent: true },
  { key: "avg_value", label: "Avg Value", type: "number", bar: true, percent: true },
  { key: "grade", label: "Grade", type: "number", bar: true },
];

export const POSITION_PILL_EMPTY_TEXT = "No positions available for the current sport.";

export function formatNumber(value, options = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }

  const numericValue = Number(value);
  if (options.currency) {
    return numericValue.toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
  }
  if (options.percent) {
    return `${numericValue.toFixed(1)}%`;
  }
  return numericValue.toFixed(2);
}

export function parseMaxSalary(value) {
  const normalized = String(value || "").replace(/[$,\s]+/g, "");
  if (!normalized) {
    return null;
  }

  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

export function compareValues(left, right, type) {
  if (left === null || left === undefined || left === "") {
    return right === null || right === undefined || right === "" ? 0 : 1;
  }
  if (right === null || right === undefined || right === "") {
    return -1;
  }

  if (type === "number") {
    return Number(left) - Number(right);
  }

  return String(left).localeCompare(String(right), undefined, {
    sensitivity: "base",
  });
}

export function buildMetricStats(records) {
  return COLUMN_DEFS.reduce((stats, column) => {
    if (!column.bar) {
      return stats;
    }

    const values = records
      .map((record) => record[column.key])
      .filter((value) => value !== null && value !== undefined)
      .map((value) => Number(value));

    stats[column.key] = {
      min: values.length ? Math.min(...values) : null,
      max: values.length ? Math.max(...values) : null,
    };
    return stats;
  }, {});
}

export function metricRatio(value, stats) {
  if (value === null || value === undefined || !stats) {
    return 0;
  }

  const minValue = stats.min;
  const maxValue = stats.max;
  if (minValue === null || maxValue === null) {
    return 0;
  }
  if (maxValue <= minValue) {
    return 1;
  }

  const ratio = (Number(value) - minValue) / (maxValue - minValue);
  return Math.max(0, Math.min(1, ratio));
}

export function metricBackgroundColor(ratio) {
  if (ratio >= 0.95) {
    return "#dcfce7";
  }
  if (ratio >= 0.9) {
    return "#fef9c3";
  }
  if (ratio >= 0.85) {
    return "#ffedd5";
  }
  return "#fee2e2";
}

function hasNumericValue(record, key) {
  return record[key] !== null && record[key] !== undefined && Number.isFinite(Number(record[key]));
}

function getAllowedPositions(slot, lineupTemplate) {
  return lineupTemplate?.position_map?.[slot] || [slot];
}

function isEligibleForSlot(record, slot, lineupTemplate) {
  const playerPositions = record.builder_position_values || [];
  const allowedPositions = getAllowedPositions(slot, lineupTemplate);
  return allowedPositions.some((position) => playerPositions.includes(position));
}

function uniqueLineupSlots(lineupTemplate) {
  const seen = new Set();
  return (lineupTemplate?.slots || []).filter((slot) => {
    if (seen.has(slot)) {
      return false;
    }
    seen.add(slot);
    return true;
  });
}

export function buildPositionLeaderBadges(records, lineupTemplate) {
  const badgesByName = {};
  const metrics = [
    { key: "avg_projection", label: "top projection", className: "name-badge-projection" },
    { key: "grade", label: "top grade", className: "name-badge-grade" },
    { key: "avg_value", label: "top value", className: "name-badge-value" },
  ];

  uniqueLineupSlots(lineupTemplate).forEach((slot) => {
    const candidates = records.filter((record) => isEligibleForSlot(record, slot, lineupTemplate));
    metrics.forEach((metric) => {
      const leader = candidates.reduce((best, candidate) => {
        if (!hasNumericValue(candidate, metric.key)) {
          return best;
        }
        if (!best || Number(candidate[metric.key]) > Number(best[metric.key])) {
          return candidate;
        }
        return best;
      }, null);

      if (!leader) {
        return;
      }

      badgesByName[leader.name] = badgesByName[leader.name] || [];
      badgesByName[leader.name].push({
        key: `${slot}-${metric.key}`,
        label: `${slot} ${metric.label}`,
        text: slot,
        className: metric.className,
      });
    });
  });

  return badgesByName;
}

export function buildStrategyBadgesByName(records = [], selectedPlayers = [], sport) {
  const activePlayers = selectedPlayers.filter(Boolean);
  return records.reduce((badgesByName, record) => {
    const badges = buildStrategyBadges(record, activePlayers, sport);
    if (badges.length) {
      badgesByName[record.name] = badges;
    }
    return badgesByName;
  }, {});
}

function buildStrategyBadges(record, selectedPlayers, sport) {
  if (!selectedPlayers.length || selectedPlayers.some((selectedPlayer) => selectedPlayer.name === record.name)) {
    return [];
  }

  const badges = [];
  const normalizedSport = String(sport || "").toLowerCase();
  selectedPlayers.forEach((selectedPlayer) => {
    if (normalizedSport === "nfl" || normalizedSport === "cfb") {
      addFootballStrategyBadges(badges, record, selectedPlayer);
    } else if (normalizedSport === "mlb") {
      addMlbStrategyBadges(badges, record, selectedPlayer);
    } else if (["nba", "wnba", "cbb"].includes(normalizedSport)) {
      addBasketballStrategyBadges(badges, record, selectedPlayers);
    } else if (normalizedSport === "epl") {
      addEplStrategyBadges(badges, record, selectedPlayer);
    }
  });
  return badges;
}

function addFootballStrategyBadges(badges, record, selectedPlayer) {
  if (hasAnyPosition(selectedPlayer, ["QB"]) && sameTeam(record, selectedPlayer) && hasAnyPosition(record, ["WR", "TE"])) {
    addStrategyBadge(badges, "nfl-qb-pair", "QB Pair", `Same-team pass catcher with ${selectedPlayer.name}`, "name-badge-strategy");
  }
  if (hasAnyPosition(selectedPlayer, ["QB"]) && areOpponents(record, selectedPlayer) && isDefense(record)) {
    addStrategyBadge(badges, "nfl-qb-defense-warning", "Avoid", `Opposing defense against selected QB ${selectedPlayer.name}`, "name-badge-warning");
  }
  if (isDefense(selectedPlayer) && areOpponents(record, selectedPlayer) && hasAnyPosition(record, ["QB", "RB", "WR", "TE"])) {
    addStrategyBadge(badges, "nfl-vs-defense", "Vs DEF", `Offensive player against selected defense ${selectedPlayer.name}`, "name-badge-warning");
  }
  if (hasAnyPosition(selectedPlayer, ["RB"]) && sameTeam(record, selectedPlayer) && isDefense(record)) {
    addStrategyBadge(badges, "nfl-rb-defense", "RB+D", `Same-team defense with selected RB ${selectedPlayer.name}`, "name-badge-strategy");
  }
  if (isDefense(selectedPlayer) && sameTeam(record, selectedPlayer) && hasAnyPosition(record, ["RB"])) {
    addStrategyBadge(badges, "nfl-defense-rb", "RB+D", `Same-team RB with selected defense ${selectedPlayer.name}`, "name-badge-strategy");
  }
}

function addMlbStrategyBadges(badges, record, selectedPlayer) {
  if (hasAnyPosition(selectedPlayer, ["P"]) && areOpponents(record, selectedPlayer) && !hasAnyPosition(record, ["P"])) {
    addStrategyBadge(badges, "mlb-vs-pitcher", "Vs P", `Hitter facing selected pitcher ${selectedPlayer.name}`, "name-badge-warning");
  }
  if (!hasAnyPosition(selectedPlayer, ["P"]) && areOpponents(record, selectedPlayer) && hasAnyPosition(record, ["P"])) {
    addStrategyBadge(badges, "mlb-vs-bats", "Vs Bats", `Pitcher facing selected hitter ${selectedPlayer.name}`, "name-badge-warning");
  }
  if (!hasAnyPosition(selectedPlayer, ["P"]) && !hasAnyPosition(record, ["P"]) && sameTeam(record, selectedPlayer)) {
    addStrategyBadge(badges, "mlb-team-bat", "Team Bat", `Same-team hitter with ${selectedPlayer.name}`, "name-badge-strategy");
  }
}

function addBasketballStrategyBadges(badges, record, selectedPlayers) {
  const team = normalizeTeam(record.team);
  if (!team) {
    return;
  }
  const selectedSameTeamCount = selectedPlayers.filter((selectedPlayer) => normalizeTeam(selectedPlayer.team) === team).length;
  if (selectedSameTeamCount >= 2) {
    addStrategyBadge(badges, "basketball-team-x3", "Team x3", "Would be the third player from this team", "name-badge-warning");
  }
}

function addEplStrategyBadges(badges, record, selectedPlayer) {
  if (hasAnyPosition(selectedPlayer, ["GK"]) && sameTeam(record, selectedPlayer) && hasAnyPosition(record, ["D"])) {
    addStrategyBadge(badges, "epl-clean-sheet-pair", "CS Pair", `Clean-sheet pair with selected GK ${selectedPlayer.name}`, "name-badge-strategy");
  }
  if (hasAnyPosition(selectedPlayer, ["D"]) && sameTeam(record, selectedPlayer) && hasAnyPosition(record, ["GK"])) {
    addStrategyBadge(badges, "epl-defender-gk-pair", "CS Pair", `Clean-sheet pair with selected defender ${selectedPlayer.name}`, "name-badge-strategy");
  }
  if ((hasAnyPosition(selectedPlayer, ["GK"]) || hasAnyPosition(selectedPlayer, ["D"])) && areOpponents(record, selectedPlayer) && hasAnyPosition(record, ["F", "M"])) {
    addStrategyBadge(badges, "epl-vs-clean-sheet", "Vs CS", `Attacker against selected clean-sheet player ${selectedPlayer.name}`, "name-badge-warning");
  }
  if (hasAnyPosition(selectedPlayer, ["F", "M"]) && areOpponents(record, selectedPlayer) && (hasAnyPosition(record, ["GK"]) || hasAnyPosition(record, ["D"]))) {
    addStrategyBadge(badges, "epl-vs-attack", "Vs Att", `Defensive player against selected attacker ${selectedPlayer.name}`, "name-badge-warning");
  }
}

function addStrategyBadge(badges, key, text, label, className) {
  if (badges.some((badge) => badge.key === key)) {
    return;
  }
  badges.push({ key, text, label, className });
}

function sameTeam(left, right) {
  const leftTeam = normalizeTeam(left.team);
  const rightTeam = normalizeTeam(right.team);
  return Boolean(leftTeam && rightTeam && leftTeam === rightTeam);
}

function areOpponents(left, right) {
  const leftTeam = normalizeTeam(left.team);
  const rightTeam = normalizeTeam(right.team);
  const leftOpponent = normalizeTeam(left.opponent);
  const rightOpponent = normalizeTeam(right.opponent);
  return Boolean(
    (leftTeam && rightOpponent && leftTeam === rightOpponent) ||
      (rightTeam && leftOpponent && rightTeam === leftOpponent),
  );
}

function normalizeTeam(value) {
  return value ? String(value).trim().toUpperCase() : "";
}

function isDefense(record) {
  return hasAnyPosition(record, ["D", "D/ST", "DST", "DEF"]);
}

function hasAnyPosition(record, positions) {
  const recordPositions = getRecordPositions(record);
  return positions.some((position) => recordPositions.has(position) || positionAliases(position).some((alias) => recordPositions.has(alias)));
}

function getRecordPositions(record) {
  const values = [
    ...(record.builder_position_values || []),
    ...(record.position_filter_values || []),
    ...splitPositionText(record.builder_position),
    ...splitPositionText(record.fd_position),
    ...splitPositionText(record.rw_position),
  ];
  return new Set(values.map((position) => String(position).trim().toUpperCase()).filter(Boolean));
}

function splitPositionText(value) {
  if (!value) {
    return [];
  }
  return String(value)
    .replace("D/ST", "DST_PLACEHOLDER")
    .split("/")
    .map((position) => position.trim().toUpperCase().replace("DST_PLACEHOLDER", "D/ST"))
    .filter(Boolean);
}

function positionAliases(position) {
  const normalized = String(position).trim().toUpperCase();
  const aliases = {
    D: ["D", "DEF", "D/ST", "DST"],
    "D/ST": ["D", "DEF", "D/ST", "DST"],
    DST: ["D", "DEF", "D/ST", "DST"],
    DEF: ["D", "DEF", "D/ST", "DST"],
    F: ["F", "FWD", "FW"],
    M: ["M", "MID"],
    GK: ["GK"],
  };
  return aliases[normalized] || [normalized];
}

export function buildPlayerBadges(record, positionBadges = [], strategyBadges = []) {
  const projectionHot = record.avg_projection !== null && record.avg_projection >= 90;
  const valueHot = record.avg_value !== null && record.avg_value >= 90;
  const sourceBadges = [];

  if (projectionHot && valueHot) {
    sourceBadges.push({ key: "star", label: "Elite projection and value", text: "\u2605", className: "name-badge-star" });
  } else if (valueHot) {
    sourceBadges.push({ key: "value", label: "Elite value", text: "$", className: "name-badge-value" });
  } else if (projectionHot) {
    sourceBadges.push({ key: "projection", label: "Elite projection", text: "\u{1F4AA}", className: "name-badge-projection" });
  }

  return [...sourceBadges, ...positionBadges, ...strategyBadges];
}

export function computeBlendedProjection(record) {
  const values = [record.fd_projection, record.rw_projection].filter((value) => value !== null && value !== undefined);
  if (!values.length) {
    return null;
  }
  return values.reduce((sum, value) => sum + Number(value), 0) / values.length;
}

export function formatSalary(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }
  return Number(value).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}
