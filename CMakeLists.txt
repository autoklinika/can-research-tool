cmake_minimum_required(VERSION 3.21)
project(can_research_tool LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(CRT_BUILD_TESTS "Build CRT unit tests" ON)

add_library(crt_filter_engine
    src/filter/filter_engine.cpp
)

target_include_directories(crt_filter_engine
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(crt_filter_engine PUBLIC cxx_std_20)

if(MSVC)
    target_compile_options(crt_filter_engine PRIVATE /W4 /permissive-)
else()
    target_compile_options(crt_filter_engine PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()

if(CRT_BUILD_TESTS)
    enable_testing()

    add_executable(crt_filter_engine_tests
        tests/filter_engine_tests.cpp
    )
    target_link_libraries(crt_filter_engine_tests PRIVATE crt_filter_engine)

    add_test(NAME crt_filter_engine_tests COMMAND crt_filter_engine_tests)
endif()
