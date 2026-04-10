#pragma once

#include <Eigen/Dense>
#include <string>
#include <vector>
#include <memory>
#include <cstdint>
#include "azeoapc/types.h"

namespace azeoapc {

/**
 * SQLite Timeseries Storage
 *
 * Persists all optimizer variables, states, and diagnostics to a SQLite
 * database for logging, crash recovery, and post-analysis.
 *
 * Database schema:
 *
 * ── controller_info ──────────────────────────────────
 *   controller_name TEXT, config_hash TEXT, created_at TEXT
 *
 * ── cv_timeseries ────────────────────────────────────
 *   timestamp_ms INTEGER, cycle INTEGER,
 *   cv_index INTEGER, cv_name TEXT,
 *   measured REAL, setpoint REAL, ss_target REAL,
 *   predicted REAL, lo_limit REAL, hi_limit REAL,
 *   disturbance REAL, error REAL, weight REAL,
 *   enabled INTEGER
 *
 * ── mv_timeseries ────────────────────────────────────
 *   timestamp_ms INTEGER, cycle INTEGER,
 *   mv_index INTEGER, mv_name TEXT,
 *   value REAL, ss_target REAL,
 *   du REAL, lo_limit REAL, hi_limit REAL,
 *   rate_limit REAL, at_lo_limit INTEGER, at_hi_limit INTEGER,
 *   enabled INTEGER
 *
 * ── dv_timeseries ────────────────────────────────────
 *   timestamp_ms INTEGER, cycle INTEGER,
 *   dv_index INTEGER, dv_name TEXT, value REAL
 *
 * ── solver_log ───────────────────────────────────────
 *   timestamp_ms INTEGER, cycle INTEGER,
 *   layer INTEGER (1/2/3),
 *   status TEXT, objective REAL,
 *   solve_time_ms REAL, iterations INTEGER,
 *   relaxed_priorities TEXT (JSON array)
 *
 * ── controller_state ─────────────────────────────────
 *   timestamp_ms INTEGER, cycle INTEGER,
 *   mode TEXT, total_solve_ms REAL,
 *   diagnostics_json TEXT
 *
 * ── prediction_log (optional, can be large) ──────────
 *   timestamp_ms INTEGER, cycle INTEGER,
 *   step INTEGER, cv_index INTEGER,
 *   y_predicted REAL, y_free REAL
 *
 * All tables use (timestamp_ms, cycle) as the time axis.
 * timestamp_ms = Unix epoch milliseconds for absolute time.
 * cycle = monotonically increasing integer for ordering.
 */

struct CVRecord {
    double measured;
    double setpoint;
    double ss_target;
    double predicted;     // one-step-ahead prediction
    double lo_limit;
    double hi_limit;
    double disturbance;
    double error;         // measured - setpoint
    double weight;
    bool enabled;
};

struct MVRecord {
    double value;
    double ss_target;
    double du;            // applied move
    double lo_limit;
    double hi_limit;
    double rate_limit;
    bool at_lo_limit;
    bool at_hi_limit;
    bool enabled;
};

struct DVRecord {
    double value;
};

struct SolverRecord {
    int layer;            // 1, 2, or 3
    SolverStatus status;
    double objective;
    double solve_time_ms;
    int iterations;
    std::vector<int> relaxed_priorities;
};

struct ControllerStateRecord {
    ControllerMode mode;
    double total_solve_ms;
    std::string diagnostics_json;
};

class Storage {
public:
    /// Open or create database at path
    Storage(const std::string& db_path);
    ~Storage();

    /// Initialize schema (creates tables if not exists)
    void initSchema(const std::string& controller_name,
                    const std::vector<std::string>& cv_names,
                    const std::vector<std::string>& mv_names,
                    const std::vector<std::string>& dv_names);

    // ---- Write (called every cycle) ----

    /// Begin a new cycle (returns cycle number)
    int64_t beginCycle(int64_t timestamp_ms);

    /// Log CV data for current cycle
    void logCV(int64_t timestamp_ms, int64_t cycle,
               int cv_index, const std::string& cv_name,
               const CVRecord& record);

    /// Log MV data for current cycle
    void logMV(int64_t timestamp_ms, int64_t cycle,
               int mv_index, const std::string& mv_name,
               const MVRecord& record);

    /// Log DV data for current cycle
    void logDV(int64_t timestamp_ms, int64_t cycle,
               int dv_index, const std::string& dv_name,
               const DVRecord& record);

    /// Log solver result for a layer
    void logSolver(int64_t timestamp_ms, int64_t cycle,
                   const SolverRecord& record);

    /// Log overall controller state
    void logControllerState(int64_t timestamp_ms, int64_t cycle,
                            const ControllerStateRecord& record);

    /// Log prediction trajectory (optional, can be large)
    void logPrediction(int64_t timestamp_ms, int64_t cycle,
                       int step, int cv_index,
                       double y_predicted, double y_free);

    /// Commit current cycle (batch insert for performance)
    void commitCycle();

    // ---- Read (for monitoring / analysis) ----

    /// Get CV timeseries for a variable over time range
    struct TimeseriesPoint {
        int64_t timestamp_ms;
        double value;
    };

    std::vector<TimeseriesPoint> getCVTimeseries(
        const std::string& cv_name,
        const std::string& field,   // "measured", "setpoint", "error", etc.
        int64_t start_ms, int64_t end_ms) const;

    std::vector<TimeseriesPoint> getMVTimeseries(
        const std::string& mv_name,
        const std::string& field,
        int64_t start_ms, int64_t end_ms) const;

    /// Get solver performance over time
    struct SolverStatsPoint {
        int64_t timestamp_ms;
        double solve_time_ms;
        std::string status;
    };

    std::vector<SolverStatsPoint> getSolverStats(
        int layer, int64_t start_ms, int64_t end_ms) const;

    /// Get last N cycles of controller state
    std::vector<ControllerStateRecord> getRecentState(int n_cycles) const;

    // ---- Maintenance ----

    /// Delete records older than timestamp
    void purgeOlderThan(int64_t timestamp_ms);

    /// Get database size in bytes
    int64_t databaseSize() const;

    /// Compact database (VACUUM)
    void compact();

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace azeoapc
