# Core library sources
set(AZEOAPC_CORE_SOURCES
    src/types.cpp
    src/step_response_model.cpp
    src/dynamic_matrix.cpp
    src/prediction_engine.cpp
    src/disturbance_observer.cpp
    src/scaling.cpp
    src/constraint_handler.cpp
    src/layer1_dynamic_qp.cpp
    src/layer2_ss_target.cpp
    src/layer3_nlp.cpp
    src/mpc_controller.cpp
    src/storage.cpp
)

if(AZEOAPC_ENABLE_CONFIG)
    list(APPEND AZEOAPC_CORE_SOURCES src/config.cpp)
endif()

add_library(azeoapc ${AZEOAPC_CORE_SOURCES})
add_library(azeoapc::azeoapc ALIAS azeoapc)

target_include_directories(azeoapc
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
)

target_link_libraries(azeoapc
    PUBLIC
        Eigen3::Eigen
)

# spdlog -- logging
target_link_libraries(azeoapc PRIVATE spdlog::spdlog)

# OSQP -- required for Layer 1 QP
target_link_libraries(azeoapc PRIVATE osqpstatic)
target_compile_definitions(azeoapc PRIVATE AZEOAPC_HAS_OSQP)

# HiGHS -- required for Layer 2 SS Target
target_link_libraries(azeoapc PRIVATE highs)
target_compile_definitions(azeoapc PRIVATE AZEOAPC_HAS_HIGHS)

if(AZEOAPC_ENABLE_CONFIG AND TARGET yaml-cpp::yaml-cpp)
    target_link_libraries(azeoapc PRIVATE yaml-cpp::yaml-cpp)
    target_compile_definitions(azeoapc PRIVATE AZEOAPC_HAS_YAML)
endif()

if(HDF5_FOUND)
    target_link_libraries(azeoapc PRIVATE ${HDF5_CXX_LIBRARIES})
    target_include_directories(azeoapc PRIVATE ${HDF5_INCLUDE_DIRS})
    target_compile_definitions(azeoapc PRIVATE AZEOAPC_HAS_HDF5)
endif()

if(AZEOAPC_ENABLE_LAYER3)
    target_link_libraries(azeoapc PRIVATE casadi)
    target_compile_definitions(azeoapc PRIVATE AZEOAPC_HAS_CASADI)
endif()
