#pragma once

/**
 * Azeotrope APC -- Master Include
 *
 * Open-source Advanced Process Control platform with
 * three-layer optimization (NLP + LP + QP).
 */

#include "azeoapc/types.h"
#include "azeoapc/step_response_model.h"
#include "azeoapc/dynamic_matrix.h"
#include "azeoapc/prediction_engine.h"
#include "azeoapc/disturbance_observer.h"
#include "azeoapc/constraint_handler.h"
#include "azeoapc/scaling.h"
#include "azeoapc/layer1_dynamic_qp.h"
#include "azeoapc/layer2_ss_target.h"
#include "azeoapc/storage.h"
#include "azeoapc/mpc_controller.h"

#ifdef AZEOAPC_HAS_CASADI
#include "azeoapc/layer3_nlp.h"
#endif

namespace azeoapc {
    constexpr int VERSION_MAJOR = 0;
    constexpr int VERSION_MINOR = 1;
    constexpr int VERSION_PATCH = 0;
    constexpr const char* VERSION_STRING = "0.1.0";
}
