import React from "react";
import { buildPlayerBadges, compareValues, formatNumber, metricBarColor, metricRatio } from "../utils.js";

function NameCell({ record, onPlayerSelect, isDisabled, positionBadges }) {
  const badges = buildPlayerBadges(record, positionBadges);

  return (
    <div className="name-cell">
      {onPlayerSelect ? (
        <button
          type="button"
          className={`inline-player-button${isDisabled ? " is-disabled" : ""}`}
          onClick={() => onPlayerSelect(record)}
          disabled={isDisabled}
        >
          {record.name}
        </button>
      ) : (
        <span className="name-text">{record.name}</span>
      )}
      {badges.length > 0 ? (
        <span className="name-badges">
          {badges.map((badge) => (
            <span
              key={badge.key}
              className={`name-badge ${badge.className}`}
              title={badge.label}
              aria-label={badge.label}
            >
              {badge.text}
            </span>
          ))}
        </span>
      ) : null}
    </div>
  );
}

function MetricCell({ value, column, stats }) {
  if (value === null || value === undefined) {
    return <span className="metric-empty" />;
  }

  const ratio = metricRatio(value, stats);
  const width = `${(ratio * 100).toFixed(1)}%`;
  const color = metricBarColor(ratio);
  const display = formatNumber(value, column);

  return (
    <div className="metric-wrap">
      <span className="metric-fill" style={{ width, background: color }} />
      <span className="metric-text">{display}</span>
    </div>
  );
}

export default function AggregateTable({
  columns,
  records,
  metricStats,
  sortKey,
  sortDir,
  onSortChange,
  onPlayerSelect,
  selectedPlayerNames = [],
  canSelectPlayer,
  positionLeaderBadges = {},
}) {
  const sortColumn = columns.find((column) => column.key === sortKey) || columns[0];
  const sortedRecords = [...records].sort((left, right) => {
    const comparison = compareValues(left[sortKey], right[sortKey], sortColumn.type);
    return sortDir === "asc" ? comparison : -comparison;
  });

  return (
    <div className="card">
      <div className="table-shell">
        <table className="aggregate-table">
          <thead>
            <tr className="header-row">
              {columns.map((column) => {
                const indicator = sortKey === column.key ? (sortDir === "asc" ? "↑" : "↓") : "↕";
                return (
                  <th key={column.key}>
                    <button className="sort-button" type="button" onClick={() => onSortChange(column.key, column.type)}>
                      {column.label}
                      <span className="sort-indicator" aria-hidden="true">
                        {indicator}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sortedRecords.map((record) => (
              <tr
                key={`${record.name}-${record.rw_position || "na"}-${record.salary ?? "na"}-${record.fd_projection ?? "na"}-${record.rw_projection ?? "na"}`}
                className={selectedPlayerNames.includes(record.name) ? "is-selected-row" : ""}
              >
                {columns.map((column) => {
                  if (column.key === "name") {
                    const disabled = canSelectPlayer ? !canSelectPlayer(record) : false;
                    return (
                      <td key={column.key}>
                        <NameCell
                          record={record}
                          onPlayerSelect={onPlayerSelect}
                          isDisabled={disabled}
                          positionBadges={positionLeaderBadges[record.name] || []}
                        />
                      </td>
                    );
                  }

                  if (column.bar) {
                    return (
                      <td key={column.key} className="metric-cell">
                        <MetricCell value={record[column.key]} column={column} stats={metricStats[column.key]} />
                      </td>
                    );
                  }

                  return <td key={column.key}>{formatNumber(record[column.key], column) || record[column.key] || ""}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
