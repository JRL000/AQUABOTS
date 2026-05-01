/**
 * sensor_bridge.h
 *
 * Water quality sensor bridge between the ESP32-S3 payload board and the
 * Jetson companion computer.
 *
 * Reads three sensors and forwards the latest values to the Jetson over
 * a dedicated UART at 115200 baud, once every SENSOR_BRIDGE_TASK_PERIOD_MS
 * milliseconds:
 *
 *   1. DS18B20  — water temperature (°C)         via 1-Wire bus
 *   2. TDS      — salinity (ppt)                 via analog voltage on ADC1
 *   3. EZO pH   — Atlas Scientific pH (0-14)     via UART at 9600 baud
 *
 * The Jetson side (see jetson/app.py: read_esp32) parses CSV lines in the
 * form:
 *
 *     TEMP:23.50,SAL:0.480,PH:7.21\n
 *
 * which are then JSON-wrapped and broadcast to the GUI / ground control.
 *
 * -------------------------------------------------------------------------
 * Pin / peripheral configuration
 * -------------------------------------------------------------------------
 * Every GPIO, ADC channel, UART port, and baud rate is a #define below so
 * the wiring can be changed in one place without touching the .c file.
 * Defaults mirror the Arduino prototype that Jamie wrote (project-docs/
 * sensors-code.txt) except for the Jetson UART, which uses GPIO 47/48 to
 * avoid the ESP32-S3's native USB pins on GPIO 19/20.
 *
 * If you want to remap, just edit the #defines in this file; no code change
 * is required elsewhere.
 * -------------------------------------------------------------------------
 */

#ifndef SENSOR_BRIDGE_H
#define SENSOR_BRIDGE_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_adc/adc_oneshot.h"

// ============================================================================
// DS18B20  (water temperature)  —  1-Wire
// ============================================================================

#define SENSOR_BRIDGE_ONEWIRE_GPIO          GPIO_NUM_4
#define SENSOR_BRIDGE_DS18B20_RESOLUTION    DS18B20_RESOLUTION_12B

// ============================================================================
// TDS / SALINITY  —  Analog on ADC1
// ============================================================================

/* ADC1 channel 0 == GPIO 1 on ESP32-S3.  Change both together if remapping. */
#define SENSOR_BRIDGE_TDS_ADC_UNIT          ADC_UNIT_1
#define SENSOR_BRIDGE_TDS_ADC_CHANNEL       ADC_CHANNEL_0
#define SENSOR_BRIDGE_TDS_ADC_ATTEN         ADC_ATTEN_DB_12     // 0 – ~3.1 V range
#define SENSOR_BRIDGE_TDS_ADC_BITWIDTH      ADC_BITWIDTH_DEFAULT

/* Jamie's prototype reads the sensor through a 2:1 divider (3.3 V MCU,
 * 5 V sensor output).  Leave at 2.0 for the current hardware; set to
 * 1.0 if the divider is removed. */
#define SENSOR_BRIDGE_TDS_DIVIDER_RATIO     2.0f

/* Number of oneshot samples averaged per reading (noise reduction). */
#define SENSOR_BRIDGE_TDS_SAMPLES           16

// ============================================================================
// Atlas Scientific EZO pH  —  UART
// ============================================================================

#define SENSOR_BRIDGE_PH_UART_NUM           UART_NUM_1
#define SENSOR_BRIDGE_PH_UART_RX_GPIO       GPIO_NUM_16
#define SENSOR_BRIDGE_PH_UART_TX_GPIO       GPIO_NUM_17
#define SENSOR_BRIDGE_PH_UART_BAUD          9600
#define SENSOR_BRIDGE_PH_UART_BUF_SIZE      256

/* If no new valid pH reading is seen for this long, the cached pH value is
 * still reported but the sensor is considered stale. */
#define SENSOR_BRIDGE_PH_STALE_MS           10000

// ============================================================================
// Jetson link  —  UART out
// ============================================================================

/* Jetson serial link — dedicated hardware UART (UART_NUM_2).
 *
 * History: was UART_NUM_0 (USB CDC console). That worked for sensor TEMP:
 * lines because sensor_bridge had a special-case path that bypassed the UART
 * driver and wrote via fwrite(stdout) — but the parallel swarm_bridge module
 * called uart_write_bytes() / uart_read_bytes() directly with no such bypass,
 * so all SWARM_* messages silently failed to flow. Discovered 2026-05-01.
 *
 * Moved to UART_NUM_2 + dedicated GPIOs so both sensor_bridge and swarm_bridge
 * use the standard uart_*_bytes API on a real UART driver. UART_NUM_0 stays
 * with the IDF console (USB CDC) for the interactive REPL.
 *
 * Jetson side: wire ESP32 TX (GPIO 5) → Jetson RX, ESP32 RX (GPIO 6) → Jetson
 * TX, common ground. Pixhawk owns /dev/ttyTHS1 already, so use a different
 * Jetson UART (typically /dev/ttyTHS2 on the Orin Nano 40-pin header — verify
 * against your DT overlay). Keep the cable short and twisted, away from the
 * ESC. See AQUABOTS_WIRING_GUIDE.md for the routing.
 *
 * Pin choices: GPIO 5/6 are unused safe pins on most ESP32-S3 boards (not
 * strapping pins, not USB, not used by sensor_bridge / pH / 1-Wire). If your
 * board layout needs different pins, change them here — the UART matrix on
 * S3 routes any UART to any GPIO. */
#define SENSOR_BRIDGE_JETSON_UART_NUM       UART_NUM_2
#define SENSOR_BRIDGE_JETSON_UART_TX_GPIO   GPIO_NUM_5
#define SENSOR_BRIDGE_JETSON_UART_RX_GPIO   GPIO_NUM_6
#define SENSOR_BRIDGE_JETSON_UART_BAUD      115200
#define SENSOR_BRIDGE_JETSON_UART_BUF_SIZE  512

// ============================================================================
// Task timing
// ============================================================================

#define SENSOR_BRIDGE_TASK_PERIOD_MS        3000
#define SENSOR_BRIDGE_TASK_STACK            4096
#define SENSOR_BRIDGE_TASK_PRIORITY         5

// ============================================================================
// Snapshot struct
// ============================================================================

/**
 * Latest sensor readings.  Populated by the bridge task and accessible via
 * sensor_bridge_get_snapshot().  All fields are in SI-friendly units.
 */
typedef struct {
    float    temperature_c;     // Water temperature in degrees Celsius
    float    salinity_ppt;      // Salinity in parts per thousand
    float    ph;                // pH (0 – 14)
    bool     temp_valid;        // DS18B20 produced a valid reading this cycle
    bool     sal_valid;         // ADC read and compensation math succeeded
    bool     ph_valid;          // A valid pH string has been parsed at least once
    uint32_t last_update_ms;    // esp_timer timestamp of last push to Jetson
} sensor_bridge_snapshot_t;

// ============================================================================
// Public API
// ============================================================================

/**
 * Initialise all sensor peripherals (1-Wire, ADC, pH UART, Jetson UART)
 * but do NOT start the read/publish task.
 *
 * Safe to call once during app_main before network init.  Logs a warning
 * (but does not fail) if individual sensors are missing — the task will
 * still run and report the remaining sensors.
 *
 * @return ESP_OK if at least the Jetson UART came up, else an error.
 */
esp_err_t sensor_bridge_init(void);

/**
 * Start the background FreeRTOS task that reads all three sensors and
 * transmits a CSV line to the Jetson every SENSOR_BRIDGE_TASK_PERIOD_MS.
 *
 * @return ESP_OK on success, ESP_ERR_INVALID_STATE if init not called.
 */
esp_err_t sensor_bridge_start(void);

/**
 * Stop the background task.  Peripherals remain initialised.
 */
void sensor_bridge_stop(void);

/**
 * Copy the latest sensor snapshot into the caller-provided struct.
 *
 * @param out  Destination (must not be NULL)
 * @return ESP_OK always; fields within the snapshot indicate per-sensor
 *         validity.
 */
esp_err_t sensor_bridge_get_snapshot(sensor_bridge_snapshot_t *out);

/**
 * Convenience accessors for code that only needs one value.
 * Return NAN / 0 if the sensor has never produced a valid reading.
 */
float sensor_bridge_get_temp_c(void);
float sensor_bridge_get_salinity_ppt(void);
float sensor_bridge_get_ph(void);

#endif // SENSOR_BRIDGE_H
