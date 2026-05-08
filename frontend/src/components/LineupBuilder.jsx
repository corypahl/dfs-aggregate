import React, { useMemo } from "react";
import {
  buildBestAvailableBySlot,
  buildSwapSuggestions,
  optimizeLineup,
} from "../lineupIntelligence.js";
import { computeBlendedProjection, formatNumber, formatSalary } from "../utils.js";

export function buildEmptyLineup(lineupTemplate) {
  if (!lineupTemplate?.slots?.length) {
    return [];
  }

  return lineupTemplate.slots.map((slot) => ({
    slot,
    player: null,
  }));
}

function formatDelta(value, options = {}) {
  const numeric = Number(value || 0);
  const formatted = options.salary ? formatSalary(Math.abs(numeric)) : formatNumber(Math.abs(numeric));
  return `${numeric >= 0 ? "+" : "-"}${formatted}`;
}

export default function LineupBuilder({ slate, lineup, setLineup, records = [], sport }) {
  const lineupStats = useMemo(() => {
    const totalSalary = lineup.reduce((sum, lineupSlot) => sum + Number(lineupSlot.player?.salary || 0), 0);
    const totalProjection = lineup.reduce(
      (sum, lineupSlot) => sum + Number(computeBlendedProjection(lineupSlot.player || {}) || 0),
      0,
    );
    const openSlots = lineup.filter((lineupSlot) => !lineupSlot.player).length;
    const salaryCap = Number(slate?.salary_cap || 0);
    const remainingSalary = salaryCap - totalSalary;
    const avgPerSlot = openSlots > 0 ? remainingSalary / openSlots : 0;
    return {
      salaryCap,
      totalSalary,
      totalProjection,
      openSlots,
      remainingSalary,
      avgPerSlot,
    };
  }, [lineup, slate?.salary_cap]);

  const bestAvailable = useMemo(
    () => buildBestAvailableBySlot({ records, lineup, slate, sport }).slice(0, 5),
    [lineup, records, slate, sport],
  );
  const swapSuggestions = useMemo(
    () => buildSwapSuggestions({ records, lineup, slate, sport, limit: 3 }),
    [lineup, records, slate, sport],
  );

  const applyOptimizedLineup = (preserveCurrent) => {
    const result = optimizeLineup({
      records,
      slate,
      lineup,
      sport,
      preserveCurrent,
    });
    if (result?.lineup) {
      setLineup(result.lineup);
    }
  };

  const removePlayerFromLineup = (index) => {
    setLineup((current) =>
      current.map((lineupSlot, lineupIndex) =>
        lineupIndex === index
          ? {
              ...lineupSlot,
              player: null,
            }
          : lineupSlot,
      ),
    );
  };

  if (!slate?.builder_enabled) {
    return (
      <section className="builder-section">
        <div className="builder-card">
          <div className="builder-card-header">
            <h2>Lineup Builder</h2>
          </div>
          <p className="builder-note">{slate?.builder_message || "Lineup builder is not available for this slate yet."}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="builder-section">
      <div className="builder-grid">
        <div className="builder-card">
          <div className="builder-card-header">
            <h3>My Lineup</h3>
          </div>
          <div className="builder-table-shell">
            <table className="builder-table">
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Player</th>
                  <th>Team</th>
                  <th>Pos</th>
                  <th>Salary</th>
                  <th>Proj</th>
                  <th>Grade</th>
                </tr>
              </thead>
              <tbody>
                {lineup.map((lineupSlot, index) => {
                  const player = lineupSlot.player;
                  const blendedProjection = computeBlendedProjection(player || {});
                  return (
                    <tr key={`${slate.key}-${lineupSlot.slot}-${index}`}>
                      <td>{lineupSlot.slot}</td>
                      <td>
                        {player ? (
                          <button type="button" className="inline-player-button remove" onClick={() => removePlayerFromLineup(index)}>
                            {player.name}
                          </button>
                        ) : (
                          <span className="placeholder-text">Open slot</span>
                        )}
                      </td>
                      <td>{player?.team || ""}</td>
                      <td>{player?.builder_position || ""}</td>
                      <td>{formatSalary(player?.salary)}</td>
                      <td>{blendedProjection !== null && blendedProjection !== undefined ? formatNumber(blendedProjection) : ""}</td>
                      <td>{player?.grade !== null && player?.grade !== undefined ? formatNumber(player.grade) : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td>Total</td>
                  <td />
                  <td />
                  <td />
                  <td>{formatSalary(lineupStats.totalSalary)}</td>
                  <td>{formatNumber(lineupStats.totalProjection)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <div className="builder-card">
          <div className="builder-card-header">
            <h3>Lineup Overview</h3>
          </div>
          <div className="builder-stats">
            <div className="builder-stat">
              <span className="builder-stat-label">Salary Cap</span>
              <strong>{formatSalary(lineupStats.salaryCap)}</strong>
            </div>
            <div className="builder-stat">
              <span className="builder-stat-label">Remaining Salary</span>
              <strong className={lineupStats.remainingSalary < 0 ? "stat-negative" : ""}>
                {formatSalary(lineupStats.remainingSalary)}
              </strong>
            </div>
            <div className="builder-stat">
              <span className="builder-stat-label">Avg Per Open Slot</span>
              <strong>{formatSalary(lineupStats.avgPerSlot)}</strong>
            </div>
            <div className="builder-stat">
              <span className="builder-stat-label">Open Slots</span>
              <strong>{lineupStats.openSlots}</strong>
            </div>
            <div className="builder-stat">
              <span className="builder-stat-label">Total Projection</span>
              <strong>{formatNumber(lineupStats.totalProjection)}</strong>
            </div>
          </div>
        </div>
      </div>

      <div className="builder-card assistant-card">
        <div className="builder-card-header">
          <h3>Lineup Assistant</h3>
          <div className="assistant-actions">
            <button type="button" className="assistant-button" onClick={() => applyOptimizedLineup(true)}>
              Fill Open Slots
            </button>
            <button type="button" className="assistant-button is-primary" onClick={() => applyOptimizedLineup(false)}>
              Build Best Cash
            </button>
          </div>
        </div>
        <div className="assistant-grid">
          <div className="assistant-panel">
            <span className="assistant-label">Best Available</span>
            {bestAvailable.length ? (
              <div className="assistant-list">
                {bestAvailable.map((item) => (
                  <button
                    key={`${item.slot}-${item.player.name}`}
                    type="button"
                    className="assistant-row assistant-row-button"
                    onClick={() => {
                      setLineup((current) => {
                        const next = [...current];
                        const targetIndex = next.findIndex((lineupSlot) => !lineupSlot.player && lineupSlot.slot === item.slot);
                        if (targetIndex < 0 || next.some((lineupSlot) => lineupSlot.player?.name === item.player.name)) {
                          return current;
                        }
                        next[targetIndex] = { ...next[targetIndex], player: item.player };
                        return next;
                      });
                    }}
                  >
                    <span className="assistant-slot">{item.slot}</span>
                    <span className="assistant-player">{item.player.name}</span>
                    <span className="assistant-meta">
                      {formatNumber(item.cashScore)} score
                      {item.projection !== null && item.projection !== undefined ? ` / ${formatNumber(item.projection)} proj` : ""}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="assistant-empty">No open-slot recommendations match the current filters.</p>
            )}
          </div>

          <div className="assistant-panel">
            <span className="assistant-label">Swap Ideas</span>
            {swapSuggestions.length ? (
              <div className="assistant-list">
                {swapSuggestions.map((swap) => (
                  <button
                    key={`${swap.slot}-${swap.out.name}-${swap.in.name}`}
                    type="button"
                    className="assistant-row assistant-row-button"
                    onClick={() => {
                      setLineup((current) =>
                        current.map((lineupSlot) =>
                          lineupSlot.player?.name === swap.out.name ? { ...lineupSlot, player: swap.in } : lineupSlot,
                        ),
                      );
                    }}
                  >
                    <span className="assistant-slot">{swap.slot}</span>
                    <span className="assistant-player">
                      {swap.out.name} to {swap.in.name}
                    </span>
                    <span className="assistant-meta">
                      {formatDelta(swap.scoreDelta)} score / {formatDelta(swap.projectionDelta)} proj
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="assistant-empty">No positive swaps found for the current lineup.</p>
            )}
          </div>
        </div>
      </div>

    </section>
  );
}
