#pragma once
#include <stdint.h>
#include <string.h>

// No Arduino dependency: exercise the real lifecycle on a desktop compiler.
struct Pet {
  int energy = 80, fullness = 75, joy = 75;
  bool sleeping = false;
  uint32_t lastTick = 0, expressionAt = 0;
  char expression[16] = "happy";

  static int clamp(int n) { return n < 0 ? 0 : n > 100 ? 100 : n; }
  void emote(const char* mood, uint32_t now) {
    const char* allowed[] = {"happy", "curious", "love", "excited", "sleepy", "sad", "thinking"};
    for (auto value : allowed) if (strcmp(mood, value) == 0) {
      strncpy(expression, value, sizeof(expression) - 1);
      expressionAt = now; return;
    }
  }
  void action(const char* type, uint32_t now) {
    if (!strcmp(type, "sleep")) { sleeping = true; emote("sleepy", now); }
    else if (!strcmp(type, "wake")) { sleeping = false; emote("happy", now); }
    else if (!strcmp(type, "feed")) { fullness = clamp(fullness + 20); emote("excited", now); }
    else if (!strcmp(type, "pet")) { joy = clamp(joy + 12); emote("love", now); }
    else if (!strcmp(type, "play")) {
      sleeping = false; energy = clamp(energy - 8); joy = clamp(joy + 18); emote("excited", now);
    }
  }
  void tick(uint32_t now) {
    const uint32_t ticks = (now - lastTick) / 60000U;
    if (!ticks) return;
    lastTick += ticks * 60000U;
    // Saturate elapsed ticks before integer conversion, including millis rollover.
    int n = ticks > 100 ? 100 : static_cast<int>(ticks);
    fullness = clamp(fullness - n);
    energy = clamp(energy + (sleeping ? 3 * n : -n));
    joy = clamp(joy - n);
  }
  const char* mood(uint32_t now) const {
    if (sleeping) return "sleepy";
    if (now - expressionAt < 8000U) return expression;
    if (energy < 20) return "sleepy";
    if (fullness < 20 || joy < 20) return "sad";
    return "curious";
  }
};
