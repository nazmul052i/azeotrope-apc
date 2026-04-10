#pragma once

#include <string>
#include "azeoapc/mpc_controller.h"

namespace azeoapc {

/**
 * Configuration loader
 *
 * Parses YAML config files and HDF5 model files into MPCConfig
 * and StepResponseModel objects.
 */

/// Load controller configuration from YAML
MPCConfig loadConfig(const std::string& yaml_path);

/// Save controller configuration to YAML
void saveConfig(const MPCConfig& config, const std::string& yaml_path);

/// Validate config completeness and consistency
struct ValidationResult {
    bool valid;
    std::vector<std::string> errors;
    std::vector<std::string> warnings;
};

ValidationResult validateConfig(const MPCConfig& config,
                                 const StepResponseModel& model);

}  // namespace azeoapc
