#include "azeoapc/types.h"

namespace azeoapc {

const char* solverStatusStr(SolverStatus s)
{
    switch (s) {
        case SolverStatus::OPTIMAL:         return "OPTIMAL";
        case SolverStatus::INFEASIBLE:      return "INFEASIBLE";
        case SolverStatus::MAX_ITER:        return "MAX_ITER";
        case SolverStatus::TIME_LIMIT:      return "TIME_LIMIT";
        case SolverStatus::NUMERICAL_ERROR: return "NUMERICAL_ERROR";
        case SolverStatus::NOT_SOLVED:      return "NOT_SOLVED";
        default:                            return "UNKNOWN";
    }
}

}  // namespace azeoapc
