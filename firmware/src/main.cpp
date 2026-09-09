#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#ifdef PET_TFT_IDEASPARK
#include "ideaspark_display.h"
#ifdef PET_CODEY
#if !__has_include("codey_assets.h")
#error "Codey artwork missing: run the installer assets command first"
#endif
#include "codey_assets.h"
#endif
#else
#include <U8g2lib.h>
#endif
#include <Preferences.h>
#include <esp_task_wdt.h>
#include <math.h>
#include <atomic>
#include "pet.h"
#include "button.h"
#if __has_include("pet_config.h")
#include "pet_config.h"
#else
#include "pet_config.example.h"
#endif

#ifdef PET_TFT_IDEASPARK
PipDisplay display;
LGFX_Sprite frame(&display);
#else
U8G2_SSD1306_128X64_NONAME_F_HW_I2C display(U8G2_R0, U8X8_PIN_NONE, PET_SCL, PET_SDA);
#endif
Pet pet;
struct Snapshot { int energy, fullness, joy; bool sleeping; char mood[16]; char ack[40]; };
struct Command { char id[40], action[16], mood[16], text[161]; };
struct DesktopInfo { char label[24], line1[24], line2[24], footer[24]; };
DesktopInfo desktopInfo{};
QueueHandle_t desktopUpdates;
struct NavigationEvent { char id[18]; bool automatic; uint32_t created; };
QueueHandle_t navigationEvents;
uint32_t bootNonce=0, navigationSequence=0;
BootButton bootButton;
QueueHandle_t snapshots, commands;
char ack[40] = "", caption[161] = "Hello! I'm Pip.";
uint32_t captionAt = 0;
std::atomic<bool> bridgeOnline{false};
std::atomic<bool> scanRequested{false};
std::atomic<int> desktopState{0}, desktopCount{0};
std::atomic<bool> desktopConnected{false};
const char* desktopNames[] = {"idle", "running", "waiting", "ready", "failed"};
bool displayReady = false;

void requestNavigation(bool automatic) {
  if(!bridgeOnline.load()) { Serial.println("CODEY_BUTTON ignored=offline"); return; }
  NavigationEvent event{};
  snprintf(event.id,sizeof(event.id),"%08lx-%08lx",static_cast<unsigned long>(bootNonce),static_cast<unsigned long>(++navigationSequence));
  event.automatic=automatic;event.created=millis();
  if(xQueueSend(navigationEvents,&event,0)==pdTRUE)
    Serial.printf("CODEY_BUTTON action=%s id=%s\n",automatic?"auto":"next",event.id);
  else Serial.println("CODEY_BUTTON ignored=queue_full");
}

void networkTask(void*) {
  esp_task_wdt_add(nullptr);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  Preferences prefs;
  prefs.begin("pip-wifi", true);
  String ssid = prefs.getString("ssid", PET_WIFI_SSID);
  String password = prefs.getString("password", PET_WIFI_PASSWORD);
  prefs.end();
  if (ssid.length()) WiFi.begin(ssid.c_str(), password.c_str());
  else WiFi.begin(); // Ask the Wi-Fi driver to reuse a saved station profile.
  password = "";
  uint32_t lastReconnect = millis();
  Snapshot snapshot{};
  for (;;) {
    esp_task_wdt_reset();
    xQueuePeek(snapshots, &snapshot, 0);
    if (scanRequested.exchange(false)) {
      if (WiFi.status() != WL_CONNECTED) {
        int count = WiFi.scanNetworks(false, false, false, 100);
        Serial.printf("PIP_SCAN networks=%d\n", count); WiFi.scanDelete();
      } else Serial.println("PIP_SCAN skipped=connected");
    }
    if (WiFi.status() == WL_CONNECTED) {
      WiFiClient client;
      HTTPClient http;
      http.setConnectTimeout(2000);
      http.setTimeout(2000);
      http.useHTTP10(true); // Response has Content-Length; avoid chunked decoding on device.
      String url = String(PET_BRIDGE_URL) + "/api/device";
      if (http.begin(client, url)) {
        http.addHeader("Authorization", String("Bearer ") + PET_TOKEN);
        http.addHeader("Content-Type", "application/json");
        StaticJsonDocument<512> body;
        body["energy"] = snapshot.energy; body["fullness"] = snapshot.fullness;
        body["joy"] = snapshot.joy; body["sleeping"] = snapshot.sleeping;
        body["mood"] = snapshot.mood; body["ack"] = snapshot.ack;
        NavigationEvent navigation{};
        while(xQueuePeek(navigationEvents,&navigation,0)==pdTRUE && millis()-navigation.created>10000U)
          xQueueReceive(navigationEvents,&navigation,0);
        const bool hasNavigation=xQueuePeek(navigationEvents,&navigation,0)==pdTRUE;
        if(hasNavigation){body["navigation"]["id"]=navigation.id;body["navigation"]["action"]=navigation.automatic?"auto":"next";}
        String payload; serializeJson(body, payload);
        int status = http.POST(payload);
        bridgeOnline.store(status == 200);
        if (status == 200 && http.getSize() > 0 && http.getSize() <= 1024) {
          StaticJsonDocument<1024> response;
          if (!deserializeJson(response, http.getStream())) {
            const char* navigationAck=response["navigation"]["id"] | "";
            if(hasNavigation && !strcmp(navigation.id,navigationAck)) {
              NavigationEvent consumed{};xQueueReceive(navigationEvents,&consumed,0);
              Serial.printf("CODEY_NAV_ACK id=%s ok=%d\n",navigationAck,response["navigation"]["ok"] | false);
            }
            JsonObject desktop = response["desktop"];
            desktopConnected.store(desktop["connected"] | false);
            const char* state = desktop["status"] | "idle";
            int index = 0;
            for (int i=0; i<5; ++i) if (!strcmp(state, desktopNames[i])) index=i;
            desktopState.store(index);
            desktopCount.store(constrain(desktop["count"] | 0, 0, 99));
            DesktopInfo info{};
            strlcpy(info.label, desktop["display"]["label"] | "", sizeof(info.label));
            strlcpy(info.line1, desktop["display"]["line1"] | "", sizeof(info.line1));
            strlcpy(info.line2, desktop["display"]["line2"] | "", sizeof(info.line2));
            strlcpy(info.footer, desktop["display"]["footer"] | "", sizeof(info.footer));
            xQueueOverwrite(desktopUpdates, &info);
            JsonObject cmd = response["command"];
            if (!cmd.isNull()) {
              Command next{};
              strlcpy(next.id, cmd["id"] | "", sizeof(next.id));
              strlcpy(next.action, cmd["action"] | "", sizeof(next.action));
              strlcpy(next.mood, cmd["mood"] | "", sizeof(next.mood));
              strlcpy(next.text, cmd["text"] | "", sizeof(next.text));
              xQueueSend(commands, &next, 0); // Retransmitted until the loop acknowledges it.
            }
          } else bridgeOnline.store(false);
        }
        http.end();
      } else bridgeOnline.store(false);
    } else {
      bridgeOnline.store(false);
      if (millis() - lastReconnect >= 15000U) {
        WiFi.reconnect(); lastReconnect = millis();
      }
    }
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}

void render(uint32_t now) {
  if (!displayReady) return;
#ifdef PET_TFT_IDEASPARK
#ifdef PET_CODEY
  frame.fillScreen(0);
  frame.setTextColor(2); frame.setTextSize(2); frame.setCursor(15,20); frame.print("codey");
  frame.setTextSize(1); frame.setTextColor(4); frame.setCursor(15,46); frame.print("CODEX DESKTOP PET");
  const bool linked = bridgeOnline.load() && desktopConnected.load();
  int state = linked ? desktopState.load() : 0;
  const int duration = state == 0 ? 750 : 160;
  int animFrame = codeyStarts[state] + (now/duration)%codeyCounts[state];
  uint32_t offset = codeyOffsets[animFrame], end = codeyOffsets[animFrame+1];
  auto* pixels = static_cast<uint8_t*>(frame.getBuffer());
  int pixel = 0;
  while (offset+1 < end && pixel < 144*156) {
    int count = codeyPixels[offset++]; uint8_t value = codeyPixels[offset++];
    while (count-- && pixel < 144*156) {
      pixels[(58+pixel/144)*170+13+pixel%144] = value; ++pixel;
    }
  }
  const char* labels[] = {"READY WHEN YOU ARE", "WORKING", "NEEDS YOU", "TASK FINISHED", "NEEDS ATTENTION"};
  frame.setTextColor(3); frame.setCursor(15,234);
  frame.print(linked ? (desktopInfo.label[0] ? desktopInfo.label : labels[state]) : bridgeOnline.load() ? "APP FEED UNAVAILABLE" : "CONNECTING WI-FI");
  frame.setTextColor(2); frame.setCursor(15,255);
  frame.print(linked ? desktopInfo.line1 : "YOUR DESK COMPANION");
  frame.setTextColor(4); frame.setCursor(15,276);
  if (linked) frame.print(desktopInfo.line2);
  frame.setCursor(15,303); frame.print(linked ? desktopInfo.footer : bridgeOnline.load() ? "WI-FI OK / APP OFFLINE" : "OFFLINE");
  frame.pushSprite(0,0);
#else
  const char* mood = pet.mood(now);
  constexpr uint8_t bg = 0, shell = 1, screen = 2, ink = 3, muted = 4, accent = 5;
  frame.fillScreen(bg);
  frame.setTextColor(screen); frame.setTextSize(2); frame.setCursor(15, 17); frame.print("pip.");
  frame.setTextSize(1); frame.setTextColor(muted);
  frame.setCursor(15, 42); frame.print(bridgeOnline.load() ? "WI-FI COMPANION" : "LITTLE DESK FRIEND");
  int bob = static_cast<int>(sin(now / 600.0) * 3);
  frame.fillRoundRect(10, 65 + bob, 150, 148, 28, shell);
  frame.fillRoundRect(21, 76 + bob, 128, 111, 22, screen);
  frame.fillCircle(132, 200 + bob, 2, accent);
  for (int x = 54; x <= 106; x += 8) frame.fillCircle(x, 200 + bob, 1, muted);
  bool sleepy = !strcmp(mood, "sleepy"), blink = now % 4700U < 140;
  bool happy = !strcmp(mood, "happy") || !strcmp(mood, "love") || !strcmp(mood, "excited");
  int gaze = static_cast<int>(sin(now / 2200.0) * 4);
  for (int x : {58, 109}) {
    if (sleepy || blink) frame.fillRoundRect(x - 10, 120 + bob, 20, 4, 2, ink);
    else if (happy) {
      frame.fillCircle(x, 121 + bob, 11, ink);
      frame.fillCircle(x, 127 + bob, 10, screen);
    } else frame.fillRoundRect(x - 7 + gaze, 106 + bob, 15, !strcmp(mood, "sad") ? 15 : 28, 7, ink);
  }
  frame.drawLine(76, 144 + bob, 84, 149 + bob, ink);
  frame.drawLine(84, 149 + bob, 92, 144 + bob, ink);
  if (sleepy) { frame.setCursor(127, 91 + bob); frame.setTextColor(ink); frame.print("z"); }
  if (!strcmp(mood, "love")) { frame.fillEllipse(40, 142 + bob, 6, 3, accent); frame.fillEllipse(131, 142 + bob, 6, 3, accent); }
  frame.setTextColor(muted); frame.setCursor(15, 231); frame.print(pet.sleeping ? "RECHARGING..." : mood);
  const char* labels[] = {"E", "F", "J"};
  for (int i = 0; i < 3; i++) {
    int value = i == 0 ? pet.energy : i == 1 ? pet.fullness : pet.joy;
    int x = 15 + i * 50;
    frame.setCursor(x, 253); frame.print(labels[i]);
    frame.fillRoundRect(x + 11, 254, 32, 5, 2, shell);
    frame.fillRoundRect(x + 11, 254, max(1, value * 32 / 100), 5, 2, accent);
  }
  const uint32_t age = now - captionAt;
  if (age < max(14000U, static_cast<uint32_t>(strlen(caption)) * 180U + 4000U)) {
    size_t len = strlen(caption), offset = len > 23 ? min(static_cast<size_t>(age / 180U), len - 23) : 0;
    char line[24]{}; strncpy(line, caption + offset, 23);
    frame.setTextColor(screen); frame.setCursor(15, 279); frame.print(line);
  }
  frame.setTextColor(muted); frame.setCursor(15, 303);
  frame.print(bridgeOnline.load() ? "ONLINE  /  BOOT TO PET" : "OFFLINE / BOOT TO PET");
  frame.pushSprite(0, 0);
#endif
#else
  display.clearBuffer();
  display.setFont(u8g2_font_5x7_tf);
  display.drawStr(2, 8, "PIP");
  display.drawStr(82, 8, bridgeOnline.load() ? "WI-FI OK" : "OFFLINE");
  const char* mood = pet.mood(now);
  int bob = static_cast<int>(sin(now / 600.0) * 2);
  int gaze = static_cast<int>(sin(now / 2200.0) * 3);
  bool blink = now % 4700U < 140;
  bool sleepy = !strcmp(mood, "sleepy");
  bool happy = !strcmp(mood, "happy") || !strcmp(mood, "love") || !strcmp(mood, "excited");
  for (int x : {37, 77}) {
    if (sleepy || blink) display.drawRBox(x, 28 + bob, 16, 3, 1);
    else if (happy) {
      display.drawDisc(x + 8, 29 + bob, 8);
      display.setDrawColor(0); display.drawDisc(x + 8, 34 + bob, 8); display.setDrawColor(1);
    } else display.drawRBox(x + gaze, 20 + bob, 13, !strcmp(mood, "sad") ? 10 : 18, 5);
  }
  if (sleepy) display.drawStr(102, 20 + bob, "zZ");
  else { display.drawLine(58, 40 + bob, 63, 43 + bob); display.drawLine(63, 43 + bob, 68, 40 + bob); }
  if (!strcmp(mood, "love")) { display.drawDisc(24, 36, 2); display.drawDisc(102, 36, 2); }
  const uint32_t captionDuration = max(14000U, static_cast<uint32_t>(strlen(caption)) * 180U + 4000U);
  if (now - captionAt < captionDuration) {
    // Scroll the complete reply, retaining bounded ASCII on the monochrome display.
    size_t len = strlen(caption);
    size_t offset = len > 24 ? min(static_cast<size_t>((now - captionAt) / 180U), len - 24) : 0;
    char line[25]{}; strncpy(line, caption + offset, 24); display.drawStr(2, 62, line);
  } else {
    for (int i = 0; i < 3; i++) {
      const int value = i == 0 ? pet.energy : i == 1 ? pet.fullness : pet.joy;
      display.drawFrame(2 + i * 43, 55, 38, 6);
      display.drawBox(3 + i * 43, 56, value * 36 / 100, 4);
    }
  }
  display.sendBuffer();
#endif
}

void setup() {
  Serial.begin(115200);
  bootNonce=esp_random();
  esp_task_wdt_init(15, true);
  esp_task_wdt_add(nullptr);
  pinMode(PET_BUTTON, INPUT_PULLUP);
#ifdef PET_TFT_IDEASPARK
  pinMode(32, OUTPUT); digitalWrite(32, HIGH);
  display.init(); display.setRotation(0);
  frame.setColorDepth(lgfx::palette_8bit);
  displayReady = frame.createSprite(170, 320) != nullptr;
  if (displayReady) {
#ifdef PET_CODEY
    for (unsigned i=0; i<sizeof(codeyColors)/sizeof(codeyColors[0]); ++i) frame.setPaletteColor(i, codeyColors[i]);
#else
    const uint32_t colors[] = {0xe9eee0, 0xf9faec, 0x293a32, 0xc6e3a0, 0x738266, 0x92a873};
    for (int i = 0; i < 6; i++) frame.setPaletteColor(i, colors[i]);
#endif
  }
  Serial.printf("Pip ST7789 170x320 framebuffer=%s bytes=54400\n", displayReady ? "OK" : "FAILED");
#else
  Wire.begin(PET_SDA, PET_SCL);
  Wire.setTimeOut(50);
  Wire.beginTransmission(PET_OLED_ADDRESS);
  displayReady = Wire.endTransmission() == 0;
  if (displayReady) { display.setI2CAddress(PET_OLED_ADDRESS << 1); display.begin(); }
  Serial.println(displayReady ? "Pip OLED ready" : "OLED not found; running headless");
  #endif
  snapshots = xQueueCreate(1, sizeof(Snapshot)); commands = xQueueCreate(2, sizeof(Command)); desktopUpdates = xQueueCreate(1, sizeof(DesktopInfo));
  navigationEvents=xQueueCreate(8,sizeof(NavigationEvent));
  if (!snapshots || !commands || !desktopUpdates || !navigationEvents) { Serial.println("Queue allocation failed"); ESP.restart(); }
  Snapshot initial{80, 75, 75, false, "happy", ""}; xQueueOverwrite(snapshots, &initial);
  if (xTaskCreate(networkTask, "pet-wifi", 8192, nullptr, 1, nullptr) != pdPASS) ESP.restart();
  Serial.println(strlen(PET_WIFI_SSID) ? "Wi-Fi configured" : "Trying stored Wi-Fi; serial configure available");
}

void loop() {
  esp_task_wdt_reset();
  uint32_t now = millis();
  pet.tick(now);
  xQueueReceive(desktopUpdates, &desktopInfo, 0);
  Command cmd{};
  if (xQueueReceive(commands, &cmd, 0) == pdTRUE && cmd.id[0] && strcmp(cmd.id, ack)) {
    pet.action(cmd.action, now); pet.emote(cmd.mood, now);
    if (cmd.text[0]) { strlcpy(caption, cmd.text, sizeof(caption)); captionAt = now; }
    strlcpy(ack, cmd.id, sizeof(ack));
  }
  const ButtonAction buttonAction=bootButton.update(digitalRead(PET_BUTTON),now);
  if(buttonAction!=ButtonAction::None) {
#ifdef PET_CODEY
    requestNavigation(buttonAction==ButtonAction::Auto);
#else
    pet.action(buttonAction==ButtonAction::Auto?(pet.sleeping?"wake":"sleep"):"pet",now);
#endif
  }
  Snapshot snapshot{pet.energy, pet.fullness, pet.joy, pet.sleeping, "", ""};
  strlcpy(snapshot.mood, pet.mood(now), sizeof(snapshot.mood));
  strlcpy(snapshot.ack, ack, sizeof(snapshot.ack)); xQueueOverwrite(snapshots, &snapshot);
  static char line[512]{};
  static size_t used = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      line[used] = 0;
      StaticJsonDocument<768> request;
      if (used && !deserializeJson(request, line)) {
        const char* action = request["action"] | "";
        if (!strcmp(action, "configure")) {
          const char* ssid = request["ssid"] | "";
          const char* password = request["password"] | "";
          if (strlen(ssid) > 0 && strlen(ssid) <= 32 && strlen(password) <= 63) {
            Preferences prefs; prefs.begin("pip-wifi", false);
            prefs.putString("ssid", ssid); prefs.putString("password", password); prefs.end();
            Serial.println("PIP_CONFIG_SAVED"); Serial.flush(); delay(100); ESP.restart();
          } else Serial.println("PIP_CONFIG_INVALID");
        }
#ifdef PET_TFT_IDEASPARK
        else if (!strcmp(action, "frame") && displayReady) {
          Serial.println("PIP_FRAME 170 320 54400");
          Serial.write(static_cast<const uint8_t*>(frame.getBuffer()), 54400);
          Serial.println("PIP_FRAME_END");
          esp_task_wdt_reset();
        }
#endif
        else if (!strcmp(action, "scan")) { scanRequested.store(true); }
        else if (!strcmp(action, "next") || !strcmp(action,"auto")) { requestNavigation(!strcmp(action,"auto")); }
        else if (!strcmp(action, "status")) {
          StaticJsonDocument<256> info;
          info["label"]=desktopInfo.label; info["line1"]=desktopInfo.line1; info["line2"]=desktopInfo.line2;
          Serial.print("CODEY_INFO "); serializeJson(info,Serial); Serial.println();
          Serial.printf("CODEY_STATUS state=%s count=%d linked=%d\n", desktopNames[desktopState.load()], desktopCount.load(), bridgeOnline.load() && desktopConnected.load());
          Serial.printf("PIP_STATUS uptime=%lu heap=%u minheap=%u stack=%u wifi=%d bridge=%d energy=%d fullness=%d joy=%d sleeping=%d mood=%s\n",
            static_cast<unsigned long>(now), ESP.getFreeHeap(), ESP.getMinFreeHeap(), uxTaskGetStackHighWaterMark(nullptr),
            static_cast<int>(WiFi.status()), bridgeOnline.load(), pet.energy, pet.fullness, pet.joy, pet.sleeping, pet.mood(now));
          if (WiFi.status() == WL_CONNECTED) Serial.printf("PIP_IP %s\n", WiFi.localIP().toString().c_str());
        } else { pet.action(action, now); }
      }
      memset(line, 0, sizeof(line)); used = 0;
    } else if (used < sizeof(line) - 1) line[used++] = c;
    else { memset(line, 0, sizeof(line)); used = 0; }
  }
  render(now);
  delay(40);
}
