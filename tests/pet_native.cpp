#include "../firmware/include/pet.h"
#include <assert.h>
#include <stdint.h>
int main() {
  Pet p;
  p.action("feed", 100); p.action("feed", 101); assert(p.fullness == 100);
  p.action("sleep", 200); p.tick(60000); assert(p.energy == 83); assert(p.sleeping);
  p.action("wake", 60001); p.tick(120000); assert(p.energy == 82);
  p.action("play", 120001); assert(p.energy == 74); assert(!p.sleeping);
  p.tick(120000 + 60000 * 200); assert(p.fullness == 0); assert(p.energy == 0);
  p.emote("invalid", 99); assert(strcmp(p.expression, "excited") == 0);
  assert(strcmp(p.mood(20000000), "sleepy") == 0);
  Pet wrap; wrap.lastTick = UINT32_MAX - 30000U; wrap.tick(30000U); assert(wrap.energy == 79);
  wrap.emote("love", UINT32_MAX - 1000); assert(strcmp(wrap.mood(1000), "love") == 0);
  Pet slept; slept.action("sleep", 0); slept.emote("happy", 10); assert(strcmp(slept.mood(11), "sleepy") == 0);
}
