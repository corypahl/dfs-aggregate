import React from "react";

export default function Toolbar({
  pageMode,
  sportOptions,
  pendingSport,
  onSportChange,
  slateOptions,
  selectedSlateKey,
  onSlateChange,
  statusText,
  isRefreshing,
  onRefresh,
}) {
  const isStatic = pageMode === "static";

  return (
    <div className="toolbar">
      <div className="toolbar-copy">
        <span className="section-label">{isStatic ? "GitHub Pages" : "React Frontend"}</span>
        <div className="toolbar-title">{isStatic ? "Static sport snapshot" : "Aggregate controls"}</div>
      </div>
      <div className="actions">
        <span className="status">{statusText}</span>
        {isStatic ? <span className="status-note">Static snapshot. Use GitHub Actions to rebuild.</span> : null}
        <select className="toolbar-select" aria-label="Select sport" value={pendingSport} onChange={(event) => onSportChange(event.target.value)}>
          {sportOptions.map((sportOption) => (
            <option key={sportOption.key} value={sportOption.key}>
              {sportOption.label}
            </option>
          ))}
        </select>
        <select
          className="toolbar-select"
          aria-label="Select slate"
          value={selectedSlateKey}
          onChange={(event) => onSlateChange(event.target.value)}
        >
          {slateOptions.map((slate) => (
            <option key={slate.key} value={slate.key}>
              {slate.label}
            </option>
          ))}
        </select>
        {!isStatic ? (
          <button type="button" className="action-button primary" onClick={onRefresh} disabled={isRefreshing}>
            {isRefreshing ? "Refreshing..." : "Refresh Data"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
