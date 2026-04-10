set(AZEOAPC_CORE_SOURCES
    src/step_response_model.cpp
    src/dynamic_matrix.cpp
    src/prediction_engine.cpp
    src/disturbance_observer.cpp
    src/constraint_handler.cpp
    src/scaling.cpp
    src/layer1_dynamic_qp.cpp
    src/layer2_ss_target.cpp
    src/mpc_controller.cpp
    src/config.cpp
    src/storage.cpp
)

if(AZEOAPC_ENABLE_LAYER3)
    list(APPEND AZEOAPC_CORE_SOURCES src/layer3_nlp.cpp)
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
    PRIVATE
        osqp::osqp
        highs::highs
        yaml-cpp::yaml-cpp
)

if(HDF5_FOUND)
    target_link_libraries(azeoapc PRIVATE ${HDF5_CXX_LIBRARIES})
    target_include_directories(azeoapc PRIVATE ${HDF5_INCLUDE_DIRS})
    target_compile_definitions(azeoapc PRIVATE AZEOAPC_HAS_HDF5)
endif()

if(AZEOAPC_ENABLE_LAYER3)
    target_link_libraries(azeoapc PRIVATE casadi)
    target_compile_definitions(azeoapc PRIVATE AZEOAPC_HAS_CASADI)
endif()

# SQLite (bundled, for timeseries storage)
target_compile_definitions(azeoapc PRIVATE AZEOAPC_HAS_SQLITE)
