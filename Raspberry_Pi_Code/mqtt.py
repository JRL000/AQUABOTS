import paho.mqtt.client as mqtt
import time

# Define the MQTT settings
broker = "broker.emqx.io"
port = 1883

# Topics - now matching both directions
topic_from_laptop = "raspberry/laptop_to_pi"
topic_to_laptop = "raspberry/pi_to_laptop"

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    # Subscribe to the laptop's topic
    client.subscribe(topic_from_laptop)

def on_message(client, userdata, msg):
    print(f"Received from Laptop: {msg.payload.decode()}")
    # Respond back to laptop
    client.publish(topic_to_laptop, payload="Pi received: " + msg.payload.decode(), qos=1)

# Set up MQTT client
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

# Connect to the broker
client.connect(broker, port, 60)

# Start the loop to listen for messages
client.loop_start()

try:
    while True:
        # You can add periodic messages here if needed
        time.sleep(1)
except KeyboardInterrupt:
    print("Exiting...")
    client.loop_stop()
