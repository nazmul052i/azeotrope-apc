# C++ examples
add_executable(siso_foptd siso_foptd.cpp)
target_link_libraries(siso_foptd PRIVATE azeoapc::azeoapc)

add_executable(mimo_wood_berry mimo_wood_berry.cpp)
target_link_libraries(mimo_wood_berry PRIVATE azeoapc::azeoapc)

add_executable(cstr_three_layer cstr_three_layer.cpp)
target_link_libraries(cstr_three_layer PRIVATE azeoapc::azeoapc)
