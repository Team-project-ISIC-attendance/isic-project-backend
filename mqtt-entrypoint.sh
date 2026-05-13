#!/bin/sh
set -e
mosquitto_passwd -b -c /tmp/mosquitto_passwd "${MQTT_USERNAME}" "${MQTT_PASSWORD}"
chown mosquitto:mosquitto /tmp/mosquitto_passwd
chmod 700 /tmp/mosquitto_passwd
exec mosquitto -c /mosquitto/config/mosquitto.conf
