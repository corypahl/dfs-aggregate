import React, { useMemo } from "react";
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

function getAllowedPositions(slot, lineupTemplate) {
  return lineupTemplate?.position_map?.[slot] || [slot];
}

function isEligibleForSlot(record, slot, lineupTemplate) {
  const playerPositions = record.builder_position_values || [];
  const allowedPositions = getAllowedPositions(slot, lineupTemplate);
  return allowedPositions.some((position) => playerPositions.includes(position));
}

export default function LineupBuilder({ slate, records, sportLabel, lineup, setLineup }) {
  const selectedNames = useMemo(
    () => lineup.map((lineupSlot) => lineupSlot.player?.name).filter(Boolean),
    [lineup],
  );

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

  const addPlayerToLineup = (record) => {
    setLineup((current) => {
      if (current.some((lineupSlot) => lineupSlot.player?.name === record.name)) {
        return current;
      }

      const next = [...current];
      const targetIndex = next.findIndex(
        (lineupSlot) => !lineupSlot.player && isEligibleForSlot(record, lineupSlot.slot, slate.lineup_template),
      );
      if (targetIndex < 0) {
        return current;
      }

      next[targetIndex] = {
        ...next[targetIndex],
        player: record,
      };
      return next;
    });
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
      <div className="builder-header">
        <div>
          <span className="section-label">Lineup Builder</span>
          <h2>{sportLabel} lineup workspace</h2>
        </div>
      </div>

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
            <h3>Lineup Stats</h3>
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
              <span className="builder-stat-label">Blended Projection</span>
              <strong>{formatNumber(lineupStats.totalProjection)}</strong>
            </div>
          </div>
        </div>
      </div>

    </section>
  );
}
