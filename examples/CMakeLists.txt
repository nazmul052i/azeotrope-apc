# Phase 1 examples
add_executable(cstr_closed_loop cstr_closed_loop.cpp)
target_link_libraries(cstr_closed_loop PRIVATE azeoapc::azeoapc)

# Phase 2+ examples (stubs, need Layer 1/2/3)
# add_executable(mimo_wood_berry mimo_wood_berry.cpp)
# target_link_libraries(mimo_wood_berry PRIVATE azeoapc::azeoapc)
#
# add_executable(cstr_three_layer cstr_three_layer.cpp)
# target_link_libraries(cstr_three_layer PRIVATE azeoapc::azeoapc)
