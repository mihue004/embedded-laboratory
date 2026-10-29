cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(pico_signal_analyzer C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(pico_signal_analyzer
    src/main.c
)

target_link_libraries(pico_signal_analyzer
    pico_stdlib
    hardware_gpio
    hardware_timer
    hardware_sync
)

pico_enable_stdio_usb(pico_signal_analyzer 1)
pico_enable_stdio_uart(pico_signal_analyzer 0)

pico_add_extra_outputs(pico_signal_analyzer)
