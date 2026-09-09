#pragma once
// Copy to pet_config.h. Never put an OpenAI API key on the ESP32.
#define PET_WIFI_SSID ""
#define PET_WIFI_PASSWORD ""
// Your computer's LAN IPv4 address, not localhost. No trailing slash.
#define PET_BRIDGE_URL "http://192.168.1.100:8787"
#define PET_TOKEN "replace-with-a-long-random-pairing-token"
#define PET_SDA 21
#define PET_SCL 22
#ifdef PET_TFT_IDEASPARK
#define PET_BUTTON 0
#else
#define PET_BUTTON 27
#endif
#define PET_OLED_ADDRESS 0x3C
