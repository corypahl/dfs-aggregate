import React, { useMemo } from "react";
import {
  buildBestAvailableBySlot,
  buildSwapSuggestions,
  optimizeLineup,
} from "../lineupIntelligence.js";
import {
  computeSlotProjection,
  computeSlotSalary,
  formatNumber,
  formatSalary,
  getSlotSalaryMultiplier,
} from "../utils.js";

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
  const isSingleGame = String(slate?.contest_type || "").replace(/[^a-z]/gi, "").toLowerCase() === "singlegame";
  const lineupStats = useMemo(() => {
    const lineupTemplate = slate?.lineup_template;
    const totalSalary = lineup.reduce(
      (sum, lineupSlot) => sum + computeSlotSalary(lineupSlot.player, lineupSlot.slot, lineupTemplate),
      0,
    );
    const totalProjection = lineup.reduce(
      (sum, lineupSlot) => sum + computeSlotProjection(lineupSlot.player, lineupSlot.slot, lineupTemplate),
      0,
    );
    const emptySlots = lineup.filter((lineupSlot) => !lineupSlot.player);
    const openSlots = emptySlots.length;
    const salaryCap = Number(slate?.salary_cap || 0);
    const remainingSalary = salaryCap - totalSalary;
    const openSalaryUnits = emptySlots.reduce(
      (sum, lineupSlot) => sum + getSlotSalaryMultiplier(lineupSlot.slot, lineupTemplate),
      0,
    );
    const avgPerSlot = openSalaryUnits > 0 ? remainingSalary / openSalaryUnits : 0;
    const teamCounts = lineup.reduce((counts, lineupSlot) => {
      const team = String(lineupSlot.player?.team || "").trim().toUpperCase();
      if (team) {
        counts.set(team, (counts.get(team) || 0) + 1);
      }
      return counts;
    }, new Map());
    const teamSplit = [...teamCounts.entries()]
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
      .map(([team, count]) => `${team} ${count}`)
      .join(" / ");
    return {
      salaryCap,
      totalSalary,
      totalProjection,
      openSlots,
      remainingSalary,
      avgPerSlot,
      teamSplit,
    };
  }, [lineup, slate?.lineup_template, slate?.salary_cap]);

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

  const promoteToMvp = (index) => {
    setLineup((current) => {
      const mvpIndex = current.findIndex((lineupSlot) => lineupSlot.slot === "MVP");
      if (mvpIndex < 0 || mvpIndex === index) {
        return current;
      }
      const next = [...current];
      const mvpPlayer = next[mvpIndex].player;
      next[mvpIndex] = { ...next[mvpIndex], player: next[index].player };
      next[index] = { ...next[index], player: mvpPlayer };
      return next;
    });
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
          {isSingleGame ? (
            <p className="builder-note">
              MVP costs and scores 1.5x. Recommendations prioritize raw ceiling, direct correlation, and coherent 4-2 or 3-3 game scripts.
            </p>
          ) : null}
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
                  const slotSalary = computeSlotSalary(player, lineupSlot.slot, slate?.lineup_template);
                  const slotProjection = computeSlotProjection(player, lineupSlot.slot, slate?.lineup_template);
                  const salaryMultiplier = getSlotSalaryMultiplier(lineupSlot.slot, slate?.lineup_template);
                  return (
                    <tr key={`${slate.key}-${lineupSlot.slot}-${index}`}>
                      <td>{lineupSlot.slot}</td>
                      <td>
                        {player ? (
                          <span className="lineup-player-actions">
                            <button type="button" className="inline-player-button remove" onClick={() => removePlayerFromLineup(index)}>
                              {player.name}
                            </button>
                            {isSingleGame && lineupSlot.slot !== "MVP" ? (
                              <button type="button" className="mvp-button" onClick={() => promoteToMvp(index)}>
                                Make MVP
                              </button>
                            ) : null}
                          </span>
                        ) : (
                          <span className="placeholder-text">Open slot</span>
                        )}
                      </td>
                      <td>{player?.team || ""}</td>
                      <td>{player?.base_position || ""}</td>
                      <td>
                        {player ? formatSalary(slotSalary) : ""}
                        {player && salaryMultiplier !== 1 ? ` (${salaryMultiplier}x)` : ""}
                      </td>
                      <td>{player ? formatNumber(slotProjection) : ""}</td>
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
              <span className="builder-stat-label">Avg Base Salary / Open</span>
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
            {isSingleGame ? (
              <div className="builder-stat">
                <span className="builder-stat-label">Team Split</span>
                <strong>{lineupStats.teamSplit || "—"}</strong>
              </div>
            ) : null}
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
              {isSingleGame ? "Build Best Single Game" : "Build Best Cash"}
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
