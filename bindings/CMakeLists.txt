find_package(pybind11 QUIET)
if(NOT pybind11_FOUND)
    include(FetchContent)
    FetchContent_Declare(
        pybind11
        GIT_REPOSITORY https://github.com/pybind/pybind11.git
        GIT_TAG v2.12.0
    )
    FetchContent_MakeAvailable(pybind11)
endif()

pybind11_add_module(_azeoapc_core pybind_opendmc.cpp)
target_link_libraries(_azeoapc_core PRIVATE azeoapc::azeoapc spdlog::spdlog)
