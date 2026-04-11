#include <pybind11/pybind11.h>
#include <pybind11/eigen.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <spdlog/spdlog.h>

// Undefine OSQP macros that conflict with our enum values
#ifdef MAX_ITER
#undef MAX_ITER
#endif

#include "azeoapc/azeoapc.h"
#include "azeoapc/layer3_nlp.h"

namespace py = pybind11;
using namespace azeoapc;

PYBIND11_MODULE(_azeoapc_core, m) {
    m.doc() = "Azeotrope APC C++ core bindings";
    m.attr("__version__") = VERSION_STRING;

    // ---- Logging control ----
    m.def("set_log_level", [](const std::string& level) {
        if (level == "trace") spdlog::set_level(spdlog::level::trace);
        else if (level == "debug") spdlog::set_level(spdlog::level::debug);
        else if (level == "info") spdlog::set_level(spdlog::level::info);
        else if (level == "warn") spdlog::set_level(spdlog::level::warn);
        else if (level == "error") spdlog::set_level(spdlog::level::err);
        else if (level == "off") spdlog::set_level(spdlog::level::off);
        else throw std::invalid_argument("Unknown log level: " + level +
                 ". Use trace/debug/info/warn/error/off.");
    }, py::arg("level"), "Set C++ logging level (trace/debug/info/warn/error/off)");

    // ---- Enums ----
    py::enum_<SolverStatus>(m, "SolverStatus")
        .value("OPTIMAL", SolverStatus::OPTIMAL)
        .value("INFEASIBLE", SolverStatus::INFEASIBLE)
        .value("MAX_ITER", SolverStatus::MAX_ITER)
        .value("TIME_LIMIT", SolverStatus::TIME_LIMIT)
        .value("NUMERICAL_ERROR", SolverStatus::NUMERICAL_ERROR)
        .value("NOT_SOLVED", SolverStatus::NOT_SOLVED);

    py::enum_<ControllerMode>(m, "ControllerMode")
        .value("MANUAL", ControllerMode::MANUAL)
        .value("AUTO", ControllerMode::AUTO)
        .value("CASCADE", ControllerMode::CASCADE);

    // ---- StepResponseModel ----
    py::class_<StepResponseModel>(m, "StepResponseModel")
        .def(py::init<int, int, int, double>(),
             py::arg("ny"), py::arg("nu"), py::arg("model_horizon"), py::arg("sample_time"))
        .def_static("from_state_space", &StepResponseModel::fromStateSpace,
             py::arg("A"), py::arg("B"), py::arg("C"), py::arg("D"),
             py::arg("model_horizon"), py::arg("sample_time"))
        .def_static("from_foptd", &StepResponseModel::fromFOPTD,
             py::arg("gain"), py::arg("time_constant"), py::arg("dead_time"),
             py::arg("sample_time"), py::arg("model_horizon"))
        .def_static("from_foptd_matrix", &StepResponseModel::fromFOPTDMatrix,
             py::arg("gains"), py::arg("time_constants"), py::arg("dead_times"),
             py::arg("sample_time"), py::arg("model_horizon"))
        .def("ny", &StepResponseModel::ny)
        .def("nu", &StepResponseModel::nu)
        .def("model_horizon", &StepResponseModel::modelHorizon)
        .def("sample_time", &StepResponseModel::sampleTime)
        .def("coefficient", &StepResponseModel::coefficient,
             py::arg("cv"), py::arg("step"), py::arg("mv"))
        .def("step_response", &StepResponseModel::stepResponse,
             py::arg("cv"), py::arg("mv"))
        .def("steady_state_gain", &StepResponseModel::steadyStateGain)
        .def("coefficient_matrix", &StepResponseModel::coefficientMatrix,
             py::arg("step"))
        .def("predict_free", &StepResponseModel::predictFree,
             py::arg("past_moves"), py::arg("P"))
        .def("predict_forced", &StepResponseModel::predictForced,
             py::arg("future_moves"), py::arg("P"), py::arg("M"))
        .def("set_cv_names", &StepResponseModel::setCVNames, py::arg("names"))
        .def("set_mv_names", &StepResponseModel::setMVNames, py::arg("names"))
        .def("cv_names", &StepResponseModel::cvNames)
        .def("mv_names", &StepResponseModel::mvNames)
        .def("__repr__", [](const StepResponseModel& m) {
            return "<StepResponseModel ny=" + std::to_string(m.ny()) +
                   " nu=" + std::to_string(m.nu()) +
                   " N=" + std::to_string(m.modelHorizon()) +
                   " dt=" + std::to_string(m.sampleTime()) + ">";
        });

    // ---- DynamicMatrix ----
    py::class_<DynamicMatrix>(m, "DynamicMatrix")
        .def(py::init<const StepResponseModel&, int, int>(),
             py::arg("model"), py::arg("P"), py::arg("M"))
        .def("matrix", &DynamicMatrix::matrix, py::return_value_policy::reference_internal)
        .def("sparse", &DynamicMatrix::sparse, py::return_value_policy::reference_internal)
        .def("cumulative_matrix", &DynamicMatrix::cumulativeMatrix, py::return_value_policy::reference_internal)
        .def("prediction_horizon", &DynamicMatrix::predictionHorizon)
        .def("control_horizon", &DynamicMatrix::controlHorizon)
        .def("ny", &DynamicMatrix::ny)
        .def("nu", &DynamicMatrix::nu)
        .def("rebuild", &DynamicMatrix::rebuild, py::arg("model"));

    // ---- PredictionEngine ----
    py::class_<PredictionEngine>(m, "PredictionEngine")
        .def(py::init<const StepResponseModel&, int, int>(),
             py::arg("model"), py::arg("P"), py::arg("M"))
        .def("update", &PredictionEngine::update,
             py::arg("y_measured"), py::arg("du_applied"))
        .def("free_response", &PredictionEngine::freeResponse)
        .def("predict", &PredictionEngine::predict, py::arg("du_future"))
        .def("reset", &PredictionEngine::reset)
        .def("past_moves_matrix", &PredictionEngine::pastMovesMatrix);

    // ---- DisturbanceObserver ----
    py::enum_<DisturbanceObserver::Method>(m, "ObserverMethod")
        .value("EXPONENTIAL_FILTER", DisturbanceObserver::Method::EXPONENTIAL_FILTER)
        .value("KALMAN_FILTER", DisturbanceObserver::Method::KALMAN_FILTER);

    py::class_<DisturbanceObserver>(m, "DisturbanceObserver")
        .def(py::init<int, DisturbanceObserver::Method>(),
             py::arg("ny"), py::arg("method") = DisturbanceObserver::Method::EXPONENTIAL_FILTER)
        .def("update", &DisturbanceObserver::update,
             py::arg("y_measured"), py::arg("y_predicted"))
        .def("estimate", &DisturbanceObserver::estimate, py::return_value_policy::reference_internal)
        .def("set_filter_gain", &DisturbanceObserver::setFilterGain, py::arg("alpha"))
        .def("set_kalman_tuning", &DisturbanceObserver::setKalmanTuning,
             py::arg("Q"), py::arg("R"))
        .def("reset", &DisturbanceObserver::reset);

    // ---- ConstraintHandler ----
    py::class_<ConstraintHandler>(m, "ConstraintHandler")
        .def(py::init<int, int, int, int>(),
             py::arg("nu"), py::arg("ny"), py::arg("M"), py::arg("P"))
        .def("set_mv_bounds", &ConstraintHandler::setMVBounds,
             py::arg("lb"), py::arg("ub"))
        .def("set_mv_rate_bounds", &ConstraintHandler::setMVRateBounds,
             py::arg("du_lb"), py::arg("du_ub"))
        .def("set_cv_safety_bounds", &ConstraintHandler::setCVSafetyBounds,
             py::arg("lb"), py::arg("ub"))
        .def("set_cv_operating_bounds", &ConstraintHandler::setCVOperatingBounds,
             py::arg("lb"), py::arg("ub"))
        .def("set_cv_concerns", &ConstraintHandler::setCVConcerns,
             py::arg("concern_lo"), py::arg("concern_hi"),
             "Set per-CV concern values [ny]. Penalty = concern^2 per slack unit.")
        .def("set_cv_ranks", &ConstraintHandler::setCVRanks,
             py::arg("rank_lo"), py::arg("rank_hi"),
             "Set per-CV rank for relaxation order [ny].")
        .def("set_mv_cost_ranks", &ConstraintHandler::setMVCostRanks,
             py::arg("mv_cost_rank"),
             "Set per-MV cost rank for lexicographic LP.")
        .def("update_mv_bound", &ConstraintHandler::updateMVBound,
             py::arg("mv_idx"), py::arg("lb"), py::arg("ub"))
        .def("update_mv_rate_limit", &ConstraintHandler::updateMVRateLimit,
             py::arg("mv_idx"), py::arg("rate"))
        .def("update_cv_operating_bound", &ConstraintHandler::updateCVOperatingBound,
             py::arg("cv_idx"), py::arg("lb"), py::arg("ub"))
        .def("update_cv_concern", &ConstraintHandler::updateCVConcern,
             py::arg("cv_idx"), py::arg("concern_lo"), py::arg("concern_hi"))
        .def("update_cv_rank", &ConstraintHandler::updateCVRank,
             py::arg("cv_idx"), py::arg("rank_lo"), py::arg("rank_hi"))
        .def("update_mv_cost_rank", &ConstraintHandler::updateMVCostRank,
             py::arg("mv_idx"), py::arg("rank"));

    // ---- Layer1Config ----
    py::class_<Layer1Config>(m, "Layer1Config")
        .def(py::init<>())
        .def_readwrite("prediction_horizon", &Layer1Config::prediction_horizon)
        .def_readwrite("control_horizon", &Layer1Config::control_horizon)
        .def_readwrite("cv_weights", &Layer1Config::cv_weights)
        .def_readwrite("mv_weights", &Layer1Config::mv_weights);

    // ---- Layer1Result ----
    py::class_<Layer1Result>(m, "Layer1Result")
        .def(py::init<>())
        .def_readonly("du", &Layer1Result::du)
        .def_readonly("y_predicted", &Layer1Result::y_predicted)
        .def_readonly("status", &Layer1Result::status)
        .def_readonly("objective", &Layer1Result::objective)
        .def_readonly("solve_time_ms", &Layer1Result::solve_time_ms)
        .def_readonly("iterations", &Layer1Result::iterations)
        .def_readonly("relaxed_priorities", &Layer1Result::relaxed_priorities);

    // ---- Layer1DynamicQP ----
    py::class_<Layer1DynamicQP>(m, "Layer1DynamicQP")
        .def(py::init<const StepResponseModel&, const Layer1Config&>(),
             py::arg("model"), py::arg("config"))
        .def("solve", &Layer1DynamicQP::solve,
             py::arg("y_free"), py::arg("y_target"),
             py::arg("u_current"), py::arg("disturbance"))
        .def("warm_start", &Layer1DynamicQP::warmStart, py::arg("du_prev"))
        .def("update_weights", &Layer1DynamicQP::updateWeights,
             py::arg("Q"), py::arg("R"))
        .def("constraints", static_cast<ConstraintHandler& (Layer1DynamicQP::*)()>(&Layer1DynamicQP::constraints),
             py::return_value_policy::reference_internal);

    // ---- Layer2Config ----
    py::class_<Layer2Config>(m, "Layer2Config")
        .def(py::init<>())
        .def_readwrite("ss_cv_weights", &Layer2Config::ss_cv_weights)
        .def_readwrite("ss_mv_costs", &Layer2Config::ss_mv_costs)
        .def_readwrite("use_lp", &Layer2Config::use_lp);

    // ---- Layer2Result ----
    py::class_<Layer2Result>(m, "Layer2Result")
        .def(py::init<>())
        .def_readonly("u_ss", &Layer2Result::u_ss)
        .def_readonly("y_ss", &Layer2Result::y_ss)
        .def_readonly("status", &Layer2Result::status)
        .def_readonly("objective", &Layer2Result::objective)
        .def_readonly("solve_time_ms", &Layer2Result::solve_time_ms);

    // ---- Layer2SSTarget ----
    py::class_<Layer2SSTarget>(m, "Layer2SSTarget")
        .def(py::init<const StepResponseModel&, const Layer2Config&>(),
             py::arg("model"), py::arg("config"))
        .def("solve", &Layer2SSTarget::solve,
             py::arg("y_setpoint"), py::arg("disturbance"),
             py::arg("dv_values") = Eigen::VectorXd())
        .def("update_setpoints", &Layer2SSTarget::updateSetpoints, py::arg("y_sp"))
        .def("update_costs", &Layer2SSTarget::updateCosts, py::arg("mv_costs"))
        .def("update_gain_matrix", &Layer2SSTarget::updateGainMatrix, py::arg("G"))
        .def("gain_matrix", &Layer2SSTarget::gainMatrix, py::return_value_policy::reference_internal)
        .def("constraints", static_cast<ConstraintHandler& (Layer2SSTarget::*)()>(&Layer2SSTarget::constraints),
             py::return_value_policy::reference_internal);

    // ---- Layer3Config ----
    py::class_<Layer3Config>(m, "Layer3Config")
        .def(py::init<>())
        .def_readwrite("model_source", &Layer3Config::model_source)
        .def_readwrite("codegen_path", &Layer3Config::codegen_path)
        .def_readwrite("execution_interval_sec", &Layer3Config::execution_interval_sec)
        .def_readwrite("nlp_max_iter", &Layer3Config::nlp_max_iter)
        .def_readwrite("nlp_tolerance", &Layer3Config::nlp_tolerance);

    // ---- StateSpaceModel ----
    py::class_<StateSpaceModel>(m, "StateSpaceModel")
        .def(py::init<>())
        .def_readwrite("A", &StateSpaceModel::A)
        .def_readwrite("B", &StateSpaceModel::B)
        .def_readwrite("C", &StateSpaceModel::C)
        .def_readwrite("D", &StateSpaceModel::D);

    // ---- Layer3Result ----
    py::class_<Layer3Result>(m, "Layer3Result")
        .def_readonly("u_optimal", &Layer3Result::u_optimal)
        .def_readonly("y_optimal", &Layer3Result::y_optimal)
        .def_readonly("linearized", &Layer3Result::linearized)
        .def_readonly("updated_gain", &Layer3Result::updated_gain)
        .def_readonly("status", &Layer3Result::status)
        .def_readonly("objective", &Layer3Result::objective)
        .def_readonly("solve_time_ms", &Layer3Result::solve_time_ms);

    // ---- Layer3NLP ----
    py::class_<Layer3NLP>(m, "Layer3NLP")
        .def(py::init<const std::string&, const Layer3Config&>(),
             py::arg("codegen_path") = "", py::arg("config") = Layer3Config())
        .def("set_model_function", &Layer3NLP::setModelFunction, py::arg("fn"))
        .def("linearize_at", &Layer3NLP::linearizeAt,
             py::arg("x_op"), py::arg("u_op"))
        .def("solve", &Layer3NLP::solve,
             py::arg("x_current"), py::arg("u_current"),
             py::arg("parameters") = Eigen::VectorXd());

    // ---- Scaling ----
    py::class_<Scaling>(m, "Scaling")
        .def(py::init<const Eigen::VectorXd&, const Eigen::VectorXd&,
                       const Eigen::VectorXd&, const Eigen::VectorXd&>(),
             py::arg("cv_lo"), py::arg("cv_hi"), py::arg("mv_lo"), py::arg("mv_hi"))
        .def("scale_cv", &Scaling::scaleCV, py::arg("raw"))
        .def("scale_mv", &Scaling::scaleMV, py::arg("raw"))
        .def("unscale_cv", &Scaling::unscaleCV, py::arg("scaled"))
        .def("unscale_mv", &Scaling::unscaleMV, py::arg("scaled"))
        .def("scale_mv_increment", &Scaling::scaleMVIncrement, py::arg("du"))
        .def("unscale_mv_increment", &Scaling::unscaleMVIncrement, py::arg("du_scaled"));

    // ---- MPCConfig ----
    py::class_<MPCConfig>(m, "MPCConfig")
        .def(py::init<>())
        .def_readwrite("sample_time", &MPCConfig::sample_time)
        .def_readwrite("layer1", &MPCConfig::layer1)
        .def_readwrite("layer2", &MPCConfig::layer2)
        .def_readwrite("enable_layer3", &MPCConfig::enable_layer3)
        .def_readwrite("layer3", &MPCConfig::layer3)
        .def_readwrite("enable_storage", &MPCConfig::enable_storage);

    // ---- DiagnosticsInfo ----
    py::class_<DiagnosticsInfo>(m, "DiagnosticsInfo")
        .def(py::init<>())
        .def_readonly("layer1_status", &DiagnosticsInfo::layer1_status)
        .def_readonly("layer2_status", &DiagnosticsInfo::layer2_status)
        .def_readonly("layer3_status", &DiagnosticsInfo::layer3_status)
        .def_readonly("layer1_solve_ms", &DiagnosticsInfo::layer1_solve_ms)
        .def_readonly("layer2_solve_ms", &DiagnosticsInfo::layer2_solve_ms)
        .def_readonly("layer3_solve_ms", &DiagnosticsInfo::layer3_solve_ms)
        .def_readonly("total_solve_ms", &DiagnosticsInfo::total_solve_ms)
        .def_readonly("layer1_iterations", &DiagnosticsInfo::layer1_iterations)
        .def_readonly("layer2_iterations", &DiagnosticsInfo::layer2_iterations);

    // ---- ControllerStatus ----
    py::class_<ControllerStatus>(m, "ControllerStatus")
        .def(py::init<>())
        .def_readonly("mode", &ControllerStatus::mode)
        .def_readonly("is_running", &ControllerStatus::is_running)
        .def_readonly("cycle_count", &ControllerStatus::cycle_count)
        .def_readonly("total_cvs", &ControllerStatus::total_cvs)
        .def_readonly("total_mvs", &ControllerStatus::total_mvs);

    // ---- ControlOutput ----
    py::class_<MPCController::ControlOutput>(m, "ControlOutput")
        .def(py::init<>())
        .def_readonly("du", &MPCController::ControlOutput::du)
        .def_readonly("u_new", &MPCController::ControlOutput::u_new)
        .def_readonly("y_predicted", &MPCController::ControlOutput::y_predicted)
        .def_readonly("y_ss_target", &MPCController::ControlOutput::y_ss_target)
        .def_readonly("u_ss_target", &MPCController::ControlOutput::u_ss_target)
        .def_readonly("disturbance", &MPCController::ControlOutput::disturbance)
        .def_readonly("layer1_status", &MPCController::ControlOutput::layer1_status)
        .def_readonly("layer2_status", &MPCController::ControlOutput::layer2_status)
        .def_readonly("total_solve_time_ms", &MPCController::ControlOutput::total_solve_time_ms)
        .def_readonly("diagnostics", &MPCController::ControlOutput::diagnostics);

    // ---- MPCController ----
    py::class_<MPCController>(m, "MPCController")
        .def(py::init<const MPCConfig&, const StepResponseModel&>(),
             py::arg("config"), py::arg("model"))
        .def("execute", &MPCController::execute,
             py::arg("y_measured"), py::arg("u_current"),
             py::arg("dv_values") = Eigen::VectorXd())
        .def("set_setpoints", &MPCController::setSetpoints, py::arg("y_sp"))
        .def("set_setpoint", &MPCController::setSetpoint,
             py::arg("cv_idx"), py::arg("sp"))
        .def("set_cv_bounds", &MPCController::setCVBounds,
             py::arg("cv_idx"), py::arg("lo"), py::arg("hi"))
        .def("set_mv_bounds", &MPCController::setMVBounds,
             py::arg("mv_idx"), py::arg("lo"), py::arg("hi"))
        .def("set_mv_rate_limit", &MPCController::setMVRateLimit,
             py::arg("mv_idx"), py::arg("rate"))
        .def("set_cv_weight", &MPCController::setCVWeight,
             py::arg("cv_idx"), py::arg("weight"))
        .def("set_mv_weight", &MPCController::setMVWeight,
             py::arg("mv_idx"), py::arg("weight"))
        .def("set_cv_concern", &MPCController::setCVConcern,
             py::arg("cv_idx"), py::arg("concern_lo"), py::arg("concern_hi"))
        .def("set_cv_rank", &MPCController::setCVRank,
             py::arg("cv_idx"), py::arg("rank_lo"), py::arg("rank_hi"))
        .def("set_mv_cost_rank", &MPCController::setMVCostRank,
             py::arg("mv_idx"), py::arg("rank"))
        .def("set_mv_cost", &MPCController::setMVCost,
             py::arg("mv_idx"), py::arg("cost"))
        .def("update_gain_matrix", &MPCController::updateGainMatrix,
             py::arg("G"),
             "Update Layer 2 gain matrix (called by Layer 3 RTO).")
        .def("set_mode", &MPCController::setMode, py::arg("mode"))
        .def("mode", &MPCController::mode)
        .def("status", &MPCController::status)
        .def("model", &MPCController::model, py::return_value_policy::reference_internal)
        .def("ny", &MPCController::ny)
        .def("nu", &MPCController::nu)
        .def("cycle_count", &MPCController::cycleCount)
        .def("__repr__", [](const MPCController& c) {
            return "<MPCController ny=" + std::to_string(c.ny()) +
                   " nu=" + std::to_string(c.nu()) +
                   " cycles=" + std::to_string(c.cycleCount()) + ">";
        });
}
