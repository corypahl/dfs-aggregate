import React, { useEffect, useMemo, useState } from "react";
import AggregateTable from "./components/AggregateTable.jsx";
import FilterPanel from "./components/FilterPanel.jsx";
import LineupBuilder, { buildEmptyLineup } from "./components/LineupBuilder.jsx";
import {
  buildMetricStats,
  buildPlayerBadges,
  buildPositionLeaderBadges,
  buildStrategyBadgesByName,
  COLUMN_DEFS,
  parseMaxSalary,
} from "./utils.js";

function getInitialSlateKey(initialData) {
  const fallback = initialData?.selected_slate_key || initialData?.slates?.[0]?.key || "no-slate";
  if (typeof window === "undefined") {
    return fallback;
  }

  const requestedSlate = new URLSearchParams(window.location.search).get("slate");
  if (!requestedSlate) {
    return fallback;
  }

  return initialData?.slates?.some((slate) => slate.key === requestedSlate) ? requestedSlate : fallback;
}

export default function App({ bootstrap }) {
  const [data] = useState(bootstrap.initialData || null);
  const [selectedSlateKey] = useState(getInitialSlateKey(bootstrap.initialData));
  const [selectedPositions, setSelectedPositions] = useState([]);
  const [maxSalary, setMaxSalary] = useState("");
  const [sortKey, setSortKey] = useState("grade");
  const [sortDir, setSortDir] = useState("desc");
  const [lineup, setLineup] = useState([]);
  const [taggedOnly, setTaggedOnly] = useState(false);

  const selectedSlate = useMemo(() => {
    if (!data?.slates?.length) {
      return null;
    }
    return data.slates.find((slate) => slate.key === selectedSlateKey) || data.slates[0];
  }, [data, selectedSlateKey]);

  const metricStats = useMemo(() => buildMetricStats(selectedSlate?.records || []), [selectedSlate]);
  const visibleColumns = useMemo(() => {
    const hasFanDuelData = (selectedSlate?.records || []).some(
      (record) =>
        (record.fd_projection !== null && record.fd_projection !== undefined) ||
        (record.fd_value !== null && record.fd_value !== undefined),
    );
    return hasFanDuelData ? COLUMN_DEFS : COLUMN_DEFS.filter((column) => !column.fanduelOnly);
  }, [selectedSlate]);
  const selectedPlayerNames = useMemo(
    () => lineup.map((lineupSlot) => lineupSlot.player?.name).filter(Boolean),
    [lineup],
  );
  const selectedPlayers = useMemo(
    () => lineup.map((lineupSlot) => lineupSlot.player).filter(Boolean),
    [lineup],
  );

  useEffect(() => {
    setLineup(buildEmptyLineup(selectedSlate?.lineup_template));
  }, [selectedSlate?.key, selectedSlate?.lineup_template]);

  const baseFilteredRecords = useMemo(() => {
    if (!selectedSlate) {
      return [];
    }

    const maxSalaryValue = parseMaxSalary(maxSalary);
    return selectedSlate.records.filter((record) => {
      const matchesPosition =
        !selectedPositions.length ||
        selectedPositions.some((position) => (record.position_filter_values || []).includes(position));
      const matchesSalary =
        maxSalaryValue === null ||
        (record.salary !== null && record.salary !== undefined && Number(record.salary) <= maxSalaryValue);
      return matchesPosition && matchesSalary;
    });
  }, [maxSalary, selectedPositions, selectedSlate]);
  const positionLeaderBadges = useMemo(
    () => buildPositionLeaderBadges(baseFilteredRecords, selectedSlate?.lineup_template),
    [baseFilteredRecords, selectedSlate?.lineup_template],
  );
  const strategyBadgesByName = useMemo(
    () => buildStrategyBadgesByName(baseFilteredRecords, selectedPlayers, data?.sport),
    [baseFilteredRecords, data?.sport, selectedPlayers],
  );
  const filteredRecords = useMemo(
    () =>
      taggedOnly
        ? baseFilteredRecords.filter(
            (record) =>
              buildPlayerBadges(
                record,
                positionLeaderBadges[record.name] || [],
                strategyBadgesByName[record.name] || [],
              ).length > 0,
          )
        : baseFilteredRecords,
    [baseFilteredRecords, positionLeaderBadges, strategyBadgesByName, taggedOnly],
  );

  const handleSortChange = (nextSortKey, type) => {
    if (sortKey === nextSortKey) {
      setSortDir((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }

    setSortKey(nextSortKey);
    setSortDir(type === "number" ? "desc" : "asc");
  };

  if (!data || !selectedSlate) {
    return (
      <div className="app-empty">
        <h1>DFS Lineup Builder</h1>
        <p>No data is available yet for this view.</p>
      </div>
    );
  }

  const canSelectPlayerForLineup = (record) => {
    if (!selectedSlate?.builder_enabled || !selectedSlate?.lineup_template) {
      return false;
    }
    if (selectedPlayerNames.includes(record.name)) {
      return false;
    }
    const playerPositions = record.builder_position_values || [];
    return lineup.some((lineupSlot) => {
      if (lineupSlot.player) {
        return false;
      }
      const allowedPositions = selectedSlate.lineup_template.position_map?.[lineupSlot.slot] || [lineupSlot.slot];
      return allowedPositions.some((position) => playerPositions.includes(position));
    });
  };

  const addPlayerToLineup = (record) => {
    setLineup((current) => {
      if (!selectedSlate?.lineup_template) {
        return current;
      }
      if (current.some((lineupSlot) => lineupSlot.player?.name === record.name)) {
        return current;
      }

      const next = [...current];
      const targetIndex = next.findIndex((lineupSlot) => {
        if (lineupSlot.player) {
          return false;
        }
        const allowedPositions = selectedSlate.lineup_template.position_map?.[lineupSlot.slot] || [lineupSlot.slot];
        return allowedPositions.some((position) => (record.builder_position_values || []).includes(position));
      });

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

  return (
    <div className="page-shell">
      <section className="hero">
        <div className="hero-inner">
          <div className="hero-copy">
            <h1>{data.sport_label} Lineup Builder</h1>
          </div>
          <div className="hero-grid">
            <div className="meta-card">
              <span className="meta-label">Sport</span>
              <span className="meta-value">{data.sport_label}</span>
            </div>
            <div className="meta-card">
              <span className="meta-label">Slate</span>
              <span className="meta-value">{selectedSlate.label}</span>
            </div>
            <div className="meta-card">
              <span className="meta-label">Sources</span>
              <span className="meta-value">{data.sources_label}</span>
            </div>
            <div className="meta-card">
              <span className="meta-label">Players</span>
              <span className="meta-value">{selectedSlate.player_count}</span>
            </div>
          </div>
        </div>
      </section>

      <main className="page-content">
        <LineupBuilder
          slate={selectedSlate}
          lineup={lineup}
          setLineup={setLineup}
        />

        <FilterPanel
          positionOptions={selectedSlate.position_options}
          selectedPositions={selectedPositions}
          onTogglePosition={(position) =>
            setSelectedPositions((current) =>
              current.includes(position) ? current.filter((item) => item !== position) : [...current, position],
            )
          }
          maxSalary={maxSalary}
          onMaxSalaryChange={setMaxSalary}
          taggedOnly={taggedOnly}
          onTaggedOnlyChange={setTaggedOnly}
          onClearFilters={() => {
            setSelectedPositions([]);
            setMaxSalary("");
            setTaggedOnly(false);
          }}
        />

        <AggregateTable
          columns={visibleColumns}
          records={filteredRecords}
          metricStats={metricStats}
          sortKey={sortKey}
          sortDir={sortDir}
          onSortChange={handleSortChange}
          onPlayerSelect={selectedSlate?.builder_enabled ? addPlayerToLineup : undefined}
          selectedPlayerNames={selectedPlayerNames}
          canSelectPlayer={canSelectPlayerForLineup}
          positionLeaderBadges={positionLeaderBadges}
          strategyBadgesByName={strategyBadgesByName}
        />
      </main>
    </div>
  );
}
