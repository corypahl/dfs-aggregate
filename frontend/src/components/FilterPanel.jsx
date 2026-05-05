import React from "react";
import { POSITION_PILL_EMPTY_TEXT } from "../utils.js";

export default function FilterPanel({
  positionOptions,
  selectedPositions,
  onTogglePosition,
  maxSalary,
  onMaxSalaryChange,
  onClearFilters,
}) {
  return (
    <>
      <div className="filter-panel">
        <label className="filter-control filter-control-select">
          <span className="filter-label">Position</span>
          <div className="position-filter-container">
            {positionOptions.length ? (
              <div className="position-pill-group">
                {positionOptions.map((position) => {
                  const isActive = selectedPositions.includes(position);
                  return (
                    <button
                      key={position}
                      type="button"
                      className={`position-pill${isActive ? " is-active" : ""}`}
                      aria-pressed={isActive ? "true" : "false"}
                      onClick={() => onTogglePosition(position)}
                    >
                      {position}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="position-pill-empty">{POSITION_PILL_EMPTY_TEXT}</div>
            )}
          </div>
        </label>

        <label className="filter-control filter-control-compact">
          <span className="filter-label">Max Salary</span>
          <input
            className="filter-input"
            type="text"
            placeholder="e.g. 6500"
            aria-label="Filter Max Salary"
            value={maxSalary}
            onChange={(event) => onMaxSalaryChange(event.target.value)}
          />
        </label>
      </div>

      <div className="filter-actions">
        <button type="button" className="action-button secondary" onClick={onClearFilters}>
          Clear Filters
        </button>
      </div>
    </>
  );
}
