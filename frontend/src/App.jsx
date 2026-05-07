import React, { useEffect, useMemo, useState } from "react";
import AggregateTable from "./components/AggregateTable.jsx";
import FilterPanel from "./components/FilterPanel.jsx";
import LineupBuilder, { buildEmptyLineup } from "./components/LineupBuilder.jsx";
import Toolbar from "./components/Toolbar.jsx";
import { buildMetricStats, buildPlayerBadges, buildPositionLeaderBadges, COLUMN_DEFS, parseMaxSalary } from "./utils.js";

function buildStatusText(pageMode, generatedAt, refreshError) {
  if (refreshError) {
    return `Refresh failed: ${refreshError}`;
  }
  if (pageMode === "static") {
    return `Published: ${generatedAt}`;
  }
  return `Last updated: ${generatedAt}`;
}

export default function App({ bootstrap }) {
  const [data, setData] = useState(bootstrap.initialData || null);
  const [pendingSport, setPendingSport] = useState(bootstrap.initialSport || bootstrap.initialData?.sport || "nba");
  const [selectedSlateKey, setSelectedSlateKey] = useState(
    bootstrap.initialData?.selected_slate_key || bootstrap.initialData?.slates?.[0]?.key || "no-slate",
  );
  const [selectedPositions, setSelectedPositions] = useState([]);
  const [maxSalary, setMaxSalary] = useState("");
  const [sortKey, setSortKey] = useState("salary");
  const [sortDir, setSortDir] = useState("desc");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState("");
  const [lineup, setLineup] = useState([]);
  const [taggedOnly, setTaggedOnly] = useState(false);

  const selectedSlate = useMemo(() => {
    if (!data?.slates?.length) {
      return null;
    }
    return data.slates.find((slate) => slate.key === selectedSlateKey) || data.slates[0];
  }, [data, selectedSlateKey]);

  const metricStats = useMemo(() => buildMetricStats(selectedSlate?.records || []), [selectedSlate]);
  const selectedPlayerNames = useMemo(
    () => lineup.map((lineupSlot) => lineupSlot.player?.name).filter(Boolean),
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
  const filteredRecords = useMemo(
    () =>
      taggedOnly
        ? baseFilteredRecords.filter((record) => buildPlayerBadges(record, positionLeaderBadges[record.name] || []).length > 0)
        : baseFilteredRecords,
    [baseFilteredRecords, positionLeaderBadges, taggedOnly],
  );

  const sportOptions = bootstrap.sportOptions || [];
  const pageMode = bootstrap.pageMode || "local";
  const statusText = buildStatusText(pageMode, data?.generated_at || "", refreshError);

  const handleSlateChange = (nextSlateKey) => {
    setSelectedSlateKey(nextSlateKey);
    setSelectedPositions([]);
    setMaxSalary("");
    setTaggedOnly(false);
    setLineup([]);
  };

  const handleSortChange = (nextSortKey, type) => {
    if (sortKey === nextSortKey) {
      setSortDir((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }

    setSortKey(nextSortKey);
    setSortDir(type === "number" ? "desc" : "asc");
  };

  const handleSportChange = (nextSport) => {
    setPendingSport(nextSport);
    if (pageMode === "static") {
      const target = sportOptions.find((sportOption) => sportOption.key === nextSport);
      if (target?.href) {
        window.location.href = target.href;
      }
    }
  };

  const handleRefresh = async () => {
    if (!window.location.protocol.startsWith("http")) {
      setRefreshError("local server mode is required (`python main.py --serve`).");
      return;
    }

    setIsRefreshing(true);
    setRefreshError("");
    try {
      const response = await fetch("/refresh", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ sport: pendingSport }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = await response.json();
      if (payload?.data) {
        setData(payload.data);
        setPendingSport(payload.data.sport);
        setSelectedSlateKey(payload.data.selected_slate_key || payload.data.slates?.[0]?.key || "no-slate");
        setSelectedPositions([]);
        setMaxSalary("");
        setTaggedOnly(false);
        setSortKey("salary");
        setSortDir("desc");
        setLineup([]);
      } else {
        window.location.reload();
      }
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : "Unknown refresh error");
    } finally {
      setIsRefreshing(false);
    }
  };

  if (!data || !selectedSlate) {
    return (
      <div className="app-empty">
        <h1>DFS Aggregate</h1>
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
            <span className="eyebrow">React Frontend</span>
            <h1>{data.sport_label} DFS Aggregate</h1>
            <p className="hero-text">{data.hero_text}</p>
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
          records={filteredRecords}
          sportLabel={data.sport_label}
          lineup={lineup}
          setLineup={setLineup}
        />

        <Toolbar
          pageMode={pageMode}
          sportOptions={sportOptions}
          pendingSport={pendingSport}
          onSportChange={handleSportChange}
          slateOptions={data.slates}
          selectedSlateKey={selectedSlate.key}
          onSlateChange={handleSlateChange}
          statusText={statusText}
          isRefreshing={isRefreshing}
          onRefresh={handleRefresh}
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
          columns={COLUMN_DEFS}
          records={filteredRecords}
          metricStats={metricStats}
          sortKey={sortKey}
          sortDir={sortDir}
          onSortChange={handleSortChange}
          onPlayerSelect={selectedSlate?.builder_enabled ? addPlayerToLineup : undefined}
          selectedPlayerNames={selectedPlayerNames}
          canSelectPlayer={canSelectPlayerForLineup}
          positionLeaderBadges={positionLeaderBadges}
        />
      </main>
    </div>
  );
}
