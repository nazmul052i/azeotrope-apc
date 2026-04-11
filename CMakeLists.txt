cmake_minimum_required(VERSION 3.20)
project(azeotrope-apc VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Options
option(AZEOAPC_BUILD_TESTS "Build C++ unit tests" ON)
option(AZEOAPC_BUILD_BINDINGS "Build Python bindings (pybind11)" OFF)
option(AZEOAPC_BUILD_EXAMPLES "Build C++ examples" ON)
option(AZEOAPC_ENABLE_LAYER1 "Enable Layer 1 QP (requires OSQP)" OFF)
option(AZEOAPC_ENABLE_LAYER2 "Enable Layer 2 LP (requires HiGHS)" OFF)
option(AZEOAPC_ENABLE_LAYER3 "Enable Layer 3 NLP (requires CasADi)" OFF)
option(AZEOAPC_ENABLE_CONFIG "Enable YAML config loading (requires yaml-cpp)" OFF)

# Dependencies -- always required
include(FetchContent)

find_package(Eigen3 3.3 QUIET)
if(NOT Eigen3_FOUND)
    message(STATUS "Eigen3 not found, fetching via FetchContent")
    FetchContent_Declare(
        eigen
        GIT_REPOSITORY https://gitlab.com/libeigen/eigen.git
        GIT_TAG 3.4.0
        GIT_SHALLOW TRUE
    )
    set(EIGEN_BUILD_DOC OFF CACHE BOOL "" FORCE)
    set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
    set(EIGEN_BUILD_PKGCONFIG OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(eigen)
endif()

# OSQP (Layer 1 QP solver -- always required)
find_package(osqp QUIET)
if(NOT osqp_FOUND)
    message(STATUS "OSQP not found, fetching via FetchContent")
    FetchContent_Declare(
        osqp
        GIT_REPOSITORY https://github.com/osqp/osqp.git
        GIT_TAG v0.6.3
    )
    FetchContent_MakeAvailable(osqp)
endif()

# HiGHS (Layer 2 LP/QP solver -- always required)
find_package(highs QUIET)
if(NOT highs_FOUND)
    message(STATUS "HiGHS not found, fetching via FetchContent")
    FetchContent_Declare(
        highs
        GIT_REPOSITORY https://github.com/ERGO-Code/HiGHS.git
        GIT_TAG v1.7.0
    )
    set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(highs)
endif()

# HDF5
find_package(HDF5 COMPONENTS CXX QUIET)

# yaml-cpp
if(AZEOAPC_ENABLE_CONFIG)
    find_package(yaml-cpp QUIET)
    if(NOT yaml-cpp_FOUND)
        FetchContent_Declare(
            yaml-cpp
            GIT_REPOSITORY https://github.com/jbeder/yaml-cpp.git
            GIT_TAG 0.8.0
        )
        FetchContent_MakeAvailable(yaml-cpp)
    endif()
endif()

# spdlog (logging)
find_package(spdlog QUIET)
if(NOT spdlog_FOUND)
    message(STATUS "spdlog not found, fetching via FetchContent")
    FetchContent_Declare(
        spdlog
        GIT_REPOSITORY https://github.com/gabime/spdlog.git
        GIT_TAG v1.12.0
    )
    set(SPDLOG_FMT_EXTERNAL OFF CACHE BOOL "" FORCE)
    set(SPDLOG_BUILD_SHARED OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(spdlog)
endif()

# CasADi (optional, Layer 3)
if(AZEOAPC_ENABLE_LAYER3)
    find_package(casadi REQUIRED)
endif()

# Core library
add_subdirectory(core)

# Python bindings
if(AZEOAPC_BUILD_BINDINGS)
    add_subdirectory(bindings)
endif()

# Examples
if(AZEOAPC_BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()

# Tests
if(AZEOAPC_BUILD_TESTS)
    enable_testing()
    add_subdirectory(core/tests)
endif()
