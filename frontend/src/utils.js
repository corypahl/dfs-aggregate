export const COLUMN_DEFS = [
  { key: "name", label: "Name", type: "text" },
  { key: "rw_position", label: "RW Position", type: "text" },
  { key: "salary", label: "Salary", type: "number", currency: true },
  { key: "fd_projection", label: "FD Proj", type: "number", bar: true },
  { key: "fd_value", label: "FD Value", type: "number", bar: true },
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

export function metricBarColor(ratio) {
  const hue = 120 * ratio;
  return `hsl(${Math.round(hue)} 72% 45%)`;
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

export function buildPlayerBadges(record, positionBadges = []) {
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

  return [...sourceBadges, ...positionBadges];
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
