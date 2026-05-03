from machine import UART, ADC, Pin
import onewire, ds18x20
import time, os

# ====== USER SETTINGS ======
PH_TX = 8
PH_RX = 18

TDS_PIN = 6
TEMP_PIN = 3

CSV_FILENAME = "sensor_log.csv"
LOG_INTERVAL = 2
# ===========================


# ====== pH SETUP ======
try:
    ph_uart = UART(2, baudrate=9600, tx=PH_TX, rx=PH_RX)
    ph_enabled = True
except:
    ph_enabled = False

def read_ph():
    if not ph_enabled:
        return "no_ph"
    
    try:
        ph_uart.write("R\r")
        time.sleep(1)

        if ph_uart.any():
            raw = ph_uart.read().decode().strip()
            for part in raw.split("\r"):
                try:
                    return float(part)
                except:
                    continue
        return "no_ph"
    except:
        return "no_ph"


# ====== TDS SETUP ======
try:
    adc = ADC(Pin(TDS_PIN))
    adc.atten(ADC.ATTN_11DB)
    tds_enabled = True
except:
    tds_enabled = False

def read_tds():
    if not tds_enabled:
        return "no_tds"
    
    try:
        raw = adc.read()
        voltage = raw * (3.3 / 4095)
        tds = (133.42 * voltage**3 - 255.86 * voltage**2 + 857.39 * voltage) * 0.5
        return tds
    except:
        return "no_tds"


# ====== TEMP SETUP ======
try:
    dat = Pin(TEMP_PIN)
    ow = onewire.OneWire(dat)
    ds = ds18x20.DS18X20(ow)
    roms = ds.scan()

    if len(roms) > 0:
        temp_enabled = True
    else:
        temp_enabled = False
except:
    temp_enabled = False

def read_temp():
    if not temp_enabled:
        return "no_temp"
    
    try:
        ds.convert_temp()
        time.sleep_ms(750)
        return ds.read_temp(roms[0])
    except:
        return "no_temp"


# ====== CSV SETUP ======
if CSV_FILENAME not in os.listdir():
    with open(CSV_FILENAME, "w") as f:
        f.write("timestamp,pH,TDS_ppm,temp_C\n")
    print("Created new CSV file")
else:
    print("Appending to existing CSV")


# ====== MAIN LOOP ======
while True:
    timestamp = time.time()

    ph = read_ph()
    tds = read_tds()
    temp = read_temp()

    print("Time:", timestamp,
          "| pH:", ph,
          "| TDS:", tds,
          "| Temp:", temp)

    with open(CSV_FILENAME, "a") as f:
        f.write("{},{},{},{}\n".format(timestamp, ph, tds, temp))

    time.sleep(LOG_INTERVAL)