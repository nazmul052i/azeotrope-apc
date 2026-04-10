#include <pybind11/pybind11.h>
#include <pybind11/eigen.h>
#include <pybind11/stl.h>
#include "azeoapc/azeoapc.h"

namespace py = pybind11;

PYBIND11_MODULE(_azeoapc_core, m) {
    m.doc() = "Azeotrope APC C++ core bindings";

    // Version
    m.attr("__version__") = azeoapc::VERSION_STRING;

    // Enums
    py::enum_<azeoapc::SolverStatus>(m, "SolverStatus")
        .value("OPTIMAL", azeoapc::SolverStatus::OPTIMAL)
        .value("INFEASIBLE", azeoapc::SolverStatus::INFEASIBLE)
        .value("MAX_ITER", azeoapc::SolverStatus::MAX_ITER)
        .value("TIME_LIMIT", azeoapc::SolverStatus::TIME_LIMIT)
        .value("NUMERICAL_ERROR", azeoapc::SolverStatus::NUMERICAL_ERROR)
        .value("NOT_SOLVED", azeoapc::SolverStatus::NOT_SOLVED);

    py::enum_<azeoapc::ControllerMode>(m, "ControllerMode")
        .value("MANUAL", azeoapc::ControllerMode::MANUAL)
        .value("AUTO", azeoapc::ControllerMode::AUTO)
        .value("CASCADE", azeoapc::ControllerMode::CASCADE);

    // StepResponseModel
    py::class_<azeoapc::StepResponseModel>(m, "StepResponseModel")
        .def(py::init<int, int, int, double>(),
             py::arg("ny"), py::arg("nu"),
             py::arg("model_horizon"), py::arg("sample_time"))
        .def_static("from_hdf5", &azeoapc::StepResponseModel::fromHDF5)
        .def_static("from_state_space", &azeoapc::StepResponseModel::fromStateSpace)
        .def_static("from_foptd", &azeoapc::StepResponseModel::fromFOPTD)
        .def("ny", &azeoapc::StepResponseModel::ny)
        .def("nu", &azeoapc::StepResponseModel::nu)
        .def("model_horizon", &azeoapc::StepResponseModel::modelHorizon)
        .def("sample_time", &azeoapc::StepResponseModel::sampleTime)
        .def("coefficient", &azeoapc::StepResponseModel::coefficient)
        .def("step_response", &azeoapc::StepResponseModel::stepResponse)
        .def("steady_state_gain", &azeoapc::StepResponseModel::steadyStateGain)
        .def("predict_free", &azeoapc::StepResponseModel::predictFree)
        .def("save_hdf5", &azeoapc::StepResponseModel::saveHDF5);

    // DynamicMatrix
    py::class_<azeoapc::DynamicMatrix>(m, "DynamicMatrix")
        .def(py::init<const azeoapc::StepResponseModel&, int, int>())
        .def("matrix", &azeoapc::DynamicMatrix::matrix)
        .def("prediction_horizon", &azeoapc::DynamicMatrix::predictionHorizon)
        .def("control_horizon", &azeoapc::DynamicMatrix::controlHorizon);

    // MPCController
    py::class_<azeoapc::MPCController>(m, "MPCController")
        .def_static("from_files", &azeoapc::MPCController::fromFiles)
        .def("execute", &azeoapc::MPCController::execute)
        .def("set_setpoints", &azeoapc::MPCController::setSetpoints)
        .def("set_setpoint", &azeoapc::MPCController::setSetpoint)
        .def("set_cv_bounds", &azeoapc::MPCController::setCVBounds)
        .def("set_mv_bounds", &azeoapc::MPCController::setMVBounds)
        .def("set_mv_rate_limit", &azeoapc::MPCController::setMVRateLimit)
        .def("set_mode", &azeoapc::MPCController::setMode)
        .def("mode", &azeoapc::MPCController::mode)
        .def("ny", &azeoapc::MPCController::ny)
        .def("nu", &azeoapc::MPCController::nu)
        .def("cycle_count", &azeoapc::MPCController::cycleCount);

    // ControlOutput
    py::class_<azeoapc::MPCController::ControlOutput>(m, "ControlOutput")
        .def_readonly("du", &azeoapc::MPCController::ControlOutput::du)
        .def_readonly("u_new", &azeoapc::MPCController::ControlOutput::u_new)
        .def_readonly("y_predicted", &azeoapc::MPCController::ControlOutput::y_predicted)
        .def_readonly("y_ss_target", &azeoapc::MPCController::ControlOutput::y_ss_target)
        .def_readonly("u_ss_target", &azeoapc::MPCController::ControlOutput::u_ss_target)
        .def_readonly("layer1_status", &azeoapc::MPCController::ControlOutput::layer1_status)
        .def_readonly("layer2_status", &azeoapc::MPCController::ControlOutput::layer2_status)
        .def_readonly("total_solve_time_ms", &azeoapc::MPCController::ControlOutput::total_solve_time_ms);

    // Storage (read-only access from Python)
    py::class_<azeoapc::Storage>(m, "Storage")
        .def("get_cv_timeseries", &azeoapc::Storage::getCVTimeseries)
        .def("get_mv_timeseries", &azeoapc::Storage::getMVTimeseries)
        .def("get_solver_stats", &azeoapc::Storage::getSolverStats)
        .def("database_size", &azeoapc::Storage::databaseSize);
}
