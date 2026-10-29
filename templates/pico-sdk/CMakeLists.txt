cmake_minimum_required(VERSION 3.13)

if(NOT PICO_SDK_PATH)
    if(DEFINED ENV{PICO_SDK_PATH})
        set(PICO_SDK_PATH "$ENV{PICO_SDK_PATH}")
    else()
        message(FATAL_ERROR
            "PICO_SDK_PATH is not set. Configure it with "
            "-DPICO_SDK_PATH=/path/to/pico-sdk or set the PICO_SDK_PATH environment variable.")
    endif()
endif()

set(PICO_SDK_PATH "${PICO_SDK_PATH}"
    CACHE PATH "Path to the Raspberry Pi Pico SDK")

if(NOT EXISTS "${PICO_SDK_PATH}/external/pico_sdk_import.cmake")
    message(FATAL_ERROR
        "Pico SDK import file not found: ${PICO_SDK_PATH}/external/pico_sdk_import.cmake")
endif()

include("${PICO_SDK_PATH}/external/pico_sdk_import.cmake")

project(example_pico_app C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(PICO_BOARD pico2 CACHE STRING "Target board")

pico_sdk_init()

add_executable(example_pico_app
    src/main.c
)

target_link_libraries(example_pico_app
    pico_stdlib
)

pico_enable_stdio_usb(example_pico_app 1)
pico_enable_stdio_uart(example_pico_app 0)
pico_add_extra_outputs(example_pico_app)
