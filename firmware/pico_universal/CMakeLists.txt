cmake_minimum_required(VERSION 3.13)

set(PICO_SDK_PATH
    "${CMAKE_CURRENT_LIST_DIR}/../../pico-sdk"
    CACHE PATH "Path to the Raspberry Pi Pico SDK")

include("${PICO_SDK_PATH}/external/pico_sdk_import.cmake")

project(pico_universal C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(PICO_BOARD pico2 CACHE STRING "Target board")
set(PICO_FLASH_SIZE_BYTES 4128768)

pico_sdk_init()

add_library(pico_universal STATIC
    src/device_config.c
    src/resource_manager.c
    src/gpio_configurator.c
    src/gpio_configurator_pico.c
    src/device_runtime.c
    src/device_runtime_pico.c
    src/pio_runtime.c
    src/pio_runtime_pico.c
    src/signal_generator_pico.c
    src/signal_analyzer_pico.c
    src/config_storage.c
    src/peripheral_runtime_pico.c
)

pico_generate_pio_header(
    pico_universal
    ${CMAKE_CURRENT_LIST_DIR}/src/squarewave.pio
)

target_include_directories(pico_universal PUBLIC
    "${CMAKE_CURRENT_LIST_DIR}/include"
)

target_link_libraries(pico_universal PUBLIC
    pico_stdlib
    hardware_gpio
    hardware_pio
    hardware_spi
    hardware_i2c
    hardware_uart
    hardware_clocks
    hardware_flash
    pico_flash
)

add_executable(pico_universal_firmware
    src/main.c
)

target_link_libraries(pico_universal_firmware
    PRIVATE
        pico_universal
        pico_stdlib
)

pico_enable_stdio_usb(pico_universal_firmware 1)
pico_enable_stdio_uart(pico_universal_firmware 0)

pico_add_extra_outputs(pico_universal_firmware)
