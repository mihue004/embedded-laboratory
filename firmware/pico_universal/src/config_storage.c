#include "config_storage.h"

#include "hardware/flash.h"
#include "hardware/sync.h"
#include "pico/flash.h"
#include "pico/platform.h"
#include "pico/error.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

#define CONFIG_STORAGE_MAGIC       0x454C4142u
#define CONFIG_STORAGE_VERSION     2u
#define CONFIG_STORAGE_LEGACY_VERSION 1u

#define CONFIG_FLASH_TOTAL_SIZE    (4u * 1024u * 1024u)

#define CONFIG_SLOT_A_OFFSET \
    (CONFIG_FLASH_TOTAL_SIZE - 2u * FLASH_SECTOR_SIZE)

#define CONFIG_SLOT_B_OFFSET \
    (CONFIG_FLASH_TOTAL_SIZE - FLASH_SECTOR_SIZE)

typedef struct {
    uint32_t magic;
    uint32_t version;
    uint32_t data_size;
    uint32_t generation;
    uint32_t crc32;
    device_config_t config;
} config_storage_record_t;

/* Alte Speicherstruktur für die Migration vorhandener Konfigurationen. */
typedef struct {
    uint32_t magic;
    uint32_t version;
    uint32_t data_size;
    uint32_t crc32;
    device_config_t config;
} legacy_storage_record_t;

#define CONFIG_DATA_SIZE \
    ((sizeof(config_storage_record_t) + FLASH_PAGE_SIZE - 1u) \
     / FLASH_PAGE_SIZE * FLASH_PAGE_SIZE)

typedef struct {
    uint8_t data[CONFIG_DATA_SIZE];
} config_flash_buffer_t;

typedef struct {
    uint32_t offset;
    const config_flash_buffer_t *buffer;
} config_flash_write_t;

_Static_assert(
    CONFIG_DATA_SIZE <= FLASH_SECTOR_SIZE,
    "Configuration exceeds reserved flash sector"
);

_Static_assert(
    CONFIG_SLOT_A_OFFSET >= CONFIG_FLASH_TOTAL_SIZE - 65536u,
    "Configuration slot A overlaps application flash"
);

static uint32_t calculate_crc32(
    const uint8_t *data,
    size_t length
)
{
    uint32_t crc = 0xFFFFFFFFu;

    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];

        for (unsigned int bit = 0; bit < 8; ++bit) {
            uint32_t mask = (uint32_t)-(int32_t)(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }

    return ~crc;
}

static bool read_slot(
    uint32_t offset,
    config_storage_record_t *record
)
{
    if (record == NULL) {
        return false;
    }

    const config_storage_record_t *stored =
        (const config_storage_record_t *)(XIP_BASE + offset);

    memcpy(record, stored, sizeof(*record));

    if (record->magic != CONFIG_STORAGE_MAGIC ||
        record->version != CONFIG_STORAGE_VERSION ||
        record->data_size != sizeof(device_config_t)) {
        return false;
    }

    uint32_t crc = calculate_crc32(
        (const uint8_t *)&record->config,
        sizeof(device_config_t)
    );

    return crc == record->crc32 &&
           device_config_validate(&record->config);
}

static void debug_slot(const char *name, uint32_t offset)
{
    config_storage_record_t record;

    memcpy(
        &record,
        (const void *)(XIP_BASE + offset),
        sizeof(record)
    );

    uint32_t calculated_crc = calculate_crc32(
        (const uint8_t *)&record.config,
        sizeof(device_config_t)
    );

    bool header_valid =
        record.magic == CONFIG_STORAGE_MAGIC &&
        record.version == CONFIG_STORAGE_VERSION &&
        record.data_size == sizeof(device_config_t);

    bool crc_valid = calculated_crc == record.crc32;

    bool config_valid =
        header_valid &&
        crc_valid &&
        device_config_validate(&record.config);

    printf(
        "CONFIG,DEBUG,%s,OFFSET,%08lX,MAGIC,%08lX,"
        "VERSION,%lu,SIZE,%lu,GEN,%lu,CRC,%08lX,"
        "CALC_CRC,%08lX,HEADER,%u,CRC_OK,%u,VALID,%u\n",
        name,
        (unsigned long)offset,
        (unsigned long)record.magic,
        (unsigned long)record.version,
        (unsigned long)record.data_size,
        (unsigned long)record.generation,
        (unsigned long)record.crc32,
        (unsigned long)calculated_crc,
        header_valid ? 1u : 0u,
        crc_valid ? 1u : 0u,
        config_valid ? 1u : 0u
    );
}

void config_storage_debug(void)
{
    debug_slot("A", CONFIG_SLOT_A_OFFSET);
    debug_slot("B", CONFIG_SLOT_B_OFFSET);
}

static bool read_legacy_config(device_config_t *config)
{
    legacy_storage_record_t record;

    const legacy_storage_record_t *stored =
        (const legacy_storage_record_t *)(
            XIP_BASE + CONFIG_SLOT_B_OFFSET
        );

    memcpy(&record, stored, sizeof(record));

    if (record.magic != CONFIG_STORAGE_MAGIC ||
        record.version != CONFIG_STORAGE_LEGACY_VERSION ||
        record.data_size != sizeof(device_config_t)) {
        return false;
    }

    uint32_t crc = calculate_crc32(
        (const uint8_t *)&record.config,
        sizeof(device_config_t)
    );

    if (crc != record.crc32 ||
        !device_config_validate(&record.config)) {
        return false;
    }

    memcpy(config, &record.config, sizeof(*config));
    return true;
}

bool config_storage_load(device_config_t *config)
{
    if (config == NULL) {
        return false;
    }

    config_storage_record_t slot_a;
    config_storage_record_t slot_b;

    bool valid_a = read_slot(CONFIG_SLOT_A_OFFSET, &slot_a);
    bool valid_b = read_slot(CONFIG_SLOT_B_OFFSET, &slot_b);

    if (valid_a && valid_b) {
        const config_storage_record_t *newest =
            (int32_t)(slot_b.generation - slot_a.generation) > 0
                ? &slot_b
                : &slot_a;

        memcpy(config, &newest->config, sizeof(*config));
        return true;
    }

    if (valid_a) {
        memcpy(config, &slot_a.config, sizeof(*config));
        return true;
    }

    if (valid_b) {
        memcpy(config, &slot_b.config, sizeof(*config));
        return true;
    }

    /* Migration des bisherigen Ein-Slot-Formats. */
    return read_legacy_config(config);
}

static void __no_inline_not_in_flash_func(flash_write_callback)(void *param)
{
    const config_flash_write_t *write =
        (const config_flash_write_t *)param;

    flash_range_erase(write->offset, FLASH_SECTOR_SIZE);

    flash_range_program(
        write->offset,
        write->buffer->data,
        CONFIG_DATA_SIZE
    );
}

bool config_storage_save(const device_config_t *config)
{
    if (config == NULL || !device_config_validate(config)) {
        return false;
    }

    config_storage_record_t slot_a;
    config_storage_record_t slot_b;

    bool valid_a = read_slot(CONFIG_SLOT_A_OFFSET, &slot_a);
    bool valid_b = read_slot(CONFIG_SLOT_B_OFFSET, &slot_b);

    uint32_t target_offset;
    uint32_t generation = 1;

    if (valid_a && valid_b) {
        bool a_is_newer =
            (int32_t)(slot_a.generation - slot_b.generation) > 0;

        target_offset = a_is_newer
            ? CONFIG_SLOT_B_OFFSET
            : CONFIG_SLOT_A_OFFSET;

        generation = (a_is_newer
            ? slot_a.generation
            : slot_b.generation) + 1u;
    } else if (valid_a) {
        target_offset = CONFIG_SLOT_B_OFFSET;
        generation = slot_a.generation + 1u;
    } else if (valid_b) {
        target_offset = CONFIG_SLOT_A_OFFSET;
        generation = slot_b.generation + 1u;
    } else {
        /* Auch bei alter Legacy-Konfiguration zuerst Slot A nutzen. */
        target_offset = CONFIG_SLOT_A_OFFSET;
    }

    static config_flash_buffer_t buffer
        __attribute__((aligned(FLASH_PAGE_SIZE)));

    memset(buffer.data, 0xFF, sizeof(buffer.data));

    config_storage_record_t record = {
        .magic = CONFIG_STORAGE_MAGIC,
        .version = CONFIG_STORAGE_VERSION,
        .data_size = sizeof(device_config_t),
        .generation = generation,
        .crc32 = 0,
        .config = *config
    };

    record.crc32 = calculate_crc32(
        (const uint8_t *)&record.config,
        sizeof(record.config)
    );

    memcpy(buffer.data, &record, sizeof(record));

    config_flash_write_t write = {
        .offset = target_offset,
        .buffer = &buffer
    };

    int result = flash_safe_execute(
        flash_write_callback,
        &write,
        1000
    );

    if (result != PICO_OK) {
        return false;
    }

    /* Geschriebenen Slot anschließend vollständig überprüfen. */
    config_storage_record_t verification;

    if (!read_slot(target_offset, &verification)) {
        return false;
    }

    return verification.generation == generation &&
           memcmp(
               &verification.config,
               config,
               sizeof(*config)
           ) == 0;
}
