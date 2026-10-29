#include <stdio.h>

#include "pico/stdlib.h"
#include "hardware/clocks.h"
#include "hardware/pio.h"

#include "squarewave.pio.h"

#define SIGNAL_GPIO 15
#define SIGNAL_FREQUENCY_HZ 1000.0f

int main(void)
{
    stdio_init_all();
    sleep_ms(2000);

    PIO pio = pio0;
    uint sm = pio_claim_unused_sm(pio, true);

    uint offset = pio_add_program(pio, &squarewave_program);

    pio_sm_config config =
        squarewave_program_get_default_config(offset);

    sm_config_set_set_pins(&config, SIGNAL_GPIO, 1);

    uint32_t sys_clock_hz = clock_get_hz(clk_sys);

    // 64 PIO-Taktzyklen pro vollständiger Periode
    float divider =
        (float)sys_clock_hz /
        (SIGNAL_FREQUENCY_HZ * 64.0f);

    sm_config_set_clkdiv(&config, divider);

    pio_gpio_init(pio, SIGNAL_GPIO);

    pio_sm_set_consecutive_pindirs(
        pio, sm, SIGNAL_GPIO, 1, true
    );

    pio_sm_init(pio, sm, offset, &config);
    pio_sm_set_enabled(pio, sm, true);

    while (true) {
        printf("PIO-Rechtecksignal aktiv | GPIO: %d | Sollfrequenz: %.0f Hz\n",
               SIGNAL_GPIO, SIGNAL_FREQUENCY_HZ);
        stdio_flush();
        sleep_ms(1000);
    }

    while (true) {
        sleep_ms(1000);
    }

    return 0;
}
