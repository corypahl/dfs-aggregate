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

function buildRecommendations(records, lineup, lineupTemplate, selectedNames, avgPerSlot, mode) {
  const recommendations = [];
  for (const lineupSlot of lineup) {
    if (lineupSlot.player) {
      continue;
    }

    const candidates = records
      .filter((record) => !selectedNames.includes(record.name))
      .filter((record) => isEligibleForSlot(record, lineupSlot.slot, lineupTemplate))
      .filter((record) => (mode === "shortlist" ? record.salary !== null && record.salary <= avgPerSlot : true))
      .sort((left, right) => (right.grade || -1) - (left.grade || -1));

    if (candidates.length) {
      recommendations.push({ ...candidates[0], recommendedFor: lineupSlot.slot });
    } else {
      recommendations.push({
        name: mode === "shortlist" ? "--- Open Slot ---" : "--- No Players ---",
        team: "",
        builder_position: lineupSlot.slot,
        salary: null,
        grade: null,
        blended_projection: null,
        recommendedFor: lineupSlot.slot,
        isPlaceholder: true,
      });
    }
  }
  return recommendations;
}

function RecommendationTable({ title, records, onSelectPlayer }) {
  if (!records.length) {
    return null;
  }

  return (
    <div className="builder-card">
      <div className="builder-card-header">
        <h3>{title}</h3>
      </div>
      <div className="builder-table-shell">
        <table className="builder-table compact">
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
            {records.map((record) => (
              <tr key={`${title}-${record.recommendedFor}-${record.name}`}>
                <td>{record.recommendedFor}</td>
                <td>
                  {record.isPlaceholder ? (
                    <span className="placeholder-text">{record.name}</span>
                  ) : (
                    <button type="button" className="inline-player-button" onClick={() => onSelectPlayer(record)}>
                      {record.name}
                    </button>
                  )}
                </td>
                <td>{record.team || ""}</td>
                <td>{record.builder_position || ""}</td>
                <td>{formatSalary(record.salary)}</td>
                <td>{record.blended_projection !== null && record.blended_projection !== undefined ? formatNumber(record.blended_projection) : ""}</td>
                <td>{record.grade !== null && record.grade !== undefined ? formatNumber(record.grade) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
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

  const bestPlays = useMemo(
    () => buildRecommendations(records, lineup, slate?.lineup_template, selectedNames, lineupStats.avgPerSlot, "best"),
    [lineup, lineupStats.avgPerSlot, records, selectedNames, slate?.lineup_template],
  );
  const shortlist = useMemo(
    () => buildRecommendations(records, lineup, slate?.lineup_template, selectedNames, lineupStats.avgPerSlot, "shortlist"),
    [lineup, lineupStats.avgPerSlot, records, selectedNames, slate?.lineup_template],
  );

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

      <div className="builder-grid">
        <RecommendationTable
          title={`Shortlist (${formatSalary(lineupStats.avgPerSlot)} max average slot spend)`}
          records={shortlist}
          onSelectPlayer={addPlayerToLineup}
        />
        <RecommendationTable title="Best Plays" records={bestPlays} onSelectPlayer={addPlayerToLineup} />
      </div>
    </section>
  );
}
