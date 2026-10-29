cmake_minimum_required(VERSION 3.13)

set(PICO_SDK_PATH
    "${CMAKE_CURRENT_LIST_DIR}/../../pico-sdk"
    CACHE PATH "Path to the Raspberry Pi Pico SDK")

include("${PICO_SDK_PATH}/external/pico_sdk_import.cmake")

project(pico_testbench C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(PICO_BOARD pico2 CACHE STRING "Target board")

pico_sdk_init()

add_executable(pico_testbench
    src/main.c
)

pico_generate_pio_header(
    pico_testbench
    "${CMAKE_CURRENT_LIST_DIR}/src/squarewave.pio"
)

target_link_libraries(pico_testbench
    pico_stdlib
    hardware_pio
    hardware_clocks
)

pico_enable_stdio_usb(pico_testbench 1)
pico_enable_stdio_uart(pico_testbench 0)
pico_add_extra_outputs(pico_testbench)
