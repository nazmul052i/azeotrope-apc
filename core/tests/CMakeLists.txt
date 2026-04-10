include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.14.0
)
FetchContent_MakeAvailable(googletest)

# Test executables
set(TEST_SOURCES
    test_step_response.cpp
    test_dynamic_matrix.cpp
    test_prediction.cpp
    test_layer1_qp.cpp
    test_layer2_lp.cpp
    test_constraint_handler.cpp
    test_storage.cpp
    test_mpc_controller.cpp
)

foreach(TEST_SRC ${TEST_SOURCES})
    get_filename_component(TEST_NAME ${TEST_SRC} NAME_WE)
    add_executable(${TEST_NAME} ${TEST_SRC})
    target_link_libraries(${TEST_NAME}
        PRIVATE
            azeoapc::azeoapc
            GTest::gtest_main
    )
    add_test(NAME ${TEST_NAME} COMMAND ${TEST_NAME})
endforeach()

if(AZEOAPC_ENABLE_LAYER3)
    add_executable(test_layer3_nlp test_layer3_nlp.cpp)
    target_link_libraries(test_layer3_nlp PRIVATE azeoapc::azeoapc GTest::gtest_main)
    add_test(NAME test_layer3_nlp COMMAND test_layer3_nlp)
endif()
