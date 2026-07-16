cmake_minimum_required(VERSION 3.21)
project(can_research_tool LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(CRT_BUILD_TESTS "Build CRT unit tests" ON)
option(CRT_BUILD_APP "Build Qt/QML CAN Research Tool application" ON)

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

if(CRT_BUILD_APP)
    find_package(Qt6 6.5 QUIET COMPONENTS Core Gui Qml Quick QuickControls2)
    if(Qt6_FOUND)
        qt_standard_project_setup(REQUIRES 6.5)

        add_library(crt_filter_qt
            src/filter/qt/filter_preset_store.cpp
            include/crt/filter/qt/filter_preset_store.hpp
        )
        target_link_libraries(crt_filter_qt PUBLIC crt_filter_engine Qt6::Core Qt6::Qml)
        target_include_directories(crt_filter_qt PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
        set_target_properties(crt_filter_qt PROPERTIES AUTOMOC ON)

        qt_add_executable(crt_app
            app/crt_main.cpp
        )
        target_link_libraries(crt_app PRIVATE crt_filter_qt Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2)

        qt_add_qml_module(crt_app
            URI CRT.App
            VERSION 1.0
            QML_FILES
                qml/CRT/App/Main.qml
                qml/CRT/App/ActivityButton.qml
                qml/CRT/App/FiltersPage.qml
                qml/CRT/App/PlaceholderPage.qml
        )
    else()
        message(STATUS "Qt6 was not found; CRT application target is skipped")
    endif()
endif()

if(CRT_BUILD_TESTS)
    enable_testing()

    add_executable(crt_filter_engine_tests
        tests/filter_engine_tests.cpp
    )
    target_link_libraries(crt_filter_engine_tests PRIVATE crt_filter_engine)

    add_test(NAME crt_filter_engine_tests COMMAND crt_filter_engine_tests)
endif()
