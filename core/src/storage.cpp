#include "azeoapc/storage.h"
#include <stdexcept>

namespace azeoapc {

// Pimpl definition (empty for now -- SQLite integration deferred)
struct Storage::Impl {};

Storage::Storage(const std::string& /*db_path*/)
    : impl_(std::make_unique<Impl>())
{
}

Storage::~Storage() = default;

void Storage::initSchema(const std::string&, const std::vector<std::string>&,
                          const std::vector<std::string>&, const std::vector<std::string>&)
{
    throw std::runtime_error("Storage: SQLite not yet implemented");
}

int64_t Storage::beginCycle(int64_t) { return 0; }
void Storage::logCV(int64_t, int64_t, int, const std::string&, const CVRecord&) {}
void Storage::logMV(int64_t, int64_t, int, const std::string&, const MVRecord&) {}
void Storage::logDV(int64_t, int64_t, int, const std::string&, const DVRecord&) {}
void Storage::logSolver(int64_t, int64_t, const SolverRecord&) {}
void Storage::logControllerState(int64_t, int64_t, const ControllerStateRecord&) {}
void Storage::logPrediction(int64_t, int64_t, int, int, double, double) {}
void Storage::commitCycle() {}

std::vector<Storage::TimeseriesPoint> Storage::getCVTimeseries(
    const std::string&, const std::string&, int64_t, int64_t) const { return {}; }
std::vector<Storage::TimeseriesPoint> Storage::getMVTimeseries(
    const std::string&, const std::string&, int64_t, int64_t) const { return {}; }
std::vector<Storage::SolverStatsPoint> Storage::getSolverStats(
    int, int64_t, int64_t) const { return {}; }
std::vector<ControllerStateRecord> Storage::getRecentState(int) const { return {}; }

void Storage::purgeOlderThan(int64_t) {}
int64_t Storage::databaseSize() const { return 0; }
void Storage::compact() {}

}  // namespace azeoapc
