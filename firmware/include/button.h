#pragma once
#include <stdint.h>

enum class ButtonAction { None, Next, Auto };
struct BootButton {
  bool lastRaw=true, stable=true;
  uint32_t changedAt=0, pressedAt=0;
  ButtonAction update(bool released, uint32_t now) {
    if(released!=lastRaw){changedAt=now;lastRaw=released;}
    if(now-changedAt<30U || stable==released)return ButtonAction::None;
    stable=released;
    if(!stable){pressedAt=now;return ButtonAction::None;}
    return now-pressedAt>=800U ? ButtonAction::Auto : ButtonAction::Next;
  }
};
