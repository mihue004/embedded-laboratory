cmake_minimum_required(VERSION 3.13)

set(PICO_SDK_PATH
    "${CMAKE_CURRENT_LIST_DIR}/../../pico-sdk"
    CACHE PATH "Path to the Raspberry Pi Pico SDK"
)

include("${PICO_SDK_PATH}/external/pico_sdk_import.cmake")

project(pico_pio_squarewave C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

set(PICO_BOARD pico2 CACHE STRING "Target board")

pico_sdk_init()

add_executable(pio_squarewave
    src/main.c
)

pico_generate_pio_header(
    pio_squarewave
    "${CMAKE_CURRENT_LIST_DIR}/src/squarewave.pio"
)

target_link_libraries(pio_squarewave
    pico_stdlib
    hardware_pio
    hardware_clocks
)

pico_enable_stdio_usb(pio_squarewave 1)
pico_enable_stdio_uart(pio_squarewave 0)

pico_add_extra_outputs(pio_squarewave)
